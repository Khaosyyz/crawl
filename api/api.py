import os
import sys
from pathlib import Path

# 将项目根目录添加到 Python 路径
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

from flask import Flask, jsonify, request, Response
from flask_cors import CORS  # 导入 CORS
import json
import logging
from db.mongodb import MongoDB
from bson import ObjectId, json_util
import datetime
import traceback

class MongoJSONEncoder(json.JSONEncoder):
    """处理MongoDB特殊类型的JSON编码器"""
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return super().default(obj)

# 设置日志记录
logging.basicConfig(
    level=logging.INFO,  # 改为INFO级别以获取更多信息
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(project_root, "logs", "api.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("api")

app = Flask(__name__)
# 配置 CORS，允许所有域名访问，并添加更多选项
CORS(app, resources={r"/api/*": {"origins": "*", "methods": ["GET", "POST", "OPTIONS"], "allow_headers": ["Content-Type", "Authorization"]}})
app.json_encoder = MongoJSONEncoder  # 使用自定义的JSON编码器
# 禁用Flask默认日志
app.logger.disabled = True
log = logging.getLogger('werkzeug')
log.disabled = True

# 初始化MongoDB连接
db = MongoDB()

def jsonify_with_util(*args, **kwargs):
    """使用 json_util 创建 JSON 响应"""
    return Response(
        json.dumps(dict(*args, **kwargs)),
        mimetype='application/json'
    )

@app.route('/api/articles')
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
        logger.info(f"获取到文章总数: {total}")
        
        # 获取分页数据
        articles = db.get_articles(
            query=query,
            skip=(page - 1) * per_page,
            limit=per_page,
            sort=[('date_time', -1)]  # 按时间倒序排序
        )
        logger.info(f"获取到文章列表: {len(articles)} 篇")
        
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
        
        logger.debug(f"响应数据: {response_data}")
        return jsonify(response_data)
    except Exception as e:
        logger.error(f"获取文章列表出错: {e}")
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        
        # 检查是否是 JSONP 请求
        callback = request.args.get('callback')
        error_response = {
            'status': 'error',
            'message': '获取文章列表失败，请稍后再试',
            'error': str(e)
        }
        
        if callback:
            # 如果是 JSONP 请求，返回带有回调的 JavaScript
            jsonp_response = f"{callback}({json.dumps(error_response, cls=MongoJSONEncoder)})"
            return Response(jsonp_response, mimetype='application/javascript')
            
        return jsonify(error_response), 500

@app.route('/api/articles/<article_id>')
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
        logger.error(f"获取文章详情出错: {e}")
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        return jsonify({
            'status': 'error',
            'message': '获取文章详情失败，请稍后再试',
            'error': str(e)
        }), 500

@app.route('/api/search')
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
        # 获取数据源过滤参数
        source = request.args.get('source')
        
        # 构建搜索条件
        search_criteria = {}
        
        # 如果指定了数据源，添加到搜索条件中
        if source:
            search_criteria['source'] = source
        
        # 执行全文搜索
        results = db.search_articles(
            query=query,
            search_criteria=search_criteria,
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
        logger.error(f"搜索文章出错: {e}")
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        return jsonify({
            'status': 'error',
            'message': '搜索文章失败，请稍后再试',
            'error': str(e)
        }), 500

@app.route('/api/stats')
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
        logger.error(f"获取统计信息出错: {e}")
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        return jsonify({
            'status': 'error',
            'message': '获取统计信息失败，请稍后再试',
            'error': str(e)
        }), 500

def main():
    """启动API服务"""
    print("API服务已启动，正在监听 http://0.0.0.0:8080")
    app.run(host='0.0.0.0', port=8080, debug=False)

if __name__ == '__main__':
    main()

# Vercel serverless function handler
def handler(request, context):
    """Vercel serverless function handler"""
    # 创建WSGI应用的代理
    return app