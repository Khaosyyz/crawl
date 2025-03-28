"""
通用日志处理模块
提供按天分割日志文件功能，并自动删除超过24小时的旧日志
"""

import os
import glob
import logging
from logging.handlers import TimedRotatingFileHandler
import time
from threading import Lock, Thread
import datetime

# 全局锁用于保护日志清理操作
log_cleanup_lock = Lock()

class DailyLogHandler(TimedRotatingFileHandler):
    """按天滚动的日志处理器，扩展TimedRotatingFileHandler
    自动删除超过保留天数的日志文件
    """
    
    def __init__(self, filename, when='midnight', interval=1, backupCount=1, encoding='utf-8'):
        """初始化日志处理器
        filename: 日志文件路径
        when: 滚动时间点，默认为midnight表示每天凌晨
        interval: 滚动间隔，默认为1表示每天
        backupCount: 保留的备份数量，默认为1表示只保留当天和前一天的日志
        encoding: 文件编码
        """
        # 确保日志目录存在
        log_dir = os.path.dirname(filename)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            
        super().__init__(
            filename=filename,
            when=when,
            interval=interval,
            backupCount=backupCount,
            encoding=encoding,
            utc=False
        )
        
        # 在初始化时执行一次清理
        self.cleanup_logs(log_dir)
    
    def cleanup_logs(self, log_dir):
        """清理旧的日志文件"""
        with log_cleanup_lock:
            try:
                # 获取当前时间
                now = time.time()
                cutoff = now - (24 * 3600)  # 24小时前的时间戳
                
                # 获取所有日志文件
                log_files = glob.glob(os.path.join(log_dir, "*.log*"))
                
                # 删除超过24小时的日志文件
                for log_file in log_files:
                    # 跳过当前使用的日志文件
                    if log_file == self.baseFilename:
                        continue
                        
                    # 获取文件的修改时间
                    mtime = os.path.getmtime(log_file)
                    if mtime < cutoff:
                        try:
                            os.remove(log_file)
                            print(f"已删除旧日志文件: {log_file}")
                        except (OSError, IOError) as e:
                            print(f"删除日志文件 {log_file} 失败: {e}")
                            
            except Exception as e:
                print(f"清理日志文件时出错: {e}")


def setup_logger(name, log_file, level=logging.INFO, console_output=True):
    """配置一个日志记录器，使用DailyLogHandler
    
    参数:
    name: 日志记录器名称
    log_file: 日志文件路径
    level: 日志级别
    console_output: 是否同时输出到控制台
    
    返回:
    配置好的日志记录器
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 清除已有的handler
    if logger.handlers:
        logger.handlers.clear()
    
    # 配置格式
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # 文件处理器 - 按天滚动
    file_handler = DailyLogHandler(
        filename=log_file,
        when='midnight',
        interval=1,
        backupCount=1  # 保留最近1天的日志（再加上当天的）
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # 控制台处理器
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger


def start_log_cleanup_thread(log_dir, interval=3600):
    """启动一个周期性清理日志的后台线程
    
    参数:
    log_dir: 日志目录
    interval: 清理间隔，单位为秒，默认1小时
    """
    def cleanup_thread():
        while True:
            try:
                # 获取当前时间
                now = time.time()
                cutoff = now - (24 * 3600)  # 24小时前的时间戳
                
                with log_cleanup_lock:
                    # 获取所有日志文件
                    log_files = []
                    for root, _, files in os.walk(log_dir):
                        for file in files:
                            if file.endswith(".log") or ".log." in file:
                                log_files.append(os.path.join(root, file))
                    
                    # 删除超过24小时的日志文件
                    for log_file in log_files:
                        # 获取文件的修改时间
                        mtime = os.path.getmtime(log_file)
                        if mtime < cutoff:
                            try:
                                os.remove(log_file)
                                print(f"定时清理 - 已删除旧日志文件: {log_file}")
                            except (OSError, IOError) as e:
                                print(f"定时清理 - 删除日志文件 {log_file} 失败: {e}")
                
                # 等待下一次清理
                time.sleep(interval)
                
            except Exception as e:
                print(f"日志清理线程出错: {e}")
                time.sleep(60)  # 出错后等待1分钟再试
    
    # 创建后台线程
    thread = Thread(target=cleanup_thread, daemon=True)
    thread.start()
    print(f"日志清理线程已启动，每 {interval} 秒清理一次超过24小时的日志文件")
    return thread 