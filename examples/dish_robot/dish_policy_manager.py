import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable, Dict

import torch
from lerobot.policies.act.modeling_act import ACTPolicy
from lerobot.utils.robot_utils import busy_wait

try:
    from config import DISH_CONFIGS as _DISH_CONFIGS_DICT, DEVICE, USE_FP16, FPS, EPISODE_TIME_S, NUM_STEPS_PER_EPISODE
except ImportError:
    _DISH_CONFIGS_DICT = {
        "xhs": {
            "model_path": "/home/nvidia/model/scooping_model_xhs/pretrained_model",
            "display_name": "番茄炒蛋菜品",
        },
        "pg": {
            "model_path": "/home/nvidia/model/scooping_model_pg/pretrained_model",
            "display_name": "排骨菜品",
        },
    }
    DEVICE = "cuda"
    USE_FP16 = False
    FPS = 30
    EPISODE_TIME_S = 12
    NUM_STEPS_PER_EPISODE = 500


DishType = Enum(
    "DishType",
    {dish_id.upper(): dish_id for dish_id in _DISH_CONFIGS_DICT.keys()},
)


@dataclass
class DishConfig:
    name: str
    model_path: str
    display_name: str


DISH_CONFIGS: Dict[DishType, DishConfig] = {}
for dish_id, cfg in _DISH_CONFIGS_DICT.items():
    dish_type = DishType[dish_id.upper()]
    DISH_CONFIGS[dish_type] = DishConfig(
        name=dish_id,
        model_path=cfg["model_path"],
        display_name=cfg["display_name"],
    )


class DishPolicyManager:
    def __init__(
        self,
        dish_configs: Dict[DishType, DishConfig],
        device: str = "cuda",
        use_fp16: bool = False,
        fps: int = 30,
        episode_time_s: float = 12,
        num_steps_per_episode: int = 500,
    ):
        self.device = device
        self.use_fp16 = use_fp16
        self.fps = fps
        self.episode_time_s = episode_time_s
        self.num_steps_per_episode = num_steps_per_episode
        self.dish_configs = dish_configs
        
        self.policies: Dict[DishType, ACTPolicy] = {}
        self.current_dish: Optional[DishType] = None
        self.is_executing = False
        self.execution_lock = threading.Lock()
        self._stop_flag = False
        self._current_step = 0
        self._total_steps = 0
        self._episode_count = 0
        
        self._load_all_policies()
    
    def _load_all_policies(self):
        print("=" * 50)
        print("Loading all dish policies...")
        print("=" * 50)
        
        for dish_type, config in self.dish_configs.items():
            print(f"Loading {config.display_name}...")
            print(f"  Path: {config.model_path}")
            policy = ACTPolicy.from_pretrained(config.model_path)
            
            if self.use_fp16:
                policy = policy.half()
            
            policy.to(self.device)
            policy.eval()
            self.policies[dish_type] = policy
            print(f"[OK] {config.display_name} loaded")
        
        print("=" * 50)
        print(f"All policies loaded! Total: {len(self.policies)}")
        print("=" * 50)
    
    def select_dish(self, dish_type: DishType) -> bool:
        with self.execution_lock:
            if self.is_executing:
                return False
            
            if dish_type not in self.policies:
                print(f"[ERROR] Unknown dish: {dish_type}")
                return False
            
            self.current_dish = dish_type
            self.policies[dish_type].reset()
            print(f"[OK] Selected: {self.dish_configs[dish_type].display_name}")
            return True
    
    def start_episode(
        self,
        observation_provider: Callable[[], dict],
        action_executor: Callable[[torch.Tensor], None],
        episode_time_s: Optional[float] = None,
        num_episodes: int = 1,
        reset_smoother_callback: Optional[Callable[[], None]] = None,
        start_logging_callback: Optional[Callable[[str], None]] = None,
        stop_logging_callback: Optional[Callable[[], None]] = None,
    ):
        with self.execution_lock:
            if self.is_executing:
                return False
            
            if self.current_dish is None:
                print("No dish selected!")
                return False
            
            self.is_executing = True
            self._stop_flag = False
        
        if episode_time_s is None:
            episode_time_s = self.episode_time_s
        
        def _run():
            try:
                policy = self.policies[self.current_dish]
                dish_name = self.dish_configs[self.current_dish].display_name
                
                for episode_idx in range(num_episodes):
                    if self._stop_flag:
                        break
                    
                    print(f"\nEpisode {episode_idx + 1}/{num_episodes}")
                    
                    if start_logging_callback:
                        start_logging_callback(f"{dish_name}_ep{episode_idx + 1}")
                    
                    policy.reset()
                    if reset_smoother_callback:
                        reset_smoother_callback()
                    
                    step = 0
                    start_t = time.perf_counter()
                    timestamp = 0.0
                    first_action_printed = False
                    
                    
                    while timestamp < episode_time_s and not self._stop_flag:
                        start_loop_t = time.perf_counter()
                        
                        try:
                            observation = observation_provider()
                            if observation is None:
                                time.sleep(0.001)
                                continue
                            
                            
                            
                            if self.use_fp16:
                                observation = {
                                    k: v.half() if v.dtype == torch.float32 else v
                                    for k, v in observation.items()
                                }
                            
                            with torch.inference_mode():
                                action = policy.select_action(observation)
                            
                            if action is None:
                                break
                            
                            if not first_action_printed:
                                action_np = action.squeeze(0).cpu().numpy()
                                print(f"[DEBUG] First action: {action_np[:3].round(2)}...")
                                first_action_printed = True
                            
                            action_executor(action)
                            step += 1
                            self._current_step = step
                        except Exception as e:
                            print(f"[ERROR] Step {step}: {e}")
                            break
                        
                        dt_s = time.perf_counter() - start_loop_t
                        busy_wait(1.0 / self.fps - dt_s)
                        timestamp = time.perf_counter() - start_t
                    
                    elapsed = time.perf_counter() - start_t
                    self._episode_count += 1
                    print(f"Episode finished: {step} steps, {elapsed:.1f}s")
                    
                    if stop_logging_callback:
                        stop_logging_callback()
                    
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    
                    
                    
                    if reset_smoother_callback is not None:
                        reset_smoother_callback()
                    
                    if episode_idx < num_episodes - 1:
                        print("Waiting before next episode...")
                        time.sleep(2.0)
                
                print(f"\nAll episodes finished: {num_episodes} episodes")
            
            finally:
                with self.execution_lock:
                    self.is_executing = False
        
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return True
    
    def stop(self):
        self._stop_flag = True
    
    def get_status(self) -> dict:
        with self.execution_lock:
            return {
                "is_executing": self.is_executing,
                "current_dish": self.current_dish.value if self.current_dish else None,
                "current_step": self._current_step,
                "episode_count": self._episode_count,
            }


def get_dish_type_by_value(value: str) -> Optional[DishType]:
    for dish_type in DishType:
        if dish_type.value == value:
            return dish_type
    return None
