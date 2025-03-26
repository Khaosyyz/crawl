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

# 初始化数据库连接
db = MongoDB()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            
            # 处理不同的路径
            if self.path.startswith('/api/articles'):
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
                
            elif self.path.startswith('/api/stats'):
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
                # 默认响应
                response_data = {
                    'status': 'success',
                    'message': 'API服务运行正常',
                    'endpoints': ['/api/articles', '/api/stats']
                }
                self.wfile.write(json.dumps(response_data).encode())
                
        except Exception as e:
            # 处理错误
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            error_response = {
                'status': 'error',
                'message': '处理请求时出错',
                'error': str(e)
            }
            
            self.wfile.write(json.dumps(error_response).encode())
    
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