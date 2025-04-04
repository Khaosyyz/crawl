#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
日志清理脚本 - 用于定期清空logs目录下的所有日志文件
"""

import os
import time
import shutil
import datetime
from src.utils.log_handler import get_logger
from src.utils.paths import LOGS_DIR

# 创建日志记录器
logger = get_logger("logs_cleaner")

def clean_logs():
    """
    清空logs目录下的所有日志文件，但保留当前日志文件
    """
    try:
        logger.info("开始清理日志文件...")
        
        # 获取当前脚本的日志文件路径
        current_log_file = os.path.join(LOGS_DIR, "logs_cleaner.log")
        
        # 记录开始清理前的状态
        total_size_before = 0
        file_count_before = 0
        
        for filename in os.listdir(LOGS_DIR):
            file_path = os.path.join(LOGS_DIR, filename)
            if os.path.isfile(file_path) and filename.endswith('.log'):
                file_size = os.path.getsize(file_path)
                total_size_before += file_size
                file_count_before += 1
        
        # 清空每个日志文件（非当前日志文件）
        cleaned_files = 0
        for filename in os.listdir(LOGS_DIR):
            file_path = os.path.join(LOGS_DIR, filename)
            # 只处理.log结尾的文件，跳过目录和当前日志文件
            if not filename.endswith('.log') or os.path.isdir(file_path) or file_path == current_log_file:
                continue
                
            try:
                # 清空文件内容而不是删除文件
                open(file_path, 'w').close()
                cleaned_files += 1
                logger.info(f"已清空日志文件: {filename}")
            except Exception as e:
                logger.error(f"清空日志文件 {filename} 失败: {str(e)}")
        
        # 记录清理后的状态
        total_size_after = 0
        file_count_after = 0
        
        for filename in os.listdir(LOGS_DIR):
            file_path = os.path.join(LOGS_DIR, filename)
            if os.path.isfile(file_path) and filename.endswith('.log'):
                file_size = os.path.getsize(file_path)
                total_size_after += file_size
                file_count_after += 1
        
        # 计算清理效果
        saved_space = total_size_before - total_size_after
        saved_space_mb = saved_space / (1024 * 1024)
        
        logger.info(f"日志清理完成，共清空 {cleaned_files} 个文件")
        logger.info(f"清理前: {file_count_before} 个日志文件，总大小 {total_size_before / (1024 * 1024):.2f} MB")
        logger.info(f"清理后: {file_count_after} 个日志文件，总大小 {total_size_after / (1024 * 1024):.2f} MB")
        logger.info(f"节省空间: {saved_space_mb:.2f} MB")
        
        return True
    except Exception as e:
        logger.error(f"清理日志文件时发生错误: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def start_logs_cleaner():
    """
    开始日志清理过程，返回结果供调度器使用
    """
    logger.info("启动日志清理服务")
    result = clean_logs()
    if result:
        logger.info("日志清理成功")
    else:
        logger.error("日志清理失败")
    return result

if __name__ == "__main__":
    # 直接运行时，立即执行日志清理
    logger.info("直接执行日志清理脚本")
    start_logs_cleaner()
