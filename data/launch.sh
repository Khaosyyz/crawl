#!/bin/bash

# 确保在脚本出错时退出
set -e

# 定义日志文件
LOG_DIR="logs"
STARTUP_LOG="$LOG_DIR/startup.log"

# 确保日志目录存在
mkdir -p $LOG_DIR

# 记录启动时间
echo "=======================================" >> $STARTUP_LOG
echo "启动时间: $(date)" >> $STARTUP_LOG
echo "=======================================" >> $STARTUP_LOG

# 检查Python环境
echo "检查Python环境..." >> $STARTUP_LOG
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到python3命令" | tee -a $STARTUP_LOG
    exit 1
fi

# 检查虚拟环境
VENV_DIR="venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "创建Python虚拟环境..." | tee -a $STARTUP_LOG
    python3 -m venv $VENV_DIR
    source $VENV_DIR/bin/activate
    pip install --upgrade pip
    pip install selenium openai flask pytz
else
    source $VENV_DIR/bin/activate
fi

# 确保目录结构存在
mkdir -p crawlers

# 启动数据清洗服务（持续运行）
start_cleaner() {
    echo "启动数据清洗服务..." | tee -a $STARTUP_LOG
    nohup python3 cleandata.py > $LOG_DIR/cleaner.log 2>&1 &
    CLEANER_PID=$!
    echo "数据清洗服务已启动，PID: $CLEANER_PID" | tee -a $STARTUP_LOG

    # 将PID保存到文件，以便后续可以停止服务
    echo $CLEANER_PID > $LOG_DIR/cleaner.pid
}

# 启动Web API服务
start_api() {
    echo "启动Web API服务..." | tee -a $STARTUP_LOG
    nohup python3 api.py > $LOG_DIR/api.log 2>&1 &
    API_PID=$!
    echo "Web API服务已启动，PID: $API_PID" | tee -a $STARTUP_LOG

    # 将PID保存到文件，以便后续可以停止服务
    echo $API_PID > $LOG_DIR/api.pid
}

# 设置定时爬虫任务
setup_cron() {
    echo "设置定时爬虫任务..." | tee -a $STARTUP_LOG

    # 创建临时crontab文件
    TEMP_CRON=$(mktemp)

    # 导出当前crontab内容
    crontab -l > $TEMP_CRON 2>/dev/null || true

    # 检查爬虫任务是否已存在
    if ! grep -q "crawlers/x.py" $TEMP_CRON; then
        # 添加爬虫任务 - 每3小时运行一次X爬虫
        echo "0 */3 * * * cd $(pwd) && $VENV_DIR/bin/python3 -m crawlers.x > $LOG_DIR/x_crawler_\$(date +\%Y\%m\%d\%H\%M\%S).log 2>&1" >> $TEMP_CRON
        # 应用新的crontab设置
        crontab $TEMP_CRON
        echo "已添加X爬虫的定时任务(每3小时执行一次)" | tee -a $STARTUP_LOG
    else
        echo "X爬虫的定时任务已存在，跳过" | tee -a $STARTUP_LOG
    fi

    # 删除临时文件
    rm $TEMP_CRON
}

# 停止所有服务
stop_services() {
    echo "正在停止所有服务..." | tee -a $STARTUP_LOG

    # 停止清洗服务
    if [ -f "$LOG_DIR/cleaner.pid" ]; then
        CLEANER_PID=$(cat $LOG_DIR/cleaner.pid)
        if kill -0 $CLEANER_PID 2>/dev/null; then
            kill $CLEANER_PID
            echo "已停止数据清洗服务(PID: $CLEANER_PID)" | tee -a $STARTUP_LOG
        else
            echo "数据清洗服务(PID: $CLEANER_PID)已不在运行" | tee -a $STARTUP_LOG
        fi
        rm $LOG_DIR/cleaner.pid
    fi

    # 停止API服务
    if [ -f "$LOG_DIR/api.pid" ]; then
        API_PID=$(cat $LOG_DIR/api.pid)
        if kill -0 $API_PID 2>/dev/null; then
            kill $API_PID
            echo "已停止Web API服务(PID: $API_PID)" | tee -a $STARTUP_LOG
        else
            echo "Web API服务(PID: $API_PID)已不在运行" | tee -a $STARTUP_LOG
        fi
        rm $LOG_DIR/api.pid
    fi
}

# 运行爬虫（用于测试）
run_crawler() {
    echo "正在运行X爬虫进行测试..." | tee -a $STARTUP_LOG
    python3 -m crawlers.x
    echo "X爬虫测试运行完成" | tee -a $STARTUP_LOG
}

# 显示使用说明
show_usage() {
    echo "使用方法: $0 [命令]"
    echo "命令:"
    echo "  start     - 启动所有服务(清洗服务和API)"
    echo "  stop      - 停止所有服务"
    echo "  restart   - 重启所有服务"
    echo "  cron      - 只设置定时爬虫任务"
    echo "  crawler   - 手动运行一次爬虫(测试用)"
    echo "  cleaner   - 只启动数据清洗服务"
    echo "  api       - 只启动Web API服务"
}

# 根据命令行参数执行相应操作
case "$1" in
    start)
        stop_services  # 先停止已有服务
        start_cleaner
        start_api
        setup_cron
        echo "所有服务已启动" | tee -a $STARTUP_LOG
        ;;
    stop)
        stop_services
        echo "所有服务已停止" | tee -a $STARTUP_LOG
        ;;
    restart)
        stop_services
        sleep 2
        start_cleaner
        start_api
        echo "所有服务已重启" | tee -a $STARTUP_LOG
        ;;
    cron)
        setup_cron
        ;;
    crawler)
        run_crawler
        ;;
    cleaner)
        if [ -f "$LOG_DIR/cleaner.pid" ]; then
            CLEANER_PID=$(cat $LOG_DIR/cleaner.pid)
            if kill -0 $CLEANER_PID 2>/dev/null; then
                echo "数据清洗服务已在运行中(PID: $CLEANER_PID)" | tee -a $STARTUP_LOG
                exit 0
            fi
        fi
        start_cleaner
        ;;
    api)
        if [ -f "$LOG_DIR/api.pid" ]; then
            API_PID=$(cat $LOG_DIR/api.pid)
            if kill -0 $API_PID 2>/dev/null; then
                echo "Web API服务已在运行中(PID: $API_PID)" | tee -a $STARTUP_LOG
                exit 0
            fi
        fi
        start_api
        ;;
    *)
        show_usage
        ;;
esac

exit 0