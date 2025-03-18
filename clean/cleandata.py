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
import threading  # 添加线程库

# 创建全局线程锁用于保护文件操作
jsonl_lock = threading.Lock()

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

# 设置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "cleandata.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("cleandata")

# 常量定义
API_KEY = 'p9mtsT4ioDYm1'
API_BASE_URL = 'https://ai.liaobots.work/v1'
MODEL_NAME = 'gemini-2.0-flash-exp'

# 初始化 OpenAI 客户端
client = OpenAI(
    api_key=API_KEY,
    base_url=API_BASE_URL
)

# 临时数据文件路径
X_TEMP_DATA_PATH = os.path.join(DATA_DIR, 'x_tempdata.json')
CRU_TEMP_DATA_PATH = os.path.join(DATA_DIR, 'cru_tempdata.json')
DATA_JSONL_PATH = os.path.join(DATA_DIR, 'data.jsonl')

# 工具函数
def generate_id(text: str) -> str:
    """生成唯一ID"""
    return hashlib.md5(text.encode()).hexdigest()

# 确保data.jsonl文件存在
def ensure_jsonl_file_exists():
    """确保JSONL文件存在，如果不存在则创建一个空文件"""
    if not os.path.exists(DATA_JSONL_PATH):
        logger.info(f"创建新的JSONL文件: {DATA_JSONL_PATH}")
        # 确保父目录存在
        os.makedirs(os.path.dirname(DATA_JSONL_PATH), exist_ok=True)
        with open(DATA_JSONL_PATH, 'w', encoding='utf-8') as f:
            # 不需要写入任何内容，JSONL文件可以是空行
            pass  # 创建空文件
    elif os.path.getsize(DATA_JSONL_PATH) == 0:
        # 如果文件存在但为空，确保它是一个有效的空JSONL文件
        logger.info(f"确保JSONL文件不为空: {DATA_JSONL_PATH}")
    else:
        logger.debug(f"JSONL文件已存在: {DATA_JSONL_PATH}")

# 系统提示词管理
class SystemPrompts:
    """系统提示词管理类，为不同数据源提供专用提示词"""
    
    @staticmethod
    def get_x_prompt() -> str:
        """获取处理X.com数据的系统提示词"""
        return ("将资讯按以下固定格式整理成中文新闻：\n\n"
                "完整日期时间，格式为YYYY-MM-DD HH:MM\n"
                "根据内容自拟标题，精简且保持吸引力，确保标题中的英文和数字前后都有空格提高可读性\n"
                "资讯内容，内容必须与作者信息完全分离，不要在内容中包含作者信息、'详情请查看'或重复来源链接（来源链接会单独保存）\n"
                "保留原文或标题某些专有英文名词，不要翻译，例如 AI，或是公司名，人名之类\n"
                "作者：[作者名] (@[用户名])\n"
                "粉丝数：[粉丝数] | 点赞：[点赞数] | 转发：[转发数]\n\n"
                "资讯内容和标题都应以新闻文笔优化原文，英文和数字前后必须加空格提高可读性。必须严格删除与AI无关的内容，"
                "如果整条内容与AI技术、人工智能应用、机器学习等完全无关，则直接跳过该条不处理。直接输出整理后的资讯，不要在开头或结束添加任何"
                "额外说明、标题或格式符号。不要在正文中描述点赞和转发数据、包含作者信息或添加'阅读原文'、'详情请查看'等提示。按发布时间排序，"
                "并在日期时间前依次添加序号，例如1.。\n\n"
                "特别注意：资讯内容不应包含任何作者信息，作者信息必须单独成行，以'作者：'开头。")
    
    @staticmethod
    def get_crunchbase_prompt() -> str:
        """获取处理Crunchbase数据的系统提示词"""
        return ("你是一位专业的投资信息分析专家，你的任务是将英文Crunchbase文章完整翻译并整理为结构化中文内容。\n\n"
                "直接输出转换后的内容，不要添加任何前言、后语或额外说明。严格按照以下格式输出：\n\n"
                "原文发布日期，格式为YYYY-MM-DD\n"  # 按照格式清洗
                "根据内容给出简明扼要的中文标题，强调投资/融资相关信息\n"  # 直接给出中文标题，不要加粗、不要加引号或其他格式
                "完整将原文的标题，内容都翻译成中文，且必须翻译成中文，分段清晰\n\n"  # 完整翻译成中文，分段清晰
                "作者：原作者姓名\n"  # 原作者信息
                "公司/产品：相关公司或产品名称\n"  # 从文章提取的公司或产品信息
                "投资信息：融资金额，投资方\n\n"  # 融资信息摘要，如有
                
                "无论输入何种格式，请确保输出的一致性：\n"
                "1. 如果没有完整日期，仅提供年份\n"
                "2. 标题必须突出投资和融资信息\n"
                "3. 完整保留所有关键业务细节和数字\n"
                "4. 确保段落之间有空行，保持原文的结构\n"
                "5. 请根据输入内容，提取或推断公司、产品、投资信息等要素\n"
                "6. 如果原文没有某些字段信息，用'未提供'代替，而不是省略该字段\n"
                "7. 如果输入混乱或缺少关键信息，尽量从现有内容中提取逻辑，生成合理内容\n"
                
                "翻译要求：\n"
                "- 必须将所有非中文内容完整翻译成中文，不保留任何英文原文（公司名、产品名、人名等专有名词除外）\n"
                "- 确保没有任何内容被跳过或保持英文状态\n"
                "- 避免使用任何非中文表达，如俄语、法语等其他语言词汇\n"
                "- 专业术语必须使用中文对应词汇，不要保留英文术语\n"
                "- 所有段落、句子必须100%翻译成中文，不遗漏任何内容\n"
                
                "格式要求：\n"
                "- 使用简洁流畅的中文表达\n"
                "- 准确保留所有数字、融资金额、估值等财务数据\n"
                "- 不要添加分隔符或使用markdown格式\n"
                "- 英文和数字前后加空格提高可读性\n"
                "- 保留原文的段落结构和换行格式\n"
                "- 如果原文没有提供明确数据，请用'未知'代替\n")
    
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


# 工具函数
class TextUtils:
    """文本处理工具类"""
    
    @staticmethod
    def standardize_punctuation(content: str) -> str:
        """标准化内容中的标点符号，确保以句号结尾，但保留内容中的换行符"""
        if not content:
            return ""
        
        # 保留内容中的换行符，只移除末尾的标点符号和空格
        cleaned = re.sub(r'[.,，、;；:：!！?？\s]+$', '', content)
        
        # 确保内容不为空
        if not cleaned.strip():
            return ""
        
        # 添加句号结尾
        cleaned = cleaned.strip() + '。'
        
        # 修复可能的重复句号
        cleaned = re.sub(r'。+$', '。', cleaned)
        
        return cleaned
    
    @staticmethod
    def format_crunchbase_content(content: str) -> str:
        """特殊格式化Crunchbase内容，增强段落可读性"""
        if not content:
            return ""
        
        # 将小数点前标记为特殊字符，避免小数点被当作句号处理
        # 先保护小数点格式 (前后都是数字的点)
        content = re.sub(r'(\d)\.(\d)', r'\1##DOT##\2', content)
        
        # 确保段落之间有足够的换行符（对真正的句末标点）
        content = re.sub(r'([。！？!?])\s*(?=\S)', r'\1\n\n', content)
        
        # 恢复被保护的小数点
        content = re.sub(r'##DOT##', '.', content)
        
        # 删除可能的连续三个以上换行
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        return content


# 数据存储管理
class DataStorage:
    """数据存储管理类，负责数据的保存、加载和去重等操作"""
    
    @staticmethod
    def get_existing_urls() -> set:
        """获取已存在的URL集合，用于去重"""
        existing_urls = set()
        
        try:
            with jsonl_lock:  # 使用线程锁保护文件读取
                if os.path.exists(DATA_JSONL_PATH) and os.path.getsize(DATA_JSONL_PATH) > 0:
                    with open(DATA_JSONL_PATH, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if not line:  # 跳过空行
                                continue
                            try:
                                item = json.loads(line)
                                if 'source_url' in item and item['source_url']:
                                    existing_urls.add(item['source_url'])
                            except json.JSONDecodeError as e:
                                logger.warning(f"解析已存在数据时出错: {e}, 行内容: {line[:50]}...")
                                continue
        except Exception as e:
            logger.error(f"读取已存在URL时出错: {e}")
            logger.error(traceback.format_exc())
        
        return existing_urls
    
    @staticmethod
    def save_to_jsonl(parsed_data: List[Dict[str, Any]]) -> int:
        """将处理后的数据保存到JSONL文件，并进行URL去重
        
        Args:
            parsed_data: 要保存的数据列表
            
        Returns:
            保存的数据条数
        """
        # 确保JSONL文件存在
        ensure_jsonl_file_exists()
        
        # 获取已存在的URL集合，用于去重
        existing_urls = DataStorage.get_existing_urls()
        
        saved_count = 0
        with jsonl_lock:  # 使用线程锁保护文件写入
            with open(DATA_JSONL_PATH, 'a', encoding='utf-8') as f:
                for item in parsed_data:
                    # 使用source_url字段进行去重
                    source_url = item.get('source_url', '')
                    if source_url and source_url in existing_urls:
                        logger.info(f"跳过已存在的URL: {source_url}")
                        continue
                    
                    # 确保必要字段存在
                    if not item.get('content'):
                        logger.warning(f"跳过缺少内容的条目: {item.get('title', '无标题')}")
                        continue
                    
                    # 如果没有ID字段，生成一个
                    if 'id' not in item:
                        content_for_id = item.get('content', '') + item.get('title', '')
                        item['id'] = generate_id(content_for_id)
                        
                    # 保存到文件
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')
                    saved_count += 1
                    
                    # 添加到已存在的URL集合
                    if source_url:
                        existing_urls.add(source_url)
        
        return saved_count
    
    @staticmethod
    def clear_temp_file(file_path: str):
        """清空临时文件"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('[]')
            logger.info(f"已清空临时文件: {file_path}")
        except Exception as e:
            logger.error(f"清空临时文件失败: {e}")
    
    @staticmethod
    def update_temp_file(file_path: str, data: List[Dict[str, Any]]):
        """更新临时文件内容"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"已更新临时文件: {file_path}")
        except Exception as e:
            logger.error(f"更新临时文件失败: {e}")
    
    @staticmethod
    def load_temp_data(file_path: str) -> List[Dict[str, Any]]:
        """加载临时文件数据
        
        Args:
            file_path: 临时文件路径
            
        Returns:
            临时数据列表，如果文件不存在或内容为空，返回空列表
        """
        data = []
        try:
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        if not isinstance(data, list):
                            logger.warning(f"临时文件格式不正确: {file_path}")
                            data = []
                        
                        # 诊断日志：输出前几条数据的结构
                        if data and 'x_tempdata' in file_path:
                            sample_size = min(2, len(data))
                            logger.info(f"X.com临时数据样本 (前{sample_size}条):")
                            
                            for i, item in enumerate(data[:sample_size]):
                                logger.info(f"  数据项 #{i+1}:")
                                
                                # 检查顶级字段
                                logger.info(f"    顶级字段: {sorted(item.keys())}")
                                
                                # 检查raw字段的结构
                                if 'raw' in item:
                                    raw_keys = sorted(item['raw'].keys())
                                    logger.info(f"    raw字段包含: {raw_keys}")
                                    
                                    # 特别检查点赞和转发字段
                                    if 'favorite_count' in item['raw']:
                                        logger.info(f"    点赞数: {item['raw']['favorite_count']}")
                                    if 'retweet_count' in item['raw']:
                                        logger.info(f"    转发数: {item['raw']['retweet_count']}")
            else:
                # 如果文件不存在或为空，创建一个空文件
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('[]')
        except Exception as e:
            logger.error(f"加载临时文件失败: {file_path}, 错误: {e}")
            data = []
        
        return data


# 数据处理器基类和子类
class BaseDataProcessor:
    """数据处理器基类，定义了数据处理器的通用接口"""
    
    def __init__(self, temp_data_path: str):
        """初始化数据处理器
        
        Args:
            temp_data_path: 临时数据文件路径
        """
        self.temp_data_path = temp_data_path
        self.model = MODEL_NAME  # 使用全局定义的模型名称
        self.client = client  # 使用全局定义的API客户端
    
    def process(self) -> int:
        """处理数据的主方法，子类必须实现此方法"""
        raise NotImplementedError("子类必须实现process方法")
    
    def _call_ai_api(self, system_message: str, prompt: str) -> str:
        """
        调用AI API进行处理
        
        Args:
            system_message: 系统提示词
            prompt: 用户提示词
            
        Returns:
            处理后的结果
        """
        logger.info(f"准备调用AI API，系统提示词长度: {len(system_message)}，用户提示词长度: {len(prompt)}")
        
        # 确保model和client属性存在，如果不存在则使用全局变量
        model = getattr(self, 'model', MODEL_NAME)
        api_client = getattr(self, 'client', client)
        
        max_retries = 5  # 增加最大重试次数
        initial_retry_delay = 3.0
        max_retry_delay = 30.0
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"第 {attempt}/{max_retries} 次尝试调用AI API，使用模型: {model}")
                start_time = time.time()
                
                # 使用API客户端发起请求
                response = api_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1
                )
                
                # 计算API调用时间
                elapsed_time = time.time() - start_time
                logger.info(f"API调用成功，耗时: {elapsed_time:.2f} 秒")
                
                # 获取返回结果
                if response.choices and len(response.choices) > 0:
                    result_text = response.choices[0].message.content
                    
                    # 记录返回结果的长度
                    logger.info(f"API返回结果长度: {len(result_text)}")
                    
                    # 记录返回结果的概要（前50个字符）
                    if result_text and len(result_text) > 0:
                        preview = result_text[:50].replace('\n', ' ')
                        logger.info(f"返回结果概要: {preview}...")
                    
                    return result_text
                else:
                    logger.warning("API返回结果为空或格式不正确")
                    return ""
                
            except Exception as e:
                # 计算重试等待时间（指数退避策略）
                retry_delay = min(initial_retry_delay * (2 ** (attempt - 1)), max_retry_delay)
                
                # 判断是否还有重试机会
                if attempt < max_retries:
                    # 不同类型的错误记录不同的日志
                    if "Connection" in str(e) or "Timeout" in str(e) or "timeout" in str(e).lower():
                        logger.warning(f"API连接错误 (尝试 {attempt}/{max_retries}): {str(e)}")
                    elif "rate limit" in str(e).lower() or "too many requests" in str(e).lower():
                        logger.warning(f"API速率限制 (尝试 {attempt}/{max_retries}): {str(e)}")
                        # 速率限制时等待更长时间
                        retry_delay = max(retry_delay * 2, 10.0)
                    else:
                        logger.warning(f"API调用失败 (尝试 {attempt}/{max_retries}): {str(e)}")
                    
                    # 记录详细错误信息
                    logger.warning(f"错误详情: {traceback.format_exc()}")
                    
                    # 添加随机抖动避免多个请求同时重试
                    jitter = random.uniform(0, 1)
                    actual_delay = retry_delay + jitter
                    
                    logger.info(f"等待 {actual_delay:.2f} 秒后重试...")
                    time.sleep(actual_delay)
                else:
                    # 最后一次尝试失败，记录详细错误
                    logger.error(f"API调用失败 (最终尝试): {str(e)}")
                    logger.error(f"详细错误: {traceback.format_exc()}")
                    
        logger.error(f"在 {max_retries} 次尝试后，API调用仍然失败")
        return ""


class XDataProcessor(BaseDataProcessor):
    """X.com数据处理器，专门处理来自X.com的数据"""
    
    def __init__(self):
        """初始化X.com数据处理器"""
        super().__init__(X_TEMP_DATA_PATH)
        # 显式设置model和client属性，确保它们被正确初始化
        self.model = MODEL_NAME
        self.client = client
    
    def process(self) -> int:
        """处理X.com数据，完全重新实现，不再使用分批处理逻辑
        
        Returns:
            成功保存的数据条数
        """
        logger.info("开始处理X.com数据...")
        
        # 加载临时数据
        try:
            data = DataStorage.load_temp_data(self.temp_data_path)
            if not data:
                logger.info("没有发现X.com临时数据")
                return 0
                
            logger.info(f"加载了 {len(data)} 条X.com临时数据")
        except Exception as e:
            logger.error(f"加载X.com临时数据失败: {e}")
            logger.error(traceback.format_exc())
            return 0
        
        # 获取已存在的URL集合，用于去重
        existing_urls = DataStorage.get_existing_urls()
        
        # 计数器
        total_items = len(data)
        saved_count = 0
        
        # 获取系统提示词
        system_message = SystemPrompts.get_x_prompt()
        
        # 准备完整的提示文本
        user_prompt = f"请按照指定格式整理以下 {total_items} 条X.com推文，删除与AI无关的内容：\n\n"
        
        # 为每条数据创建唯一标识，避免URL重复问题
        processed_data_map = {}
        
        for i, item in enumerate(data, 1):
            # 获取源URL
            source_url = item.get('source_url', '') or item.get('url', '')
            if 'raw' in item and not source_url:
                source_url = item['raw'].get('url', '')
            
            # 如果URL已存在，直接跳过
            if source_url and source_url in existing_urls:
                logger.info(f"跳过已存在的URL: {source_url}")
                continue
            
            # 从item中提取数据
            content = item.get('text', '')
            if not content:
                # 如果text不存在，尝试从raw中获取text
                if 'raw' in item and 'text' in item['raw']:
                    content = item['raw']['text']
            
            if not content:
                logger.warning(f"跳过没有内容的X.com数据 #{i}")
                continue
            
            # 添加额外信息使AI更容易处理
            username = ''
            name = ''
            followers = 0
            likes = 0
            retweets = 0
            
            # 从raw中提取更多信息
            if 'raw' in item:
                raw = item['raw']
                username = raw.get('username', '')
                name = raw.get('name', '')
                followers = raw.get('followers_count', 0)
                likes = raw.get('favorite_count', 0)
                retweets = raw.get('retweet_count', 0)
            
            # 构建更完整的内容描述
            prompt_content = f"{content}\n"
            if name or username:
                prompt_content += f"作者: {name} (@{username})\n"
            if followers or likes or retweets:
                prompt_content += f"统计数据: 粉丝数 {followers}, 点赞 {likes}, 转发 {retweets}\n"
            
            # 使用索引作为唯一标识符
            item_id = f"item_{i}"
            processed_data_map[item_id] = item
            
            # 添加到提示词中，包含唯一标识符
            user_prompt += f"{i}. [ID:{item_id}] {prompt_content}\n\n"
            
            # 添加原始URL
            if source_url:
                user_prompt += f"来源URL: {source_url}\n\n"
        
        # 如果没有有效数据可处理，直接返回
        if not processed_data_map:
            logger.info("没有新的X.com数据需要处理")
            return 0
        
        # 直接调用API，一次性处理所有数据
        logger.info(f"准备一次性处理 {len(processed_data_map)} 条X.com数据，提示词长度: {len(user_prompt)}")
        
        try:
            # 最大重试次数
            max_retries = 5
            cleaned_result = None
            
            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(f"第 {attempt}/{max_retries} 次尝试调用API处理X.com数据")
                    
                    # 创建新的OpenAI客户端
                    api_client = OpenAI(
                        api_key=API_KEY,
                        base_url=API_BASE_URL
                    )
                    
                    # 记录开始时间
                    start_time = time.time()
                    
                    # 设置较长的超时时间
                    timeout = 180  # 3分钟超时
                    
                    # 直接调用API
                    response = api_client.chat.completions.create(
                        model=MODEL_NAME,
                        messages=[
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.1,
                        timeout=timeout
                    )
                    
                    # 计算API调用时间
                    elapsed_time = time.time() - start_time
                    logger.info(f"API调用成功，耗时: {elapsed_time:.2f} 秒")
                    
                    # 处理API结果
                    if response.choices and len(response.choices) > 0:
                        cleaned_result = response.choices[0].message.content
                        logger.info(f"API返回结果长度: {len(cleaned_result)}")
                        
                        # 成功获取结果，跳出重试循环
                        break
                    else:
                        logger.warning(f"API返回结果为空 (尝试 {attempt}/{max_retries})")
                        if attempt == max_retries:
                            logger.error(f"在 {max_retries} 次尝试后仍无有效返回，处理失败")
                
                except Exception as e:
                    logger.error(f"API调用出错 (尝试 {attempt}/{max_retries}): {e}")
                    logger.error(traceback.format_exc())
                    
                    if attempt < max_retries:
                        # 重试等待时间随重试次数增加
                        wait_time = 10 * attempt
                        logger.info(f"等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"在 {max_retries} 次尝试后API调用仍然失败，处理失败")
            
            # 如果成功获取结果，解析并保存
            if cleaned_result:
                logger.info(f"解析X.com清洗结果...")
                
                # 日志输出结果预览
                preview_length = min(300, len(cleaned_result))
                logger.info(f"清洗结果预览: {cleaned_result[:preview_length]}...")
                
                # 使用自定义方法解析结果，传入原始ID映射以便还原数据
                parsed_items = self._parse_cleaned_result_with_id(cleaned_result, processed_data_map)
                
                if parsed_items:
                    # 保存到JSONL文件
                    saved_count = DataStorage.save_to_jsonl(parsed_items)
                    logger.info(f"已保存 {saved_count} 条X.com数据")
                else:
                    logger.warning(f"解析失败，未能提取有效数据")
        
        except Exception as e:
            logger.error(f"处理X.com数据时发生错误: {e}")
            logger.error(traceback.format_exc())
        
        # 处理完成后清空临时数据
        if saved_count > 0:
            DataStorage.clear_temp_file(self.temp_data_path)
            logger.info(f"已清空X.com临时数据，成功保存 {saved_count} 条")
        
        return saved_count
    
    def _parse_cleaned_result_with_id(self, cleaned_result: str, original_data_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """解析清洗后的结果（使用ID匹配方式）
        
        Args:
            cleaned_result: 清洗后的文本
            original_data_map: 原始数据映射，键为ID，值为原始数据
            
        Returns:
            解析后的数据列表
        """
        if not cleaned_result or not original_data_map:
            return []
        
        logger.info("解析X.com清洗结果...")
        
        # 分割处理后的结果为单独的条目
        # X.com的结果格式通常为 "序号. 日期\n标题\n内容\n作者..."
        news_items = []
        pattern = r'(\d+)\.\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})'
        split_items = re.split(pattern, cleaned_result)
        
        # 记录分割项数量，帮助调试
        logger.info(f"分割后的项目数量: {len(split_items)}")
        
        # 第一项如果是空白，去掉
        if split_items and not split_items[0].strip():
            split_items.pop(0)
            logger.info("移除了第一个空白项")
        
        # 确保分割项数量符合期望
        if len(split_items) % 3 != 0:
            logger.warning(f"分割项数量异常: {len(split_items)}，可能无法正确解析")
        
        # 解析分割后的条目
        parsed_items = []
        i = 0
        while i < len(split_items) - 2:
            try:
                # 提取序号、日期和内容
                item_number = split_items[i]
                date_time = split_items[i+1]
                content_part = split_items[i+2].strip()
                
                logger.info(f"处理第 {item_number} 条，日期时间: {date_time}")
                
                # 分割内容为标题、正文和附加信息
                content_lines = content_part.strip().split('\n')
                
                # 从内容中尝试找到原始数据的ID
                original_item = None
                original_id_match = re.search(r'\[ID:(item_\d+)\]', content_part)
                if original_id_match:
                    item_id = original_id_match.group(1)
                    if item_id in original_data_map:
                        original_item = original_data_map[item_id]
                        logger.info(f"找到匹配的原始数据ID: {item_id}")
                
                # 如果没有找到原始数据，尝试通过序号查找
                if not original_item and item_number.isdigit():
                    item_id = f"item_{item_number}"
                    if item_id in original_data_map:
                        original_item = original_data_map[item_id]
                        logger.info(f"通过序号找到匹配的原始数据: {item_number}")
                
                # 必须找到原始数据才继续处理，否则无法确保作者与URL匹配
                if not original_item:
                    logger.warning(f"无法找到条目 {item_number} 的原始数据，跳过")
                    i += 3
                    continue
                
                # 从原始数据中提取URL和作者信息
                source_url = ''
                if 'source_url' in original_item and original_item['source_url']:
                    source_url = original_item['source_url']
                elif 'url' in original_item and original_item['url']:
                    source_url = original_item['url']
                elif 'raw' in original_item and 'url' in original_item['raw']:
                    source_url = original_item['raw']['url']
                
                # 提取原始作者数据
                original_author = ''
                original_username = ''
                if 'raw' in original_item:
                    original_author = original_item['raw'].get('name', '')
                    original_username = original_item['raw'].get('username', '')
                    
                # 提取原始统计数据
                followers = 0
                likes = 0
                retweets = 0
                if 'raw' in original_item:
                    followers = original_item['raw'].get('followers_count', 0)
                    likes = original_item['raw'].get('favorite_count', 0)
                    retweets = original_item['raw'].get('retweet_count', 0)
                
                # 找不到URL，记录警告并跳过
                if not source_url:
                    logger.warning(f"条目 {item_number} 没有找到来源URL，跳过")
                    i += 3
                    continue
                
                # 查找来源URL (主要用于日志记录，实际使用原始数据中的URL)
                found_url = ''
                for line in content_lines:
                    if line.startswith('来源URL:') or line.startswith('来源URL：'):
                        found_url = line.replace('来源URL:', '').replace('来源URL：', '').strip()
                        # 从内容行中移除URL行
                        content_lines = [l for l in content_lines if l != line]
                        logger.info(f"在清洗结果中找到URL: {found_url}，但将使用原始数据URL: {source_url}")
                        break
                
                # 至少需要标题和内容
                if len(content_lines) < 2:
                    logger.warning(f"跳过格式不正确的条目 {item_number}")
                    i += 3
                    continue
                
                # 提取标题和内容
                title = content_lines[0].strip()
                
                # 查找作者行、统计行的索引
                author_line_idx = -1
                stats_line_idx = -1
                
                for j, line in enumerate(content_lines):
                    if line.startswith('作者：'):
                        author_line_idx = j
                    elif '粉丝数：' in line and '点赞：' in line:
                        stats_line_idx = j
                
                logger.info(f"作者行索引: {author_line_idx}, 统计行索引: {stats_line_idx}")
                
                # 提取内容（从标题行之后到作者行之前）
                if author_line_idx > 1:
                    content = '\n'.join(content_lines[1:author_line_idx])
                else:
                    # 如果没有找到作者行，假设内容是从标题到倒数第二行
                    content = '\n'.join(content_lines[1:-1]) if len(content_lines) > 2 else ''
                
                # 确保内容中不包含作者信息（进一步过滤）
                content_lines_filtered = []
                for line in content.split('\n'):
                    if not line.strip().startswith('作者：') and not line.strip().startswith('作者:'):
                        content_lines_filtered.append(line)
                content = '\n'.join(content_lines_filtered)
                
                # 标准化内容中的标点符号
                content = TextUtils.standardize_punctuation(content)
                
                # 提取作者信息，但优先使用原始数据中的作者信息
                author = ''
                if original_author and original_username:
                    author = f"{original_author} (@{original_username})"
                    logger.info(f"使用原始数据中的作者信息: {author}")
                elif author_line_idx >= 0:
                    # 如果原始数据中没有作者信息，才使用清洗结果中的作者
                    author_line = content_lines[author_line_idx]
                    author = author_line.replace('作者：', '').strip()
                    logger.info(f"使用清洗结果中的作者信息: {author}")
                
                # 生成唯一ID
                unique_id = generate_id(f"{date_time}_{title}_{content[:100]}")
                
                # 构建解析后的数据项
                parsed_item = {
                    'id': unique_id,
                    'source': 'x.com',
                    'published_at': date_time,
                    'title': title,
                    'content': content,
                    'author': author,
                    'source_url': source_url,
                    'meta': {
                        'followers': followers,
                        'likes': likes,
                        'retweets': retweets
                    },
                    'formatted_for_readability': True  # 标记数据已经过格式化
                }
                
                parsed_items.append(parsed_item)
                logger.info(f"成功解析条目 {item_number}，作者: {author}, URL: {source_url}")
                
            except Exception as e:
                logger.error(f"解析X.com清洗结果时出错: {e}")
                logger.error(traceback.format_exc())
            
            # 移动到下一个条目
            i += 3
        
        logger.info(f"成功解析 {len(parsed_items)} 条X.com数据")
        return parsed_items
    
    def _remove_processed_items(self, temp_data: List[Dict[str, Any]], processed_ids: set):
        """从临时数据中移除已处理的条目"""
        if not processed_ids:
            return
        
        # 只保留未处理的条目
        remaining_items = [item for i, item in enumerate(temp_data) if i not in processed_ids]
        
        if remaining_items:
            logger.info(f"有 {len(remaining_items)} 条数据未能处理，保留在临时文件中")
            DataStorage.update_temp_file(self.temp_data_path, remaining_items)
        else:
            # 清空临时存储
            DataStorage.clear_temp_file(self.temp_data_path)
            logger.info("所有数据处理完成，已清空临时文件")


class CrunchbaseDataProcessor(BaseDataProcessor):
    """Crunchbase数据处理器，专门处理来自Crunchbase的数据，单条处理以避免超出上下文限制"""
    
    def __init__(self):
        """初始化Crunchbase数据处理器"""
        super().__init__(CRU_TEMP_DATA_PATH)
        # 显式设置model和client属性，确保它们被正确初始化
        self.model = MODEL_NAME
        self.client = client
    
    def process(self) -> int:
        """完全重写的处理Crunchbase数据方法，不再依赖_call_ai_api
        
        Returns:
            成功保存的数据条数
        """
        logger.info("开始处理Crunchbase数据...")
        
        # 加载临时数据
        try:
            data = DataStorage.load_temp_data(self.temp_data_path)
            if not data:
                logger.info("没有发现Crunchbase临时数据")
                return 0
                
            logger.info(f"加载了 {len(data)} 条Crunchbase临时数据")
        except Exception as e:
            logger.error(f"加载Crunchbase临时数据失败: {e}")
            logger.error(traceback.format_exc())
            return 0
        
        # 获取已存在的URL集合，用于去重
        existing_urls = DataStorage.get_existing_urls()
        logger.info(f"已加载 {len(existing_urls)} 个已存在的URL")
        
        # 计数器
        total_items = len(data)
        saved_count = 0
        processed_ids = set()
        
        # 获取系统提示词
        system_message = SystemPrompts.get_crunchbase_prompt()
        
        # 逐条处理数据
        for i, item in enumerate(data):
            try:
                url = item.get('url', '')
                # 跳过已存在的URL
                if url and url in existing_urls:
                    logger.info(f"跳过已存在的URL: {url}")
                    processed_ids.add(i)
                    continue
                    
                logger.info(f"处理第 {i+1}/{total_items} 条数据")
                
                title = item.get('title', '')
                logger.info(f"处理Crunchbase标题: {title[:50]}{'...' if len(title) > 50 else ''}")
                
                # 格式化数据项为API输入
                formatted_text = self._format_single_item(item, i+1)
                
                # 直接调用API，不使用_call_ai_api方法
                max_retries = 3  # 最大重试次数
                for attempt in range(1, max_retries + 1):
                    try:
                        logger.info(f"第 {attempt}/{max_retries} 次尝试处理Crunchbase数据项 {i+1}")
                        
                        # 创建新的OpenAI客户端，避免依赖实例变量
                        api_client = OpenAI(
                            api_key=API_KEY,
                            base_url=API_BASE_URL
                        )
                        
                        # 记录开始时间
                        start_time = time.time()
                        
                        # 直接调用API
                        response = api_client.chat.completions.create(
                            model=MODEL_NAME,  # 直接使用常量，不依赖self.model
                            messages=[
                                {"role": "system", "content": system_message},
                                {"role": "user", "content": formatted_text}
                            ],
                            temperature=0.1
                        )
                        
                        # 计算API调用时间
                        elapsed_time = time.time() - start_time
                        logger.info(f"API调用成功，耗时: {elapsed_time:.2f} 秒")
                        
                        # 处理API结果
                        if response.choices and len(response.choices) > 0:
                            cleaned_result = response.choices[0].message.content
                            logger.info(f"API返回结果长度: {len(cleaned_result)}")
                            
                            # 解析结果
                            parsed_items = self._parse_single_result(cleaned_result, item)
                            
                            if parsed_items:
                                # 保存到JSONL文件
                                batch_saved = DataStorage.save_to_jsonl(parsed_items)
                                saved_count += batch_saved
                                processed_ids.add(i)
                                logger.info(f"成功保存Crunchbase数据项 {i+1}，标题: {title[:30]}...")
                                
                                # 添加URL到已存在集合，避免重复处理
                                if url:
                                    existing_urls.add(url)
                                
                                # 成功处理，跳出重试循环
                                break
                            else:
                                logger.warning(f"数据项 {i+1} 解析失败")
                                if attempt == max_retries:
                                    logger.error(f"在 {max_retries} 次尝试后仍解析失败，跳过此条目")
                        else:
                            logger.warning(f"API返回结果为空 (尝试 {attempt}/{max_retries})")
                            if attempt == max_retries:
                                logger.error(f"在 {max_retries} 次尝试后仍无有效返回，跳过此条目")
                        
                    except Exception as e:
                        logger.error(f"处理数据项 {i+1} 时出错 (尝试 {attempt}/{max_retries}): {e}")
                        logger.error(traceback.format_exc())
                        
                        if attempt < max_retries:
                            # 重试等待时间随重试次数增加
                            wait_time = 5 * attempt
                            logger.info(f"等待 {wait_time} 秒后重试...")
                            time.sleep(wait_time)
                        else:
                            logger.error(f"在 {max_retries} 次尝试后API调用仍然失败，跳过此条目")
                
                # 条目间添加延迟，避免API调用过于频繁
                if i < total_items - 1:
                    wait_time = 3
                    logger.info(f"等待 {wait_time} 秒后处理下一条...")
                    time.sleep(wait_time)
                
                # 每处理3条数据，保存一次临时状态
                if (i + 1) % 3 == 0 and processed_ids:
                    self._remove_processed_items(data, processed_ids)
                    logger.info(f"已处理 {len(processed_ids)}/{total_items} 条，已保存中间状态")
                
            except Exception as e:
                logger.error(f"处理Crunchbase数据项 {i+1} 出错: {e}")
                logger.error(traceback.format_exc())
        
        # 处理完成后，从临时数据中移除已处理的条目
        if processed_ids:
            self._remove_processed_items(data, processed_ids)
        
        logger.info(f"Crunchbase数据处理完成，共成功保存 {saved_count} 条")
        return saved_count
    
    def _format_single_item(self, item: Dict[str, Any], index: int) -> str:
        """格式化单个Crunchbase数据项为AI处理的文本
        
        Args:
            item: 数据项
            index: 数据项索引
            
        Returns:
            格式化后的文本
        """
        # 提取必要字段
        title = item.get('title', '')
        content = item.get('content', '')
        investment_amount = item.get('investment_amount', 'N/A')
        investors = item.get('investors', [])
        company_product = item.get('company_product', '未知')
        published_date = item.get('published_date', datetime.now().strftime('%Y-%m-%d'))
        author = item.get('author', '未知')
        
        # 格式化投资信息
        if investment_amount != 'N/A' and investment_amount != '未知':
            if isinstance(investors, list):
                investors_text = ', '.join(investors)
            else:
                investors_text = str(investors)
            investment_info = f"投资金额: {investment_amount}, 投资方: {investors_text}"
        else:
            investment_info = ""
        
        # 格式化公司/产品信息
        if company_product and company_product != '未知':
            company_info = f"公司/产品: {company_product}"
        else:
            company_info = ""
        
        # 构建格式化文本
        formatted_text = f"{published_date}\n{title}\n\n{content}\n\n"
        if investment_info:
            formatted_text += f"{investment_info}\n"
        if company_info:
            formatted_text += f"{company_info}\n"
        if author and author != '未知':
            formatted_text += f"作者: {author}"
        
        return formatted_text
    
    def _parse_single_result(self, cleaned_result: str, original_item: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析单个Crunchbase数据项的清洗结果
        
        Args:
            cleaned_result: 清洗后的文本
            original_item: 原始数据项
            
        Returns:
            解析后的数据列表
        """
        try:
            # 获取原始数据中的URL
            source_url = original_item.get('url', '')
            
            # 拆分清洗结果成行
            lines = cleaned_result.split('\n')
            
            # 初始化各字段
            published_date = ""
            title = ""
            content_lines = []
            author = ""
            company_product = ""
            investment_info = {}
            
            # 提取原始数据中的字段（用于回退）
            original_title = original_item.get('title', '')
            original_content = original_item.get('content', '')
            original_published_date = original_item.get('published_date', '')
            original_author = original_item.get('author', '')
            
            # 处理第一行（日期）
            if len(lines) > 0:
                date_str = lines[0].strip()
                if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
                    published_date = date_str
                else:
                    # 使用原始日期
                    published_date = original_published_date
            
            # 处理第二行（标题）
            if len(lines) > 1:
                title = lines[1].strip()
            if not title:
                title = original_title
            
            # 处理后续行，区分内容和元数据
            in_content = True
            
            for j in range(2, len(lines)):
                line = lines[j].strip()
                
                # 跳过空行，但在内容中保留段落分隔
                if not line:
                    if in_content:
                        content_lines.append("")
                    continue
                
                # 检测元数据行
                if line.startswith("作者："):
                    in_content = False
                    author = line.replace("作者：", "").strip()
                elif line.startswith("公司/产品："):
                    in_content = False
                    company_product = line.replace("公司/产品：", "").strip()
                elif line.startswith("投资信息："):
                    in_content = False
                    investment_info_text = line.replace("投资信息：", "").strip()
                elif in_content:
                    # 添加到内容部分
                    content_lines.append(line)
            
            # 处理内容，保留段落结构
            content_text = ""
            for i, para in enumerate(content_lines):
                if not para:  # 空字符串表示段落分隔
                    if content_text:
                        content_text += "\n\n"
                else:
                    if content_text and not content_text.endswith("\n\n"):
                        content_text += "\n\n"
                    content_text += para
            
            # 如果内容为空，使用原始内容
            if not content_text.strip():
                content_text = original_content
            
            # 如果作者为空，使用原始作者
            if not author:
                author = original_author
            
            # 格式化内容，增强段落可读性
            content_text = TextUtils.format_crunchbase_content(content_text)
            
            # 生成唯一ID
            item_id = generate_id(f"{published_date}_{title}_{content_text[:50] if content_text else ''}")
            
            # 修改投资信息解析逻辑
            if investment_info_text:
                # 解析融资金额
                amount_match = re.search(r'融资金额：([^，。]+)', investment_info_text)
                if amount_match:
                    investment_info['amount'] = amount_match.group(1).strip()
                
                # 解析估值
                valuation_match = re.search(r'估值\s*([^，。]+)', investment_info_text)
                if valuation_match:
                    investment_info['valuation'] = valuation_match.group(1).strip()
                
                # 解析投资方
                investors_match = re.search(r'投资方：([^，。]+)', investment_info_text)
                if investors_match:
                    investment_info['investors'] = investors_match.group(1).strip()
            
            # 创建解析后的数据项
            parsed_item = {
                "id": item_id,
                "source": "crunchbase.com",
                "published_at": f"{published_date} 00:00",
                "title": title,
                "content": content_text,
                "author": author,
                "source_url": source_url,
                "company_product": company_product if company_product else "未提供",
                "investment_info": investment_info,  # 改为对象格式
                "published_date": original_published_date,
                "meta": {
                    "cleaned_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            }
            
            logger.info(f"成功解析Crunchbase文章: {title}")
            return [parsed_item]
            
        except Exception as e:
            logger.error(f"解析Crunchbase数据失败: {e}")
            logger.error(traceback.format_exc())
            return []
    
    def _remove_processed_items(self, temp_data: List[Dict[str, Any]], processed_ids: set):
        """从临时数据中移除已处理的条目
        
        Args:
            temp_data: 临时数据列表
            processed_ids: 已处理的条目ID集合
        """
        if not processed_ids:
            return
        
        # 过滤出未处理的条目
        remaining_items = [item for i, item in enumerate(temp_data) if i not in processed_ids]
        
        if remaining_items:
            logger.info(f"有 {len(remaining_items)} 条数据未能处理，保留在临时文件中")
            # 更新临时文件
            DataStorage.update_temp_file(self.temp_data_path, remaining_items)
        else:
            # 清空临时存储
            DataStorage.clear_temp_file(self.temp_data_path)
            logger.info("所有数据处理完成，已清空临时文件")


# 数据清洗协调器
class DataCleanCoordinator:
    """数据清洗协调器，负责协调各种数据源的清洗处理"""
    
    def __init__(self):
        """初始化数据清洗协调器"""
        # 初始化各数据处理器
        self.x_processor = XDataProcessor()
        self.crunchbase_processor = CrunchbaseDataProcessor()
    
    def process_x_data(self) -> int:
        """处理X.com数据
        
        Returns:
            成功保存的数据条数
        """
        return self.x_processor.process()
    
    def process_crunchbase_data(self) -> int:
        """处理Crunchbase数据
        
        Returns:
            成功保存的数据条数
        """
        return self.crunchbase_processor.process()


# 主程序
def process_once():
    """执行一次完整的数据处理流程"""
    try:
        logger.info("开始执行数据处理")
        
        # 在 macOS 上禁用可能导致问题的信号处理
        if sys.platform == 'darwin':
            logger.info("检测到 macOS 系统，禁用 SIGALRM 信号处理")
            # 在 macOS 上 SIGALRM 可能导致问题
            signal.signal(signal.SIGALRM, signal.SIG_IGN)
        
        # 初始化数据协调器
        coordinator = DataCleanCoordinator()
        
        # 确保JSONL文件存在且内容有效
        try:
            ensure_jsonl_file_exists()
            # 验证文件是否可读取
            if os.path.exists(DATA_JSONL_PATH) and os.path.getsize(DATA_JSONL_PATH) > 0:
                with open(DATA_JSONL_PATH, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    valid_content = False
                    
                    # 检查文件中是否有有效内容
                    for line in lines:
                        if line.strip():
                            try:
                                # 尝试解析每一行为JSON
                                json.loads(line.strip())
                                valid_content = True
                            except json.JSONDecodeError:
                                # 发现无效行
                                valid_content = False
                                break
            
                    # 如果发现内容无效，重置文件
                    if not valid_content:
                        logger.warning(f"JSONL文件包含无效的JSON格式，重置文件: {DATA_JSONL_PATH}")
                        with open(DATA_JSONL_PATH, 'w', encoding='utf-8') as f_write:
                            # 创建空的有效文件
                            pass
        except Exception as e:
            logger.error(f"初始化JSONL文件时出错: {e}")
            logger.error(traceback.format_exc())
            # 出错时确保文件存在且为空（有效的JSONL格式）
            with open(DATA_JSONL_PATH, 'w', encoding='utf-8') as f:
                pass
        
        # 检查临时文件是否存在
        x_temp_exists = os.path.exists(X_TEMP_DATA_PATH) and os.path.getsize(X_TEMP_DATA_PATH) > 2
        cru_temp_exists = os.path.exists(CRU_TEMP_DATA_PATH) and os.path.getsize(CRU_TEMP_DATA_PATH) > 2
        
        # 记录处理状态
        total_processed = 0
        x_processed = 0
        cru_processed = 0
        
        # 创建处理结果字典，用于存储各线程的处理结果
        results = {'x_processed': 0, 'cru_processed': 0}
        
        # 定义处理X.com数据的函数
        def process_x_data():
            try:
                logger.info("开始处理X.com数据...")
                results['x_processed'] = coordinator.process_x_data()
                logger.info(f"X.com数据处理完成，共处理 {results['x_processed']} 条")
            except Exception as e:
                logger.error(f"处理X.com数据时出错: {str(e)}")
                logger.error(traceback.format_exc())
                results['x_processed'] = 0
        
        # 定义处理Crunchbase数据的函数
        def process_cru_data():
            try:
                logger.info("开始处理Crunchbase数据...")
                results['cru_processed'] = coordinator.process_crunchbase_data()
                logger.info(f"Crunchbase数据处理完成，共处理 {results['cru_processed']} 条")
            except Exception as e:
                logger.error(f"处理Crunchbase数据时出错: {str(e)}")
                logger.error(traceback.format_exc())
                results['cru_processed'] = 0
        
        # 创建线程列表
        threads = []
        
        # 添加X.com处理线程
        if x_temp_exists:
            x_thread = threading.Thread(target=process_x_data)
            threads.append(x_thread)
            x_thread.start()
            logger.info("启动X.com数据处理线程")
        else:
            logger.info("没有发现X.com临时数据，跳过处理")
        
        # 添加Crunchbase处理线程
        if cru_temp_exists:
            cru_thread = threading.Thread(target=process_cru_data)
            threads.append(cru_thread)
            cru_thread.start()
            logger.info("启动Crunchbase数据处理线程")
        else:
            logger.info("没有发现Crunchbase临时数据，跳过处理")
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        # 汇总处理结果
        total_processed = results['x_processed'] + results['cru_processed']
        
        # 记录总处理条数
        logger.info(f"全部数据处理完成，共处理 {total_processed} 条")
        
    except Exception as e:
        logger.error(f"数据处理过程中出错: {str(e)}")
        logger.error(traceback.format_exc())


def main():
    """
    主函数，负责调度整个数据清洗流程
    """
    logger.info("数据清洗服务启动")
    
    try:
        # 输出系统信息，帮助诊断
        logger.info(f"Python版本: {sys.version}")
        logger.info(f"操作系统: {platform.platform()}")
        
        # 在 macOS 上禁用可能导致问题的信号处理
        if sys.platform == 'darwin':
            logger.info("检测到 macOS 系统，禁用 SIGALRM 信号处理")
            signal.signal(signal.SIGALRM, signal.SIG_IGN)
        
        # 设置最大运行次数和重试次数
        max_runs = 3
        run_count = 0
        
        while run_count < max_runs:
            run_count += 1
            logger.info(f"开始第 {run_count}/{max_runs} 次运行")
            
            try:
                # 执行一次完整的数据处理
                process_once()
                
                # 检查是否还有未处理的临时数据
                x_temp_exists = os.path.exists(X_TEMP_DATA_PATH) and os.path.getsize(X_TEMP_DATA_PATH) > 10
                cru_temp_exists = os.path.exists(CRU_TEMP_DATA_PATH) and os.path.getsize(CRU_TEMP_DATA_PATH) > 10
                
                if not (x_temp_exists or cru_temp_exists):
                    logger.info("所有临时数据已处理完毕，退出程序")
                    break
                
                # 在处理不完整的情况下，记录剩余数据信息
                if x_temp_exists:
                    try:
                        x_data = DataStorage.load_temp_data(X_TEMP_DATA_PATH)
                        logger.info(f"X.com临时数据剩余 {len(x_data)} 条")
                    except Exception as e:
                        logger.error(f"读取X.com临时数据失败: {e}")
                
                if cru_temp_exists:
                    try:
                        cru_data = DataStorage.load_temp_data(CRU_TEMP_DATA_PATH)
                        logger.info(f"Crunchbase临时数据剩余 {len(cru_data)} 条")
                    except Exception as e:
                        logger.error(f"读取Crunchbase临时数据失败: {e}")
                
                # 如果还有剩余数据，等待一段时间后继续
                if run_count < max_runs and (x_temp_exists or cru_temp_exists):
                    wait_time = 30  # 等待30秒
                    logger.info(f"等待 {wait_time} 秒后进行下一轮处理...")
                    time.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"第 {run_count} 次运行时出错: {str(e)}")
                logger.error(traceback.format_exc())
                
                # 重试前等待
                if run_count < max_runs:
                    retry_wait = 60  # 错误后等待更长时间（60秒）
                    logger.info(f"等待 {retry_wait} 秒后重试...")
                    time.sleep(retry_wait)
    
    except Exception as e:
        logger.error(f"主程序执行时发生严重错误: {e}")
        logger.error(traceback.format_exc())
    
    finally:
        # 无论如何都要输出服务结束信息
        logger.info("数据清洗服务结束")


if __name__ == "__main__":
    main()