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
        
        # 获取总文章数
        total_articles = db.get_article_count()
        
        # 获取各数据源的文章数
        sources = {}
        for source in ['x.com', 'crunchbase']:
            count = db.get_article_count({'source': source})
            sources[source] = count
            
        # 获取最新更新时间
        latest_article = db.get_articles(limit=1, sort=[('date_time', -1)])
        last_update = latest_article[0]['date_time'] if latest_article else None
        
        response_data = {
            'status': 'success',
            'data': {
                'total_articles': total_articles,
                'sources': sources,
                'last_update': last_update
            }
        }
        
        return response_data
        
    except Exception as e:
        # 处理错误
        response.status = 500
        return {
            'status': 'error',
            'message': '获取统计信息失败，请稍后再试',
            'error': str(e)
        } 