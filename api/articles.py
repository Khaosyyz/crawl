from http.server import BaseHTTPRequestHandler
import json
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

# 导入 MongoDB 连接
from db.mongodb import MongoDB

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            
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
            
            # 检查是否是 JSONP 请求
            if '?callback=' in self.path:
                callback = self.path.split('callback=')[1].split('&')[0]
                response_text = f"{callback}({json.dumps(response_data)})"
                self.wfile.write(response_text.encode())
            else:
                self.wfile.write(json.dumps(response_data).encode())
            
        except Exception as e:
            # 处理错误
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            error_response = {
                'status': 'error',
                'message': '获取文章列表失败，请稍后再试',
                'error': str(e)
            }
            
            self.wfile.write(json.dumps(error_response).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers() 