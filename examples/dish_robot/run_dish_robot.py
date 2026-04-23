import argparse
import time
import threading
import glob
import os
from datetime import datetime

import torch

from dish_policy_manager import DishPolicyManager, DishType, DISH_CONFIGS

try:
    from config import DEVICE, USE_FP16, WEB_HOST, WEB_PORT, FPS, EPISODE_TIME_S, ROBOT_PORT, ROBOT_MAX_RELATIVE_TARGET, SMOOTHING_ALPHA, NUM_STEPS_PER_EPISODE
except ImportError:
    DEVICE = "cuda"
    USE_FP16 = False
    WEB_HOST = "0.0.0.0"
    WEB_PORT = 7860
    FPS = 30
    EPISODE_TIME_S = 12
    ROBOT_PORT = "/dev/ttyCH343USB0"
    ROBOT_MAX_RELATIVE_TARGET = 50.0
    SMOOTHING_ALPHA = 0.5
    NUM_STEPS_PER_EPISODE = 500


class JointLogger:
    def __init__(self, log_dir: str = "joint_logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = None
        self.current_episode = 0
        self.step_count = 0
        self.start_time = None
        self.custom_filename = None
    
    def start_episode(self, dish_name: str = "unknown", filename: str = None):
        if self.log_file:
            self.log_file.close()
        
        if filename:
            filepath = os.path.join(self.log_dir, f"{filename}.txt")
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(self.log_dir, f"{timestamp}_{dish_name}_episode{self.current_episode}.txt")
        
        self.log_file = open(filepath, "w")
        self.log_file.write("# timestamp,step,shoulder_pan,shoulder_lift,elbow_flex,wrist_flex,wrist_roll,gripper,action_pan,action_lift,action_elbow,action_flex,action_roll,action_gripper\n")
        self.step_count = 0
        self.start_time = time.time()
        self.current_episode += 1
        print(f"[LOG] Started logging to {filepath}")
    
    def log_state(self, state: list, action: list = None):
        if self.log_file:
            elapsed = time.time() - self.start_time if self.start_time else 0
            state_str = ",".join([f"{v:.4f}" for v in state])
            if action:
                action_str = ",".join([f"{v:.4f}" for v in action])
                self.log_file.write(f"{elapsed:.4f},{self.step_count},{state_str},{action_str}\n")
            else:
                self.log_file.write(f"{elapsed:.4f},{self.step_count},{state_str}\n")
            self.step_count += 1
            self.log_file.flush()
    
    def end_episode(self):
        if self.log_file:
            self.log_file.close()
            self.log_file = None
            print(f"[LOG] Episode ended, {self.step_count} steps logged")
    
    def close(self):
        if self.log_file:
            self.log_file.close()
            self.log_file = None


def find_robot_port():
    patterns = [
        "/dev/ttyCH343USB*",
        "/dev/ttyUSB*",
        "/dev/ttyACM*",
    ]
    
    for pattern in patterns:
        ports = glob.glob(pattern)
        if ports:
            for port in sorted(ports):
                if os.path.exists(port):
                    print(f"Found port: {port}")
                    return port
    
    return None


class ActionSmoother:
    def __init__(self, alpha: float = 0.5):
        self.alpha = alpha
        self.last_action = None
    
    def smooth(self, action):
        if self.last_action is None:
            self.last_action = action.copy()
            return action
        
        smoothed = self.alpha * action + (1 - self.alpha) * self.last_action
        self.last_action = smoothed.copy()
        return smoothed
    
    def reset(self):
        self.last_action = None


class MockRobotController:
    def __init__(self, fps: int = 30):
        self.current_position = torch.zeros(6)
        self.is_connected = False
        self.fps = fps
    
    def connect(self):
        time.sleep(0.5)
        self.is_connected = True
        print("Robot connected (mock)")
    
    def disconnect(self):
        self.is_connected = False
        print("Robot disconnected (mock)")
    
    def execute_action(self, action: torch.Tensor):
        self.current_position = action.squeeze(0).cpu()
    
    def get_observation(self) -> dict:
        return {
            "observation.images.handeye": torch.randn(1, 3, 480, 640, device="cuda"),
            "observation.images.front": torch.randn(1, 3, 480, 640, device="cuda"),
            "observation.state": self.current_position.cuda().unsqueeze(0),
        }


class RealRobotController:
    def __init__(self, port: str = None, fps: int = 30, smoothing_alpha: float = None, log_joints: bool = True):
        self.port = port or ROBOT_PORT
        self.fps = fps
        self.robot = None
        self.is_connected = False
        self.smoother = ActionSmoother(alpha=smoothing_alpha or SMOOTHING_ALPHA)
        self._lock = threading.Lock()
        self.log_joints = log_joints
        self.joint_logger = JointLogger() if log_joints else None
        self._last_state = None
        self._last_action = None
    
    def connect(self):
        port = self.port
        
        if not os.path.exists(port):
            print(f"Port {port} not found, scanning for available ports...")
            found_port = find_robot_port()
            if found_port:
                port = found_port
                print(f"Using port: {port}")
            else:
                raise ConnectionError("No available port found!")
        
        print(f"Connecting to robot on {port}...")
        try:
            from lerobot.robots.so101_follower import SO101Follower, SO101FollowerConfig
            from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
            
            cameras = {
                "handeye": OpenCVCameraConfig(index_or_path="/dev/video0", width=640, height=480, fps=30),
                "front": OpenCVCameraConfig(index_or_path="/dev/video2", width=640, height=480, fps=30),
            }
            
            config = SO101FollowerConfig(
                port=port,
                id="scooping_follower",
                cameras=cameras,
                max_relative_target=ROBOT_MAX_RELATIVE_TARGET,
            )
            self.robot = SO101Follower(config)
            self.robot.connect()
            self.is_connected = True
            print("Robot connected!")
        except Exception as e:
            print(f"Failed to connect: {e}")
            raise
    
    def disconnect(self):
        if self.robot:
            self.robot.disconnect()
        self.is_connected = False
        self.smoother.reset()
        print("Robot disconnected")
    
    def reset_smoother(self):
        self.smoother.reset()
    
    def start_logging(self, dish_name: str = "unknown", filename: str = None):
        if self.joint_logger:
            self.joint_logger.start_episode(dish_name, filename)
    
    def stop_logging(self):
        if self.joint_logger:
            self.joint_logger.end_episode()
    
    def execute_action(self, action: torch.Tensor):
        if self.robot:
            with self._lock:
                import numpy as np
                action_np = action.squeeze(0).cpu().numpy()
                action_np = self.smoother.smooth(action_np)
                
                motor_names = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
                action_dict = {}
                for i, motor in enumerate(motor_names):
                    if i < len(action_np):
                        val = float(action_np[i])
                        if motor == "gripper":
                            val = max(0.0, min(100.0, val))
                        action_dict[f"{motor}.pos"] = val
                
                self._last_action = action_np.tolist()
                
                if self.joint_logger and self._last_state:
                    self.joint_logger.log_state(self._last_state, self._last_action)
                
                try:
                    self.robot.send_action(action_dict)
                except Exception as e:
                    print(f"[WARN] send_action failed: {e}")
                    raise
    
    def get_observation(self) -> dict:
        if self.robot:
            with self._lock:
                obs = self.robot.get_observation()
                
                import numpy as np
                motor_names = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
                state_list = []
                for motor in motor_names:
                    key = f"{motor}.pos"
                    if key in obs:
                        state_list.append(obs[key])
                
                if len(state_list) == 6:
                    state = np.array(state_list, dtype=np.float32)
                else:
                    state = np.zeros(6, dtype=np.float32)
                
                self._last_state = state.tolist()
                
                result = {
                    "observation.state": torch.from_numpy(state).unsqueeze(0).to("cuda"),
                    "task": "",
                    "robot_type": "so101_follower",
                }
                
                for cam_name in ["handeye", "front"]:
                    if cam_name in obs:
                        img = obs[cam_name]
                        if isinstance(img, np.ndarray):
                            img = torch.from_numpy(img).type(torch.float32) / 255.0
                            img = img.permute(2, 0, 1).contiguous()
                            result[f"observation.images.{cam_name}"] = img.unsqueeze(0).to("cuda")
                
                return result
        return None


def run_mock():
    from web_ui import DishRobotWebUI
    
    print("=" * 60)
    print("打饭机器人控制系统启动 (模拟模式)")
    print("=" * 60)
    
    policy_manager = DishPolicyManager(
        dish_configs=DISH_CONFIGS,
        device=DEVICE,
        use_fp16=USE_FP16,
        fps=FPS,
        episode_time_s=EPISODE_TIME_S,
        num_steps_per_episode=NUM_STEPS_PER_EPISODE,
    )
    
    robot = MockRobotController(fps=FPS)
    robot.connect()
    
    ui = DishRobotWebUI(
        policy_manager=policy_manager,
        robot_controller=robot,
        camera_provider=robot,
        host=WEB_HOST,
        port=WEB_PORT,
    )
    
    print(f"\nWeb UI: http://localhost:{WEB_PORT}")
    ui.run()


def run_real():
    from web_ui import DishRobotWebUI
    
    print("=" * 60)
    print("打饭机器人控制系统启动 (真实机器人)")
    print("=" * 60)
    
    policy_manager = DishPolicyManager(
        dish_configs=DISH_CONFIGS,
        device=DEVICE,
        use_fp16=USE_FP16,
        fps=FPS,
        episode_time_s=EPISODE_TIME_S,
        num_steps_per_episode=NUM_STEPS_PER_EPISODE,
    )
    
    robot = RealRobotController(fps=FPS)
    robot.connect()
    
    ui = DishRobotWebUI(
        policy_manager=policy_manager,
        robot_controller=robot,
        camera_provider=robot,
        host=WEB_HOST,
        port=WEB_PORT,
    )
    
    print(f"\nWeb UI: http://localhost:{WEB_PORT}")
    ui.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dish Robot Control System")
    parser.add_argument("mode", choices=["mock", "real"], default="mock", help="Run mode")
    args = parser.parse_args()
    
    if args.mode == "mock":
        run_mock()
    else:
        run_real()
