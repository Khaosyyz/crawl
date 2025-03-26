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
        
        # 恢复小数点
        content = content.replace('##DOT##', '.')
        
        return content


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
                        retry_delay = max(retry_delay * 2, 10.0)
                    else:
                        logger.warning(f"API调用失败 (尝试 {attempt}/{max_retries}): {str(e)}")
                    
                    time.sleep(retry_delay)
                else:
                    logger.error(f"API调用最终失败: {str(e)}")
                    return ""
        
        return ""
    
    def close(self):
        """关闭资源"""
        self.storage.close()


class XDataProcessor(DataProcessor):
    """X.com数据处理器"""
    
    def process(self) -> int:
        """处理X.com数据"""
        try:
            # 加载临时数据
            raw_data = self.storage.load_temp_data(X_TEMP_DATA_PATH)
            if not raw_data:
                logger.info("没有X.com数据需要处理")
                return 0
            
            # 获取系统提示词
            system_prompt = SystemPrompts.get_x_prompt()
            
            # 处理数据
            processed_data = []
            for item in raw_data:
                try:
                    # 准备提示词
                    prompt = json.dumps(item, ensure_ascii=False)
                    
                    # 调用AI处理
                    result = self._call_ai_api(system_prompt, prompt)
                    if not result:
                        continue
                    
                    # 构建文章数据
                    article = {
                        "title": "",  # 将从AI返回结果中提取
                        "content": result,
                        "source": "x.com",
                        "source_url": item.get("source_url", ""),
                        "date_time": item.get("date_time", ""),
                        "author": item.get("author", ""),
                        "raw": item  # 保存原始数据
                    }
                    
                    processed_data.append(article)
                    
                except Exception as e:
                    logger.error(f"处理X.com数据项失败: {str(e)}")
                    continue
            
            # 保存处理后的数据
            saved_count = self.storage.save_articles(processed_data)
            
            # 清空临时文件
            self.storage.clear_temp_file(X_TEMP_DATA_PATH)
            
            return saved_count
            
        except Exception as e:
            logger.error(f"处理X.com数据失败: {str(e)}")
            return 0


class CrunchbaseDataProcessor(DataProcessor):
    """Crunchbase数据处理器"""
    
    def process(self) -> int:
        """处理Crunchbase数据"""
        try:
            # 加载临时数据
            raw_data = self.storage.load_temp_data(CRU_TEMP_DATA_PATH)
            if not raw_data:
                logger.info("没有Crunchbase数据需要处理")
                return 0
            
            # 获取系统提示词
            system_prompt = SystemPrompts.get_crunchbase_prompt()
            
            # 处理数据
            processed_data = []
            for item in raw_data:
                try:
                    # 准备提示词
                    prompt = json.dumps(item, ensure_ascii=False)
                    
                    # 调用AI处理
                    result = self._call_ai_api(system_prompt, prompt)
                    if not result:
                        continue
                    
                    # 构建文章数据
                    article = {
                        "title": "",  # 将从AI返回结果中提取
                        "content": result,
                        "source": "crunchbase.com",
                        "source_url": item.get("source_url", ""),
                        "date_time": item.get("date_time", ""),
                        "author": item.get("author", ""),
                        "raw": item  # 保存原始数据
                    }
                    
                    processed_data.append(article)
                    
                except Exception as e:
                    logger.error(f"处理Crunchbase数据项失败: {str(e)}")
                    continue
            
            # 保存处理后的数据
            saved_count = self.storage.save_articles(processed_data)
            
            # 清空临时文件
            self.storage.clear_temp_file(CRU_TEMP_DATA_PATH)
            
            return saved_count
            
        except Exception as e:
            logger.error(f"处理Crunchbase数据失败: {str(e)}")
            return 0


def process_all_data() -> bool:
    """处理所有数据源的数据"""
    success = True
    processors = [
        XDataProcessor(),
        CrunchbaseDataProcessor()
    ]
    
    try:
        for processor in processors:
            try:
                count = processor.process()
                logger.info(f"处理器 {processor.__class__.__name__} 完成，保存了 {count} 条数据")
            except Exception as e:
                logger.error(f"处理器 {processor.__class__.__name__} 失败: {str(e)}")
                success = False
            finally:
                processor.close()
    except Exception as e:
        logger.error(f"处理数据时发生错误: {str(e)}")
        success = False
    
    return success


if __name__ == "__main__":
    success = process_all_data()
    sys.exit(0 if success else 1)