import time
import os
import glob
from datetime import datetime

from lerobot.robots.so101_follower import SO101Follower, SO101FollowerConfig
from lerobot.teleoperators.so101_leader import SO101Leader, SO101LeaderConfig
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.utils.robot_utils import busy_wait


def find_port(patterns):
    for pattern in patterns:
        ports = glob.glob(pattern)
        if ports:
            for port in sorted(ports):
                if os.path.exists(port):
                    return port
    return None


class JointRecorder:
    def __init__(self, log_dir: str = "joint_logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = None
        self.step_count = 0
        self.start_time = None
        self.is_recording = False
    
    def start(self, filename: str):
        if self.log_file:
            self.log_file.close()
        
        filepath = os.path.join(self.log_dir, f"{filename}.txt")
        self.log_file = open(filepath, "w")
        self.log_file.write("# timestamp,step,shoulder_pan,shoulder_lift,elbow_flex,wrist_flex,wrist_roll,gripper\n")
        self.step_count = 0
        self.start_time = time.time()
        self.is_recording = True
        print(f"\n[REC] Started recording to {filepath}")
        print("[REC] Press 's' + Enter to stop, 'q' + Enter to quit\n")
    
    def log(self, positions: dict):
        if self.log_file and self.is_recording:
            elapsed = time.time() - self.start_time if self.start_time else 0
            motor_names = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
            values = [positions.get(f"{m}.pos", 0.0) for m in motor_names]
            line = f"{elapsed:.4f},{self.step_count}," + ",".join([f"{v:.4f}" for v in values]) + "\n"
            self.log_file.write(line)
            self.step_count += 1
            self.log_file.flush()
    
    def stop(self):
        if self.log_file:
            self.log_file.close()
            self.log_file = None
            self.is_recording = False
            print(f"\n[REC] Recording stopped, {self.step_count} steps saved")
    
    def toggle(self, filename: str = None):
        if self.is_recording:
            self.stop()
            return False
        elif filename:
            self.start(filename)
            return True
        return False


def teleoperate_with_recording(
    leader_port: str,
    follower_port: str,
    fps: int = 30,
    log_dir: str = "joint_logs",
):
    motor_names = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
    
    cameras = {
        "handeye": OpenCVCameraConfig(index_or_path="/dev/video2", width=640, height=480, fps=30),
        "front": OpenCVCameraConfig(index_or_path="/dev/video0", width=640, height=480, fps=30),
    }
    
    print("=" * 50)
    print("遥操作 + 录制模式")
    print("=" * 50)
    
    print(f"\nConnecting leader arm on {leader_port}...")
    leader_config = SO101LeaderConfig(port=leader_port, id="leader")
    leader = SO101Leader(leader_config)
    leader.connect()
    print("Leader connected!")
    
    print(f"\nConnecting follower arm on {follower_port}...")
    follower_config = SO101FollowerConfig(
        port=follower_port,
        id="follower",
        cameras=cameras,
    )
    follower = SO101Follower(follower_config)
    follower.connect()
    print("Follower connected!")
    
    recorder = JointRecorder(log_dir)
    
    print("\n" + "=" * 50)
    print("Commands (type and press Enter):")
    print("  rec <name>  - start recording (e.g., 'rec 1')")
    print("  s           - stop recording")
    print("  q           - quit")
    print("=" * 50)
    
    import threading
    import queue
    
    cmd_queue = queue.Queue()
    
    def input_thread():
        while True:
            try:
                cmd = input().strip().lower()
                cmd_queue.put(cmd)
                if cmd == "q":
                    break
            except EOFError:
                break
    
    input_thread_obj = threading.Thread(target=input_thread, daemon=True)
    input_thread_obj.start()
    
    print("\nTeleoperating... (type commands and press Enter)")
    
    try:
        while True:
            loop_start = time.perf_counter()
            
            try:
                cmd = cmd_queue.get_nowait()
                if cmd == "q":
                    print("\nQuitting...")
                    break
                elif cmd == "s":
                    recorder.stop()
                elif cmd.startswith("rec "):
                    parts = cmd.split()
                    if len(parts) == 2:
                        recorder.start(parts[1])
            except queue.Empty:
                pass
            
            action = leader.get_action()
            follower.send_action(action)
            
            if recorder.is_recording:
                recorder.log(action)
            
            dt_s = time.perf_counter() - loop_start
            busy_wait(1 / fps - dt_s)
    
    except KeyboardInterrupt:
        print("\nInterrupted")
    
    finally:
        recorder.stop()
        leader.disconnect()
        follower.disconnect()
        print("Disconnected")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Teleoperate with joint recording")
    parser.add_argument("--leader-port", type=str, default=None, help="Leader arm port")
    parser.add_argument("--follower-port", type=str, default=None, help="Follower arm port")
    parser.add_argument("--fps", type=int, default=30, help="FPS")
    parser.add_argument("--log-dir", type=str, default="joint_logs", help="Log directory")
    args = parser.parse_args()
    
    leader_port = args.leader_port
    follower_port = args.follower_port
    
    if not leader_port:
        print("Scanning for leader port...")
        leader_port = find_port(["/dev/ttyCH343USB0", "/dev/ttyUSB0", "/dev/ttyACM0"])
        if not leader_port:
            print("ERROR: Leader port not found!")
            return
    
    if not follower_port:
        print("Scanning for follower port...")
        follower_port = find_port(["/dev/ttyCH343USB2", "/dev/ttyUSB2", "/dev/ttyACM2"])
        if not follower_port:
            print("ERROR: Follower port not found!")
            return
    
    print(f"Leader port: {leader_port}")
    print(f"Follower port: {follower_port}")
    
    teleoperate_with_recording(
        leader_port=leader_port,
        follower_port=follower_port,
        fps=args.fps,
        log_dir=args.log_dir,
    )


if __name__ == "__main__":
    main()
