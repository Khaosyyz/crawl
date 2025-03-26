from http.server import BaseHTTPRequestHandler
import json
import sys
import os
import traceback
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

# 导入 MongoDB 连接
try:
    from db.mongodb import MongoDB
    mongodb_import_success = True
except Exception as e:
    mongodb_import_success = False
    mongodb_import_error = str(e)
    mongodb_import_traceback = traceback.format_exc()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            
            # 检查MongoDB模块是否成功导入
            if not mongodb_import_success:
                error_response = {
                    'status': 'error',
                    'message': '导入MongoDB模块失败',
                    'error': mongodb_import_error,
                    'traceback': mongodb_import_traceback
                }
                self.wfile.write(json.dumps(error_response).encode())
                return
            
            # 初始化数据库连接
            try:
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
                
                self.wfile.write(json.dumps(response_data).encode())
                
            except Exception as db_error:
                error_response = {
                    'status': 'error',
                    'message': '数据库操作失败',
                    'error': str(db_error),
                    'traceback': traceback.format_exc()
                }
                self.wfile.write(json.dumps(error_response).encode())
            
        except Exception as e:
            # 处理错误
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            error_response = {
                'status': 'error',
                'message': '获取统计信息失败，请稍后再试',
                'error': str(e),
                'traceback': traceback.format_exc()
            }
            
            self.wfile.write(json.dumps(error_response).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers() 