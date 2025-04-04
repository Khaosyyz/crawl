#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import json
import threading
import traceback
import importlib
import schedule
from datetime import datetime
from src.utils.log_handler import get_logger

# 创建日志记录器
logger = get_logger("scheduler")

# 配置文件路径
CONFIG_FILE = 'src/config/schedule_config.json'

def load_config():
    """加载调度配置"""
    try:
        if not os.path.exists(CONFIG_FILE):
            logger.warning(f"配置文件不存在: {CONFIG_FILE}，使用默认配置")
            return get_default_config()
        
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            logger.info(f"成功加载配置文件: {CONFIG_FILE}")
            return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {str(e)}")
        return get_default_config()

def get_default_config():
    """获取默认调度配置"""
    return {
        "crawler": {
            "x": {"interval": "3h", "enabled": True},
            "crunchbase": {"interval": "12h", "enabled": True}
        },
        "cleaner": {
            "interval": "1m",
            "enabled": True
        }
    }

def save_config(config):
    """保存配置到文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        logger.info(f"配置已保存到: {CONFIG_FILE}")
    except Exception as e:
        logger.error(f"保存配置失败: {str(e)}")

def run_task(task_name, module_path, func_name, *args, **kwargs):
    """运行指定的任务"""
    try:
        logger.info(f"开始执行任务: {task_name}")
        
        # 动态导入模块并执行函数
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        result = func(*args, **kwargs)
        
        logger.info(f"任务执行完成: {task_name}, 结果: {result}")
        return result
    except Exception as e:
        error_msg = f"任务执行失败: {task_name}, 错误: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return False

def run_x_crawler():
    """运行X爬虫"""
    return run_task("X爬虫", "src.crawlers.run_crawler", "run_crawler", "x")

def run_crunchbase_crawler():
    """运行Crunchbase爬虫"""
    return run_task("Crunchbase爬虫", "src.crawlers.run_crawler", "run_crawler", "crunchbase")

def run_cleaner():
    """运行数据清洗"""
    return run_task("数据清洗", "src.clean.cleaner", "start_cleaner")

def run_logs_cleaner():
    """运行日志清理"""
    return run_task("日志清理", "logs.clean_logs", "start_logs_cleaner")

def schedule_job(name, task_func, interval_str):
    """安排定时任务，使用间隔时间"""
    # 解析间隔时间字符串
    if interval_str.endswith('m'):
        minutes = int(interval_str[:-1])
        schedule.every(minutes).minutes.do(task_func).tag(name)
        interval_desc = f"每{minutes}分钟"
    elif interval_str.endswith('h'):
        hours = int(interval_str[:-1])
        schedule.every(hours).hours.do(task_func).tag(name)
        interval_desc = f"每{hours}小时"
    elif interval_str.endswith('d'):
        days = int(interval_str[:-1])
        schedule.every(days).days.do(task_func).tag(name)
        interval_desc = f"每{days}天"
    else:
        # 向下兼容旧版本的时间点格式
        times = [t.strip() for t in interval_str.split(',')]
        for t in times:
            schedule.every().day.at(t).do(task_func).tag(name)
        interval_desc = f"每天的 {interval_str}"
    
    logger.info(f"已安排任务 {name} 执行频率: {interval_desc}")

def setup_schedule(config):
    """设置所有调度任务"""
    # 清除现有调度
    schedule.clear()
    
    # 设置爬虫调度
    crawler_config = config.get("crawler", {})
    if crawler_config.get("x", {}).get("enabled", False):
        interval = crawler_config["x"].get("interval", "3h")
        schedule_job("x_crawler", run_x_crawler, interval)
        # 首次运行
        run_x_crawler()
    
    if crawler_config.get("crunchbase", {}).get("enabled", False):
        interval = crawler_config["crunchbase"].get("interval", "12h")
        schedule_job("crunchbase_crawler", run_crunchbase_crawler, interval)
        # 首次运行
        run_crunchbase_crawler()
    
    # 设置清洗调度
    cleaner_config = config.get("cleaner", {})
    if cleaner_config.get("enabled", False):
        interval = cleaner_config.get("interval", "1m")
        schedule_job("cleaner", run_cleaner, interval)
        # 首次运行
        run_cleaner()
    
    # 设置日志清理调度
    logs_cleaner_config = config.get("logs_cleaner", {})
    if logs_cleaner_config.get("enabled", False):
        interval = logs_cleaner_config.get("interval", "24h")
        schedule_job("logs_cleaner", run_logs_cleaner, interval)
        # 首次运行
        run_logs_cleaner()
    
    logger.info("调度任务设置完成")

def run_pending_jobs():
    """运行待处理的作业"""
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到中断信号，停止调度")
            break
        except Exception as e:
            logger.error(f"调度运行错误: {str(e)}")
            logger.error(traceback.format_exc())
            time.sleep(5)  # 出错后等待一段时间再继续

def print_schedule_status():
    """打印当前调度状态"""
    jobs = schedule.get_jobs()
    logger.info(f"当前共有 {len(jobs)} 个调度任务:")
    
    for job in jobs:
        next_run = job.next_run
        if next_run:
            time_diff = next_run - datetime.now()
            hours, remainder = divmod(time_diff.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            time_to_run = f"{hours}小时{minutes}分钟{seconds}秒后"
        else:
            time_to_run = "未安排"
            
        tag_name = "未命名"
        if job.tags:
            tag_name = next(iter(job.tags))
            
        logger.info(f"  - {tag_name}: 下次运行在 {time_to_run}")

def start_scheduler():
    """启动调度器"""
    try:
        config = load_config()
        setup_schedule(config)
        print_schedule_status()
        
        scheduler_thread = threading.Thread(target=run_pending_jobs, daemon=True)
        scheduler_thread.start()
        
        logger.info("调度器已启动")
        return scheduler_thread
    except Exception as e:
        logger.error(f"启动调度器失败: {str(e)}")
        logger.error(traceback.format_exc())
        return None

def stop_scheduler(thread):
    """停止调度器"""
    if thread and thread.is_alive():
        thread.join(timeout=1)
        logger.info("调度器已停止")

def update_schedule_config(module, name, field, value):
    """更新调度配置"""
    config = load_config()
    
    if module not in config:
        config[module] = {}
    
    if name and name not in config[module]:
        config[module][name] = {}
    
    if name:
        config[module][name][field] = value
    else:
        config[module][field] = value
    
    save_config(config)
    return config

if __name__ == "__main__":
    logger.info("直接启动调度器")
    thread = start_scheduler()
    
    try:
        # 保持主线程运行
        while thread and thread.is_alive():
            time.sleep(60)
            print_schedule_status()
    except KeyboardInterrupt:
        logger.info("收到中断信号，退出程序")
    finally:
        stop_scheduler(thread) 