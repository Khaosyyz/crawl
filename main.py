#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
爬虫系统主入口
"""

import os
import sys
import signal
import argparse
import subprocess
import time
from src.utils.log_handler import get_logger
from src.utils.scheduler_loop import start_scheduler, stop_scheduler
from src.crawlers.run_crawler import run_crawler
from src.clean.cleaner import start_cleaner

# 创建日志记录器
logger = get_logger("main")

# 记录启动的进程PID
SERVICE_PIDS = {}
PID_FILE = "service_pids.txt"

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="爬虫系统主入口")
    parser.add_argument("command", choices=["start", "stop", "status", "crawl", "clean"], 
                      help="命令: start-启动所有服务, stop-停止所有服务, status-查看状态, crawl-仅爬虫, clean-仅清洗")
    parser.add_argument("--crawler", type=str, 
                      choices=["x", "crunchbase", "all"], 
                      default="all", 
                      help="选择爬虫: x, crunchbase, all")
    return parser.parse_args()

def save_pid(service_name, pid):
    """保存服务PID"""
    SERVICE_PIDS[service_name] = pid
    with open(PID_FILE, 'a') as f:
        f.write(f"{service_name}:{pid}\n")
    logger.info(f"服务 {service_name} 已启动，PID: {pid}")

def load_pids():
    """加载已保存的PID"""
    if not os.path.exists(PID_FILE):
        return {}
    
    pids = {}
    try:
        with open(PID_FILE, 'r') as f:
            for line in f:
                if ':' in line:
                    service, pid = line.strip().split(':', 1)
                    pids[service] = int(pid)
    except Exception as e:
        logger.error(f"加载PID文件失败: {e}")
    
    return pids

def clear_pids():
    """清除PID文件"""
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    logger.info("已清除PID文件")

def is_process_running(pid):
    """检查进程是否运行中"""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def run_api_server():
    """运行API服务器"""
    logger.info("启动API服务器...")
    try:
        # 使用子进程启动API服务器
        api_process = subprocess.Popen(
            ["python3", "-m", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        save_pid("api", api_process.pid)
        return api_process.pid
    except Exception as e:
        logger.error(f"启动API服务器失败: {e}")
        return None

def start_services():
    """启动所有服务"""
    logger.info("正在启动所有服务...")
    
    # 清除旧的PID文件
    clear_pids()
    
    # 启动调度器
    logger.info("正在启动调度器...")
    scheduler_thread = start_scheduler()
    if scheduler_thread:
        save_pid("scheduler", os.getpid())  # 调度器在主进程中运行
    
    # 启动API服务
    api_pid = run_api_server()
    
    logger.info("所有服务已启动")
    
    # 保持主进程运行
    try:
        while True:
            time.sleep(5)
            # 检查子进程状态
            for service, pid in list(SERVICE_PIDS.items()):
                if not is_process_running(pid) and service != "scheduler":
                    logger.warning(f"服务 {service} (PID: {pid}) 已停止，正在重启...")
                    if service == "api":
                        api_pid = run_api_server()
            
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止所有服务...")
        stop_services()
    
    return True

def stop_services():
    """停止所有服务"""
    logger.info("正在停止所有服务...")
    
    # 加载已保存的PID
    pids = load_pids()
    for service, pid in pids.items():
        try:
            if is_process_running(pid):
                logger.info(f"停止服务 {service} (PID: {pid})...")
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
                # 检查是否真的停止了
                if is_process_running(pid):
                    logger.warning(f"服务 {service} 没有响应 SIGTERM，发送 SIGKILL...")
                    os.kill(pid, signal.SIGKILL)
        except Exception as e:
            logger.error(f"停止服务 {service} 时出错: {e}")
    
    # 清除PID文件
    clear_pids()
    logger.info("所有服务已停止")
    return True

def show_status():
    """显示服务状态"""
    logger.info("当前服务状态:")
    
    pids = load_pids()
    if not pids:
        logger.info("没有运行中的服务")
        return
    
    for service, pid in pids.items():
        status = "运行中" if is_process_running(pid) else "已停止"
        logger.info(f"  {service}: {status} (PID: {pid})")

def main():
    """主函数"""
    args = parse_args()
    
    if args.command == "start":
        start_services()
    elif args.command == "stop":
        stop_services()
    elif args.command == "status":
        show_status()
    elif args.command == "crawl":
        logger.info(f"启动爬虫: {args.crawler}")
        run_crawler(args.crawler)
    elif args.command == "clean":
        logger.info("启动数据清洗")
        start_cleaner()

if __name__ == "__main__":
    main() 