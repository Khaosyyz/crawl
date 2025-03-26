import sys
import json
from pathlib import Path
from typing import Dict, Any

# 添加项目根目录到Python路径
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

# 导入MongoDB连接
from db.mongodb import MongoDB

def handler(request, response):
    # 设置CORS头
    response.headers = {
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET,OPTIONS,PATCH,DELETE,POST,PUT",
        "Access-Control-Allow-Headers": "X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version",
        "Content-Type": "application/json"
    }
    
    # 处理OPTIONS请求
    if request.method == "OPTIONS":
        return {"status": "success"}
    
    try:
        # 初始化数据库连接
        db = MongoDB()
        
        # 获取文章列表
        page = 1
        per_page = 10
        query = {}
        
        # 获取总文章数
        total = db.get_article_count(query)
        
        # 获取分页数据
        articles = db.get_articles(
            query=query,
            skip=(page - 1) * per_page,
            limit=per_page,
            sort=[('date_time', -1)]  # 按时间倒序排序
        )
        
        # 序列化为可JSON化的数据
        serializable_articles = []
        for article in articles:
            # 对每个文章中的特殊类型进行处理
            serializable_article = {}
            for key, value in article.items():
                if key == '_id':
                    serializable_article[key] = str(value)
                else:
                    serializable_article[key] = value
            serializable_articles.append(serializable_article)
        
        response_data = {
            'status': 'success',
            'total': total,
            'page': page,
            'per_page': per_page,
            'data': serializable_articles
        }
        
        return response_data
        
    except Exception as e:
        # 处理错误
        response.status = 500
        return {
            'status': 'error',
            'message': '获取文章列表失败，请稍后再试',
            'error': str(e)
        } 