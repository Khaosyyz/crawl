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
# 注意：在 Vercel Serverless 环境中，写入文件系统可能受限或非持久化
# 仅使用 StreamHandler 以避免文件系统权限问题
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("api")

app = Flask(__name__)
# 配置 CORS，允许所有域名访问
CORS(app) # 简化配置，允许所有来源，如果需要更严格控制，可以配置 origins

# 禁用Flask默认日志
app.logger.disabled = True
log = logging.getLogger('werkzeug')
log.disabled = True

# 初始化MongoDB连接 (包装在 try-except 中)
try:
    db = MongoDB()
    logger.info("MongoDB 连接初始化成功")
except Exception as e:
    logger.error(f"初始化 MongoDB 连接失败: {e}")
    logger.error(traceback.format_exc())
    db = None  # 设置为 None，以便后续检查

@app.route('/api/articles')
def get_articles():
    """API端点：获取文章列表，支持来源过滤、分页和日期分页"""
    # 检查数据库连接状态
    if db is None:
        logger.error("数据库连接不可用，无法获取文章")
        return jsonify({
            'status': 'error',
            'message': '数据库连接失败，请稍后重试'
        }), 500
        
    try:
        # 获取分页参数
        page = int(request.args.get('page', 1))
        date_page = int(request.args.get('date_page', 1))
        source = request.args.get('source', 'x.com') # 默认源改为 x.com

        # 根据来源确定每页项目数
        items_per_page = 9 if source == 'x.com' else 3

        # 构建基础查询条件
        base_query = {'source': source}

        # --- 合并 api/articles.py 的日期范围逻辑 ---
        reference_date = None
        tz_shanghai = pytz.timezone('Asia/Shanghai')
        
        try:
            # 获取最新文章以确定参考日期
            newest_article = db.get_articles(
                query={'source': source},
                limit=1,
                sort=[('date_time', -1)]
            )
            
            if newest_article and newest_article[0].get('date_time'):
                try:
                    # 处理不同类型的日期值
                    dt_obj = newest_article[0]['date_time']
                    
                    if isinstance(dt_obj, str):
                        # 尝试解析 ISO 格式字符串，处理 'Z'
                        dt_obj = dt_obj.replace('Z', '+00:00')
                        if 'T' in dt_obj:  # ISO 格式
                            dt_obj = datetime.datetime.fromisoformat(dt_obj)
                        else:  # 可能是自定义格式
                            try:
                                dt_obj = datetime.datetime.strptime(dt_obj, '%Y-%m-%d %H:%M:%S')
                            except ValueError:
                                logger.error(f"无法解析日期字符串: {dt_obj}，尝试其他格式")
                                # 尝试其他常见格式
                                formats = ['%Y-%m-%d', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y']
                                for fmt in formats:
                                    try:
                                        dt_obj = datetime.datetime.strptime(dt_obj, fmt)
                                        break
                                    except ValueError:
                                        continue
                    
                    if isinstance(dt_obj, datetime.datetime):
                        # 确保时区感知
                        if dt_obj.tzinfo is None or dt_obj.tzinfo.utcoffset(dt_obj) is None:
                            dt_obj = pytz.utc.localize(dt_obj)  # 假设是 UTC
                        reference_date = dt_obj.astimezone(tz_shanghai)
                        logger.info(f"使用数据库中最新文章日期作为参考: {reference_date}")
                    else:
                        logger.error(f"数据库返回的日期类型未知: {type(dt_obj)}，使用当前时间")
                        reference_date = datetime.datetime.now(tz_shanghai)
                        
                except Exception as date_parse_e:
                    logger.error(f"解析最新文章日期时发生错误: {date_parse_e}，使用当前时间")
                    reference_date = datetime.datetime.now(tz_shanghai)
        except Exception as e:
            logger.error(f"获取最新文章日期失败: {e}，使用当前时间")

        if reference_date is None:
            reference_date = datetime.datetime.now(tz_shanghai)
            logger.info(f"未能确定参考日期，使用当前系统时间: {reference_date}")

        # 日期分页处理 (每页 2 天)
        start_days_ago = (date_page - 1) * 2
        end_days_ago = start_days_ago + 2

        # 计算日期范围 - 使用参考日期
        start_date = (reference_date - datetime.timedelta(days=end_days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = (reference_date - datetime.timedelta(days=start_days_ago)).replace(hour=23, minute=59, second=59, microsecond=999999)

        # 转换为字符串格式进行查询 (因为数据库中存储的可能是字符串)
        start_date_str = start_date.strftime('%Y-%m-%d %H:%M:%S')
        end_date_str = end_date.strftime('%Y-%m-%d %H:%M:%S')
        
        # 日期部分（不含时间）
        start_date_only = start_date.strftime('%Y-%m-%d')
        end_date_only = end_date.strftime('%Y-%m-%d')
        
        # 同时尝试多种日期格式查询
        date_query = {
            '$or': [
                # 尝试完整日期时间字符串格式匹配 (标准格式)
                {'date_time': {'$gte': start_date_str, '$lte': end_date_str}},
                # 尝试ISO格式匹配
                {'date_time': {'$gte': start_date.isoformat(), '$lte': end_date.isoformat()}},
                # 尝试只匹配日期部分 (最常见格式)
                {'date_time': {'$regex': f"^{start_date_only}"}},
                # 尝试匹配日期范围的任何一天 (更宽松的匹配)
                {'date_time': {'$regex': f"^2025-03-"}},
                # 尝试日期对象匹配
                {'date_time': {'$gte': start_date, '$lte': end_date}}
            ]
        }
        
        logger.info(f"查询日期范围: {start_date.isoformat()} 到 {end_date.isoformat()}")
        logger.info(f"日期查询条件: {date_query}")

        # 添加调试查询 - 不带日期限制先查一下
        try:
            # 查询5篇最新文章
            test_articles = db.get_articles(
                query={'source': source},
                limit=5,
                sort=[('date_time', -1)]
            )
            
            logger.info(f"测试查询 source={source} 结果: 找到 {len(test_articles)} 篇文章")
            if test_articles:
                for idx, article in enumerate(test_articles):
                    date_val = article.get('date_time', '无日期')
                    title = article.get('title', '无标题')[:30]
                    logger.info(f"测试文章 {idx+1}: 日期={date_val}, 类型={type(date_val)}, 标题={title}")
        except Exception as e:
            logger.error(f"测试查询失败: {e}")

        # 合并查询条件
        query = {**base_query, **date_query}
        logger.info(f"最终查询条件: {query}")
        # --- 日期范围逻辑结束 ---

        # 计算跳过的记录数
        skip = (page - 1) * items_per_page

        # 获取当前日期范围和页面的文章总数 (用于分页)
        total_in_date_range = db.get_article_count(query)
        logger.info(f"查询条件下找到的文章总数: {total_in_date_range}")

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
                    # 处理不同类型的日期值
                    oldest_dt_obj = oldest_article[0]['date_time']
                    
                    if isinstance(oldest_dt_obj, str):
                        oldest_dt_obj = oldest_dt_obj.replace('Z', '+00:00')
                        if 'T' in oldest_dt_obj:  # ISO 格式
                            oldest_dt_obj = datetime.datetime.fromisoformat(oldest_dt_obj)
                        else:  # 可能是自定义格式
                            try:
                                oldest_dt_obj = datetime.datetime.strptime(oldest_dt_obj, '%Y-%m-%d %H:%M:%S')
                            except ValueError:
                                # 尝试其他常见格式
                                formats = ['%Y-%m-%d', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y']
                                for fmt in formats:
                                    try:
                                        oldest_dt_obj = datetime.datetime.strptime(oldest_dt_obj, fmt)
                                        break
                                    except ValueError:
                                        continue
                    
                    if isinstance(oldest_dt_obj, datetime.datetime):
                        if oldest_dt_obj.tzinfo is None or oldest_dt_obj.tzinfo.utcoffset(oldest_dt_obj) is None:
                            oldest_dt_obj = pytz.utc.localize(oldest_dt_obj)
                        oldest_date_sh = oldest_dt_obj.astimezone(tz_shanghai)
                        
                        # 使用最新的 reference_date 来计算差异 (确保都是 date 对象)
                        days_diff = (reference_date.date() - oldest_date_sh.date()).days
                        total_date_pages = max(1, (days_diff // 2) + 1) # 每页2天, 至少1页
                        logger.info(f"最早文章日期: {oldest_date_sh}, 天数差: {days_diff}, 总日期页数: {total_date_pages}")
                except Exception as e:
                    logger.error(f"解析最早文章日期时发生错误: {e}")
        except Exception as e:
            logger.error(f"获取最早文章日期失败: {e}")
        # --- 日期分页总数逻辑结束 ---

        response_data = {
            'status': 'success',
            'total_in_date_range': total_in_date_range,
            'page': page,
            'date_page': date_page,
            'total_date_pages': total_date_pages,
            'per_page': items_per_page,
            'source': source,
            'date_range': {
                'start': start_date.strftime('%Y-%m-%d'),
                'end': end_date.strftime('%Y-%m-%d')
            },
            'data': articles # 已由 db 层序列化
        }

        # 检查是否是 JSONP 请求 (保持兼容性)
        callback = request.args.get('callback')
        if callback:
            jsonp_response = f"{callback}({json.dumps(response_data)})"
            return Response(jsonp_response, mimetype='application/javascript')

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
    if db is None:
        logger.error("数据库连接不可用，无法获取文章详情")
        return jsonify({
            'status': 'error',
            'message': '数据库连接失败，请稍后重试'
        }), 500
        
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
        logger.error(f"获取文章详情出错 (ID: {article_id}): {e}")
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        return jsonify({
            'status': 'error',
            'message': '获取文章详情失败，请稍后再试',
            'error': str(e)
        }), 500

@app.route('/api/search')
def search_articles():
    """API端点：全文搜索文章"""
    if db is None:
        logger.error("数据库连接不可用，无法执行搜索")
        return jsonify({
            'status': 'error',
            'message': '数据库连接失败，请稍后重试'
        }), 500
        
    try:
        query_term = request.args.get('q', '') # 使用 query_term 避免与 MongoDB 查询变量混淆
        if not query_term:
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
        if source:
            search_criteria['source'] = source

        logger.info(f"搜索关键词: '{query_term}', 来源: {source}, 页面: {page}, 每页: {per_page}")
            
        # 调用 db 层的搜索方法
        results, total_results = db.search_articles(
            query_term=query_term,
            query_filter=search_criteria, # 传递过滤条件
            page=page,
            per_page=per_page
        )
        
        return jsonify({
            'status': 'success',
            'query': query_term,
            'total': total_results,
            'page': page,
            'per_page': per_page,
            'source_filter': source, # 返回当前使用的来源过滤器
            'data': results # db 层应处理序列化
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
    """API端点：获取数据库统计信息"""
    if db is None:
        logger.error("数据库连接不可用，无法获取统计信息")
        return jsonify({
            'status': 'error',
            'message': '数据库连接失败，请稍后重试'
        }), 500
        
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

# 添加一个简单的健康检查接口，用于验证 API 是否正常运行
@app.route('/api/health')
def health_check():
    """API端点：健康检查"""
    try:
        # 如果数据库连接可用，执行简单查询验证连接
        db_status = "连接正常" if db and hasattr(db, 'check_connection') and db.check_connection() else "未连接"
    except Exception as e:
        logger.error(f"健康检查中数据库连接测试失败: {e}")
        db_status = f"连接错误: {str(e)}"
    
    response = {
        'status': 'online',
        'timestamp': datetime.datetime.now().isoformat(),
        'database': db_status,
        'environment': os.environ.get('VERCEL_ENV', 'development')
    }
    return jsonify(response)

@app.route('/api/all-articles')
def get_all_articles():
    """API端点：获取所有文章（不进行日期过滤，仅用于测试）"""
    if db is None:
        logger.error("数据库连接不可用，无法获取文章")
        return jsonify({
            'status': 'error',
            'message': '数据库连接失败，请稍后重试'
        }), 500
        
    try:
        # 获取分页参数
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        # 获取数据源过滤参数
        source = request.args.get('source', 'x.com')  # 默认源改为 x.com
        
        # 构建基础查询条件
        query = {'source': source}
        
        # 计算跳过的记录数
        skip = (page - 1) * per_page
        
        # 获取总文章数
        total_articles = db.get_article_count(query)
        logger.info(f"查询条件 {query} 下找到的文章总数: {total_articles}")
        
        # 获取分页数据
        articles = db.get_articles(
            query=query,
            skip=skip,
            limit=per_page,
            sort=[('date_time', -1)]  # 按时间倒序排序
        )
        logger.info(f"为页面 {page} 获取到文章列表: {len(articles)} 篇")
        
        # 处理返回值
        response_data = {
            'status': 'success',
            'total': total_articles,
            'page': page,
            'per_page': per_page,
            'source': source,
            'data': articles,
            'message': '这是测试API，返回所有文章而不进行日期过滤'
        }
        
        # 检查是否是 JSONP 请求
        callback = request.args.get('callback')
        if callback:
            jsonp_response = f"{callback}({json.dumps(response_data)})"
            return Response(jsonp_response, mimetype='application/javascript')
            
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"获取所有文章列表出错: {e}")
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        
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

# 注意：移除了 main() 和 handler() 函数
# Vercel Serverless Functions 直接查找名为 'app' 的 Flask 实例