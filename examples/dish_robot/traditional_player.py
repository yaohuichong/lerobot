import glob
import json
import os
import time

from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.robots.so101_follower import SO101Follower, SO101FollowerConfig
from lerobot.utils.robot_utils import busy_wait


def find_robot_port():
    patterns = ["/dev/ttyCH343USB*", "/dev/ttyUSB*", "/dev/ttyACM*"]
    for pattern in patterns:
        ports = glob.glob(pattern)
        if ports:
            for port in sorted(ports):
                if os.path.exists(port):
                    return port
    return None


def txt_to_json(txt_path: str) -> dict:
    data = {
        "metadata": {
            "source_file": os.path.basename(txt_path),
            "total_steps": 0,
            "duration_s": 0.0,
        },
        "trajectory": [],
    }

    motor_names = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]

    with open(txt_path, "r") as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        if line.startswith("#") or not line:
            continue

        parts = line.split(",")
        if len(parts) >= 8:
            timestamp = float(parts[0])
            step = int(parts[1])
            values = [float(v) for v in parts[2:8]]

            frame = {
                "timestamp": round(timestamp, 4),
                "step": step,
                "joints": {motor_names[i]: round(values[i], 4) for i in range(6)},
            }
            data["trajectory"].append(frame)

    if data["trajectory"]:
        data["metadata"]["total_steps"] = len(data["trajectory"])
        data["metadata"]["duration_s"] = round(data["trajectory"][-1]["timestamp"], 4)

    return data


def json_to_txt(json_data: dict, txt_path: str):
    with open(txt_path, "w") as f:
        f.write("# timestamp,step,shoulder_pan,shoulder_lift,elbow_flex,wrist_flex,wrist_roll,gripper\n")
        for frame in json_data["trajectory"]:
            joints = frame["joints"]
            line = f"{frame['timestamp']},{frame['step']},{joints['shoulder_pan']},{joints['shoulder_lift']},{joints['elbow_flex']},{joints['wrist_flex']},{joints['wrist_roll']},{joints['gripper']}\n"
            f.write(line)


def convert_all_txt_to_json(log_dir: str = "joint_logs"):
    json_dir = os.path.join(log_dir, "json")
    os.makedirs(json_dir, exist_ok=True)

    for i in range(1, 100):
        txt_path = os.path.join(log_dir, f"{i}.txt")
        if os.path.exists(txt_path):
            json_data = txt_to_json(txt_path)
            json_path = os.path.join(json_dir, f"{i}.json")

            with open(json_path, "w") as f:
                json.dump(json_data, f, indent=2)

            print(f"Converted {txt_path} -> {json_path}")
            print(
                f"  Steps: {json_data['metadata']['total_steps']}, Duration: {json_data['metadata']['duration_s']}s"
            )

    print(f"\nJSON files saved to: {json_dir}")


class TraditionalPlayer:
    def __init__(self, log_dir: str = "joint_logs"):
        self.log_dir = log_dir
        self.robot = None
        self.motor_names = [
            "shoulder_pan",
            "shoulder_lift",
            "elbow_flex",
            "wrist_flex",
            "wrist_roll",
            "gripper",
        ]
        self.trajectories = {}
        self._load_trajectories()

    def _load_trajectories(self):
        for i in range(1, 100):
            txt_path = os.path.join(self.log_dir, f"{i}.txt")
            if os.path.exists(txt_path):
                self.trajectories[i] = txt_to_json(txt_path)

        print(f"Loaded {len(self.trajectories)} trajectories: {list(self.trajectories.keys())}")

    def connect(self):
        port = find_robot_port()
        if not port:
            raise ConnectionError("No robot port found!")

        print(f"Connecting to robot on {port}...")

        cameras = {
            "handeye": OpenCVCameraConfig(index_or_path="/dev/video2", width=640, height=480, fps=30),
            "front": OpenCVCameraConfig(index_or_path="/dev/video0", width=640, height=480, fps=30),
        }

        config = SO101FollowerConfig(
            port=port,
            id="follower",
            cameras=cameras,
        )
        self.robot = SO101Follower(config)
        self.robot.connect()
        print("Robot connected!")

    def disconnect(self):
        if self.robot:
            self.robot.disconnect()
            print("Robot disconnected")

    def get_current_position(self) -> dict:
        obs = self.robot.get_observation()
        positions = {}
        for motor in self.motor_names:
            key = f"{motor}.pos"
            positions[motor] = obs.get(key, 0.0)
        return positions

    def send_position(self, positions: dict):
        action_dict = {}
        for motor in self.motor_names:
            if motor in positions:
                val = float(positions[motor])
                if motor == "gripper":
                    val = max(0.0, min(100.0, val))
                action_dict[f"{motor}.pos"] = val
        self.robot.send_action(action_dict)

    def play_trajectory(self, traj_id: int, speed: float = 1.0, fps: int = 30):
        if traj_id not in self.trajectories:
            print(f"Trajectory {traj_id} not found!")
            return

        traj = self.trajectories[traj_id]
        frames = traj["trajectory"]

        print(f"\nPlaying trajectory {traj_id}")
        print(f"  Steps: {traj['metadata']['total_steps']}")
        print(f"  Duration: {traj['metadata']['duration_s']}s")
        print(f"  Speed: {speed}x")

        dt = 1.0 / fps / speed

        for i, frame in enumerate(frames):
            loop_start = time.perf_counter()

            self.send_position(frame["joints"])

            if i % 30 == 0:
                print(f"  Step {i}/{len(frames)} ({i / len(frames) * 100:.1f}%)")

            elapsed = time.perf_counter() - loop_start
            busy_wait(dt - elapsed)

        print(f"Trajectory {traj_id} completed!")

    def play_sequence(self, sequence: list, speed: float = 1.0, pause_between: float = 1.0):
        print(f"\nPlaying sequence: {sequence}")

        for traj_id in sequence:
            self.play_trajectory(traj_id, speed=speed)
            if traj_id != sequence[-1]:
                print(f"  Pausing {pause_between}s before next trajectory...")
                time.sleep(pause_between)

        print("\nSequence completed!")

    def interactive_mode(self):
        print("\n" + "=" * 50)
        print("传统算法回放模式")
        print("=" * 50)
        print(f"已加载轨迹: {list(self.trajectories.keys())}")
        print("\nCommands:")
        print("  play <id>       - play trajectory (e.g., 'play 1')")
        print("  seq <id1> <id2> - play sequence (e.g., 'seq 1 2 3')")
        print("  speed <value>   - set speed (e.g., 'speed 0.5' for half speed)")
        print("  pos             - show current position")
        print("  goto <j1> <j2> <j3> <j4> <j5> <gripper> - move to position")
        print("  info <id>       - show trajectory info")
        print("  convert         - convert all txt to json")
        print("  quit            - exit")
        print()

        speed = 1.0

        while True:
            try:
                cmd = input("> ").strip().lower()

                if cmd == "quit" or cmd == "q":
                    break

                elif cmd == "pos":
                    pos = self.get_current_position()
                    print("Current position:")
                    for motor, val in pos.items():
                        print(f"  {motor}: {val:.2f}")

                elif cmd.startswith("play "):
                    parts = cmd.split()
                    if len(parts) == 2:
                        traj_id = int(parts[1])
                        self.play_trajectory(traj_id, speed=speed)
                    else:
                        print("Usage: play <id>")

                elif cmd.startswith("seq "):
                    parts = cmd.split()
                    if len(parts) >= 2:
                        sequence = [int(p) for p in parts[1:]]
                        self.play_sequence(sequence, speed=speed)
                    else:
                        print("Usage: seq <id1> <id2> ...")

                elif cmd.startswith("speed "):
                    parts = cmd.split()
                    if len(parts) == 2:
                        speed = float(parts[1])
                        print(f"Speed set to {speed}x")
                    else:
                        print("Usage: speed <value>")

                elif cmd.startswith("goto "):
                    parts = cmd.split()
                    if len(parts) == 7:
                        values = [float(v) for v in parts[1:]]
                        target = dict(zip(self.motor_names, values, strict=True))
                        self.send_position(target)
                        print(f"Moved to: {target}")
                    else:
                        print(
                            "Usage: goto <shoulder_pan> <shoulder_lift> <elbow_flex> <wrist_flex> <wrist_roll> <gripper>"
                        )

                elif cmd.startswith("info "):
                    parts = cmd.split()
                    if len(parts) == 2:
                        traj_id = int(parts[1])
                        if traj_id in self.trajectories:
                            traj = self.trajectories[traj_id]
                            print(f"Trajectory {traj_id}:")
                            print(f"  Steps: {traj['metadata']['total_steps']}")
                            print(f"  Duration: {traj['metadata']['duration_s']}s")
                            if traj["trajectory"]:
                                first = traj["trajectory"][0]["joints"]
                                last = traj["trajectory"][-1]["joints"]
                                print(f"  Start: {first}")
                                print(f"  End: {last}")
                        else:
                            print(f"Trajectory {traj_id} not found")
                    else:
                        print("Usage: info <id>")

                elif cmd == "convert":
                    convert_all_txt_to_json(self.log_dir)
                    self._load_trajectories()

                else:
                    print("Unknown command. Type 'quit' to exit.")

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")

        print("Exiting...")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Traditional algorithm player")
    parser.add_argument(
        "--log-dir",
        type=str,
        default="/home/nvidia/lerobot/examples/dish_robot/joint_logs",
        help="Log directory",
    )
    parser.add_argument("--convert", action="store_true", help="Convert txt to json and exit")
    args = parser.parse_args()

    if args.convert:
        convert_all_txt_to_json(args.log_dir)
        return

    player = TraditionalPlayer(log_dir=args.log_dir)

    try:
        player.connect()
        player.interactive_mode()
    finally:
        player.disconnect()


if __name__ == "__main__":
    main()
