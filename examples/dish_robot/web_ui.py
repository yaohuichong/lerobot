import time
import threading

import gradio as gr

from dish_policy_manager import DishPolicyManager, DishType, DISH_CONFIGS


PRESET_MEALS = {
    "套餐一 (番茄鸡蛋+土豆丝)": [
        {"dish": "番茄鸡蛋菜品", "count": 1},
        {"dish": "土豆丝菜品", "count": 1},
    ],
    "套餐二 (排骨+番茄鸡蛋)": [
        {"dish": "排骨菜品", "count": 1},
        {"dish": "番茄鸡蛋菜品", "count": 1},
    ],
    "套餐三 (排骨+土豆丝)": [
        {"dish": "排骨菜品", "count": 1},
        {"dish": "土豆丝菜品", "count": 1},
    ],
    "套餐四 (排骨+番茄鸡蛋+土豆丝)": [
        {"dish": "排骨菜品", "count": 1},
        {"dish": "番茄鸡蛋菜品", "count": 1},
        {"dish": "土豆丝菜品", "count": 1},
    ],
}


class DishRobotWebUI:
    def __init__(
        self,
        policy_manager: DishPolicyManager,
        robot_controller,
        camera_provider,
        host: str = "0.0.0.0",
        port: int = 7860,
    ):
        self.policy_manager = policy_manager
        self.robot_controller = robot_controller
        self.camera_provider = camera_provider
        self.host = host
        self.port = port
        
        self.dish_options = {
            config.display_name: dish_type
            for dish_type, config in DISH_CONFIGS.items()
        }
        
        self.single_dish_options = {
            name: dish_type
            for name, dish_type in self.dish_options.items()
            if "麦仁" not in name
        }
    
    def _get_status(self) -> str:
        status = self.policy_manager.get_status()
        if status["is_executing"]:
            current_dish = status["current_dish"]
            if current_dish:
                for dt, cfg in DISH_CONFIGS.items():
                    if dt.value == current_dish:
                        return f"执行中: {cfg.display_name} (步数: {status['current_step']})"
                return f"执行中: {current_dish} (步数: {status['current_step']})"
        elif status["current_dish"]:
            current_dish = status["current_dish"]
            for dt, cfg in DISH_CONFIGS.items():
                if dt.value == current_dish:
                    return f"已选择: {cfg.display_name}"
            return f"已选择: {current_dish}"
        return "空闲"
    
    def _select_dish(self, dish_name: str) -> str:
        if dish_name not in self.dish_options:
            return "[ERROR] 请选择菜品"
        
        dish_type = self.dish_options[dish_name]
        if self.policy_manager.select_dish(dish_type):
            return f"[OK] 已选择: {dish_name}"
        else:
            return "[ERROR] 选择失败"
    
    def _start_episode(self, num_episodes: int, episode_time: float) -> str:
        status = self.policy_manager.get_status()
        if status["is_executing"]:
            return "[ERROR] 正在执行中"
        
        if not status["current_dish"]:
            return "[ERROR] 请先选择菜品"
        
        def observation_provider():
            return self.camera_provider.get_observation()
        
        def action_executor(action):
            self.robot_controller.execute_action(action)
        
        if self.policy_manager.start_episode(
            observation_provider=observation_provider,
            action_executor=action_executor,
            episode_time_s=episode_time,
            num_episodes=num_episodes,
            reset_smoother_callback=self.robot_controller.reset_smoother,
            start_logging_callback=getattr(self.robot_controller, 'start_logging', None),
            stop_logging_callback=getattr(self.robot_controller, 'stop_logging', None),
        ):
            return f"[OK] 开始执行 ({num_episodes} 次, 每次 {episode_time} 秒)"
        else:
            return "[ERROR] 启动失败"
    
    def _stop(self) -> str:
        self.policy_manager.stop()
        return "[OK] 已停止"
    
    def _start_preset(self, preset_name: str, episode_time: float) -> str:
        if preset_name not in PRESET_MEALS:
            return "[ERROR] 请选择套餐"
        
        status = self.policy_manager.get_status()
        if status["is_executing"]:
            return "[ERROR] 正在执行中"
        
        meal = PRESET_MEALS[preset_name]
        
        def run_preset():
            for item in meal:
                dish_name = item["dish"]
                count = item["count"]
                
                if dish_name not in self.dish_options:
                    print(f"[ERROR] 菜品不存在: {dish_name}")
                    continue
                
                dish_type = self.dish_options[dish_name]
                self.policy_manager.select_dish(dish_type)
                
                def observation_provider():
                    return self.camera_provider.get_observation()
                
                def action_executor(action):
                    self.robot_controller.execute_action(action)
                
                print(f"[套餐] 开始执行: {dish_name} x {count}")
                
                self.policy_manager.start_episode(
                    observation_provider=observation_provider,
                    action_executor=action_executor,
                    episode_time_s=episode_time,
                    num_episodes=count,
                    reset_smoother_callback=self.robot_controller.reset_smoother,
                    start_logging_callback=getattr(self.robot_controller, 'start_logging', None),
                    stop_logging_callback=getattr(self.robot_controller, 'stop_logging', None),
                )
                
                while self.policy_manager.get_status()["is_executing"]:
                    time.sleep(0.5)
                
                print(f"[套餐] 完成: {dish_name}")
                time.sleep(1.0)
            
            print(f"[套餐] 全部完成: {preset_name}")
        
        thread = threading.Thread(target=run_preset, daemon=True)
        thread.start()
        return f"[OK] 开始执行套餐: {preset_name}"
    
    def _start_single_dish(self, dish_name: str) -> str:
        if dish_name not in self.dish_options:
            return "[ERROR] 菜品不存在"
        
        status = self.policy_manager.get_status()
        if status["is_executing"]:
            return "[ERROR] 正在执行中"
        
        dish_type = self.dish_options[dish_name]
        self.policy_manager.select_dish(dish_type)
        
        def observation_provider():
            return self.camera_provider.get_observation()
        
        def action_executor(action):
            self.robot_controller.execute_action(action)
        
        self.policy_manager.start_episode(
            observation_provider=observation_provider,
            action_executor=action_executor,
            episode_time_s=12,
            num_episodes=2,
            reset_smoother_callback=self.robot_controller.reset_smoother,
            start_logging_callback=getattr(self.robot_controller, 'start_logging', None),
            stop_logging_callback=getattr(self.robot_controller, 'stop_logging', None),
        )
        return f"[OK] 开始执行: {dish_name} (2次)"
    
    def create_ui(self):
        css = """
        .gradio-container {
            max-width: 100% !important;
        }
        .dish-btn {
            min-height: 60px !important;
            font-size: 1.1em !important;
        }
        .preset-btn {
            min-height: 60px !important;
            font-size: 1.1em !important;
        }
        .stop-btn {
            min-height: 80px !important;
            font-size: 1.2em !important;
        }
        """
        
        with gr.Blocks(title="打饭机器人控制", theme=gr.themes.Soft(), css=css) as demo:
            gr.Markdown("# 🍚 打饭机器人控制系统")
            
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### 🍱 套餐")
                    preset_btns = {}
                    for preset_name in PRESET_MEALS.keys():
                        preset_btns[preset_name] = gr.Button(
                            preset_name, 
                            variant="primary", 
                            size="lg",
                            elem_classes=["preset-btn"]
                        )
                
                with gr.Column(scale=1):
                    gr.Markdown("### 🥘 单点")
                    dish_btns = {}
                    for dish_name in self.single_dish_options.keys():
                        dish_btns[dish_name] = gr.Button(
                            dish_name,
                            variant="secondary",
                            size="lg",
                            elem_classes=["dish-btn"]
                        )
            
            with gr.Row():
                with gr.Column(scale=2):
                    status_text = gr.Textbox(label="状态", value="空闲", interactive=False)
                with gr.Column(scale=1):
                    stop_btn = gr.Button("🛑 停止", variant="stop", size="lg", elem_classes=["stop-btn"])
            
            with gr.Accordion("⚙️ 调试设置", open=False):
                gr.Markdown("调试模式：可自定义菜品和轮次")
                with gr.Row():
                    with gr.Column():
                        debug_dish = gr.Dropdown(
                            choices=list(self.dish_options.keys()),
                            label="选择菜品",
                        )
                        debug_select_btn = gr.Button("选择菜品", variant="secondary")
                        debug_select_output = gr.Textbox(label="结果", interactive=False)
                    
                    with gr.Column():
                        debug_episodes = gr.Slider(1, 10, value=1, step=1, label="执行轮次")
                        debug_time = gr.Slider(5, 30, value=12, step=1, label="每次时长(秒)")
                        debug_start_btn = gr.Button("开始执行", variant="secondary")
                        debug_output = gr.Textbox(label="执行结果", interactive=False)
            
            action_output = gr.Textbox(label="执行结果", interactive=False)
            
            def update_status():
                return self._get_status()
            
            for preset_name, btn in preset_btns.items():
                btn.click(
                    fn=lambda pn=preset_name: self._start_preset(pn, 12),
                    inputs=[],
                    outputs=[action_output],
                ).then(fn=update_status, outputs=[status_text])
            
            for dish_name, btn in dish_btns.items():
                btn.click(
                    fn=lambda dn=dish_name: self._start_single_dish(dn),
                    inputs=[],
                    outputs=[action_output],
                ).then(fn=update_status, outputs=[status_text])
            
            stop_btn.click(
                fn=self._stop,
                outputs=[action_output],
            ).then(fn=update_status, outputs=[status_text])
            
            debug_select_btn.click(
                fn=self._select_dish,
                inputs=[debug_dish],
                outputs=[debug_select_output],
            ).then(fn=update_status, outputs=[status_text])
            
            debug_start_btn.click(
                fn=self._start_episode,
                inputs=[debug_episodes, debug_time],
                outputs=[debug_output],
            ).then(fn=update_status, outputs=[status_text])
        
        return demo
    
    def run(self):
        demo = self.create_ui()
        demo.launch(
            server_name=self.host,
            server_port=self.port,
            share=False,
        )
