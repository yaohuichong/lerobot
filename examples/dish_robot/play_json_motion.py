# -*- coding: utf-8 -*-
from __future__ import print_function
import json
import os
import sys
import time
import glob

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    from lerobot.robots.so101_follower import SO101Follower, SO101FollowerConfig
    from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
    from lerobot.utils.robot_utils import busy_wait
    ROBOT_AVAILABLE = True
except ImportError:
    print("Warning: lerobot modules not available. Running in simulation mode.")
    ROBOT_AVAILABLE = False


def find_robot_port():
    """Find robot serial port"""
    patterns = ["/dev/ttyCH343USB*", "/dev/ttyUSB*", "/dev/ttyACM*"]
    for pattern in patterns:
        ports = glob.glob(pattern)
        if ports:
            for port in sorted(ports):
                if os.path.exists(port):
                    return port
    return None


def load_json_trajectory(json_path):
    """Load trajectory from JSON file"""
    with open(json_path, 'r') as f:
        data = json.load(f)
    return data


def get_available_motions(log_dir):
    """Get available motion files from joint_logs directory"""
    motions = {}
    for i in range(1, 100):
        json_path = os.path.join(log_dir, "{}.json".format(i))
        if os.path.exists(json_path):
            motions[i] = json_path
    return motions


def load_calibration_file(calibration_path):
    """Load calibration data from JSON file"""
    with open(calibration_path, 'r') as f:
        data = json.load(f)
    return data


class MotionPlayer:
    """Player for JSON motion files"""
    
    def __init__(self, log_dir="joint_logs", calibration_path=None):
        self.log_dir = log_dir
        self.calibration_path = calibration_path
        self.robot = None
        self.motor_names = ["shoulder_pan", "shoulder_lift", "elbow_flex", 
                           "wrist_flex", "wrist_roll", "gripper"]
        self.motions = {}
        self._load_motions()
    
    def _load_motions(self):
        """Load all available motion files"""
        log_path = os.path.join(os.path.dirname(__file__), self.log_dir)
        if not os.path.exists(log_path):
            # Try absolute path
            log_path = self.log_dir
        
        self.motions = get_available_motions(log_path)
        print("Loaded {} motion files: {}".format(len(self.motions), sorted(self.motions.keys())))
    
    def connect(self, skip_calibration=False):
        """Connect to robot
        
        Args:
            skip_calibration: If True, skip calibration and load from file instead
        """
        if not ROBOT_AVAILABLE:
            print("Running in simulation mode (no robot connection)")
            return
        
        port = find_robot_port()
        if not port:
            raise ConnectionError("No robot port found!")
        
        print("Connecting to robot on {}...".format(port))
        
        # Load calibration from file if provided
        if skip_calibration and self.calibration_path:
            if not os.path.exists(self.calibration_path):
                raise FileNotFoundError("Calibration file not found: {}".format(self.calibration_path))
            print("Loading calibration from: {}".format(self.calibration_path))
            calibration_dir = os.path.dirname(self.calibration_path)
            calibration_id = os.path.splitext(os.path.basename(self.calibration_path))[0]
        else:
            calibration_dir = None
            calibration_id = "follower"
        
        cameras = {
            "handeye": OpenCVCameraConfig(index_or_path="/dev/video2", width=640, height=480, fps=30),
            "front": OpenCVCameraConfig(index_or_path="/dev/video0", width=640, height=480, fps=30),
        }
        
        config = SO101FollowerConfig(
            port=port,
            id=calibration_id,
            cameras=cameras,
            calibration_dir=calibration_dir,
        )
        self.robot = SO101Follower(config)
        
        # Connect with or without calibration
        if skip_calibration and self.calibration_path:
            # Load calibration data from file
            calibration_data = load_calibration_file(self.calibration_path)
            self.robot.calibration = calibration_data
            # Connect without running calibration
            self.robot.bus.connect()
            if not self.robot.is_calibrated:
                print("Writing calibration to motors...")
                self.robot.bus.write_calibration(calibration_data)
            for cam in self.robot.cameras.values():
                cam.connect()
            self.robot.configure()
            print("Robot connected with loaded calibration!")
        else:
            self.robot.connect()
            print("Robot connected!")
    
    def disconnect(self):
        """Disconnect from robot"""
        if self.robot:
            self.robot.disconnect()
            print("Robot disconnected")
    
    def send_joint_positions(self, positions):
        """Send joint positions to robot"""
        if not self.robot:
            return
        
        action_dict = {}
        for motor in self.motor_names:
            if motor in positions:
                val = float(positions[motor])
                if motor == "gripper":
                    val = max(0.0, min(100.0, val))
                action_dict["{}.pos".format(motor)] = val
        self.robot.send_action(action_dict)
    
    def play_motion(self, motion_id, fps=30, loop=False):
        """
        Play a motion from JSON file
        
        Args:
            motion_id: ID of the motion file (e.g., 1 for 1.json)
            fps: Frames per second (default 30)
            loop: Whether to loop the motion
        """
        if motion_id not in self.motions:
            print("Error: Motion {} not found!".format(motion_id))
            print("Available motions: {}".format(sorted(self.motions.keys())))
            return
        
        json_path = self.motions[motion_id]
        data = load_json_trajectory(json_path)
        
        print("\n" + "=" * 50)
        print("Playing motion {}".format(motion_id))
        print("=" * 50)
        print("File: {}".format(json_path))
        print("Total frames: {}".format(len(data)))
        print("FPS: {}".format(fps))
        print("Loop: {}".format(loop))
        print("-" * 50)
        
        dt = 1.0 / fps
        
        try:
            while True:
                for i, frame in enumerate(data):
                    loop_start = time.perf_counter()
                    
                    # Extract joint positions from frame
                    positions = {
                        "shoulder_pan": frame.get("shoulder_pan", 0),
                        "shoulder_lift": frame.get("shoulder_lift", 0),
                        "elbow_flex": frame.get("elbow_flex", 0),
                        "wrist_flex": frame.get("wrist_flex", 0),
                        "wrist_roll": frame.get("wrist_roll", 0),
                        "gripper": frame.get("gripper", 0),
                    }
                    
                    # Send to robot
                    self.send_joint_positions(positions)
                    
                    # Print progress every 30 frames
                    if i % 30 == 0:
                        print("  Frame {}/{} ({:.1f}%)".format(i, len(data), i * 100.0 / len(data)))
                    
                    # Maintain frame rate
                    elapsed = time.perf_counter() - loop_start
                    sleep_time = dt - elapsed
                    if sleep_time > 0:
                        if ROBOT_AVAILABLE:
                            busy_wait(sleep_time)
                        else:
                            time.sleep(sleep_time)
                
                print("Motion {} completed!".format(motion_id))
                
                if not loop:
                    break
                else:
                    print("Looping...")
        
        except KeyboardInterrupt:
            print("\nMotion interrupted by user")
    
    def interactive_mode(self):
        """Interactive mode for selecting and playing motions"""
        print("\n" + "=" * 50)
        print("JSON Motion Player - Interactive Mode")
        print("=" * 50)
        print("Available motions: {}".format(sorted(self.motions.keys())))
        print("\nCommands:")
        print("  play <id>       - Play motion (e.g., 'play 1')")
        print("  loop <id>       - Play motion in loop (e.g., 'loop 2')")
        print("  fps <value>     - Set playback FPS (default 30)")
        print("  list            - List available motions")
        print("  quit            - Exit")
        print("-" * 50)
        if self.calibration_path:
            print("Calibration file: {}".format(self.calibration_path))
        
        fps = 30
        
        while True:
            try:
                cmd = raw_input("> ").strip().lower()
                
                if cmd == "quit" or cmd == "q":
                    break
                
                elif cmd == "list" or cmd == "ls":
                    print("Available motions: {}".format(sorted(self.motions.keys())))
                
                elif cmd.startswith("play "):
                    parts = cmd.split()
                    if len(parts) == 2:
                        motion_id = int(parts[1])
                        self.play_motion(motion_id, fps=fps, loop=False)
                    else:
                        print("Usage: play <id>")
                
                elif cmd.startswith("loop "):
                    parts = cmd.split()
                    if len(parts) == 2:
                        motion_id = int(parts[1])
                        print("Press Ctrl+C to stop looping")
                        self.play_motion(motion_id, fps=fps, loop=True)
                    else:
                        print("Usage: loop <id>")
                
                elif cmd.startswith("fps "):
                    parts = cmd.split()
                    if len(parts) == 2:
                        fps = int(parts[1])
                        print("FPS set to {}".format(fps))
                    else:
                        print("Usage: fps <value>")
                
                else:
                    print("Unknown command. Available: play, loop, fps, list, quit")
            
            except KeyboardInterrupt:
                print("\nInterrupted")
            except Exception as e:
                print("Error: {}".format(e))
        
        print("Exiting...")


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Play JSON motion files on SO101 robot")
    parser.add_argument("--log-dir", type=str, default="joint_logs", 
                       help="Directory containing JSON motion files")
    parser.add_argument("--motion", "-m", type=int, default=None,
                       help="Motion ID to play (e.g., 1, 2, 3)")
    parser.add_argument("--fps", type=int, default=30,
                       help="Playback FPS (default: 30)")
    parser.add_argument("--loop", action="store_true",
                       help="Loop the motion")
    parser.add_argument("--interactive", "-i", action="store_true",
                       help="Run in interactive mode")
    parser.add_argument("--calibration", "-c", type=str, default=None,
                       help="Path to calibration JSON file (skips calibration if provided)")
    parser.add_argument("--skip-calibration", "-s", action="store_true",
                       help="Skip calibration and load from file (requires --calibration)")
    
    args = parser.parse_args()
    
    # Create player with calibration path
    player = MotionPlayer(log_dir=args.log_dir, calibration_path=args.calibration)
    
    try:
        # Connect to robot (with or without calibration)
        player.connect(skip_calibration=args.skip_calibration)
        
        if args.interactive or args.motion is None:
            # Interactive mode
            player.interactive_mode()
        else:
            # Play specific motion
            player.play_motion(args.motion, fps=args.fps, loop=args.loop)
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        player.disconnect()


if __name__ == "__main__":
    main()
