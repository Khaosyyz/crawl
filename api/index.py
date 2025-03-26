from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import json
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

# 导入 MongoDB 连接
from db.mongodb import MongoDB

# 初始化数据库连接
db = MongoDB()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
        # 解析路径
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        response_data = {}
        
        # 根据路径路由到不同的处理程序
        if path == '/api' or path == '/api/':
            # API首页
            response_data = {
                'status': 'success',
                'message': 'API服务正常',
                'endpoints': [
                    '/api/hello - 测试端点',
                    '/api/articles - 文章列表',
                    '/api/stats - 统计数据'
                ],
                'path': self.path
            }
        elif path == '/api/hello':
            # Hello端点
            response_data = {
                'status': 'success',
                'message': 'Hello World from Vercel Function',
                'path': self.path
            }
        elif path == '/api/articles':
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
            
            response_data = {
                'status': 'success',
                'total': total,
                'page': page,
                'per_page': per_page,
                'data': articles
            }
            
            # 检查是否是 JSONP 请求
            if '?callback=' in self.path:
                callback = self.path.split('callback=')[1].split('&')[0]
                response_text = f"{callback}({json.dumps(response_data)})"
                self.wfile.write(response_text.encode())
            else:
                self.wfile.write(json.dumps(response_data).encode())
        elif path == '/api/stats':
            # 获取统计信息
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
            
            self.wfile.write(json.dumps(response_data).encode())
        else:
            # 未找到对应端点
            response_data = {
                'status': 'error',
                'message': 'Endpoint not found',
                'path': self.path
            }
            
        # 发送响应
        self.wfile.write(json.dumps(response_data).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

def handler(request):
    """简单的测试函数"""
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps({
            "message": "Hello from index.py",
            "path": request.get('path', 'unknown')
        })
    } 