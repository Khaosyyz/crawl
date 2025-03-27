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
        return (
            "你是一位专业的AI行业资讯分析整理师，请将X.com上的推文整理为标准的新闻格式。\n\n"
            "如果内容与AI技术、人工智能应用或机器学习等领域无关，请直接回复:\"这条资讯与AI无关，跳过。\"\n\n"
            "如果内容与AI相关，请按以下格式返回清洗后的内容：\n\n"
            "标题: [根据内容生成的标题，确保简洁明了并包含关键信息]\n"
            "正文: [推文的主要内容，清晰简洁的行业新闻格式，移除冗余信息，保持专业性]\n"
            "作者: [原作者名] (@[用户名])\n"
            "粉丝数: [粉丝数值]\n"
            "点赞数: [点赞数值]\n"
            "转发数: [转发数值]\n"
            "日期: [原文发布日期，格式为YYYY-MM-DD HH:MM]\n\n"
            
            "处理要求：\n"
            "1. 必须严格按照以上字段顺序和格式返回\n"
            "2. 标题必须提取或生成，不可为空\n"
            "3. 正文必须经过整理，以专业新闻的语气呈现\n"
            "4. 保留专有名词的英文原文\n"
            "5. 英文和数字前后需加空格提高可读性\n"
            "6. 所有返回必须是结构化的字段，便于JSON解析\n"
            "7. 不在返回内容中添加额外说明或注释\n"
            "8. 所有内容必须有明确边界，每个字段单独成行"
        )
    
    @staticmethod
    def get_crunchbase_prompt() -> str:
        """获取处理Crunchbase数据的系统提示词"""
        return (
            "你是一位专业的投资信息分析整理师，请将Crunchbase文章处理为标准的新闻格式。\n\n"
            "请按以下格式返回清洗后的内容：\n\n"
            "标题: [根据内容生成的标题，突出投资和融资信息]\n"
            "正文: [完整翻译成中文的文章内容，分段清晰]\n"
            "作者: [原作者姓名]\n"
            "公司: [相关公司名称]\n"
            "融资轮次: [轮次信息，如种子轮、A轮等]\n"
            "融资金额: [融资金额]\n"
            "投资方: [投资机构或个人]\n"
            "日期: [原文发布日期，格式为YYYY-MM-DD]\n\n"
            
            "处理要求：\n"
            "1. 必须严格按照以上字段顺序和格式返回\n"
            "2. 标题必须生成，突出融资关键信息\n"
            "3. 正文必须完全翻译成中文，保留专有名词\n"
            "4. 英文和数字前后需加空格提高可读性\n"
            "5. 所有返回必须是结构化的字段，便于JSON解析\n"
            "6. 不在返回内容中添加额外说明或注释\n"
            "7. 如原文没有提供某字段信息，请使用'未提供'填充\n"
            "8. 所有内容必须有明确边界，每个字段单独成行"
        )
    
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
                    
                    # 检查是否是"跳过"响应
                    if "这条资讯与AI无关，跳过" in result:
                        logger.info("资讯与AI无关，跳过处理")
                        continue
                    
                    # 从AI返回结果中提取结构化数据
                    article = self._parse_ai_response(result, item)
                    
                    # 确保article不为None
                    if article:
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
            logger.error(f"X.com数据处理失败: {str(e)}")
            return 0
    
    def _parse_ai_response(self, response: str, original_item: Dict) -> Optional[Dict]:
        """从AI响应中解析结构化数据
        
        Args:
            response: AI返回的文本
            original_item: 原始数据项
            
        Returns:
            结构化的文章数据，解析失败则返回None
        """
        try:
            # 初始化文章数据
            article = {
                "title": "",
                "content": "",
                "source": "x.com",
                "source_url": original_item.get("source_url", ""),
                "date_time": original_item.get("date_time", ""),
                "author": "",
                "followers_count": 0,
                "favorite_count": 0,
                "retweet_count": 0,
                "raw": original_item
            }
            
            # 解析AI返回的结构化内容
            lines = response.strip().split('\n')
            current_field = None
            field_content = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 检查是否是字段标识行
                if ":" in line and len(line.split(":", 1)[0]) < 20:
                    # 如果已有当前字段，先保存
                    if current_field and field_content:
                        field_value = '\n'.join(field_content).strip()
                        if current_field == "标题":
                            article["title"] = field_value
                        elif current_field == "正文":
                            article["content"] = field_value
                        elif current_field == "作者":
                            article["author"] = field_value
                        elif current_field == "粉丝数":
                            try:
                                article["followers_count"] = int(field_value.replace(',', ''))
                            except:
                                pass
                        elif current_field == "点赞数":
                            try:
                                article["favorite_count"] = int(field_value.replace(',', ''))
                            except:
                                pass
                        elif current_field == "转发数":
                            try:
                                article["retweet_count"] = int(field_value.replace(',', ''))
                            except:
                                pass
                        elif current_field == "日期":
                            article["date_time"] = field_value
                    
                    # 设置新的当前字段
                    field_parts = line.split(":", 1)
                    current_field = field_parts[0].strip()
                    field_content = [field_parts[1].strip()] if len(field_parts) > 1 else []
                else:
                    # 继续添加到当前字段
                    if current_field:
                        field_content.append(line)
            
            # 处理最后一个字段
            if current_field and field_content:
                field_value = '\n'.join(field_content).strip()
                if current_field == "标题":
                    article["title"] = field_value
                elif current_field == "正文":
                    article["content"] = field_value
                elif current_field == "作者":
                    article["author"] = field_value
                elif current_field == "粉丝数":
                    try:
                        article["followers_count"] = int(field_value.replace(',', ''))
                    except:
                        pass
                elif current_field == "点赞数":
                    try:
                        article["favorite_count"] = int(field_value.replace(',', ''))
                    except:
                        pass
                elif current_field == "转发数":
                    try:
                        article["retweet_count"] = int(field_value.replace(',', ''))
                    except:
                        pass
                elif current_field == "日期":
                    article["date_time"] = field_value
            
            # 整理文章格式，确保文章结构完整
            # 如果标题为空，从内容提取或生成一个
            if not article["title"] and article["content"]:
                first_line = article["content"].split('\n', 1)[0]
                if len(first_line) < 100:
                    article["title"] = first_line
                else:
                    article["title"] = first_line[:100] + "..."
            
            # 确保内容不为空
            if not article["content"]:
                logger.warning("解析后的文章内容为空，使用原始文本")
                article["content"] = response
            
            return article
            
        except Exception as e:
            logger.error(f"解析AI响应失败: {str(e)}")
            return None


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
                    
                    # 从AI返回结果中提取结构化数据
                    article = self._parse_ai_response(result, item)
                    
                    # 确保article不为None
                    if article:
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
            logger.error(f"Crunchbase数据处理失败: {str(e)}")
            return 0
    
    def _parse_ai_response(self, response: str, original_item: Dict) -> Optional[Dict]:
        """从AI响应中解析结构化数据
        
        Args:
            response: AI返回的文本
            original_item: 原始数据项
            
        Returns:
            结构化的文章数据，解析失败则返回None
        """
        try:
            # 初始化文章数据
            article = {
                "title": "",
                "content": "",
                "source": "crunchbase.com",
                "source_url": original_item.get("source_url", ""),
                "date_time": original_item.get("date_time", ""),
                "author": "",
                "company": "",
                "funding_round": "",
                "funding_amount": "",
                "investors": "",
                "raw": original_item
            }
            
            # 解析AI返回的结构化内容
            lines = response.strip().split('\n')
            current_field = None
            field_content = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 检查是否是字段标识行
                if ":" in line and len(line.split(":", 1)[0]) < 20:
                    # 如果已有当前字段，先保存
                    if current_field and field_content:
                        field_value = '\n'.join(field_content).strip()
                        if current_field == "标题":
                            article["title"] = field_value
                        elif current_field == "正文":
                            article["content"] = field_value
                        elif current_field == "作者":
                            article["author"] = field_value
                        elif current_field == "公司":
                            article["company"] = field_value
                        elif current_field == "融资轮次":
                            article["funding_round"] = field_value
                        elif current_field == "融资金额":
                            article["funding_amount"] = field_value
                        elif current_field == "投资方":
                            article["investors"] = field_value
                        elif current_field == "日期":
                            article["date_time"] = field_value
                    
                    # 设置新的当前字段
                    field_parts = line.split(":", 1)
                    current_field = field_parts[0].strip()
                    field_content = [field_parts[1].strip()] if len(field_parts) > 1 else []
                else:
                    # 继续添加到当前字段
                    if current_field:
                        field_content.append(line)
            
            # 处理最后一个字段
            if current_field and field_content:
                field_value = '\n'.join(field_content).strip()
                if current_field == "标题":
                    article["title"] = field_value
                elif current_field == "正文":
                    article["content"] = field_value
                elif current_field == "作者":
                    article["author"] = field_value
                elif current_field == "公司":
                    article["company"] = field_value
                elif current_field == "融资轮次":
                    article["funding_round"] = field_value
                elif current_field == "融资金额":
                    article["funding_amount"] = field_value
                elif current_field == "投资方":
                    article["investors"] = field_value
                elif current_field == "日期":
                    article["date_time"] = field_value
            
            # 整理文章格式，确保文章结构完整
            # 如果标题为空，从内容提取或生成一个
            if not article["title"] and article["content"]:
                first_line = article["content"].split('\n', 1)[0]
                if len(first_line) < 100:
                    article["title"] = first_line
                else:
                    article["title"] = first_line[:100] + "..."
            
            # 确保内容不为空
            if not article["content"]:
                logger.warning("解析后的文章内容为空，使用原始文本")
                article["content"] = response
            
            return article
            
        except Exception as e:
            logger.error(f"解析AI响应失败: {str(e)}")
            return None


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