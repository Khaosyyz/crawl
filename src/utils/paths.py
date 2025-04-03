#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
路径处理模块，统一项目中的路径引用
"""

import os
import sys

# 获取项目根目录（main.py所在目录）
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 源代码目录
SRC_DIR = os.path.join(ROOT_DIR, 'src')

# 数据目录
DATA_DIR = os.path.join(SRC_DIR, 'data')

# 日志目录
LOGS_DIR = os.path.join(ROOT_DIR, 'logs')

# 临时数据文件路径
X_TEMP_DATA_PATH = os.path.join(DATA_DIR, 'x_tempdata.json')
CRU_TEMP_DATA_PATH = os.path.join(DATA_DIR, 'cru_tempdata.json')

# X爬虫URL缓存文件
X_URLS_PATH = os.path.join(DATA_DIR, 'x_urls.json')

# Crunchbase爬虫URL缓存文件
CRU_URLS_PATH = os.path.join(DATA_DIR, 'crunchbase', 'cru_urls.json')
CRU_URLS_DEBUG_PATH = os.path.join(DATA_DIR, 'crunchbase', 'cru_urls_debug.json')

# 确保目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, 'crunchbase'), exist_ok=True)

# 添加src目录到Python路径
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

def get_abs_path(rel_path):
    """
    将相对路径转换为绝对路径
    
    Args:
        rel_path: 相对于项目根目录的路径
        
    Returns:
        绝对路径
    """
    return os.path.join(ROOT_DIR, rel_path) 