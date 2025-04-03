#!/bin/bash

# 项目启动脚本
# 用于启动各种服务组件或执行常见命令

# 退出时清理进程
trap 'cleanup' EXIT

# 获取脚本所在目录作为项目根目录
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$PROJECT_ROOT"

# 定义日志颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # 重置颜色

# 创建日志和数据目录
mkdir -p logs
mkdir -p src/data

# 清理函数，用于捕获退出信号
cleanup() {
    echo -e "${YELLOW}正在清理进程...${NC}"
    if [ -n "$PROCESS_PID" ]; then
        kill $PROCESS_PID 2>/dev/null
        echo -e "${GREEN}已停止进程${NC}"
    fi
    echo -e "${GREEN}清理完成${NC}"
}

# 显示帮助信息
show_help() {
    echo -e "${BLUE}AI 新闻爬虫与数据清洗系统${NC}"
    echo "用法: $0 [命令]"
    echo ""
    echo "可用命令:"
    echo "  start                    启动所有服务"
    echo "  stop                     停止所有服务"
    echo "  status                   查看服务状态"
    echo "  crawler [x|crunchbase]   运行爬虫 (可选择特定爬虫)"
    echo "  cleaner                  运行数据清洗"
    echo "  help                     显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 start                 启动所有服务"
    echo "  $0 stop                  停止所有服务"
    echo "  $0 crawler x             运行X爬虫"
    echo "  $0 cleaner               运行数据清洗器"
}

# 根据命令执行对应操作
case "$1" in
    start)
        echo -e "${GREEN}启动所有服务...${NC}"
        python3 main.py start
        ;;
    stop)
        echo -e "${GREEN}停止所有服务...${NC}"
        python3 main.py stop
        ;;
    status)
        echo -e "${GREEN}查看服务状态...${NC}"
        python3 main.py status
        ;;
    crawler)
        if [ -z "$2" ]; then
            echo -e "${GREEN}运行所有爬虫...${NC}"
            python3 main.py crawl
        else
            echo -e "${GREEN}运行 $2 爬虫...${NC}"
            python3 main.py crawl --crawler $2
        fi
        ;;
    cleaner)
        echo -e "${GREEN}运行数据清洗...${NC}"
        python3 main.py clean
        ;;
    help|*)
        show_help
        ;;
esac

exit 0