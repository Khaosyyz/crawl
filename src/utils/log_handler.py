import os
import logging
from logging.handlers import RotatingFileHandler
import datetime
from src.utils.paths import LOGS_DIR

class LogHandler:
    """
    统一日志处理模块，支持按日期切割并自动创建目录
    """
    
    def __init__(self):
        # 使用统一的日志目录
        self.logs_dir = LOGS_DIR
        os.makedirs(self.logs_dir, exist_ok=True)
        
    def get_logger(self, name, level=logging.INFO, max_bytes=5*1024*1024, backup_count=3):
        """
        获取一个日志记录器
        
        Args:
            name: 日志名称
            level: 日志级别
            max_bytes: 单个日志文件最大大小
            backup_count: 保留的日志文件数量
            
        Returns:
            logging.Logger: 日志记录器
        """
        logger = logging.getLogger(name)
        logger.setLevel(level)
        
        # 清除现有处理器
        if logger.handlers:
            logger.handlers.clear()
            
        # 创建日志文件名（替换点为下划线）
        safe_name = name.replace('.', '_')
        log_file = os.path.join(self.logs_dir, f"{safe_name}.log")
        
        # 添加文件处理器
        file_handler = RotatingFileHandler(
            log_file, 
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        
        # 设置日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # 添加控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        return logger

# 全局日志处理器实例
log_handler = LogHandler()

def get_logger(name, level=logging.INFO):
    """
    获取日志记录器的快捷方式
    """
    return log_handler.get_logger(name, level) 