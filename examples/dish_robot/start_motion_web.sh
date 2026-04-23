#!/bin/bash

# 打饭机器人动作控制网页启动脚本
# 菜品映射：排骨=1，番茄炒蛋=2，土豆丝=3

cd "$(dirname "$0")"

# 默认参数
HOST="0.0.0.0"
PORT=7860
CALIBRATION=""
SKIP_CALIBRATION=""

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -c|--calibration)
            CALIBRATION="-c $2"
            shift 2
            ;;
        -s|--skip-calibration)
            SKIP_CALIBRATION="-s"
            shift
            ;;
        -p|--port)
            PORT=$2
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  -c, --calibration <path>  校准文件路径"
            echo "  -s, --skip-calibration    跳过校准，从文件加载"
            echo "  -p, --port <port>         端口号 (默认: 7860)"
            echo "  -h, --help                显示帮助"
            echo ""
            echo "Examples:"
            echo "  $0                                    # 正常启动，自动检测校准"
            echo "  $0 -c ~/calibration.json -s          # 使用指定校准文件启动"
            echo "  $0 -s                                # 跳过校准（使用已有校准）"
            echo "  $0 -p 8080                           # 使用8080端口"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "======================================"
echo "  打饭机器人动作控制系统"
echo "======================================"
echo ""
echo "菜品列表："
echo "  🍖 排骨"
echo "  🍅 番茄炒蛋"
echo "  🥔 土豆丝"
echo ""
echo "功能说明："
echo "  📋 菜单点餐 - 为每个菜品选择份数（支持手动输入）"
echo "  ➕ 添加到队列 - 将选择的菜品添加到执行队列"
echo "  ▶️ 开始执行 - 按队列顺序执行，显示打饭进度"
echo "  🗑️ 清空队列 - 清空待执行队列"
echo "  ⚡ 快速执行 - 直接执行单份菜品"
echo ""
echo "网页地址: http://localhost:${PORT}"
echo "======================================"
echo ""

python motion_web_ui.py --host ${HOST} --port ${PORT} ${CALIBRATION} ${SKIP_CALIBRATION}
