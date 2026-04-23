DISH_CONFIGS = {
    "xhs": {
        "model_path": "/home/nvidia/model/scooping_model_xhs/pretrained_model",
        "display_name": "番茄鸡蛋菜品",
    },
    "pg": {
        "model_path": "/home/nvidia/model/scooping_model_pg/pretrained_model",
        "display_name": "排骨菜品",
    },
    "tds": {
        "model_path": "/home/nvidia/model/scooping_model_tds/pretrained_model",
        "display_name": "土豆丝菜品",
    },
    "mr_x": {
        "model_path": "/home/nvidia/model/scooping_model_mr_x/pretrained_model",
        "display_name": "麦仁菜品",
    },
}

DEVICE = "cuda"
USE_FP16 = False
FPS = 30
EPISODE_TIME_S = 12
NUM_EPISODES = 1
NUM_STEPS_PER_EPISODE = 500
WEB_HOST = "0.0.0.0"
WEB_PORT = 7860

ROBOT_PORT = "/dev/ttyCH343USB0"
ROBOT_MAX_RELATIVE_TARGET = 50.0
SMOOTHING_ALPHA = 0.5
