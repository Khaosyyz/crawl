#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
向后兼容层 - 从新路径导入存储函数
"""

import logging
from src.clean.storage import get_unprocessed_data, update_processed_data, DataStorage

# 创建日志记录器
logger = logging.getLogger("storage_compat")
logger.info("使用向后兼容的存储模块导入")

# 导出需要的函数和类，保持向后兼容
__all__ = ['get_unprocessed_data', 'update_processed_data', 'DataStorage'] 