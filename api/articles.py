from http.server import BaseHTTPRequestHandler
import json
import sys
import os
import traceback
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import datetime
import pytz

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
            
            # 解析URL参数
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            
            # 获取分页参数
            page = int(query_params.get('page', ['1'])[0])
            source = query_params.get('source', ['x.com'])[0]
            date_page = int(query_params.get('date_page', ['1'])[0])
            items_per_page = 9 if source == 'x.com' else 3  # x.com每页9条，crunchbase每页3条
            
            # 初始化数据库连接
            try:
                db = MongoDB()
                
                # 构建查询条件
                query = {'source': source}
                
                # 获取总文章数
                total = db.get_article_count(query)
                
                # 计算日期范围
                today = datetime.datetime.now(pytz.timezone('Asia/Shanghai'))
                
                # 日期分页处理
                # 第一页显示今天和昨天的数据，第二页显示前天和大前天，依此类推
                start_days_ago = (date_page - 1) * 2
                end_days_ago = start_days_ago + 2
                
                # 计算日期范围
                start_date = (today - datetime.timedelta(days=end_days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = (today - datetime.timedelta(days=start_days_ago)).replace(hour=23, minute=59, second=59, microsecond=999999)
                
                # 日期查询范围
                date_query = {'date_time': {'$gte': start_date.strftime('%Y-%m-%d %H:%M:%S'), 
                                            '$lte': end_date.strftime('%Y-%m-%d %H:%M:%S')}}
                
                # 合并查询条件
                query.update(date_query)
                
                # 计算跳过的记录数
                skip = (page - 1) * items_per_page
                
                # 获取分页数据
                articles = db.get_articles(
                    query=query,
                    skip=skip,
                    limit=items_per_page,
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
                
                # 获取日期分页的总数（估算值，根据数据日期范围粗略计算）
                oldest_article = db.get_articles(
                    query={'source': source}, 
                    limit=1, 
                    sort=[('date_time', 1)]  # 升序，找最早的文章
                )
                
                if oldest_article:
                    oldest_date_str = oldest_article[0].get('date_time')
                    if oldest_date_str:
                        try:
                            oldest_date = datetime.datetime.strptime(oldest_date_str, '%Y-%m-%d %H:%M:%S')
                            days_diff = (today - oldest_date).days
                            total_date_pages = (days_diff // 2) + 1
                        except:
                            total_date_pages = 1
                    else:
                        total_date_pages = 1
                else:
                    total_date_pages = 1
                
                # 响应数据
                response_data = {
                    'status': 'success',
                    'total': total,
                    'page': page,
                    'date_page': date_page,
                    'total_date_pages': total_date_pages,
                    'per_page': items_per_page,
                    'source': source,
                    'date_range': {
                        'start': start_date.strftime('%Y-%m-%d'),
                        'end': end_date.strftime('%Y-%m-%d')
                    },
                    'data': serializable_articles
                }
                
                # 检查是否是 JSONP 请求
                if '?callback=' in self.path:
                    callback = self.path.split('callback=')[1].split('&')[0]
                    response_text = f"{callback}({json.dumps(response_data)})"
                    self.wfile.write(response_text.encode())
                else:
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
                'message': '获取文章列表失败，请稍后再试',
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