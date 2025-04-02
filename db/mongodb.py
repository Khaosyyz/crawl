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
from pymongo.errors import DuplicateKeyError, ConnectionFailure
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
    
    def check_connection(self) -> bool:
        """检查MongoDB连接是否可用
        
        Returns:
            连接状态，True表示连接正常
        """
        try:
            # 向服务器发送ping命令检查连接
            self.client.admin.command('ping')
            return True
        except Exception as e:
            logger.error(f"MongoDB连接检查失败: {e}")
            return False
    
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
    
    def search_articles(self, query_term: str = None, query: str = None, query_filter: Dict[str, Any] = None, search_criteria: Dict[str, Any] = None, skip: int = 0, limit: int = 50, page: int = 1, per_page: int = 50) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], int]]:
        """搜索文章 - 支持多种参数形式以保持兼容性
        
        Args:
            query_term: 搜索关键词 (新接口，优先使用)
            query: 搜索关键词 (旧接口)
            query_filter: 附加搜索条件 (新接口)
            search_criteria: 附加搜索条件 (旧接口)
            skip: 跳过的文档数 (直接指定)
            limit: 返回的文档数 (直接指定)
            page: 页码 (基于per_page计算skip)
            per_page: 每页条数
            
        Returns:
            匹配的文章列表，或者元组(文章列表, 总匹配数)
        """
        try:
            # 参数处理 - 兼容旧接口
            search_term = query_term or query or ""
            filter_criteria = query_filter or search_criteria or {}
            
            # 计算分页 - 支持两种方式
            if page > 1 and per_page > 0:
                actual_skip = (page - 1) * per_page
                actual_limit = per_page
            else:
                actual_skip = skip
                actual_limit = limit
            
            # 记录搜索参数
            logger.info(f"搜索参数: 关键词='{search_term}', 过滤条件={filter_criteria}, 跳过={actual_skip}, 限制={actual_limit}")
            
            # 增强搜索功能，支持多字段搜索和部分匹配
            if search_term:
                text_search_query = {
                    "$or": [
                        # 全文搜索
                        {"$text": {"$search": search_term}},
                        # 标题部分匹配
                        {"title": {"$regex": search_term, "$options": "i"}},
                        # 内容部分匹配
                        {"content": {"$regex": search_term, "$options": "i"}},
                        # 作者部分匹配
                        {"author": {"$regex": search_term, "$options": "i"}}
                    ]
                }
                
                # 合并附加搜索条件和文本搜索条件
                final_query = {**text_search_query, **filter_criteria}
            else:
                # 如果没有搜索词，仅使用过滤条件
                final_query = filter_criteria
            
            # 计算总匹配数量
            total_matches = self.collection.count_documents(final_query)
            
            # 按日期倒序排序
            cursor = self.collection.find(final_query).sort([("date_time", -1)])
            
            # 应用分页
            cursor = cursor.skip(actual_skip).limit(actual_limit)
            
            # 获取并序列化结果
            results = self._serialize_docs(list(cursor))
            logger.info(f"搜索关键词 '{search_term}' 找到 {total_matches} 个结果，返回 {len(results)} 个")
            
            # 返回元组 (结果列表, 总匹配数)
            return results, total_matches
        except Exception as e:
            logger.error(f"搜索文档失败: {e}")
            return [], 0
    
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
    
    def get_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息
        
        Returns:
            包含统计信息的字典
        """
        try:
            # 获取总文章数
            total_articles = self.get_article_count()
            
            # 获取各数据源的文章数
            sources = {}
            for source in ['x.com', 'crunchbase']:
                count = self.get_article_count({'source': source})
                sources[source] = count
                
            # 获取最新更新时间
            latest_article = self.get_articles(limit=1, sort=[('date_time', -1)])
            last_update = latest_article[0]['date_time'] if latest_article else None
            
            return {
                'total_articles': total_articles,
                'sources': sources,
                'last_update': last_update
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {
                'error': str(e)
            }
    
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