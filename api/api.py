from flask import Flask, jsonify, request
import json
import os
import time
import logging


# 设置日志记录 - 只记录警告和错误
logging.basicConfig(
    level=logging.WARNING,  # 改为WARNING级别
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "api.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("api")

# 获取项目根目录路径
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 静态文件路径
STATIC_DIR = os.path.join(ROOT_DIR, 'static')
# 数据文件路径
DATA_FILE = os.path.join(ROOT_DIR, 'data', 'data.jsonl')

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='')
# 禁用Flask默认日志
app.logger.disabled = True
log = logging.getLogger('werkzeug')
log.disabled = True

# 缓存数据和更新时间
data_cache = None
last_update_time = 0
CACHE_DURATION = 35  # 缓存有效期（秒）


def load_data_from_jsonl():
    """从JSONL文件加载数据"""
    data = []
    if not os.path.exists(DATA_FILE):
        logger.warning(f"{DATA_FILE} 文件不存在")
        return []

    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    item = json.loads(line.strip())
                    data.append(item)
                except json.JSONDecodeError:
                    logger.error(f"无法解析JSONL行: {line}")
                    continue

        # 按日期时间倒序排序（最新的在前面）
        data.sort(key=lambda x: x.get('date_time', ''), reverse=True)
        return data
    except Exception as e:
        logger.error(f"加载数据出错: {e}")
        return []


def get_data():
    """获取数据，使用缓存优化性能"""
    global data_cache, last_update_time

    # 修改: 始终从文件读取最新数据，不使用缓存
    # current_time = time.time()
    # if data_cache is None or (current_time - last_update_time) > CACHE_DURATION:
    #     data_cache = load_data_from_jsonl()
    #     last_update_time = current_time
    # return data_cache
    
    # 直接返回最新数据
    return load_data_from_jsonl()


@app.route('/')
def index():
    """返回静态首页"""
    return app.send_static_file('index.html')


@app.route('/api/news')
def get_news():
    """API端点：获取新闻数据"""
    try:
        data = get_data()

        # 最近一周的数据
        # 如果需要按日期筛选，可以在这里添加筛选逻辑

        # 获取最新更新时间
        last_update = "未知"
        if data and len(data) > 0:
            last_item = data[0]  # 假设数据已按时间倒序排序
            last_update = last_item.get('date_time', '未知')

        return jsonify({
            'status': 'success',
            'count': len(data),
            'last_update': last_update,
            'data': data
        })
    except Exception as e:
        logger.error(f"API请求处理出错: {e}")
        return jsonify({
            'status': 'error',
            'message': '获取数据失败，请稍后再试',
            'error': str(e)
        }), 500


@app.route('/api/search')
def search_news():
    """API端点：搜索新闻数据"""
    try:
        # 获取搜索关键词
        query = request.args.get('q', '').lower()
        if not query:
            return jsonify({
                'status': 'error',
                'message': '请提供搜索关键词'
            }), 400

        # 获取所有数据
        data = get_data()

        # 搜索匹配的内容
        results = []
        for item in data:
            title = item.get('title', '').lower()
            content = item.get('content', '').lower()
            author = item.get('author', '').lower()

            # 使用in运算符进行模糊匹配，而不是精确匹配
            if query in title or query in content or query in author:
                results.append(item)

        # 返回结果
        return jsonify({
            'status': 'success',
            'count': len(results),
            'query': query,
            'data': results,
            'no_results': len(results) == 0  # 添加无结果标志
        })
    except Exception as e:
        logger.error(f"搜索处理出错: {e}")
        return jsonify({
            'status': 'error',
            'message': '搜索处理失败，请稍后再试',
            'error': str(e)
        }), 500


@app.route('/api/sources')
def get_sources():
    """API端点：获取所有数据源列表"""
    try:
        # 获取所有数据
        data = get_data()
        
        # 提取不同的数据源
        sources = {}
        for item in data:
            source = item.get('source', 'unknown')
            if source in sources:
                sources[source] += 1
            else:
                sources[source] = 1
        
        # 转换为列表格式
        source_list = [{"name": source, "count": count} for source, count in sources.items()]
        
        # 按文章数量排序
        source_list.sort(key=lambda x: x["count"], reverse=True)
        
        return jsonify({
            'status': 'success',
            'count': len(source_list),
            'data': source_list
        })
    except Exception as e:
        logger.error(f"获取数据源列表出错: {e}")
        return jsonify({
            'status': 'error',
            'message': '获取数据源列表失败，请稍后再试',
            'error': str(e)
        }), 500


def main():
    """主函数"""
    print("API服务已启动，正在监听 http://0.0.0.0:8080")
    # 预加载数据到缓存
    get_data()
    # 启动Flask应用
    app.run(host='0.0.0.0', port=8080, debug=False)


if __name__ == '__main__':
    main()