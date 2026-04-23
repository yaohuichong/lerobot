import glob
import os
import time

from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.robots.so101_follower import SO101Follower, SO101FollowerConfig


def find_robot_port():
    patterns = ["/dev/ttyCH343USB*", "/dev/ttyUSB*", "/dev/ttyACM*"]
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

    def start(self, filename: str):
        if self.log_file:
            self.log_file.close()

        filepath = os.path.join(self.log_dir, f"{filename}.txt")
        self.log_file = open(filepath, "w")
        self.log_file.write(
            "# timestamp,step,shoulder_pan,shoulder_lift,elbow_flex,wrist_flex,wrist_roll,gripper\n"
        )
        self.step_count = 0
        self.start_time = time.time()
        print(f"[REC] Started recording to {filepath}")

    def log(self, positions: dict):
        if self.log_file:
            elapsed = time.time() - self.start_time if self.start_time else 0
            values = [
                positions.get(m, 0.0)
                for m in [
                    "shoulder_pan",
                    "shoulder_lift",
                    "elbow_flex",
                    "wrist_flex",
                    "wrist_roll",
                    "gripper",
                ]
            ]
            line = f"{elapsed:.4f},{self.step_count}," + ",".join([f"{v:.4f}" for v in values]) + "\n"
            self.log_file.write(line)
            self.step_count += 1
            self.log_file.flush()

    def stop(self):
        if self.log_file:
            self.log_file.close()
            self.log_file = None
            print(f"[REC] Recording stopped, {self.step_count} steps saved")


class TraditionalController:
    def __init__(self):
        self.robot = None
        self.motor_names = [
            "shoulder_pan",
            "shoulder_lift",
            "elbow_flex",
            "wrist_flex",
            "wrist_roll",
            "gripper",
        ]
        self.recorder = JointRecorder()
        self.is_recording = False

    def connect(self):
        port = find_robot_port()
        if not port:
            raise ConnectionError("No robot port found!")

        print(f"Connecting to robot on {port}...")

        cameras = {
            "handeye": OpenCVCameraConfig(index_or_path="/dev/video0", width=640, height=480, fps=30),
            "front": OpenCVCameraConfig(index_or_path="/dev/video2", width=640, height=480, fps=30),
        }

        config = SO101FollowerConfig(
            port=port,
            id="scooping_follower",
            cameras=cameras,
            max_relative_target=50.0,
        )
        self.robot = SO101Follower(config)
        self.robot.connect()
        print("Robot connected!")

    def disconnect(self):
        if self.robot:
            self.robot.disconnect()
            print("Robot disconnected")

    def get_joint_positions(self) -> dict:
        obs = self.robot.get_observation()
        positions = {}
        for motor in self.motor_names:
            key = f"{motor}.pos"
            positions[motor] = obs.get(key, 0.0)

        if self.is_recording:
            self.recorder.log(positions)

        return positions

    def send_joint_positions(self, positions: dict, wait_time: float = 0.033):
        action_dict = {}
        for motor in self.motor_names:
            if motor in positions:
                val = float(positions[motor])
                if motor == "gripper":
                    val = max(0.0, min(100.0, val))
                action_dict[f"{motor}.pos"] = val

        self.robot.send_action(action_dict)

        if self.is_recording:
            self.recorder.log(positions)

        time.sleep(wait_time)

    def move_to_position(self, target: dict, duration: float = 1.0, fps: int = 30):
        current = self.get_joint_positions()
        steps = int(duration * fps)
        dt = 1.0 / fps

        for step in range(steps + 1):
            t = step / steps
            interp = {}
            for motor in self.motor_names:
                if motor in target:
                    interp[motor] = current[motor] + t * (target[motor] - current[motor])
                else:
                    interp[motor] = current[motor]
            self.send_joint_positions(interp, dt)

        print(f"Moved to position: {target}")

    def demo_scoop_motion(self):
        print("\n=== Demo: Scoop Motion ===")

        home = {
            "shoulder_pan": 0,
            "shoulder_lift": 0,
            "elbow_flex": 0,
            "wrist_flex": 0,
            "wrist_roll": 0,
            "gripper": 50,
        }
        ready = {
            "shoulder_pan": 0,
            "shoulder_lift": -30,
            "elbow_flex": 45,
            "wrist_flex": 20,
            "wrist_roll": 0,
            "gripper": 80,
        }
        scoop_start = {
            "shoulder_pan": 0,
            "shoulder_lift": -45,
            "elbow_flex": 60,
            "wrist_flex": 30,
            "wrist_roll": 0,
            "gripper": 100,
        }
        scoop_end = {
            "shoulder_pan": 0,
            "shoulder_lift": -20,
            "elbow_flex": 30,
            "wrist_flex": 10,
            "wrist_roll": 0,
            "gripper": 30,
        }

        print("1. Moving to home...")
        self.move_to_position(home, duration=1.0)

        print("2. Moving to ready position...")
        self.move_to_position(ready, duration=1.0)

        print("3. Opening gripper...")
        self.move_to_position(scoop_start, duration=0.5)

        print("4. Scooping...")
        self.move_to_position(scoop_end, duration=1.0)

        print("5. Returning to ready...")
        self.move_to_position(ready, duration=1.0)

        print("6. Returning to home...")
        self.move_to_position(home, duration=1.0)

        print("Demo complete!")

    def interactive_mode(self):
        print("\n=== Interactive Mode ===")
        print("Commands:")
        print("  pos - show current joint positions")
        print("  move <joint> <value> - move joint to value")
        print("  goto <j1> <j2> <j3> <j4> <j5> <gripper> - move all joints")
        print("  rec <filename> - start recording (e.g., 'rec 1' saves to joint_logs/1.txt)")
        print("  stop - stop recording")
        print("  demo - run scoop demo")
        print("  quit - exit")
        print()

        while True:
            try:
                cmd = input("> ").strip().lower()

                if cmd == "quit" or cmd == "q":
                    break

                elif cmd == "pos":
                    pos = self.get_joint_positions()
                    print("Current positions:")
                    for motor, val in pos.items():
                        print(f"  {motor}: {val:.2f}")

                elif cmd.startswith("move "):
                    parts = cmd.split()
                    if len(parts) == 3:
                        joint = parts[1]
                        value = float(parts[2])
                        if joint in self.motor_names:
                            self.send_joint_positions({joint: value})
                            print(f"Moved {joint} to {value}")
                        else:
                            print(f"Unknown joint: {joint}")
                    else:
                        print("Usage: move <joint> <value>")

                elif cmd.startswith("goto "):
                    parts = cmd.split()
                    if len(parts) == 7:
                        values = [float(v) for v in parts[1:]]
                        target = dict(zip(self.motor_names, values, strict=True))
                        self.move_to_position(target, duration=1.0)
                    else:
                        print(
                            "Usage: goto <shoulder_pan> <shoulder_lift> <elbow_flex> <wrist_flex> <wrist_roll> <gripper>"
                        )

                elif cmd.startswith("rec "):
                    parts = cmd.split()
                    if len(parts) == 2:
                        filename = parts[1]
                        self.recorder.start(filename)
                        self.is_recording = True
                        print(f"Recording started. File: joint_logs/{filename}.txt")
                    else:
                        print("Usage: rec <filename>")

                elif cmd == "stop":
                    if self.is_recording:
                        self.recorder.stop()
                        self.is_recording = False
                    else:
                        print("Not recording")

                elif cmd == "demo":
                    self.demo_scoop_motion()

                else:
                    print("Unknown command. Type 'quit' to exit.")

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")

        print("Exiting interactive mode...")


def main():
    controller = TraditionalController()

    try:
        controller.connect()
        controller.interactive_mode()
    finally:
        controller.disconnect()


if __name__ == "__main__":
    main()
