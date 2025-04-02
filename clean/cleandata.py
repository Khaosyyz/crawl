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
MODEL_NAME = 'gemini-2.5-pro-exp-03-25'  # 改为 gemini-2.5-pro-exp-03-25

# 控制API请求频率的参数
BATCH_SIZE = 10  # 每批处理的数据量
BATCH_INTERVAL = 20  # 批处理间隔（秒）

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
        return """你是一位专业的AI行业资讯分析整理师，请将X.com上的推文整理为标准的新闻格式。

第一步：必须先将所有内容（无论语言）完整翻译成中文，保持专业性和准确性。

第二步：判断翻译后的内容是否与AI技术、人工智能应用、机器学习、深度学习、生成式AI、大模型等人工智能相关技术领域相关。只有高度相关的内容才会被处理。

第三步：如果内容与AI相关，请按以下格式返回清洗后的内容：

标题: [根据翻译后的内容自拟新闻标题，确保简洁明了(25字以内)且包含关键信息，突出公司名称、技术名称或产品名称，避免使用"关于"、"如何"等模糊词语]
正文: [翻译后的内容，整理为清晰简洁的行业新闻格式，分段合理，删除冗余信息。如原始内容中包含URL链接，根据链接内容和上下文，使用合适的描述，例如"——报告链接：@URL"、"——图片来源：@URL"、"——视频来源：@URL"、"——资讯来源：@URL"、"——白皮书链接：@URL"等，放在相关段落后]
作者: [原作者名] (@[用户名])
粉丝数: [粉丝数值]
点赞数: [点赞数值]
转发数: [转发数值]
日期: [原文发布日期，格式为YYYY-MM-DD HH:MM]

处理要求：
1. 无论内容多少，必须先完整翻译成中文再进行判断和处理
2. 必须严格按照以上字段顺序和格式返回
3. 标题必须自拟新闻标题，25字以内，简洁有力，突出技术产品或公司名称
4. 正文必须是翻译后的中文内容，以专业新闻的语气呈现，保持原文的信息完整性
5. 保留专有名词的中文翻译，重要的技术词汇保留英文原文标注，如"大型语言模型(Large Language Model, LLM)"
6. 英文和数字前后需加空格提高可读性
7. 对原文中的URL链接，根据上下文判断链接类型，选择合适的描述文本（如报告链接、图片来源、视频链接、资讯来源、白皮书等），使用"——[适当描述]：@URL"的格式展示
8. 所有返回必须是结构化的字段，便于JSON解析
9. 如果翻译后判断内容与AI无关，则不返回任何内容
10. 不在返回内容中添加额外说明或注释
11. 所有内容必须有明确边界，每个字段单独成行
12. 注意截断太长的内容，但必须保持句子和段落的完整性"""
    
    @staticmethod
    def get_crunchbase_prompt() -> str:
        """获取处理Crunchbase数据的系统提示词"""
        return """你是一位专业的AI行业投资信息分析整理师，请将Crunchbase融资或投资文章处理为标准的新闻格式。

第一步：必须先将所有内容（无论语言）完整翻译成中文，保持专业性和准确性。

第二步：判断翻译后的内容是否与AI技术、人工智能公司、机器学习应用等相关。只有高度相关的内容才会被处理。

第三步：请按以下格式返回清洗后的内容：

标题: [格式为"公司名+融资金额+轮次"，例如"AI初创公司XXX完成1000万美元A轮融资"，确保简洁明了且符合新闻标题规范]
正文: [翻译后的内容，整理为多段式新闻正文，第一段概述融资情况，后续段落介绍公司背景、技术、产品及用途，最后段落可提及投资方信息。确保段落分明，语句通顺，可读性高。如原始内容中包含URL链接，根据链接内容和上下文，选择合适的描述文本，例如"——公司官网：@URL"、"——融资公告：@URL"、"——产品介绍：@URL"等，放在相关段落后]
作者: [原作者姓名，若无则填"未提供"]
公司: [相关公司名称，必须准确提取]
融资轮次: [轮次信息，如种子轮、A轮等，必须准确提取]
融资金额: [融资金额，必须准确提取，包含货币单位]
投资方: [投资机构或个人名称列表，必须准确提取]
日期: [原文发布日期，格式为YYYY-MM-DD]

处理要求：
1. 无论内容多少，必须先完整翻译成中文再进行判断和处理
2. 必须严格按照以上字段顺序和格式返回
3. 标题必须按照"公司名+融资金额+轮次"模式，25字以内，具有新闻价值
4. 正文必须采用专业新闻报道格式，分成3-5个段落，每段不超过3-4个句子
5. 重要的公司名称、产品名称等专有名词需保留英文原文标注，如"人工智能公司DeepMind"
6. 英文和数字前后需加空格提高可读性
7. 对原文中的URL链接，根据上下文判断链接类型，选择合适的描述文本（如公司官网、融资公告、产品介绍等），使用"——[适当描述]：@URL"的格式展示
8. 务必准确提取融资轮次、融资金额和投资方信息，这些是关键数据
9. 所有返回必须是结构化的字段，便于JSON解析
10. 如果翻译后判断内容与AI行业投资无关，则不返回任何内容
11. 不在返回内容中添加额外说明或注释
12. 如原文确实没有提供某字段信息，请使用'未提供'填充
13. 所有内容必须有明确边界，每个字段单独成行"""
    
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
                
                if ':' in line and not line.startswith('http') and not line.startswith('——报告链接：@http'):
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
            
            # 验证必要字段 - 如果缺少标题，则使用原始文本生成一个
            if 'title' not in parsed or not parsed['title']:
                logger.info("解析结果缺少标题字段，尝试生成标题")
                # 使用原始文本的开头作为标题（最多50个字符）
                raw_text = original_item.get('text', '').strip()
                if raw_text:
                    # 取前50个字符，确保不截断单词
                    if len(raw_text) > 50:
                        title_text = raw_text[:50].rsplit(' ', 1)[0] + '...'
                    else:
                        title_text = raw_text
                    parsed['title'] = f"AI相关：{title_text}"
                else:
                    # 如果原始文本为空，使用通用标题
                    parsed['title'] = "AI行业动态"
                
                logger.info(f"自动生成标题: {parsed['title']}")
            
            # 如果内容为空，尝试使用原始文本
            if 'content' not in parsed or not parsed['content']:
                logger.warning("解析结果缺少正文字段，使用原始文本")
                raw_text = original_item.get('text', '')
                if raw_text:
                    parsed['content'] = TextUtils.standardize_punctuation(raw_text)
                else:
                    # 如果真的没有内容，跳过
                    logger.warning("无法获取内容，跳过处理")
                    return None
            
            # 使用原始数据中的作者信息
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
                
                if ':' in line and not line.startswith('http') and not line.startswith('——报告链接：@http'):
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
            
            # 验证必要字段 - 如果缺少标题，则尝试从原始数据生成
            if 'title' not in parsed or not parsed['title']:
                logger.info("解析结果缺少标题字段，尝试生成标题")
                # 首先尝试使用原始文章标题
                if original_item.get('title'):
                    parsed['title'] = original_item.get('title')
                # 否则使用原始文本的开头
                else:
                    raw_text = original_item.get('content', '').strip()
                    if raw_text:
                        # 取前50个字符，确保不截断单词
                        if len(raw_text) > 50:
                            title_text = raw_text[:50].rsplit(' ', 1)[0] + '...'
                        else:
                            title_text = raw_text
                        parsed['title'] = f"投融资：{title_text}"
                    else:
                        # 如果原始文本为空，使用通用标题
                        parsed['title'] = "Crunchbase投融资资讯"
                
                logger.info(f"自动生成标题: {parsed['title']}")
            
            # 如果内容为空，尝试使用原始文本
            if 'content' not in parsed or not parsed['content']:
                logger.warning("解析结果缺少正文字段，使用原始文本")
                raw_text = original_item.get('content', '')
                if raw_text:
                    # 为原始内容应用特殊格式化
                    parsed['content'] = TextUtils.format_crunchbase_content(raw_text)
                    parsed['content'] = TextUtils.standardize_punctuation(parsed['content'])
                else:
                    # 如果真的没有内容，跳过
                    logger.warning("无法获取内容，跳过处理")
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