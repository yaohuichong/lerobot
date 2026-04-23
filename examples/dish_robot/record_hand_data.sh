#!/bin/bash

# SOArm101 + AmazingHand 数据采集脚本
# 使用lerobot原生的record功能

# 配置端口
FOLLOWER_PORT="/dev/ttyCH343USB0"
LEADER_PORT="/dev/ttyCH343USB1"
HAND_PORT="/dev/ttyCH343USB2"

# 配置数据集
DATASET_NAME="hand_grasp_demo"
DATASET_ROOT="/home/nvidia/data"
NUM_EPISODES=10
EPISODE_TIME=30
TASK="Grasp object with dexterous hand"

# 运行lerobot-record
lerobot-record \
  --robot.type=so101_follower \
  --robot.port=$FOLLOWER_PORT \
  --robot.id=follower \
  --robot.cameras='{
    handeye: {"type": "opencv", "index_or_path": "/dev/video0", "width": 640, "height": 480, "fps": 30}
  }' \
  --teleop.type=so101_leader_with_hand \
  --teleop.port=$LEADER_PORT \
  --teleop.hand_port=$HAND_PORT \
  --teleop.id=leader_with_hand \
  --dataset.repo_id=local/$DATASET_NAME \
  --dataset.root=$DATASET_ROOT \
  --dataset.num_episodes=$NUM_EPISODES \
  --dataset.episode_time_s=$EPISODE_TIME \
  --dataset.single_task="$TASK" \
  --dataset.push_to_hub=false \
  --display_data=true
