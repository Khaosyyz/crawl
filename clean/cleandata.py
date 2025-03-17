from openai import OpenAI
import json
import os
import time
import hashlib
from datetime import datetime
import pytz
import logging
import glob
import re

# 获取项目根目录
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 数据目录
DATA_DIR = os.path.join(ROOT_DIR, 'data')
# 日志目录
LOG_DIR = os.path.join(ROOT_DIR, 'logs')

# 确保目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(os.path.join(ROOT_DIR, 'clean'), exist_ok=True)

# 设置日志记录 - 只记录警告和错误
logging.basicConfig(
    level=logging.WARNING,  # 改为WARNING级别
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "cleandata.log")),  # 保存到logs目录
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("cleandata")

# 常量定义
API_KEY = 'p9mtsT4ioDYm1'
API_BASE_URL = 'https://ai.liaobots.work/v1'
MODEL_NAME = 'grok-3'
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# 初始化 OpenAI 客户端
client = OpenAI(
    api_key=API_KEY,
    base_url=API_BASE_URL
)


# 用于生成唯一ID的函数
def generate_id(text):
    return hashlib.md5(text.encode()).hexdigest()


def get_system_message(source):
    """根据数据源返回相应的系统提示词"""
    if source == "x.com":
        return ("将资讯按以下固定格式整理成中文新闻：\n\n"
                "完整日期时间，格式为YYYY-MM-DD HH:MM\n"
                "根据内容自拟标题，精简且保持吸引力，确保标题中的英文和数字前后都有空格提高可读性\n"
                "资讯内容，不要在内容中包含'详情请查看'或重复来源链接（来源链接会单独保存）\n"
                "作者：[作者名] (@[用户名])\n"
                "粉丝数：[粉丝数] | 点赞：[点赞数] | 转发：[转发数]\n\n"
                "资讯内容和标题都应以新闻文笔优化原文，英文和数字前后必须加空格提高可读性。删除与AI无关的内容或是文本量实在过少，"
                "以至于与 AI 无关的内容。直接输出整理后的资讯，不要在开头或结束添加任何"
                "额外说明、标题或格式符号。不要在正文中描述点赞和转发数据或添加'阅读原文'、'详情请查看'等提示。按发布时间排序，"
                "并在日期时间前依次添加序号，例如1.。")
    elif source == "crunchbase.com":
        return ("你是一位专业的投资信息分析专家，你的任务是将英文Crunchbase文章整理为结构化中文内容。\n\n"
                "直接输出转换后的内容，不要添加任何前言、后语或额外说明。严格按照以下格式输出：\n\n"
                "原文提供的发布时间，YYYY-MM-DD\n"  # 按照格式清洗
                "初创公司XXX完成A轮融资\n"  # 直接给出中文标题，不要加粗、不要加引号或其他格式
                "正文第一段...\n\n正文第二段...\n\n"  # 完整翻译的中文正文，分段清晰
                "作者：原作者姓名\n"  # 原作者信息
                "公司/产品：相关公司名称\n"  # 从文章提取的公司或产品信息
                "投资信息：X亿美元A轮融资，由XX领投\n\n"  # 融资信息摘要，如有\n\n"
                
                "翻译要求：\n"
                "1. 使用简洁流畅的中文表达\n"
                "2. 准确保留所有数字、融资金额、估值等财务数据\n"
                "3. 标题要突出投资亮点，正文完整传达原文信息\n"
                "4. 不要添加任何分隔符（如---、###等）\n"
                "5. 不要使用markdown格式（如**加粗**、###标题等）\n"
                "6. 不要添加序号\n"
                "7. 不要在输出中包含'提示'、'说明'、'格式'等元信息\n"
                "8. 日期格式为'YYYY-MM-DD'，不要加方括号或其他标记\n"
                "9. 英文和数字前后加空格提高可读性，该换行就应该换，不要让内容过于紧凑\n"
                "10. 严格遵循格式，如果原文没有提供明确数据，请用'未知'代替\n")
    else:
        # 默认提示词
        return ("你是一位专业的信息整理专家，请将以下内容整理成结构化的中文资讯：\n\n"
                "[完整日期时间，格式为YYYY-MM-DD HH:MM]\n"
                "自拟标题\n"
                "资讯内容\n"
                "作者信息（如有）\n\n"
                "确保整理后的内容保留原始信息的完整性，文笔流畅，并以新闻报道的形式呈现。")


def clean_data(posts, system_message=None, batch_size=3):
    """清洗和格式化爬取的帖子数据，支持分批处理"""
    if not posts:
        return None

    # 如果帖子数量少于batch_size，直接处理
    if len(posts) <= batch_size:
        return _process_single_batch(posts, system_message)
    
    # 需要分批处理
    logger.info(f"文章数量({len(posts)})超过单批处理上限({batch_size})，启用分批处理")
    
    # 分批处理
    batches = [posts[i:i+batch_size] for i in range(0, len(posts), batch_size)]
    all_cleaned_results = []
    
    for i, batch in enumerate(batches):
        logger.info(f"处理第 {i+1}/{len(batches)} 批，共 {len(batch)} 篇文章")
        batch_result = _process_single_batch(batch, system_message)
        if batch_result:
            all_cleaned_results.append(batch_result)
            # 防止API调用过快
            time.sleep(1)
    
    # 合并结果
    return "\n\n".join(all_cleaned_results)

def _process_single_batch(posts, system_message=None):
    """处理单批次数据"""
    try:
        # 确定数据源
        source = posts[0].get('source', 'unknown') if posts else 'unknown'
        
        # 将所有帖子格式化
        formatted_posts = []
        for i, post in enumerate(posts):
            formatted_text = f"{i + 1}. {post['text']}"
            formatted_posts.append(formatted_text)

        all_posts_text = "\n\n".join(formatted_posts)

        # 如果没有提供系统消息，根据数据源获取
        if system_message is None:
            system_message = get_system_message(source)

        # 调用API
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": all_posts_text}
            ],
            temperature=0.7,
            max_tokens=4000
        )

        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"数据清洗失败: {e}")
        return None


def parse_cleaned_result(cleaned_result, original_data_list=None, source_file=None):
    """将清洗后的文本解析成结构化数据"""
    if not cleaned_result:
        return []
        
    # 创建原始数据映射表，用原始文本为键
    original_data = {}
    if original_data_list:
        for item in original_data_list:
            text = item.get('text', '')
            original_data[text] = item

    # 处理多批次合并的结果
    # 不同批次间可能有重复的序号(如两个批次都有1.2.3.)，需要特殊处理
    news_items = []
    current_item = []
    
    for line in cleaned_result.split('\n'):
        # 检测新文章的开始（序号.日期格式）
        if line.strip() and re.match(r'^\d+\.\s+\d{4}-\d{2}-\d{2}', line.strip()):
            if current_item:  # 保存之前的项目
                news_items.append('\n'.join(current_item))
                current_item = []
            current_item.append(line)
        elif current_item:  # 已经开始收集一个项目
            current_item.append(line)
    
    # 添加最后一个项目
    if current_item:
        news_items.append('\n'.join(current_item))

    parsed_data = []
    global_index = 1

    for news_item in news_items:
        if not news_item.strip():
            continue
            
        lines = news_item.split('\n')
        if not lines or len(lines) < 3:  # 需要至少有日期、标题和内容
            continue

        try:
            # 解析第一行 (序号和日期时间)
            first_line = lines[0].strip()
            date_time = ""

            # 尝试提取序号和日期
            if "." in first_line and first_line.split(".", 1)[0].strip().isdigit():
                number, date_time = first_line.split(".", 1)
                # 使用全局序号替代批次内序号
                item_index = global_index
                global_index += 1
            else:
                date_time = first_line
                item_index = global_index
                global_index += 1

            # 提取标题 (第二行)
            title = lines[1].strip()

            # 提取内容和作者信息
            content_lines = []
            author = ""
            stats = {"followers_count": 0, "favorite_count": 0, "retweet_count": 0}

            i = 2
            while i < len(lines):
                line = lines[i].strip()

                # 检查是否找到作者行
                if line.startswith("作者：") or line.startswith("Author:"):
                    author = line

                    # 检查下一行是否是统计信息
                    if i + 1 < len(lines):
                        stats_line = lines[i + 1].strip()

                        # 解析统计信息
                        if "|" in stats_line:
                            parts = stats_line.split("|")
                            for part in parts:
                                part = part.strip()

                                if "：" in part:  # 中文冒号
                                    key, value = part.split("：", 1)
                                elif ":" in part:  # 英文冒号
                                    key, value = part.split(":", 1)
                                else:
                                    continue

                                key = key.strip().lower()
                                value = value.strip()

                                # 处理可能的 K/M 后缀
                                if value.endswith("K") or value.endswith("k"):
                                    value = float(value[:-1]) * 1000
                                elif value.endswith("M") or value.endswith("m"):
                                    value = float(value[:-1]) * 1000000

                                try:
                                    value = int(float(value))
                                except:
                                    value = 0

                                if "粉丝" in key or "followers" in key:
                                    stats["followers_count"] = value
                                elif "点赞" in key or "like" in key or "favorite" in key:
                                    stats["favorite_count"] = value
                                elif "转发" in key or "retweet" in key:
                                    stats["retweet_count"] = value

                    break  # 找到作者后退出循环
                else:
                    # 如果不是作者行，则添加到内容中
                    content_lines.append(line)

                i += 1

            content = "\n".join(content_lines).strip()
            
            # 标准化内容中的标点符号，确保以句号结尾
            content = standardize_punctuation(content)

            # 确保日期时间格式一致
            date_time = date_time.strip()
            
            # 确定数据来源（默认为unknown）
            source = "unknown"
            source_url = ""  # 初始化source_url变量
            
            # 尝试从原始数据中找到匹配的item来获取source和source_url
            for original_text, original_item in original_data.items():
                if original_text in content or content in original_text:
                    source = original_item.get('source', 'unknown')
                    # 优先使用原始数据中的source_url
                    if 'source_url' in original_item and original_item['source_url']:
                        source_url = original_item['source_url']
                    # 检查raw字段中是否有url，对于X爬虫数据特别有用
                    elif 'raw' in original_item and 'url' in original_item['raw']:
                        source_url = original_item['raw']['url']
                    break
            
            # 根据文件名修正source
            if source == "unknown" and source_file:
                if 'x_tempdata.json' in source_file:
                    source = 'x.com'
                elif 'cru_tempdata.json' in source_file:
                    source = 'crunchbase.com'
            
            # 二次查找源URL - 针对X数据特殊处理
            if not source_url and source == 'x.com':
                # 在所有原始数据中寻找可能的URL
                for original_text, original_item in original_data.items():
                    if 'raw' in original_item and 'url' in original_item['raw']:
                        # 尝试通过用户名匹配
                        if author and original_item.get('raw', {}).get('username', '') in author:
                            source_url = original_item['raw']['url']
                            break
            
            # 针对Crunchbase的特殊处理 - 确保日期格式正确（只有日期，没有时间）
            if source == 'crunchbase.com':
                # 提取日期部分，移除可能的时间部分
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_time)
                if date_match:
                    date_time = date_match.group(1)  # 只保留日期部分YYYY-MM-DD
            
            # 生成唯一ID，包含全局序号确保唯一性
            item_id = generate_id(f"{item_index}_{date_time}_{title}_{content[:50]}")

            # 只有当原始数据中没有source_url时，才尝试从内容中提取
            if not source_url and 'http' in content:
                try:
                    # 提取第一个URL
                    url_match = re.search(r'https?://[^\s]+', content)
                    if url_match:
                        source_url = url_match.group()
                        # 如果URL后面有标点符号，去除
                        source_url = re.sub(r'[.,;:!?)]+$', '', source_url)
                        
                        # 从content中移除提取的URL，避免重复
                        # 先尝试直接替换URL
                        cleaned_content = content.replace(source_url, '')
                        # 如果替换后的内容看起来合理，就使用它
                        if len(cleaned_content) > len(content) * 0.5:  # 确保删除URL后内容仍然有足够长度
                            # 清理多余空格和可能出现的双重标点
                            cleaned_content = re.sub(r'\s+', ' ', cleaned_content).strip()
                            cleaned_content = re.sub(r'([.,;:!?])\s*\1', r'\1', cleaned_content)
                            content = cleaned_content
                except Exception as e:
                    logger.warning(f"从内容中提取或移除URL失败: {e}")
            
            # 添加到解析结果
            parsed_data.append({
                "id": item_id,
                "index": item_index,  # 添加全局序号
                "date_time": date_time,
                "title": title,
                "content": content,
                "author": author,
                "stats": stats,
                "cleaned_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "source": source,
                "source_url": source_url,  # 添加source_url字段
                "formatted_for_readability": True  # 标记已经格式化
            })
        except Exception as e:
            logger.error(f"解析新闻项时出错: {e}")
            continue

    return parsed_data


def standardize_punctuation(content):
    """标准化内容中的标点符号，确保以句号结尾"""
    if not content:
        return ""
    
    # 移除末尾所有的标点符号和空格
    cleaned = re.sub(r'[.,，、;；:：!！?？\s]+$', '', content)
    
    # 确保内容不为空
    if not cleaned.strip():
        return ""
    
    # 添加句号结尾
    cleaned = cleaned.strip() + '。'
    
    # 修复可能的重复句号
    cleaned = re.sub(r'。+$', '。', cleaned)
    
    return cleaned.strip()


def save_to_jsonl(parsed_data):
    """将解析后的数据追加保存到JSONL文件"""
    if not parsed_data:
        return 0

    # 获取现有URL集合用于去重
    existing_urls = set()
    
    # 从现有数据中提取URLs以进行去重
    data_jsonl_path = os.path.join(DATA_DIR, 'data.jsonl')
    if os.path.exists(data_jsonl_path):
        with open(data_jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    item = json.loads(line.strip())
                    # 使用source_url字段而不是从内容提取
                    if 'source_url' in item and item['source_url']:
                        existing_urls.add(item['source_url'])
                except Exception:
                    continue

    saved_count = 0
    with open(os.path.join(DATA_DIR, 'data.jsonl'), 'a', encoding='utf-8') as f:
        for item in parsed_data:
            # 使用source_url字段进行去重
            source_url = item.get('source_url', '')
            if source_url and source_url in existing_urls:
                # 这个URL已经存在，跳过
                continue
                
            # 保存此项
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
            saved_count += 1
            
            # 添加到已存在URL集合
            if source_url:
                existing_urls.add(source_url)

    return saved_count


def process_temp_data(batch_size=10):
    """处理临时存储的数据，清洗后追加到永久存储，支持分批处理"""
    # 获取data目录下所有*_tempdata.json文件
    temp_data_files = glob.glob(os.path.join(DATA_DIR, '*_tempdata.json'))
    
    if not temp_data_files:
        logger.info("未找到任何临时数据文件")
        return 0
    
    total_saved_count = 0
    
    for temp_data_path in temp_data_files:
        source_name = os.path.basename(temp_data_path).replace('_tempdata.json', '')
        logger.info(f"开始处理来自 {source_name} 的临时数据")
        
        if not os.path.exists(temp_data_path):
            continue

        try:
            # 读取临时数据
            try:
                with open(temp_data_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content or content == '[]':
                        logger.info(f"文件 {temp_data_path} 为空或只包含空数组，跳过处理")
                        continue
                    temp_data = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析错误（{temp_data_path}）: {e}，尝试重置文件为空数组")
                # 重置为空数组
                with open(temp_data_path, 'w', encoding='utf-8') as f:
                    f.write('[]')
                continue

            if not temp_data:
                # 文件为空，跳过处理
                logger.info(f"文件 {temp_data_path} 解析后为空，跳过处理")
                continue
            
            # 检查是否所有数据都有source字段
            for item in temp_data:
                if 'source' not in item:
                    # 尝试从raw字段中获取source
                    if 'raw' in item and 'source' in item['raw']:
                        item['source'] = item['raw']['source']
                    else:
                        # 根据文件名设置source
                        if 'x_tempdata.json' in temp_data_path:
                            item['source'] = 'x.com'
                        elif 'cru_tempdata.json' in temp_data_path:
                            item['source'] = 'crunchbase.com'
                        else:
                            item['source'] = source_name
                        logger.info(f"数据项缺少source字段，根据文件名设置为{item['source']}")

            # 确定数据源以获取正确的系统提示词
            source = temp_data[0].get('source', 'unknown') if temp_data else 'unknown'
            system_message = get_system_message(source)
            
            # 分批清洗数据
            cleaned_result = clean_data(temp_data, system_message, batch_size)

            if cleaned_result:
                # 解析清洗后的结果
                parsed_data = parse_cleaned_result(cleaned_result, temp_data, temp_data_path)

                # 保存到永久存储
                saved_count = save_to_jsonl(parsed_data)
                total_saved_count += saved_count
                logger.info(f"已从 {source} 保存 {saved_count} 条数据")

                # 清空临时存储
                with open(temp_data_path, 'w', encoding='utf-8') as f:
                    json.dump([], f)
            else:
                logger.warning(f"{source} 数据清洗失败，未能获取有效结果")

        except Exception as e:
            logger.error(f"处理 {source_name} 临时数据出错: {e}")
            import traceback
            traceback.print_exc()
    
    return total_saved_count


def ensure_jsonl_file_exists():
    """确保data.jsonl文件存在"""
    if not os.path.exists(os.path.join(DATA_DIR, 'data.jsonl')):
        with open(os.path.join(DATA_DIR, 'data.jsonl'), 'w', encoding='utf-8') as f:
            pass  # 创建空文件


def main():
    """主函数-持续监控临时数据并处理"""
    print("数据清洗服务已启动，正在监控新数据...")
    ensure_jsonl_file_exists()

    # 设置合适的批处理大小，较小的批次可以避免超出AI上下文窗口
    default_batch_size = 10  # 默认批次大小
    batch_size_for_crunchbase = 5  # Crunchbase数据专用的较小批次大小，因其文章较长

    try:
        while True:
            # 检查是否存在Crunchbase临时数据
            cru_temp_data_path = os.path.join(DATA_DIR, 'cru_tempdata.json')
            if os.path.exists(cru_temp_data_path) and os.path.getsize(cru_temp_data_path) > 100:
                # 获取文件大小，判断是否需要使用更小的批大小
                file_size_mb = os.path.getsize(cru_temp_data_path) / (1024 * 1024)
                
                if file_size_mb > 0.5:  # 如果文件大于500KB
                    print(f"检测到大体积Crunchbase数据文件 ({file_size_mb:.2f}MB)，使用更小批次 {batch_size_for_crunchbase}")
                    saved_count = process_temp_data(batch_size_for_crunchbase)
                else:
                    saved_count = process_temp_data(default_batch_size)
            else:
                # 正常处理所有临时数据
                saved_count = process_temp_data(default_batch_size)
                
            if saved_count > 0:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 新处理了 {saved_count} 条数据")
            
            # 静默等待
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n数据清洗服务已停止")
    except Exception as e:
        logger.error(f"运行出错: {e}")
        import traceback
        traceback.print_exc()



if __name__ == "__main__":
    main()