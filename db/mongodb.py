"""
MongoDB数据库模块
"""

import os
import logging
import certifi
import json
from typing import List, Dict, Any, Optional, Tuple, Union
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError
from bson import ObjectId, json_util
import datetime

# 设置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mongodb")

class MongoDB:
    """MongoDB数据库管理类"""
    
    def __init__(self):
        """初始化MongoDB连接"""
        # 从环境变量获取MongoDB连接信息
        self.uri = os.getenv('MONGODB_URI', 'mongodb+srv://Khaos:Syyz6910@liaonews.9txcrbd.mongodb.net/?retryWrites=true&w=majority&appName=liaonews')
        self.db_name = os.getenv('MONGODB_DB', 'liaonews')
        self.collection_name = os.getenv('MONGODB_COLLECTION', 'articles')
        
        # 连接MongoDB
        self._connect()
        
        # 创建索引
        self._create_indexes()
    
    def _connect(self):
        """连接到MongoDB数据库"""
        try:
            # 使用certifi提供的证书
            self.client = MongoClient(self.uri, tlsCAFile=certifi.where())
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
            logger.info("MongoDB连接成功")
        except Exception as e:
            logger.error(f"MongoDB连接失败: {e}")
            raise
    
    def _create_indexes(self):
        """创建必要的索引"""
        try:
            # 创建source_url的唯一索引
            self.collection.create_index([("source_url", ASCENDING)], unique=True)
            # 创建全文搜索索引
            self.collection.create_index([("title", "text"), ("content", "text")])
            # 创建日期索引
            self.collection.create_index([("date_time", DESCENDING)])
            logger.info("MongoDB索引创建成功")
        except Exception as e:
            logger.error(f"创建索引失败: {e}")
            raise
    
    def _serialize_doc(self, doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """序列化MongoDB文档，处理特殊类型
        
        Args:
            doc: MongoDB文档
            
        Returns:
            序列化后的文档
        """
        if not doc:
            return None
            
        # 使用 json_util 序列化文档
        return json.loads(json_util.dumps(doc))
    
    def _serialize_docs(self, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """序列化MongoDB文档列表
        
        Args:
            docs: MongoDB文档列表
            
        Returns:
            序列化后的文档列表
        """
        return [self._serialize_doc(doc) for doc in docs]
    
    def get_existing_urls(self) -> List[str]:
        """获取所有已存在的URL
        
        Returns:
            URL列表
        """
        try:
            # 只获取source_url字段
            documents = self.collection.find({}, {"source_url": 1, "_id": 0})
            return [doc["source_url"] for doc in documents if "source_url" in doc]
        except Exception as e:
            logger.error(f"获取现有URL失败: {e}")
            return []
    
    def insert_articles(self, articles: List[Dict[str, Any]]) -> int:
        """批量插入文章
        
        Args:
            articles: 要插入的文章列表
            
        Returns:
            成功插入的文章数量
        """
        if not articles:
            return 0
        
        try:
            result = self.collection.insert_many(articles)
            return len(result.inserted_ids)
        except DuplicateKeyError as e:
            logger.error(f"插入文档失败: {e}")
            return 0
        except Exception as e:
            logger.error(f"批量插入文档失败: {e}")
            return 0
    
    def find_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """根据URL查找文章
        
        Args:
            url: 文章URL
            
        Returns:
            文章数据，如果不存在返回None
        """
        try:
            doc = self.collection.find_one({"source_url": url})
            return self._serialize_doc(doc)
        except Exception as e:
            logger.error(f"查询文档失败: {e}")
            return None
    
    def get_articles(self, query: Dict[str, Any] = None, skip: int = 0, limit: int = 10, sort: List[Tuple[str, int]] = None) -> List[Dict[str, Any]]:
        """获取文章列表，支持分页和排序
        
        Args:
            query: 查询条件
            skip: 跳过的文档数
            limit: 返回的文档数
            sort: 排序条件列表，如 [('date_time', -1)]
            
        Returns:
            文章列表
        """
        try:
            cursor = self.collection.find(query or {})
            if sort:
                cursor = cursor.sort(sort)
            cursor = cursor.skip(skip).limit(limit)
            return self._serialize_docs(list(cursor))
        except Exception as e:
            logger.error(f"获取文章列表失败: {e}")
            return []
    
    def get_article_by_id(self, article_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取文章
        
        Args:
            article_id: 文章ID
            
        Returns:
            文章数据，如果不存在返回None
        """
        try:
            doc = self.collection.find_one({"_id": ObjectId(article_id)})
            return self._serialize_doc(doc)
        except Exception as e:
            logger.error(f"根据ID获取文章失败: {e}")
            return None
    
    def search_articles(self, query: str, skip: int = 0, limit: int = 10) -> List[Dict[str, Any]]:
        """搜索文章
        
        Args:
            query: 搜索关键词
            skip: 跳过的文档数
            limit: 返回的文档数
            
        Returns:
            匹配的文章列表
        """
        try:
            # 使用全文搜索
            cursor = self.collection.find(
                {"$text": {"$search": query}},
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})])
            cursor = cursor.skip(skip).limit(limit)
            return self._serialize_docs(list(cursor))
        except Exception as e:
            logger.error(f"搜索文档失败: {e}")
            return []
    
    def get_article_count(self, query: Dict[str, Any] = None) -> int:
        """获取文章总数
        
        Args:
            query: 查询条件
            
        Returns:
            文章总数
        """
        try:
            return self.collection.count_documents(query or {})
        except Exception as e:
            logger.error(f"获取文章总数失败: {e}")
            return 0
    
    def close(self):
        """关闭MongoDB连接"""
        try:
            if hasattr(self, 'client'):
                self.client.close()
                logger.info("MongoDB连接已关闭")
        except Exception as e:
            logger.error(f"关闭MongoDB连接失败: {e}")
    
    def __del__(self):
        """析构函数，确保连接被关闭"""
        self.close() 