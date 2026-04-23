# 打饭机器人控制系统

双菜品ACT模型预加载 + Web可视化控制界面

## 概念说明

### Episode vs 步数

| 概念 | 说明 |
|------|------|
| **Episode** | 完整的一次打饭过程 |
| **步数** | 控制循环次数，每步执行一次动作 |
| **FPS** | 每秒执行步数（默认30） |
| **Episode时长** | 每次打饭的最大时间（默认60秒） |

### ACT Action Chunking

ACT使用Action Chunking机制：
- **一次推理** 预测 `chunk_size` 个动作（默认100）
- **逐步执行** 每步从队列中取出一个动作执行
- **推理频率** 约每 `n_action_steps` 步推理一次

## 文件结构

```
dish_robot/
├── config.py              # 配置文件 (修改这里添加新菜品)
├── dish_policy_manager.py # 策略管理器
├── web_ui.py              # Web界面
├── run_dish_robot.py      # 启动脚本
└── README.md              # 说明文档
```

## 快速开始

### 1. 修改配置

编辑 `config.py`:

```python
DISH_CONFIGS = {
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
USE_FP16 = True
FPS = 30
EPISODE_TIME_S = 60
NUM_EPISODES = 2
WEB_HOST = "0.0.0.0"
WEB_PORT = 7860
```

### 2. 安装依赖

```bash
pip install gradio
```

### 3. 启动系统

```bash
cd /home/nvidia/lerobot/examples/dish_robot
python run_dish_robot.py real
```

### 4. 访问界面

**公网访问 (扫码直达)**: https://savanna-unslatted-rosenda.ngrok-free.app

**内网访问**: http://192.168.0.16:7860

**Tailscale**: http://100.72.90.23:7860

> 公网地址每次重启ngrok会变化，运行 `python get_public_url.py` 获取最新地址和二维码

## 使用说明

1. **选择菜品**: 点击单选按钮选择要打的菜品
2. **确认选择**: 点击"确认选择"按钮
3. **设置参数**: Episode次数和时长
4. **开始执行**: 点击"开始执行"
5. **停止执行**: 执行过程中可点击"停止执行"

**注意**: 动作执行过程中无法切换菜品

---

## 添加新菜品

只需修改 `config.py` 文件即可，无需修改其他代码！

### 示例：添加酸辣土豆丝

```python
DISH_CONFIGS = {
    "xhs": {
        "model_path": "/home/nvidia/model/scooping_model_xhs/pretrained_model",
        "display_name": "番茄炒蛋菜品",
    },
    "pg": {
        "model_path": "/home/nvidia/model/scooping_model_pg/pretrained_model",
        "display_name": "排骨菜品",
    },
    # 添加新菜品
    "tds": {
        "model_path": "/home/nvidia/model/scooping_model_tds/pretrained_model",
        "display_name": "酸辣土豆丝",
    },
}
```

### 添加步骤

1. 训练新菜品模型
2. 保存到 `/home/nvidia/model/scooping_model_xxx/pretrained_model/`
3. 在 `config.py` 的 `DISH_CONFIGS` 中添加新条目
4. 重启系统

### 注意事项

- 菜品ID使用小写字母（如 `"tds"`）
- 每增加一个模型约占用 100-150MB 内存（FP16）
- 8GB Orin NX 建议最多 4-5 个模型

---

## 内存预算 (8GB Orin NX)

| 组件 | 内存占用 |
|------|---------|
| PyTorch运行时 | ~1.5GB |
| CUDA上下文 | ~0.5GB |
| ACT模型 x 2 (FP16) | ~0.3GB |
| 图像缓存 | ~0.3GB |
| **剩余可用** | **~5.4GB** |

## 故障排除

### 内存不足

1. 确保使用FP16: `USE_FP16 = True`
2. 关闭其他占用GPU的程序
3. 减少菜品数量

### 模型加载失败

1. 检查模型路径是否正确
2. 确保 `pretrained_model` 目录下有 `config.json` 和 `model.safetensors`

### Web界面无法访问

1. 检查防火墙设置
2. 确认Jetson和电脑在同一网络
