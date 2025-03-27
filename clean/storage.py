"""
数据存储管理模块
"""

import os
import json
import logging
from typing import List, Dict, Any
import sys

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from db.mongodb import MongoDB

# 设置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("storage")

class DataStorage:
    """数据存储管理类，负责数据的保存、加载和去重等操作"""
    
    def __init__(self):
        """初始化数据存储管理器"""
        self.mongodb = MongoDB()
        self._existing_urls = set()
        self._load_existing_urls()
    
    def _load_existing_urls(self):
        """加载已存在的URL集合，用于去重"""
        try:
            # 从MongoDB加载已存在的URL
            existing_urls = self.mongodb.get_existing_urls()
            self._existing_urls = set(existing_urls)
            logger.info(f"已加载 {len(self._existing_urls)} 个现有URL")
        except Exception as e:
            logger.error(f"加载现有URL失败: {e}")
            self._existing_urls = set()
    
    def url_exists(self, url: str) -> bool:
        """检查URL是否已存在
        
        Args:
            url: 要检查的URL
            
        Returns:
            True如果URL已存在，否则False
        """
        return url in self._existing_urls
    
    def store(self, article: Dict[str, Any]) -> bool:
        """保存单篇文章到数据库
        
        Args:
            article: 要保存的文章
            
        Returns:
            是否成功保存
        """
        if not article:
            logger.warning("尝试保存空文章")
            return False
            
        url = article.get('source_url', '')
        if not url:
            logger.warning("文章缺少source_url字段")
            return False
            
        # 检查URL是否已存在
        if self.url_exists(url):
            logger.info(f"跳过已存在的URL: {url}")
            return False
            
        # 保存到MongoDB
        try:
            self.mongodb.insert_articles([article])
            # 添加到已存在URL集合中
            self._existing_urls.add(url)
            logger.info(f"成功保存文章: {article.get('title', '无标题')} - {url}")
            return True
        except Exception as e:
            logger.error(f"保存文章失败: {e}")
            return False
    
    def save_articles(self, articles: List[Dict[str, Any]]) -> int:
        """保存文章数据到MongoDB
        
        Args:
            articles: 要保存的文章列表
            
        Returns:
            成功保存的文章数量
        """
        # 过滤掉已存在的URL
        new_articles = []
        for article in articles:
            url = article.get('source_url', '')
            if url and not self.url_exists(url):
                new_articles.append(article)
                self._existing_urls.add(url)
        
        # 保存新文章
        if new_articles:
            try:
                self.mongodb.insert_articles(new_articles)
                logger.info(f"成功保存 {len(new_articles)} 篇新文章")
                return len(new_articles)
            except Exception as e:
                logger.error(f"保存文章失败: {e}")
                return 0
        else:
            logger.info("没有新文章需要保存")
            return 0
    
    def save_temp_data(self, data: List[Dict[str, Any]], temp_file: str):
        """保存临时数据到文件
        
        Args:
            data: 要保存的数据
            temp_file: 临时文件路径
        """
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(temp_file), exist_ok=True)
            
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"临时数据已保存到: {temp_file}")
        except Exception as e:
            logger.error(f"保存临时数据失败: {str(e)}")
    
    def load_temp_data(self, file_path: str) -> List[Dict[str, Any]]:
        """加载临时文件数据
        
        Args:
            file_path: 临时文件路径
            
        Returns:
            临时数据列表
        """
        data = []
        try:
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        if not isinstance(data, list):
                            logger.warning(f"临时文件格式不正确: {file_path}")
                            data = []
        except Exception as e:
            logger.error(f"加载临时文件失败: {file_path}, 错误: {e}")
            data = []
        
        return data
    
    def clear_temp_file(self, file_path: str):
        """清空临时文件
        
        Args:
            file_path: 临时文件路径
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('[]')
            logger.info(f"已清空临时文件: {file_path}")
        except Exception as e:
            logger.error(f"清空临时文件失败: {e}")
    
    def close(self):
        """关闭数据存储管理器"""
        try:
            self.mongodb.close()
        except Exception as e:
            logger.error(f"关闭MongoDB连接失败: {e}") 