#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
清空MongoDB数据库中的所有文章
"""

import sys
import os
import logging
from pymongo import MongoClient
import certifi

# 设置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("db_clear")

def clear_database():
    """清空MongoDB数据库中的所有文章"""
    # 从环境变量获取MongoDB连接信息
    uri = os.getenv('MONGODB_URI', 'mongodb+srv://Khaos:Syyz6910@liaonews.9txcrbd.mongodb.net/?retryWrites=true&w=majority&appName=liaonews')
    db_name = os.getenv('MONGODB_DB', 'liaonews')
    collection_name = os.getenv('MONGODB_COLLECTION', 'articles')
    
    try:
        # 连接MongoDB
        client = MongoClient(uri, tlsCAFile=certifi.where())
        db = client[db_name]
        collection = db[collection_name]
        
        # 获取清空前的文档数量
        before_count = collection.count_documents({})
        logger.info(f"清空前文档数量: {before_count}")
        
        # 清空集合
        result = collection.delete_many({})
        
        # 获取清空后的文档数量
        after_count = collection.count_documents({})
        
        logger.info(f"已删除 {result.deleted_count} 条文档")
        logger.info(f"清空后文档数量: {after_count}")
        
        # 关闭连接
        client.close()
        
        return result.deleted_count
    except Exception as e:
        logger.error(f"清空数据库失败: {e}")
        return 0

if __name__ == "__main__":
    logger.info("开始清空数据库...")
    deleted = clear_database()
    logger.info(f"数据库清空完成，总共删除了 {deleted} 条文档") 