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
from bson import ObjectId # bson.json_util 已被移除，因为它在 db/mongodb.py 中处理了序列化
import datetime
import pytz # 新增导入
import traceback

class MongoJSONEncoder(json.JSONEncoder):
    """处理MongoDB特殊类型的JSON编码器"""
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime.datetime):
            # 保持一致性，或者使用 db/mongodb.py 中的序列化逻辑
            # 这里暂时保留 isoformat，但 db 层已用 json_util 处理
            return obj.isoformat()
        return super().default(obj)

# 设置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(project_root, "logs", "api.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("api")

app = Flask(__name__)
# 配置 CORS，允许所有域名访问
CORS(app) # 简化配置，允许所有来源，如果需要更严格控制，可以配置 origins
# app.json_encoder = MongoJSONEncoder # 移除，因为 db/mongodb.py 中 _serialize_docs 已处理序列化

# 禁用Flask默认日志
app.logger.disabled = True
log = logging.getLogger('werkzeug')
log.disabled = True

# 初始化MongoDB连接 (应该在应用上下文中处理更好，但暂时保持)
db = MongoDB()

@app.route('/api/articles')
def get_articles():
    """API端点：获取文章列表，支持来源过滤、分页和日期分页"""
    try:
        # 获取分页参数
        page = int(request.args.get('page', 1))
        date_page = int(request.args.get('date_page', 1))
        source = request.args.get('source', 'x.com') # 默认源改为 x.com

        # 根据来源确定每页项目数
        items_per_page = 9 if source == 'x.com' else 3

        # 构建基础查询条件
        base_query = {'source': source}

        # 获取总文章数 (基于来源)
        # total_source_articles = db.get_article_count(base_query) # 获取总数逻辑移到后面，基于日期范围

        # --- 合并 api/articles.py 的日期范围逻辑 ---
        reference_date = None
        try:
            # 获取最新文章以确定参考日期
            newest_article = db.get_articles(
                query={'source': source},
                limit=1,
                sort=[('date_time', -1)]
            )
            if newest_article and newest_article[0].get('date_time'):
                # db.get_articles 返回的是已序列化的 dict，date_time 是字符串
                try:
                    # 注意：MongoDB 返回的可能是 ISO 格式或其他，确保解析正确
                    # 假设 db 层返回的是 '%Y-%m-%d %H:%M:%S' 格式字符串
                    reference_date = datetime.datetime.fromisoformat(newest_article[0]['date_time'].replace('Z', '+00:00')) if isinstance(newest_article[0]['date_time'], str) else newest_article[0]['date_time']
                    # 转换到上海时区以便计算 Delta (如果需要的话，但计算差值不需要)
                    reference_date = reference_date.astimezone(pytz.timezone('Asia/Shanghai'))
                    logger.info(f"使用数据库中最新文章日期作为参考: {reference_date}")
                except ValueError:
                     # 如果格式不是 ISO 或 '%Y-%m-%d %H:%M:%S'，尝试其他格式或记录错误
                    logger.error(f"无法解析数据库中的日期格式: {newest_article[0]['date_time']}，使用当前时间。")
                    reference_date = datetime.datetime.now(pytz.timezone('Asia/Shanghai'))

        except Exception as e:
            logger.error(f"获取最新文章日期失败: {e}, 使用当前时间。")

        if reference_date is None:
            reference_date = datetime.datetime.now(pytz.timezone('Asia/Shanghai'))
            logger.info(f"未能确定参考日期，使用当前系统时间: {reference_date}")

        # 日期分页处理 (每页 2 天)
        start_days_ago = (date_page - 1) * 2
        end_days_ago = start_days_ago + 2

        # 计算日期范围 - 使用参考日期
        # 确保时区感知，以便比较
        tz_shanghai = pytz.timezone('Asia/Shanghai')
        start_date = (reference_date - datetime.timedelta(days=end_days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = (reference_date - datetime.timedelta(days=start_days_ago)).replace(hour=23, minute=59, second=59, microsecond=999999)

        # 转换为 MongoDB 查询兼容的格式 (字符串)
        start_date_str = start_date.strftime('%Y-%m-%d %H:%M:%S')
        end_date_str = end_date.strftime('%Y-%m-%d %H:%M:%S')

        # 日期查询范围
        date_query = {'date_time': {'$gte': start_date_str, '$lte': end_date_str}}

        # 合并查询条件
        query = {**base_query, **date_query}
        # --- 日期范围逻辑结束 ---

        # 计算跳过的记录数
        skip = (page - 1) * items_per_page

        # 获取当前日期范围和页面的文章总数 (用于分页)
        total_in_date_range = db.get_article_count(query)
        logger.info(f"查询条件 {query} 下找到的文章总数: {total_in_date_range}")

        # 获取分页数据
        articles = db.get_articles(
            query=query,
            skip=skip,
            limit=items_per_page,
            sort=[('date_time', -1)]  # 按时间倒序排序
        )
        logger.info(f"为页面 {page} (日期页 {date_page}) 获取到文章列表: {len(articles)} 篇")

        # --- 合并 api/articles.py 的日期分页总数逻辑 ---
        total_date_pages = 1 # 默认至少一页
        try:
            oldest_article = db.get_articles(
                query={'source': source},
                limit=1,
                sort=[('date_time', 1)] # 升序找最早
            )
            if oldest_article and oldest_article[0].get('date_time'):
                try:
                    # 同样注意日期格式解析
                    oldest_date = datetime.datetime.fromisoformat(oldest_article[0]['date_time'].replace('Z', '+00:00')) if isinstance(oldest_article[0]['date_time'], str) else oldest_article[0]['date_time']
                    oldest_date = oldest_date.astimezone(pytz.timezone('Asia/Shanghai'))
                    # 使用最新的 reference_date 来计算差异
                    days_diff = (reference_date.date() - oldest_date.date()).days # 只比较日期部分
                    total_date_pages = (days_diff // 2) + 1 # 每页2天
                except ValueError:
                    logger.error(f"无法解析最早文章日期格式: {oldest_article[0]['date_time']}")
        except Exception as e:
            logger.error(f"获取最早文章日期失败: {e}")
        # --- 日期分页总数逻辑结束 ---

        response_data = {
            'status': 'success',
            # 'total': total_source_articles, # 这个 total 意义不大，用下面的代替
            'total_in_date_range': total_in_date_range, # 当前日期范围内的总数
            'page': page,
            'date_page': date_page,
            'total_date_pages': total_date_pages, # 估算的日期总页数
            'per_page': items_per_page, # 当前来源每页数量
            'source': source,
            'date_range': { # 当前查询的日期范围
                'start': start_date.strftime('%Y-%m-%d'),
                'end': end_date.strftime('%Y-%m-%d')
            },
            'data': articles # 已由 db 层序列化
        }

        # 检查是否是 JSONP 请求 (保持兼容性)
        callback = request.args.get('callback')
        if callback:
            # 注意：json.dumps 需要能处理 MongoDB ObjectId 等类型
            # 之前依赖 app.json_encoder，现在 db 层处理了序列化，直接 dumps 即可
            jsonp_response = f"{callback}({json.dumps(response_data)})"
            return Response(jsonp_response, mimetype='application/javascript')

        logger.debug(f"响应数据: {response_data}")
        # 直接使用 jsonify，它能正确处理 dict
        return jsonify(response_data)

    except Exception as e:
        logger.error(f"获取文章列表出错: {e}")
        logger.error(f"错误堆栈: {traceback.format_exc()}")

        # 错误处理也需要检查 JSONP
        callback = request.args.get('callback')
        error_response = {
            'status': 'error',
            'message': '获取文章列表失败，请稍后再试',
            'error': str(e)
        }

        if callback:
            jsonp_response = f"{callback}({json.dumps(error_response)})"
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
    """启动API服务 (用于本地测试)"""
    # 监听 0.0.0.0 允许外部访问
    print("API服务 (本地测试) 已启动，正在监听 http://0.0.0.0:8080")
    # debug=True 方便本地调试
    app.run(host='0.0.0.0', port=8080, debug=True)

if __name__ == '__main__':
    main()

# --- 重新添加 Vercel Serverless Function Handler ---
def handler(environ, start_response):
    """Vercel Serverless Function WSGI handler."""
    # 直接将请求传递给 Flask app
    return app(environ, start_response)