from http.server import BaseHTTPRequestHandler
import json
import sys
import os
import traceback
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import datetime
import pytz
from collections import defaultdict

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
            items_per_page = 9 if source == 'x.com' else 3
            
            # 初始化数据库连接
            try:
                db = MongoDB()
                
                # 构建基本查询条件
                query = {'source': source}
                
                # 获取总文章数
                total = db.get_article_count(query)
                
                # 处理crunchbase类型 - 使用简单分页
                if source == 'crunchbase':
                    # 计算跳过的记录数
                    skip = (page - 1) * items_per_page
                    
                    # 获取分页数据
                    articles = db.get_articles(
                        query=query,
                        skip=skip,
                        limit=items_per_page,
                        sort=[('date_time', -1)]
                    )
                    
                    # 计算总页数
                    total_pages = (total + items_per_page - 1) // items_per_page
                    
                    # 构造响应数据
                    response_data = {
                        'status': 'success',
                        'total': total,
                        'page': page,
                        'total_pages': total_pages,
                        'per_page': items_per_page,
                        'source': source,
                        'pagination_mode': 'simple',
                        'data': self._serialize_articles(articles)
                    }
                else:
                    # 处理x.com类型 - 按日期分组
                    # 获取唯一日期
                    unique_dates = self._get_unique_dates(db, source)
                    
                    # 如果没有日期，返回空结果
                    if not unique_dates:
                        response_data = {
                            'status': 'success',
                            'total': total,
                            'page': page,
                            'date_page': date_page,
                            'total_date_pages': 0,
                            'per_page': items_per_page,
                            'source': source,
                            'pagination_mode': 'date_grouped',
                            'dates_in_page': [],
                            'date_articles': {},
                            'data': []
                        }
                    else:
                        # 日期分页 - 每页最多显示2天
                        date_page_size = 2
                        start_date_index = (date_page - 1) * date_page_size
                        end_date_index = min(start_date_index + date_page_size, len(unique_dates))
                        
                        # 如果日期页码超出范围，返回空结果
                        if start_date_index >= len(unique_dates):
                            response_data = {
                                'status': 'success',
                                'total': total,
                                'page': page,
                                'date_page': date_page,
                                'total_date_pages': (len(unique_dates) + date_page_size - 1) // date_page_size,
                                'unique_dates': unique_dates,
                                'per_page': items_per_page,
                                'source': source,
                                'pagination_mode': 'date_grouped',
                                'dates_in_page': [],
                                'date_articles': {},
                                'data': []
                            }
                        else:
                            # 获取当前日期页的日期
                            current_page_dates = unique_dates[start_date_index:end_date_index]
                            
                            # 初始化日期数据
                            date_articles = {}
                            all_articles = []
                            
                            # 为每个日期获取数据
                            for date in current_page_dates:
                                # 为当前日期构建查询
                                date_start = f"{date} 00:00:00"
                                date_end = f"{date} 23:59:59"
                                date_query = {
                                    'source': source,
                                    'date_time': {
                                        '$gte': date_start,
                                        '$lte': date_end
                                    }
                                }
                                
                                # 获取当前日期的所有文章
                                date_total = db.get_article_count(date_query)
                                
                                # 计算该日期下当前页的偏移量
                                date_skip = (page - 1) * items_per_page
                                
                                # 获取当前日期当前页的文章
                                date_articles_data = db.get_articles(
                                    query=date_query,
                                    skip=date_skip,
                                    limit=items_per_page,
                                    sort=[('date_time', -1)]
                                )
                                
                                # 计算当前日期的总页数
                                date_total_pages = (date_total + items_per_page - 1) // items_per_page
                                
                                # 判断当前日期是否还有更多文章
                                has_more = date_skip + len(date_articles_data) < date_total
                                
                                # 保存当前日期的数据
                                date_articles[date] = {
                                    'total': date_total,
                                    'total_pages': date_total_pages,
                                    'current_page': page,
                                    'has_more': has_more,
                                    'articles': self._serialize_articles(date_articles_data)
                                }
                                
                                # 添加到总文章列表
                                all_articles.extend(date_articles_data)
                            
                            # 构造响应数据
                            response_data = {
                                'status': 'success',
                                'total': total,
                                'page': page,
                                'date_page': date_page,
                                'total_date_pages': (len(unique_dates) + date_page_size - 1) // date_page_size,
                                'per_page': items_per_page,
                                'source': source,
                                'pagination_mode': 'date_grouped',
                                'dates_in_page': current_page_dates,
                                'date_articles': date_articles,
                                'data': self._serialize_articles(all_articles)
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
    
    def _get_unique_dates(self, db, source):
        """获取指定来源的唯一日期列表"""
        try:
            # 获取所有文章
            articles = db.get_articles(
                query={'source': source},
                skip=0,
                limit=1000,  # 设置一个较大的限制
                sort=[('date_time', -1)]
            )
            
            # 提取唯一日期
            unique_dates = set()
            for article in articles:
                date_str = article.get('date_time', '')
                if date_str:
                    # 提取日期部分（忽略时间）
                    date_only = date_str.split(' ')[0] if ' ' in date_str else date_str
                    unique_dates.add(date_only)
            
            return sorted(list(unique_dates), reverse=True)
        except:
            return []
    
    def _serialize_articles(self, articles):
        """序列化文章列表，处理特殊类型"""
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
        return serializable_articles 