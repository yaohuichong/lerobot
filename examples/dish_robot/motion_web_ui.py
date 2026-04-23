# -*- coding: utf-8 -*-
"""
Motion Web UI for SO101 robot
打饭机器人动作控制网页界面
"""

from __future__ import print_function

import glob
import json
import os
import threading
import time

# Try to import gradio
try:
    import gradio as gr

    GRADIO_AVAILABLE = True
except ImportError:
    GRADIO_AVAILABLE = False
    print("Warning: gradio not available")

# Try to import lerobot modules
try:
    from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
    from lerobot.robots.so101_follower import SO101Follower, SO101FollowerConfig
    from lerobot.utils.robot_utils import busy_wait

    ROBOT_AVAILABLE = True
except ImportError:
    ROBOT_AVAILABLE = False
    print("Warning: lerobot modules not available. Running in simulation mode.")

# Dish mapping
DISH_MAP = {
    "排骨": {"id": "1", "icon": "🍖"},
    "番茄炒蛋": {"id": "2", "icon": "🍅"},
    "土豆丝": {"id": "3", "icon": "🥔"},
}


def find_robot_port():
    """Find robot serial port"""
    ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyCH343USB*")
    if ports:
        return ports[0]
    return None


def load_json_trajectory(json_path):
    """Load trajectory from JSON file"""
    with open(json_path, "r") as f:
        data = json.load(f)
    return data


def load_calibration_file(calibration_path):
    """Load calibration from JSON file"""
    with open(calibration_path, "r") as f:
        calibration = json.load(f)
    return calibration


class MotionController:
    """Controller for JSON motion files"""

    def __init__(self, log_dir="joint_logs", calibration_path=None):
        self.log_dir = log_dir
        self.calibration_path = calibration_path
        self.robot = None
        self.motor_names = [
            "shoulder_pan",
            "shoulder_lift",
            "elbow_flex",
            "wrist_flex",
            "wrist_roll",
            "gripper",
        ]
        self.is_executing = False
        self.current_dish = None
        self.execution_lock = threading.Lock()
        self._stop_flag = False
        self._task_queue = []
        self._queue_thread = None
        self._current_index = 0
        self._total_count = 0

    def connect(self, skip_calibration=False):
        """Connect to robot"""
        if not ROBOT_AVAILABLE:
            print("Running in simulation mode (no robot connection)")
            return True

        port = find_robot_port()
        if not port:
            print("Error: No robot port found!")
            return False

        print("Connecting to robot on {}...".format(port))

        cameras = {
            "handeye": OpenCVCameraConfig(index_or_path="/dev/video0", width=640, height=480, fps=30),
            "front": OpenCVCameraConfig(index_or_path="/dev/video2", width=640, height=480, fps=30),
        }

        # Check if calibration file exists
        calibration_dir = None
        calibration_id = "follower"

        if self.calibration_path:
            if os.path.exists(self.calibration_path):
                print("Using calibration file: {}".format(self.calibration_path))
                calibration_dir = os.path.dirname(self.calibration_path)
                calibration_id = os.path.splitext(os.path.basename(self.calibration_path))[0]
            else:
                print("Warning: Calibration file not found: {}".format(self.calibration_path))
                print("Will use default calibration or run calibration")

        config = SO101FollowerConfig(
            port=port,
            id=calibration_id,
            cameras=cameras,
            calibration_dir=calibration_dir,
        )
        self.robot = SO101Follower(config)

        # Connect with option to skip calibration
        if skip_calibration and self.calibration_path and os.path.exists(self.calibration_path):
            # Load calibration from file and skip manual calibration
            print("Skipping calibration, loading from file...")
            calibration_data = load_calibration_file(self.calibration_path)
            self.robot.calibration = calibration_data
            self.robot.bus.connect()
            if not self.robot.is_calibrated:
                print("Writing calibration to motors...")
                self.robot.bus.write_calibration(calibration_data)
            for cam in self.robot.cameras.values():
                cam.connect()
            self.robot.configure()
            print("Robot connected with loaded calibration!")
        else:
            # Normal connection (may run calibration if needed)
            self.robot.connect(calibrate=not skip_calibration)
            print("Robot connected!")

        return True

    def send_joint_positions(self, positions):
        """Send joint positions to robot"""
        if not ROBOT_AVAILABLE or self.robot is None:
            print("  [DEBUG] Robot not available, skipping send_action")
            return

        action_dict = {}
        for motor in self.motor_names:
            if motor in positions:
                val = float(positions[motor])
                if motor == "gripper":
                    val = max(0.0, min(100.0, val))
                action_dict["{}.pos".format(motor)] = val

        print("  [DEBUG] Sending action: {}".format(action_dict))
        self.robot.send_action(action_dict)

    def stop(self):
        """Stop current motion and clear queue"""
        with self.execution_lock:
            self._stop_flag = True
            self._task_queue = []
        self.is_executing = False
        self.current_dish = None
        return "[OK] 已停止"

    def add_to_queue(self, dish_name, count=1):
        """Add dish to execution queue"""
        with self.execution_lock:
            for _ in range(count):
                self._task_queue.append(dish_name)
        return len(self._task_queue)

    def clear_queue(self):
        """Clear execution queue"""
        with self.execution_lock:
            self._task_queue = []
        return "[OK] 队列已清空"

    def get_queue_status(self):
        """Get current queue status"""
        with self.execution_lock:
            queue_copy = list(self._task_queue)
        if not queue_copy:
            return "队列为空"
        # Count each dish
        from collections import Counter

        counts = Counter(queue_copy)
        items = ["{}x {}".format(count, name) for name, count in counts.items()]
        return "队列: " + ", ".join(items)

    def _process_queue(self, fps=30):
        """Process task queue in background"""
        self._current_index = 0
        self._total_count = len(self._task_queue)

        while True:
            with self.execution_lock:
                if self._stop_flag or not self._task_queue:
                    break
                dish_name = self._task_queue.pop(0)
                self._current_index += 1

            self.current_dish = dish_name
            result = self._play_motion_single(dish_name, fps)
            print(result)

            # Small delay between dishes
            if self._task_queue:
                time.sleep(1.0)

        self.is_executing = False
        self.current_dish = None
        self._current_index = 0
        self._total_count = 0

    def start_queue_execution(self, fps=30):
        """Start executing queue in background thread"""
        if self.is_executing:
            return "[ERROR] 正在执行中"

        with self.execution_lock:
            if not self._task_queue:
                return "[ERROR] 队列为空"

        self.is_executing = True
        self._stop_flag = False

        self._queue_thread = threading.Thread(target=self._process_queue, args=(fps,), daemon=True)
        self._queue_thread.start()
        return "[OK] 开始执行队列"

    def _play_motion_single(self, dish_name, fps=30):
        """Play a single motion (internal use)"""
        if dish_name not in DISH_MAP:
            return "[ERROR] 未知菜品: {}".format(dish_name)

        dish_info = DISH_MAP[dish_name]
        motion_id = dish_info["id"]

        # Load motion file
        log_path = os.path.join(os.path.dirname(__file__), self.log_dir)
        json_path = os.path.join(log_path, "{}.json".format(motion_id))

        if not os.path.exists(json_path):
            return "[ERROR] 运动文件不存在: {}".format(json_path)

        data = load_json_trajectory(json_path)

        print("\n" + "=" * 50)
        print("Playing motion for: {}".format(dish_name))
        print("=" * 50)
        print("File: {}".format(json_path))
        print("Total frames: {}".format(len(data)))
        print("FPS: {}".format(fps))
        print("Robot available: {}".format(ROBOT_AVAILABLE))
        print("Robot connected: {}".format(self.robot is not None))
        print("-" * 50)

        dt = 1.0 / fps

        try:
            for i, frame in enumerate(data):
                with self.execution_lock:
                    if self._stop_flag:
                        print("Motion stopped by user")
                        return "[STOPPED] {} 已停止".format(dish_name)

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

            print("Motion for {} completed!".format(dish_name))
            return "[OK] {} 执行完成".format(dish_name)

        except Exception as e:
            print("Error during motion: {}".format(e))
            return "[ERROR] {} 执行失败: {}".format(dish_name, e)

    def play_motion(self, dish_name, fps=30):
        """
        Play motion for a dish

        Args:
            dish_name: Name of the dish (排骨, 番茄炒蛋, 土豆丝)
            fps: Playback frames per second
        """
        if dish_name not in DISH_MAP:
            print("Error: Unknown dish '{}'".format(dish_name))
            return

        dish_info = DISH_MAP[dish_name]
        motion_id = dish_info["id"]

        # Load motion file
        log_path = os.path.join(os.path.dirname(__file__), self.log_dir)
        json_path = os.path.join(log_path, "{}.json".format(motion_id))

        if not os.path.exists(json_path):
            print("Error: Motion file not found: {}".format(json_path))
            return

        data = load_json_trajectory(json_path)

        print("\n" + "=" * 50)
        print("Playing motion for: {}".format(dish_name))
        print("=" * 50)
        print("File: {}".format(json_path))
        print("Total frames: {}".format(len(data)))
        print("FPS: {}".format(fps))
        print("-" * 50)

        dt = 1.0 / fps

        try:
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

            print("Motion for {} completed!".format(dish_name))

        except Exception as e:
            print("Error during motion: {}".format(e))

    def get_status(self):
        """Get current status"""
        if self.is_executing:
            if self._total_count > 0:
                progress = (
                    "执行中 [{}/{}]: {}".format(self._current_index, self._total_count, self.current_dish)
                    if self.current_dish
                    else "执行中 [{}/{}]".format(self._current_index, self._total_count)
                )
                return progress
            return "执行中: {}".format(self.current_dish) if self.current_dish else "执行中"
        return "空闲"

    def get_progress(self):
        """Get progress info"""
        return {
            "is_executing": self.is_executing,
            "current_dish": self.current_dish,
            "current_index": self._current_index,
            "total_count": self._total_count,
            "queue_length": len(self._task_queue),
        }


class MotionWebUI:
    """Web UI for motion control"""

    def __init__(self, controller, host="0.0.0.0", port=7860):
        self.controller = controller
        self.host = host
        self.port = port

    def _play_dish(self, dish_name):
        """Play motion for a dish"""
        if not dish_name:
            return "[ERROR] 请选择菜品", self.controller.get_status(), self.controller.get_queue_status(), 0

        # Run motion in background thread
        def run_motion():
            self.controller.play_motion(dish_name, fps=30)

        thread = threading.Thread(target=run_motion, daemon=True)
        thread.start()

        return (
            "[OK] 开始执行: {}".format(dish_name),
            self.controller.get_status(),
            self.controller.get_queue_status(),
            0,
        )

    def _add_to_queue(self, dish_name, count):
        """Add dish to queue"""
        if not dish_name:
            return "[ERROR] 请选择菜品", self.controller.get_queue_status(), 0

        queue_len = self.controller.add_to_queue(dish_name, count)
        return (
            "[OK] 已添加 {} 份 {}，队列共 {} 项".format(count, dish_name, queue_len),
            self.controller.get_queue_status(),
            0,
        )

    def _add_batch_to_queue(self, count_pg, count_xhs, count_td):
        """Add multiple dishes to queue"""
        added_items = []

        # Ensure values are integers
        count_pg = int(count_pg) if count_pg else 0
        count_xhs = int(count_xhs) if count_xhs else 0
        count_td = int(count_td) if count_td else 0

        if count_pg > 0:
            self.controller.add_to_queue("排骨", count_pg)
            added_items.append("{}份排骨".format(count_pg))

        if count_xhs > 0:
            self.controller.add_to_queue("番茄炒蛋", count_xhs)
            added_items.append("{}份番茄炒蛋".format(count_xhs))

        if count_td > 0:
            self.controller.add_to_queue("土豆丝", count_td)
            added_items.append("{}份土豆丝".format(count_td))

        if not added_items:
            return "[WARNING] 没有选择任何菜品", self.controller.get_queue_status(), 0

        return "[OK] 已添加: " + ", ".join(added_items), self.controller.get_queue_status(), 0

    def _start_queue(self):
        """Start executing queue"""
        result = self.controller.start_queue_execution(fps=30)
        return result, self.controller.get_status(), self.controller.get_queue_status(), 0

    def _clear_queue(self):
        """Clear queue"""
        result = self.controller.clear_queue()
        return result, self.controller.get_queue_status(), 0

    def _stop(self):
        """Stop current motion"""
        result = self.controller.stop()
        return result, self.controller.get_status(), self.controller.get_queue_status(), 0

    def _get_status(self):
        """Get current status"""
        return self.controller.get_status()

    def _update_progress(self):
        """Update progress bar"""
        progress = self.controller.get_progress()
        if progress["is_executing"] and progress["total_count"] > 0:
            percent = int(progress["current_index"] * 100.0 / progress["total_count"])
            return self.controller.get_status(), self.controller.get_queue_status(), percent
        return self.controller.get_status(), self.controller.get_queue_status(), 0

    def create_ui(self):
        """Create Gradio UI"""
        css = """
        .gradio-container {
            max-width: 100% !important;
        }
        .dish-btn {
            min-height: 80px !important;
            font-size: 1.3em !important;
            font-weight: bold !important;
        }
        .stop-btn {
            min-height: 60px !important;
            font-size: 1.2em !important;
        }
        .status-box {
            font-size: 1.1em !important;
            text-align: center !important;
        }
        .queue-box {
            font-size: 1.0em !important;
            background-color: #f0f0f0 !important;
        }
        .menu-section {
            border: 2px solid #ddd !important;
            border-radius: 10px !important;
            padding: 15px !important;
            margin: 10px 0 !important;
        }
        .dish-label {
            min-width: 150px !important;
            font-weight: bold !important;
            font-size: 1.1em !important;
            margin-top: 10px !important;
        }
        """

        with gr.Blocks(title="打饭机器人 - 动作控制", theme=gr.themes.Soft(), css=css) as demo:
            gr.Markdown("# 🍚 打饭机器人 - 动作控制系统")

            with gr.Row():
                with gr.Column(scale=2):
                    status_text = gr.Textbox(
                        label="当前状态", value="空闲", interactive=False, elem_classes=["status-box"]
                    )
                with gr.Column(scale=2):
                    queue_text = gr.Textbox(
                        label="执行队列", value="队列为空", interactive=False, elem_classes=["queue-box"]
                    )
                with gr.Column(scale=1):
                    progress_bar = gr.Slider(
                        label="打饭进度",
                        minimum=0,
                        maximum=100,
                        value=0,
                        step=1,
                        interactive=False,
                        show_label=True,
                    )

            # 菜单选择区域
            with gr.Column(elem_classes=["menu-section"]):
                gr.Markdown("## 📋 菜单点餐")
                gr.Markdown("为每个菜品选择份数，然后点击添加到队列")

                # 排骨
                with gr.Row():
                    with gr.Column(scale=1, min_width=150):
                        gr.Markdown("### 🍖 排骨")
                    with gr.Column(scale=2):
                        count_pg = gr.Number(
                            value=0, label="份数", minimum=0, maximum=10, step=1, precision=0
                        )

                # 番茄炒蛋
                with gr.Row():
                    with gr.Column(scale=1, min_width=150):
                        gr.Markdown("### 🍅 番茄炒蛋")
                    with gr.Column(scale=2):
                        count_xhs = gr.Number(
                            value=0, label="份数", minimum=0, maximum=10, step=1, precision=0
                        )

                # 土豆丝
                with gr.Row():
                    with gr.Column(scale=1, min_width=150):
                        gr.Markdown("### 🥔 土豆丝")
                    with gr.Column(scale=2):
                        count_td = gr.Number(
                            value=0, label="份数", minimum=0, maximum=10, step=1, precision=0
                        )

                with gr.Row():
                    add_btn = gr.Button("➕ 添加到队列", variant="secondary")
                    clear_btn = gr.Button("🗑️ 清空队列", variant="secondary")
                    start_queue_btn = gr.Button("▶️ 开始执行队列", variant="primary")

            # 快速按钮区域
            with gr.Column(elem_classes=["menu-section"]):
                gr.Markdown("## ⚡ 快速执行（单份）")

                with gr.Row():
                    btn_pg = gr.Button("🍖 排骨", variant="secondary", size="lg", elem_classes=["dish-btn"])
                    btn_xhs = gr.Button(
                        "🍅 番茄炒蛋", variant="secondary", size="lg", elem_classes=["dish-btn"]
                    )
                    btn_td = gr.Button("🥔 土豆丝", variant="secondary", size="lg", elem_classes=["dish-btn"])

            with gr.Row():
                stop_btn = gr.Button("🛑 停止", variant="stop", size="lg", elem_classes=["stop-btn"])

            result_text = gr.Textbox(label="执行结果", interactive=False)

            # 自动更新进度的定时器
            timer = gr.Timer(0.5, active=False)
            timer.tick(
                fn=self._update_progress,
                outputs=[status_text, queue_text, progress_bar],
            )

            # 菜单按钮事件
            add_btn.click(
                fn=self._add_batch_to_queue,
                inputs=[count_pg, count_xhs, count_td],
                outputs=[result_text, queue_text, progress_bar],
            )

            clear_btn.click(
                fn=self._clear_queue,
                outputs=[result_text, queue_text, progress_bar],
            )

            def start_with_timer():
                result = self.controller.start_queue_execution(fps=30)
                return (
                    result,
                    self.controller.get_status(),
                    self.controller.get_queue_status(),
                    0,
                    gr.Timer(active=True),
                )

            start_queue_btn.click(
                fn=start_with_timer,
                outputs=[result_text, status_text, queue_text, progress_bar, timer],
            )

            # 快速按钮事件
            btn_pg.click(
                fn=lambda: self._play_dish("排骨"),
                outputs=[result_text, status_text, queue_text, progress_bar],
            )

            btn_xhs.click(
                fn=lambda: self._play_dish("番茄炒蛋"),
                outputs=[result_text, status_text, queue_text, progress_bar],
            )

            btn_td.click(
                fn=lambda: self._play_dish("土豆丝"),
                outputs=[result_text, status_text, queue_text, progress_bar],
            )

            def stop_with_timer():
                result = self.controller.stop()
                return (
                    result,
                    self.controller.get_status(),
                    self.controller.get_queue_status(),
                    0,
                    gr.Timer(active=False),
                )

            stop_btn.click(
                fn=stop_with_timer,
                outputs=[result_text, status_text, queue_text, progress_bar, timer],
            )

        return demo

    def run(self):
        """Run the web UI"""
        if not GRADIO_AVAILABLE:
            print("Error: Gradio not available")
            return

        demo = self.create_ui()
        demo.launch(
            server_name=self.host,
            server_port=self.port,
            share=False,
        )


def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Motion Web UI for SO101 robot",
        epilog="""
Calibration file location:
  Default: ~/.cache/huggingface/lerobot/calibration/robots/so101_follower/

Examples:
  # Normal start (will calibrate if needed)
  python motion_web_ui.py

  # Skip calibration (use existing calibration in motor)
  python motion_web_ui.py -s

  # Use specific calibration file
  python motion_web_ui.py -c ~/.cache/huggingface/lerobot/calibration/robots/so101_follower/follower.json -s
        """,
    )
    parser.add_argument(
        "--log-dir", type=str, default="joint_logs", help="Directory containing JSON motion files"
    )
    parser.add_argument(
        "--calibration",
        "-c",
        type=str,
        default=None,
        help="Path to calibration JSON file (default: auto-detect)",
    )
    parser.add_argument(
        "--skip-calibration",
        "-s",
        action="store_true",
        help="Skip calibration process (use existing calibration)",
    )
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Server host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=7860, help="Server port (default: 7860)")

    args = parser.parse_args()

    # Create controller
    controller = MotionController(log_dir=args.log_dir, calibration_path=args.calibration)

    # Connect to robot
    if not controller.connect(skip_calibration=args.skip_calibration):
        print("Failed to connect to robot")
        return

    # Create and run web UI
    ui = MotionWebUI(controller, host=args.host, port=args.port)
    ui.run()


if __name__ == "__main__":
    main()
