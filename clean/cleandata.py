"""
数据清洗模块 - 将爬取的原始数据清洗为结构化内容
支持多种数据源，包括X.com和Crunchbase等
每种数据源使用独立的处理逻辑
"""

from openai import OpenAI
import json
import os
import time
import hashlib
from datetime import datetime
import logging
import glob
import re
import traceback
from typing import List, Dict, Any, Optional, Union
import random
import signal
import sys
import platform
import threading

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from clean.storage import DataStorage

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

# 导入自定义日志处理模块
try:
    sys.path.append(LOG_DIR)
    from log_handler import setup_logger, start_log_cleanup_thread
    
    # 配置日志记录
    logger = setup_logger(
        name="cleandata",
        log_file=os.path.join(LOG_DIR, "cleandata.log"),
        level=logging.INFO,
        console_output=True
    )
    
    # 启动日志清理线程
    cleanup_thread = start_log_cleanup_thread(LOG_DIR)
    
except ImportError:
    # 如果导入失败，回退到标准日志配置
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(LOG_DIR, "cleandata.log")),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger("cleandata")
    logger.warning("无法导入自定义日志处理模块，使用标准日志配置")

# 创建全局线程锁用于保护文件操作
jsonl_lock = threading.Lock()

# 常量定义
API_KEY = 'p9mtsT4ioDYm1'
API_BASE_URL = 'https://ai.liaobots.work/v1'
MODEL_NAME = 'deepseek-v3-0324'  # 中文性能更优的模型

# 控制API请求频率的参数
BATCH_SIZE = 5  # 每批处理的数据量
BATCH_INTERVAL = 25  # 批处理间隔（秒）

# 临时数据文件路径
X_TEMP_DATA_PATH = os.path.join(DATA_DIR, 'x_tempdata.json')
CRU_TEMP_DATA_PATH = os.path.join(DATA_DIR, 'cru_tempdata.json')

# 初始化 OpenAI 客户端
client = OpenAI(
    api_key=API_KEY,
    base_url=API_BASE_URL
)

# 工具函数
def generate_id(text: str) -> str:
    """生成唯一ID"""
    return hashlib.md5(text.encode()).hexdigest()

# 系统提示词管理
class SystemPrompts:
    """系统提示词管理类，为不同数据源提供专用提示词"""
    
    @staticmethod
    def get_x_prompt() -> str:
        """获取处理X.com数据的系统提示词"""
        return """你是一位专业的AI行业资讯整理师，请将X.com上的推文整理为标准的新闻格式。

第一步：必须完整翻译成准确流畅的中文，保持专业术语的准确性。

第二步：严格判断内容是否与AI技术相关。判断标准：
- 内容必须明确涉及AI技术、大模型、机器学习、深度学习等人工智能核心技术
- 或讨论AI应用、产品发布、研究进展、商业动态
- 或分析AI行业趋势、伦理问题、监管政策等
- 拒绝仅因包含"智能"、"算法"等宽泛词汇而非真正AI相关的内容
- 拒绝表情符号过多、内容质量低的无价值信息

第三步：如果内容确实与AI相关，按以下格式返回：

标题: [25字以内的专业新闻标题，简洁并富有吸引力]
正文: [组织为清晰的中文新闻报道，分段合理，保留专业术语，删除冗余信息。将URL链接替换为适当描述，如"——报告链接：@URL"等]
作者: [原作者名] (@[用户名])
粉丝数: [数值]
点赞数: [数值]
转发数: [数值]
日期: [YYYY-MM-DD HH:MM格式]

处理要求：
1. 对非AI相关内容，不返回任何结构化字段
2. 精心编写标题，25字以内，专业准确，避免"相关"、"关于"等模糊用词
3. 正文保持信息完整性和专业性，确保段落和句子逻辑清晰
4. 对AI专业词汇，保留原文术语如"GPT-4"，并提供适当中文说明
5. 不要生成含有大量表情符号的内容
6. 不要在回复中添加额外解释或元信息"""
    
    @staticmethod
    def get_crunchbase_prompt() -> str:
        """获取处理Crunchbase数据的系统提示词"""
        return """你是一位专业的AI行业投资信息整理师，请将Crunchbase融资或投资文章处理为标准的新闻格式。

第一步：将内容完整翻译成准确专业的中文。

第二步：严格判断内容是否与AI行业投资相关。判断标准：
- 必须涉及AI技术公司、AI产品或服务的融资、收购或投资活动
- 或AI相关技术创业、风险投资、市场拓展等商业活动
- 拒绝与人工智能无明显关联的一般科技投融资新闻
- 拒绝表情符号过多、内容质量低的无价值信息

第三步：如果确定是AI相关投资内容，按以下格式返回：

标题: ["公司名+融资金额+轮次"格式，25字以内，准确专业]
正文: [组织为专业投资新闻报道，3-5段结构，首段概述融资情况，后续介绍公司、技术和产品，最后提及投资方信息]
作者: [原作者姓名，若无则填"未提供"]
公司: [相关公司名称]
融资轮次: [种子轮/A轮等具体轮次]
融资金额: [包含货币单位的金额]
投资方: [投资机构或个人名称]
日期: [YYYY-MM-DD格式]

处理要求：
1. 对非AI相关投资内容，不返回任何结构化字段
2. 精心编写标题，确保格式统一且专业
3. 正文内容必须分段清晰，每段逻辑完整，总体结构合理
4. 务必准确提取融资金额、轮次和投资方信息
5. 保留重要专有名词的原文表示，如"OpenAI"
6. 不要在回复中添加额外解释或元信息"""
    
    @staticmethod
    def get_default_prompt() -> str:
        """获取默认的系统提示词，用于未知数据源"""
        return ("你是一位专业的信息整理专家，请将以下内容整理成结构化的中文资讯：\n\n"
                "[完整日期时间，格式为YYYY-MM-DD HH:MM]\n"
                "自拟标题\n"
                "资讯内容\n"
                "作者信息（如有）\n\n"
                "确保整理后的内容保留原始信息的完整性，文笔流畅，并以新闻报道的形式呈现。")
    
    @staticmethod
    def get_for_source(source: str) -> str:
        """根据数据源获取相应的系统提示词"""
        if source == "x.com":
            return SystemPrompts.get_x_prompt()
        elif source == "crunchbase.com":
            return SystemPrompts.get_crunchbase_prompt()
        else:
            return SystemPrompts.get_default_prompt()


class TextUtils:
    """文本处理工具类"""
    
    @staticmethod
    def standardize_punctuation(content: str) -> str:
        """标准化内容中的标点符号，确保以句号结尾，但保留内容中的换行符"""
        if not content:
            return ""
        
        # 处理段落间的空行，确保段落有统一的间距
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        # 修复中文标点使用错误，例如逗号后缺少空格
        content = re.sub(r'([，。！？；：])([^\s])', r'\1 \2', content)
        
        # 确保内容以句号结尾
        content = content.rstrip()
        if content and not content[-1] in '。！？.!?':
            content += '。'
            
        return content
    
    @staticmethod
    def format_crunchbase_content(content: str) -> str:
        """格式化Crunchbase内容，为具体链接添加标签等处理"""
        if not content:
            return ""
            
        # 处理链接格式，规范为统一形式
        content = re.sub(r'(https?://\S+)', r'[链接地址: \1]', content)
            
        # 分段处理，确保每段不超过300字符
        paragraphs = content.split('\n\n')
        formatted_paragraphs = []
        
        for p in paragraphs:
            if len(p) > 300:
                # 尝试在句子边界分段
                sentences = re.split(r'(?<=[。！？.!?])\s*', p)
                current_para = ""
                
                for s in sentences:
                    if not s.strip():
                        continue
                    if len(current_para) + len(s) > 300:
                        if current_para:
                            formatted_paragraphs.append(current_para)
                        current_para = s
                    else:
                        current_para += (" " if current_para else "") + s
                
                if current_para:
                    formatted_paragraphs.append(current_para)
            else:
                formatted_paragraphs.append(p)
                
        return "\n\n".join(formatted_paragraphs)


class DataProcessor:
    """数据处理器基类"""
    
    def __init__(self):
        """初始化数据处理器"""
        self.storage = DataStorage()
        self.model = MODEL_NAME
        self.client = client
    
    def process(self) -> int:
        """处理数据的主方法，子类必须实现此方法"""
        raise NotImplementedError("子类必须实现process方法")
    
    def _call_ai_api(self, system_message: str, prompt: str) -> str:
        """调用AI API进行处理"""
        logger.info(f"准备调用AI API，系统提示词长度: {len(system_message)}，用户提示词长度: {len(prompt)}")
        
        max_retries = 5
        initial_retry_delay = 3.0
        max_retry_delay = 30.0
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"第 {attempt}/{max_retries} 次尝试调用AI API")
                start_time = time.time()
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1
                )
                
                elapsed_time = time.time() - start_time
                logger.info(f"API调用成功，耗时: {elapsed_time:.2f} 秒")
                
                if response.choices and len(response.choices) > 0:
                    result_text = response.choices[0].message.content
                    logger.info(f"API返回结果长度: {len(result_text)}")
                    return result_text
                else:
                    logger.warning("API返回结果为空或格式不正确")
                    return ""
                
            except Exception as e:
                retry_delay = min(initial_retry_delay * (2 ** (attempt - 1)), max_retry_delay)
                
                if attempt < max_retries:
                    if "Connection" in str(e) or "Timeout" in str(e):
                        logger.warning(f"API连接错误 (尝试 {attempt}/{max_retries}): {str(e)}")
                    elif "rate limit" in str(e).lower():
                        logger.warning(f"API速率限制 (尝试 {attempt}/{max_retries}): {str(e)}")
                    else:
                        logger.warning(f"API调用失败 (尝试 {attempt}/{max_retries}): {str(e)}")
                    # 增加错误重试延迟
                    logger.info(f"等待 {retry_delay:.1f} 秒后重试...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"API调用最终失败: {str(e)}")
                    return ""
        
        return ""


class XDataProcessor(DataProcessor):
    """X平台数据处理器"""
    
    def process(self) -> int:
        """处理X数据"""
        logger.info("开始处理X平台数据")
        
        # 检查临时文件是否存在
        if not os.path.exists(X_TEMP_DATA_PATH):
            logger.info("未找到X平台临时数据文件")
            return 0
        
        # 读取临时数据
        try:
            with open(X_TEMP_DATA_PATH, 'r', encoding='utf-8') as f:
                temp_data = json.load(f)
            
            if not temp_data:
                logger.info("X平台临时数据为空")
                return 0
            
            logger.info(f"读取到 {len(temp_data)} 条X平台原始数据")
            
            # 批量处理数据，每批处理 BATCH_SIZE 条
            processed_count = 0
            stored_count = 0
            
            # 添加批处理和间隔逻辑
            for i in range(0, len(temp_data), BATCH_SIZE):
                batch = temp_data[i:i+BATCH_SIZE]
                logger.info(f"处理批次 {i//BATCH_SIZE + 1}/{(len(temp_data)-1)//BATCH_SIZE + 1}，共 {len(batch)} 条数据")
                
                # 处理当前批次
                for item in batch:
                    processed_item = self._process_x_item(item)
                    if processed_item:
                        # 存储处理后的数据
                        if self.storage.store(processed_item):
                            stored_count += 1
                        processed_count += 1
                
                # 如果不是最后一批，等待一段时间再处理下一批
                if i + BATCH_SIZE < len(temp_data):
                    logger.info(f"批处理完成，等待 {BATCH_INTERVAL} 秒后处理下一批...")
                    time.sleep(BATCH_INTERVAL)
            
            # 处理完成后清空临时文件
            if processed_count > 0:
                try:
                    # 清空原始临时文件，但保留文件
                    with open(X_TEMP_DATA_PATH, 'w', encoding='utf-8') as f:
                        json.dump([], f)
                    
                    logger.info("临时数据已处理完毕，已清空原始文件")
                except Exception as e:
                    logger.error(f"清空临时数据出错: {e}")
            
            logger.info(f"X平台数据处理完成，处理 {processed_count} 条，成功存储 {stored_count} 条")
            return processed_count
            
        except Exception as e:
            logger.error(f"处理X平台数据出错: {e}")
            logger.error(traceback.format_exc())
            return 0
    
    def _process_x_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理单条X平台数据"""
        try:
            # 准备输入文本
            raw_data = item.get('raw', {})
            author_name = raw_data.get('name', '')
            author_username = raw_data.get('username', '')
            
            input_text = (
                f"推文内容: {item.get('text', '')}\n\n"
                f"作者: {author_name} (@{author_username})\n"
                f"粉丝数: {raw_data.get('followers_count', 0)}\n"
                f"点赞数: {raw_data.get('favorite_count', 0)}\n"
                f"转发数: {raw_data.get('retweet_count', 0)}\n"
                f"发布时间: {item.get('date_time', '')}"
            )
            
            # 获取系统提示词
            system_prompt = SystemPrompts.get_for_source("x.com")
            
            # 调用AI处理
            result = self._call_ai_api(system_prompt, input_text)
            
            # 如果结果为空，可能是非AI相关内容，跳过
            if not result or len(result.strip()) < 10:
                logger.info("内容可能不相关或处理结果为空，跳过")
                return None
            
            # 解析处理结果
            return self._parse_x_result(result, item)
            
        except Exception as e:
            logger.error(f"处理X数据项出错: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def _parse_x_result(self, result: str, original_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析AI处理后的X平台结果"""
        try:
            lines = result.split('\n')
            parsed = {}
            
            # 提取字段
            current_field = None
            content_lines = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if ':' in line and not line.startswith('http') and not line.startswith('——'):
                    # 如果有新字段开始，先保存之前收集的正文内容
                    if current_field == 'content' and content_lines:
                        parsed['content'] = '\n'.join(content_lines)
                        content_lines = []
                    
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    current_field = None
                    
                    if key == '标题':
                        parsed['title'] = value
                        current_field = 'title'
                    elif key == '正文':
                        # 开始收集正文内容，而不是直接赋值
                        content_lines = [value] if value else []
                        current_field = 'content'
                    elif key == '作者':
                        parsed['author'] = value
                        current_field = 'author'
                    elif key == '粉丝数':
                        try:
                            parsed['followers'] = int(value.replace(',', ''))
                        except (ValueError, TypeError):
                            parsed['followers'] = original_item.get('raw', {}).get('followers_count', 0)
                    elif key == '点赞数':
                        try:
                            parsed['likes'] = int(value.replace(',', ''))
                        except (ValueError, TypeError):
                            parsed['likes'] = original_item.get('raw', {}).get('favorite_count', 0)
                    elif key == '转发数':
                        try:
                            parsed['retweets'] = int(value.replace(',', ''))
                        except (ValueError, TypeError):
                            parsed['retweets'] = original_item.get('raw', {}).get('retweet_count', 0)
                    elif key == '日期':
                        parsed['date_time'] = value
                        current_field = 'date_time'
                else:
                    # 继续收集当前字段的内容
                    if current_field == 'content':
                        content_lines.append(line)
            
            # 保存最后收集的正文内容
            if current_field == 'content' and content_lines:
                parsed['content'] = '\n'.join(content_lines)
            
            # 验证必要字段 - 如果缺少标题或内容，则返回None
            if not parsed.get('title') or not parsed.get('content'):
                logger.warning("解析结果缺少标题或正文字段，跳过处理")
                return None
            
            # 准备作者信息
            author_name = original_item.get('raw', {}).get('name', '')
            author_username = original_item.get('raw', {}).get('username', '')
            author_display = f"{author_name} (@{author_username})" if author_name and author_username else author_name or author_username
            
            # 构建最终结构化数据
            structured_data = {
                'title': parsed.get('title', ''),
                'content': parsed.get('content', ''),
                'author': parsed.get('author', author_display),
                'date_time': parsed.get('date_time', original_item.get('date_time', '')),
                'source': 'x.com',
                'source_url': original_item.get('source_url', original_item.get('raw', {}).get('url', '')),
                'likes': parsed.get('likes', original_item.get('raw', {}).get('favorite_count', 0)),
                'retweets': parsed.get('retweets', original_item.get('raw', {}).get('retweet_count', 0)),
                'followers': parsed.get('followers', original_item.get('raw', {}).get('followers_count', 0)),
                'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # 生成唯一ID
            id_text = f"{structured_data['source']}_{structured_data['source_url']}"
            structured_data['id'] = generate_id(id_text)
            
            return structured_data
            
        except Exception as e:
            logger.error(f"解析X处理结果出错: {e}")
            logger.error(traceback.format_exc())
            return None


class CrunchbaseDataProcessor(DataProcessor):
    """Crunchbase数据处理器"""
    
    def process(self) -> int:
        """处理Crunchbase数据"""
        logger.info("开始处理Crunchbase数据")
        
        # 检查临时文件是否存在
        if not os.path.exists(CRU_TEMP_DATA_PATH):
            logger.info("未找到Crunchbase临时数据文件")
            return 0
        
        # 读取临时数据
        try:
            with open(CRU_TEMP_DATA_PATH, 'r', encoding='utf-8') as f:
                temp_data = json.load(f)
            
            if not temp_data:
                logger.info("Crunchbase临时数据为空")
                return 0
            
            logger.info(f"读取到 {len(temp_data)} 条Crunchbase原始数据")
            
            # 批量处理数据
            processed_count = 0
            stored_count = 0
            
            # 添加批处理和间隔逻辑
            for i in range(0, len(temp_data), BATCH_SIZE):
                batch = temp_data[i:i+BATCH_SIZE]
                logger.info(f"处理批次 {i//BATCH_SIZE + 1}/{(len(temp_data)-1)//BATCH_SIZE + 1}，共 {len(batch)} 条数据")
                
                # 处理当前批次
                for item in batch:
                    processed_item = self._process_crunchbase_item(item)
                    if processed_item:
                        # 存储处理后的数据
                        if self.storage.store(processed_item):
                            stored_count += 1
                        processed_count += 1
                
                # 如果不是最后一批，等待一段时间再处理下一批
                if i + BATCH_SIZE < len(temp_data):
                    logger.info(f"批处理完成，等待 {BATCH_INTERVAL} 秒后处理下一批...")
                    time.sleep(BATCH_INTERVAL)
            
            # 处理完成后清空临时文件
            if processed_count > 0:
                try:
                    # 清空原始临时文件，但保留文件
                    with open(CRU_TEMP_DATA_PATH, 'w', encoding='utf-8') as f:
                        json.dump([], f)
                    
                    logger.info("临时数据已处理完毕，已清空原始文件")
                except Exception as e:
                    logger.error(f"清空临时数据出错: {e}")
            
            logger.info(f"Crunchbase数据处理完成，处理 {processed_count} 条，成功存储 {stored_count} 条")
            return processed_count
            
        except Exception as e:
            logger.error(f"处理Crunchbase数据出错: {e}")
            logger.error(traceback.format_exc())
            return 0
    
    def _process_crunchbase_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理单条Crunchbase数据"""
        try:
            # 准备输入文本
            input_text = (
                f"文章标题: {item.get('title', '')}\n\n"
                f"文章内容: {item.get('content', '')}\n\n"
                f"作者: {item.get('author', '')}\n"
                f"发布时间: {item.get('date_time', '')}\n"
                f"URL: {item.get('url', '')}"
            )
            
            # 获取系统提示词
            system_prompt = SystemPrompts.get_for_source("crunchbase.com")
            
            # 调用AI处理
            result = self._call_ai_api(system_prompt, input_text)
            
            # 如果结果为空，跳过
            if not result or len(result.strip()) < 10:
                logger.info("处理结果为空，跳过")
                return None
            
            # 解析处理结果
            return self._parse_crunchbase_result(result, item)
            
        except Exception as e:
            logger.error(f"处理Crunchbase数据项出错: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def _parse_crunchbase_result(self, result: str, original_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析AI处理后的Crunchbase结果"""
        try:
            lines = result.split('\n')
            parsed = {}
            
            # 提取字段
            current_field = None
            content_lines = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if ':' in line and not line.startswith('http') and not line.startswith('——'):
                    # 如果有新字段开始，先保存之前收集的正文内容
                    if current_field == 'content' and content_lines:
                        parsed['content'] = '\n'.join(content_lines)
                        content_lines = []
                    
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    current_field = None
                    
                    if key == '标题':
                        parsed['title'] = value
                        current_field = 'title'
                    elif key == '正文':
                        # 开始收集正文内容，而不是直接赋值
                        content_lines = [value] if value else []
                        current_field = 'content'
                    elif key == '作者':
                        parsed['author'] = value
                        current_field = 'author'
                    elif key == '公司':
                        parsed['company'] = value
                        current_field = 'company'
                    elif key == '融资轮次':
                        parsed['funding_round'] = value
                        current_field = 'funding_round'
                    elif key == '融资金额':
                        parsed['funding_amount'] = value
                        current_field = 'funding_amount'
                    elif key == '投资方':
                        parsed['investors'] = value
                        current_field = 'investors'
                    elif key == '日期':
                        parsed['date_time'] = value
                        current_field = 'date_time'
                else:
                    # 继续收集当前字段的内容
                    if current_field == 'content':
                        content_lines.append(line)
            
            # 保存最后收集的正文内容
            if current_field == 'content' and content_lines:
                parsed['content'] = '\n'.join(content_lines)
            
            # 验证必要字段 - 如果缺少标题或内容，则返回None
            if not parsed.get('title') or not parsed.get('content'):
                logger.warning("解析结果缺少标题或正文字段，跳过处理")
                return None
            
            # 构建最终结构化数据
            structured_data = {
                'title': parsed.get('title', ''),
                'content': parsed.get('content', ''),
                'author': parsed.get('author', original_item.get('author', '')),
                'date_time': parsed.get('date_time', original_item.get('date_time', '')),
                'source': 'crunchbase.com',
                'source_url': original_item.get('url', ''),
                'company': parsed.get('company', '未提供'),
                'funding_round': parsed.get('funding_round', '未提供'),
                'funding_amount': parsed.get('funding_amount', '未提供'),
                'investors': parsed.get('investors', '未提供'),
                'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # 生成唯一ID
            id_text = f"{structured_data['source']}_{structured_data['source_url']}"
            structured_data['id'] = generate_id(id_text)
            
            return structured_data
            
        except Exception as e:
            logger.error(f"解析Crunchbase处理结果出错: {e}")
            logger.error(traceback.format_exc())
            return None


# 信号处理
def handle_signal(signum, frame):
    """处理信号"""
    if signum == signal.SIGUSR1:
        logger.info("收到 SIGUSR1 信号，立即检查数据")
        process_data()
    elif signum == signal.SIGTERM or signum == signal.SIGINT:
        logger.info(f"收到信号 {signum}，准备退出")
        sys.exit(0)


# 数据处理主函数
def process_data():
    """处理数据的主函数"""
    logger.info("开始检查临时数据...")
    total_processed = 0
    
    # 处理X平台数据
    x_processor = XDataProcessor()
    try:
        x_processed = x_processor.process()
        total_processed += x_processed
        logger.info(f"X平台数据处理完成，共处理 {x_processed} 条")
    except Exception as e:
        logger.error(f"X平台数据处理失败: {e}")
    
    # 处理Crunchbase数据
    cru_processor = CrunchbaseDataProcessor()
    try:
        cru_processed = cru_processor.process()
        total_processed += cru_processed
        logger.info(f"Crunchbase数据处理完成，共处理 {cru_processed} 条")
    except Exception as e:
        logger.error(f"Crunchbase数据处理失败: {e}")
    
    logger.info(f"处理完成，共处理 {total_processed} 条数据")
    return total_processed


if __name__ == "__main__":
    # 注册信号处理器
    if platform.system() != "Windows":  # Windows不支持SIGUSR1
        signal.signal(signal.SIGUSR1, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    
    logger.info("开始执行数据处理")
    
    # 设置循环间隔，单位为秒
    interval = 7200  # 2小时
    
    while True:
        processed = process_data()
        logger.info(f"等待 {interval} 秒后再次检查...")
        time.sleep(interval)