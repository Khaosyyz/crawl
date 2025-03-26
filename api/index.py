from flask import Flask, jsonify, request, Response
import os
import sys
from pathlib import Path
import json
import logging
from bson import ObjectId, json_util
import datetime
import traceback

# 添加项目根目录到 Python 路径
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

# 导入 MongoDB 连接
from db.mongodb import MongoDB

# 创建 Flask 应用
app = Flask(__name__)

# JSON编码器
class MongoJSONEncoder(json.JSONEncoder):
    """处理MongoDB特殊类型的JSON编码器"""
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return super().default(obj)

# 初始化MongoDB连接
db = MongoDB()

@app.route('/api/articles', methods=['GET'])
def get_articles():
    """API端点：获取文章列表，支持分页"""
    try:
        # 获取分页参数
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        source = request.args.get('source')  # 可选的数据源过滤
        
        # 构建查询条件
        query = {}
        if source:
            query['source'] = source
            
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
        callback = request.args.get('callback')
        if callback:
            # 如果是 JSONP 请求，返回带有回调的 JavaScript
            jsonp_response = f"{callback}({json.dumps(response_data, cls=MongoJSONEncoder)})"
            return Response(jsonp_response, mimetype='application/javascript')
        
        return jsonify(response_data)
    except Exception as e:
        error_response = {
            'status': 'error',
            'message': '获取文章列表失败，请稍后再试',
            'error': str(e)
        }
        
        # 检查是否是 JSONP 请求
        callback = request.args.get('callback')
        if callback:
            # 如果是 JSONP 请求，返回带有回调的 JavaScript
            jsonp_response = f"{callback}({json.dumps(error_response, cls=MongoJSONEncoder)})"
            return Response(jsonp_response, mimetype='application/javascript')
            
        return jsonify(error_response), 500

@app.route('/api/articles/<article_id>', methods=['GET'])
def get_article(article_id):
    """API端点：获取单篇文章详情"""
    try:
        article = db.get_article_by_id(article_id)
        if not article:
            return jsonify({
                'status': 'error',
                'message': '文章不存在'
            }), 404
            
        return jsonify({
            'status': 'success',
            'data': article
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': '获取文章详情失败，请稍后再试',
            'error': str(e)
        }), 500

@app.route('/api/search', methods=['GET'])
def search_articles():
    """API端点：全文搜索文章"""
    try:
        query = request.args.get('q', '')
        if not query:
            return jsonify({
                'status': 'error',
                'message': '请提供搜索关键词'
            }), 400
            
        # 获取分页参数
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        
        # 执行全文搜索
        results = db.search_articles(
            query=query,
            skip=(page - 1) * per_page,
            limit=per_page
        )
        
        # 获取总数
        total = len(results)
        
        return jsonify({
            'status': 'success',
            'total': total,
            'page': page,
            'per_page': per_page,
            'data': results
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': '搜索文章失败，请稍后再试',
            'error': str(e)
        }), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """API端点：获取统计信息"""
    try:
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
        
        return jsonify({
            'status': 'success',
            'data': {
                'total_articles': total_articles,
                'sources': sources,
                'last_update': last_update
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': '获取统计信息失败，请稍后再试',
            'error': str(e)
        }), 500

# 设置默认的 CORS 响应头
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

# Vercel serverless function 入口点
def handler(request):
    with app.request_context(request):
        return app.full_dispatch_request() 