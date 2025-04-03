#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据清洗模块 - 将爬取的原始数据清洗为结构化内容
支持多种数据源，包括X.com和Crunchbase等
每种数据源使用独立的处理逻辑
"""

import os
import sys
import json
import time
import logging
import re
import hashlib
import traceback
import signal
import random
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime
import threading
from openai import OpenAI

from src.utils.paths import X_TEMP_DATA_PATH, CRU_TEMP_DATA_PATH, LOGS_DIR, DATA_DIR
from src.utils.log_handler import get_logger

# 创建日志记录器
logger = get_logger("cleandata")

# 创建全局线程锁用于保护文件操作
jsonl_lock = threading.Lock()

# 常量定义
API_KEY = 'p9mtsT4ioDYm1'
API_BASE_URL = 'https://ai.liaobots.work/v1'
MODEL_NAME = 'deepseek-v3-0324'

# 更详细的API配置
API_REQUEST_TIMEOUT = 60  # 秒
API_MAX_TOKENS = 4000

# 控制API请求频率的参数
BATCH_SIZE = 8  # 每批处理的数据量，从3改为8
BATCH_INTERVAL = 10  # 批处理间隔（秒），从30减少到10

# 内容验证常量
MIN_CLEAN_TITLE_LENGTH = 8  # 标题最小长度
MAX_EMOJI_RATIO = 0.1  # 表情符号最大比例

# 初始化 OpenAI 客户端
try:
    client = OpenAI(
        api_key=API_KEY,
        base_url=API_BASE_URL,
        timeout=API_REQUEST_TIMEOUT
    )
    logger.info(f"OpenAI 客户端初始化成功，使用模型: {MODEL_NAME}, 基础URL: {API_BASE_URL}")
except Exception as e:
    logger.error(f"OpenAI 客户端初始化失败: {str(e)}")
    client = None

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

第一步：必须将任何语言完整翻译成准确流畅的中文，保持专业术语的准确性。

第二步：判断内容是否与AI技术相关。判断标准：
- 内容涉及AI技术、大模型、机器学习、深度学习等人工智能核心技术
- 或讨论AI应用、产品发布、研究进展、商业动态
- 或分析AI行业趋势、伦理问题、监管政策等
- 重要：关于AI艺术、AI生成内容的讨论、争议和观点也属于相关内容
- 批评AI或讨论AI的负面影响也是相关内容，这些讨论对理解行业非常重要
- 拒绝表情符号过多、内容质量低的无价值信息

第三步：如果内容与AI相关，必须返回以下JSON格式数据：

```json
{
  "title": "25字以内的专业新闻标题",
  "content": "组织为清晰的中文新闻报道，分段合理，保留专业术语。必须处理原文中的所有媒体链接和URL，将它们以描述性文本的形式放在正文末尾（如有多个链接则分行列出）。例如：\n\n正文内容...\n\n——图片链接：https://example.com/image.jpg\n——视频链接：https://example.com/video.mp4",
  "author": "原作者名 (@用户名)",
  "粉丝数": 数值,
  "点赞数": 数值,
  "转发数": 数值,
  "日期": "YYYY-MM-DD HH:MM格式"
}
```

处理要求：
1. 对非AI相关内容，返回空对象 `{}`
2. 所有内容必须严格按照JSON格式返回，确保格式正确可解析
3. 精心编写标题，25字以内，专业准确，避免"相关"、"关于"等模糊用词
4. 正文保持信息完整性和专业性，确保段落和句子逻辑清晰
5. 对AI专业词汇，保留原文术语如"GPT-4"，并提供适当中文说明
6. 所有英文和数字前后都必须加空格提高可读性，例如"GPT-4 模型"而非"GPT-4模型"，"共 50 张图片"而非"共50张图片"
7. 必须处理并保留原文中的媒体链接，对于图片链接使用"——图片链接："开头，对于视频链接使用"——视频链接："开头，对于普通链接使用"——链接："开头
8. 最终内容必须只返回JSON格式，不要有其他额外文本"""
    
    @staticmethod
    def get_crunchbase_prompt() -> str:
        """获取处理Crunchbase数据的系统提示词"""
        return """你是一位专业的AI行业投资信息整理师，请将Crunchbase融资或投资文章处理为标准的新闻格式。

第一步：将内容完整翻译成准确专业的中文，保持原文的信息量和详细程度。

第二步：严格判断内容是否与AI行业投资相关。判断标准：
- 必须涉及AI技术公司、AI产品或服务的融资、收购或投资活动
- 或AI相关技术创业、风险投资、市场拓展等商业活动
- 拒绝与人工智能无明显关联的一般科技投融资新闻
- 拒绝表情符号过多、内容质量低的无价值信息

第三步：如果确定是AI相关投资内容，必须返回以下JSON格式数据：

```json
{
  "title": "公司名+融资金额+轮次格式，25字以内",
  "content": "将原文翻译成流利易懂的中文，但必须保持原文的段落结构、信息量和详细程度。不要过度精简内容，确保重要细节如公司历史、融资背景、产品描述、市场分析等关键信息都被保留。英文和数字前后必须加空格提高可读性。",
  "author": "原作者姓名，若无则填'未提供'",
  "公司": "相关公司名称",
  "融资轮次": "种子轮/A轮等具体轮次",
  "融资金额": "包含货币单位的金额",
  "投资方": "投资机构或个人名称",
  "日期": "从输入文本的'发布时间'字段提取日期，格式为YYYY-MM-DD，若无法提取则使用'未提供'"
}
```

处理要求：
1. 对非AI相关投资内容，返回空对象 `{}`
2. 所有内容必须严格按照JSON格式返回，确保格式正确可解析
3. 精心编写标题，确保格式统一且专业
4. 正文内容必须保持原文的全部信息量、段落结构和逻辑脉络，不要过度简化或删减内容
5. 务必准确提取融资金额、轮次和投资方信息
6. 保留重要专有名词的原文表示，如"OpenAI"
7. 所有英文和数字前后都必须加空格提高可读性，例如"融资 1000 万美元"而非"融资1000万美元"
8. 务必从输入文本的"发布时间"字段提取日期，不要填写"未提供"除非原文确实没有日期
9. 最终内容必须只返回JSON格式，不要有其他额外文本"""
    
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
    def ensure_space_around_english_and_numbers(text: str) -> str:
        """确保英文单词和数字前后有空格"""
        if not text:
            return ""
        
        # 匹配英文单词或数字
        # 1. 中文后面跟英文/数字，需要加空格
        text = re.sub(r'([\u4e00-\u9fa5])([a-zA-Z0-9])', r'\1 \2', text)
        
        # 2. 英文/数字后面跟中文，需要加空格
        text = re.sub(r'([a-zA-Z0-9])([\u4e00-\u9fa5])', r'\1 \2', text)
        
        # 不处理URL或链接中的空格
        # 先标记URL
        urls = re.findall(r'https?://[^\s]+', text)
        for i, url in enumerate(urls):
            placeholder = f"__URL_PLACEHOLDER_{i}__"
            text = text.replace(url, placeholder)
        
        # 处理连续数字间的空格异常（例如：100 000 -> 100000）
        text = re.sub(r'(\d+)\s+(\d+)', lambda m: m.group(1) + m.group(2) if len(m.group(1)) + len(m.group(2)) <= 10 else m.group(0), text)
        
        # 恢复URL
        for i, url in enumerate(urls):
            placeholder = f"__URL_PLACEHOLDER_{i}__"
            text = text.replace(placeholder, url)
        
        return text
    
    @staticmethod
    def format_crunchbase_content(content: str) -> str:
        """格式化Crunchbase内容，为具体链接添加标签等处理"""
        if not content:
            return ""
            
        # 处理链接格式，规范为统一形式
        content = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', 
                         lambda m: f"[链接]({m.group(0)})", content)
        
        # 确保段落之间有适当的空行
        content = re.sub(r'(?<!\n)\n(?!\n)', "\n\n", content)
        
        # 限制段落长度，超过300字符的段落适当分段
        paragraphs = content.split("\n\n")
        formatted_paragraphs = []
        for para in paragraphs:
            if len(para) > 300:
                sentences = re.split(r'([。！？.!?])', para)
                new_para = ""
                char_count = 0
                for i in range(0, len(sentences), 2):
                    if i+1 < len(sentences):
                        sentence = sentences[i] + sentences[i+1]
                    else:
                        sentence = sentences[i]
                    if char_count + len(sentence) > 300:
                        new_para += "\n\n" + sentence
                        char_count = len(sentence)
                    else:
                        new_para += sentence
                        char_count += len(sentence)
                formatted_paragraphs.append(new_para)
            else:
                formatted_paragraphs.append(para)
        
        return "\n\n".join(formatted_paragraphs)
    
    @staticmethod
    def count_emoji(text: str) -> int:
        """统计文本中表情符号的数量"""
        # Unicode表情符号范围
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # 表情符号
            "\U0001F300-\U0001F5FF"  # 符号和象形文字
            "\U0001F680-\U0001F6FF"  # 交通和地图符号
            "\U0001F700-\U0001F77F"  # 字母符号
            "\U0001F780-\U0001F7FF"  # 几何符号
            "\U0001F800-\U0001F8FF"  # 补充箭头
            "\U0001F900-\U0001F9FF"  # 补充符号和象形文字
            "\U0001FA00-\U0001FA6F"  # 国际象棋符号
            "\U0001FA70-\U0001FAFF"  # 符号和象形文字扩展
            "\U00002702-\U000027B0"  # Dingbats
            "\U000024C2-\U0001F251" 
            "]+"
        )
        return len(emoji_pattern.findall(text))
    
    @staticmethod
    def validate_cleaned_content(title: str, content: str) -> bool:
        """验证清洗后的内容是否符合要求"""
        # 检查标题长度，降低要求为至少2个字符
        if not title or len(title) < 2:
            logger.warning(f"标题长度不足: '{title}'")
            return False
            
        # 检查内容长度
        if not content or len(content) < 50:
            logger.warning(f"内容长度不足: {len(content) if content else 0}字符")
            return False
            
        # 检查表情符号比例
        emoji_count = TextUtils.count_emoji(title + content)
        total_length = len(title) + len(content)
        emoji_ratio = emoji_count / total_length if total_length > 0 else 0
        
        if emoji_ratio > MAX_EMOJI_RATIO:
            logger.warning(f"表情符号比例过高: {emoji_ratio:.2f}, 共{emoji_count}个表情符号")
            return False
            
        # 我们不再使用关键词检查，完全由AI在提示词中判断是否与AI相关
        return True


class DataProcessor:
    """数据处理器基类，提供通用处理逻辑"""
    
    def __init__(self):
        """初始化数据处理器"""
        # 导入DataStorage类
        from src.clean.storage import DataStorage
        
        # 使用全局客户端
        self.client = client
        if self.client is None:
            logger.error("无法初始化数据处理器，OpenAI客户端不可用")
            # 尝试重新初始化客户端
            try:
                self.client = OpenAI(
                    api_key=API_KEY,
                    base_url=API_BASE_URL,
                    timeout=API_REQUEST_TIMEOUT
                )
                logger.info("成功重新初始化OpenAI客户端")
            except Exception as e:
                logger.error(f"重新初始化OpenAI客户端失败: {str(e)}")
        
        self.model = MODEL_NAME
        self.storage = DataStorage()
    
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
                    temperature=0.1,
                    timeout=30  # 增加超时时间到30秒
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
            # 确保raw是一个字典
            if 'raw' not in item or not isinstance(item['raw'], dict):
                logger.error(f"X数据缺少raw字段或raw不是字典类型: {item.get('source_url', 'unknown')}")
                return None
            
            # 准备输入文本
            raw_data = item.get('raw', {})
            author_name = raw_data.get('name', '')
            author_username = raw_data.get('username', '')
            
            # 日志记录更详细的数据
            logger.info(f"处理X数据: 作者={author_name}, 粉丝={raw_data.get('followers_count', 0)}, URL={item.get('source_url', '')}")
            
            # 处理媒体URL
            media_urls_text = ""
            if 'media_urls' in raw_data and raw_data['media_urls']:
                media_urls = raw_data['media_urls']
                media_urls_text = "\n\n媒体链接:\n"
                for i, url in enumerate(media_urls):
                    media_type = "图片" if any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif']) else "视频" if any(ext in url.lower() for ext in ['.mp4', '.mov', '.avi']) else "链接"
                    media_urls_text += f"{i+1}. {media_type}链接: {url}\n"
            
            # 构建输入文本，确保所有必要信息都包含
            input_text = (
                f"推文内容: {item.get('text', '')}\n\n"
                f"作者: {author_name} (@{author_username})\n"
                f"粉丝数: {raw_data.get('followers_count', 0)}\n"
                f"点赞数: {raw_data.get('favorite_count', 0)}\n"
                f"转发数: {raw_data.get('retweet_count', 0)}\n"
                f"发布时间: {item.get('date_time', '')}"
            )
            
            # 添加媒体URL信息
            if media_urls_text:
                input_text += f"\n{media_urls_text}"
            
            # 获取系统提示词
            system_prompt = SystemPrompts.get_for_source("x.com")
            
            # 调用AI处理，增加重试
            max_retries = 3
            for retry in range(max_retries):
                try:
                    result = self._call_ai_api(system_prompt, input_text)
                    break
                except Exception as e:
                    if retry < max_retries - 1:
                        logger.warning(f"API调用失败，重试 ({retry+1}/{max_retries}): {str(e)}")
                        time.sleep(5)
                    else:
                        logger.error(f"API调用最终失败: {str(e)}")
                        return None
            
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
            # 记录原始API响应以进行调试
            logger.info(f"API原始响应: {result}")
            
            # 首先尝试将结果解析为JSON
            try:
                # 检查是否包含JSON字符串（可能被额外文本包围）
                json_start = result.find('{')
                json_end = result.rfind('}')
                
                if json_start >= 0 and json_end > json_start:
                    json_str = result[json_start:json_end+1]
                    logger.info(f"尝试解析JSON: {json_str}")
                    parsed_json = json.loads(json_str)
                    
                    # 如果成功解析为JSON，从中提取我们需要的字段
                    if isinstance(parsed_json, dict):
                        # 应用空格处理函数
                        title = parsed_json.get('标题', parsed_json.get('title', ''))
                        content = parsed_json.get('正文', parsed_json.get('content', ''))
                        title = TextUtils.ensure_space_around_english_and_numbers(title)
                        content = TextUtils.ensure_space_around_english_and_numbers(content)
                        
                        return {
                            'title': title,
                            'content': content,
                            'author': parsed_json.get('作者', parsed_json.get('author', '')),
                            'date_time': parsed_json.get('日期', parsed_json.get('date_time', original_item.get('date_time', ''))),
                            'source': 'x.com',
                            'source_url': original_item.get('source_url', original_item.get('raw', {}).get('url', '')),
                            'likes': parsed_json.get('点赞数', parsed_json.get('likes', original_item.get('raw', {}).get('favorite_count', 0))),
                            'retweets': parsed_json.get('转发数', parsed_json.get('retweets', original_item.get('raw', {}).get('retweet_count', 0))),
                            'followers': parsed_json.get('粉丝数', parsed_json.get('followers', original_item.get('raw', {}).get('followers_count', 0))),
                            'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'id': generate_id(f"x.com_{original_item.get('source_url', '')}")
                        }
            except Exception as e:
                logger.warning(f"JSON解析失败，回退到文本解析: {e}")
            
            # 如果JSON解析失败，回退到文本解析
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
            
            # 应用空格处理函数
            title = TextUtils.ensure_space_around_english_and_numbers(parsed.get('title', ''))
            content = TextUtils.ensure_space_around_english_and_numbers(parsed.get('content', ''))
            
            # 构建最终结构化数据
            structured_data = {
                'title': title,
                'content': content,
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
            # 准备输入文本，确保包含published_date字段
            input_text = (
                f"文章标题: {item.get('title', '')}\n\n"
                f"文章内容: {item.get('content', '')}\n\n"
                f"作者: {item.get('author', '')}\n"
                f"发布时间: {item.get('published_date', item.get('date_time', ''))}\n"
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
            # 记录原始API响应以进行调试
            logger.info(f"API原始响应(Crunchbase): {result}")
            
            # 首先尝试将结果解析为JSON
            try:
                # 检查是否包含JSON字符串（可能被额外文本包围）
                json_start = result.find('{')
                json_end = result.rfind('}')
                
                if json_start >= 0 and json_end > json_start:
                    json_str = result[json_start:json_end+1]
                    logger.info(f"尝试解析JSON(Crunchbase): {json_str}")
                    parsed_json = json.loads(json_str)
                    
                    # 如果成功解析为JSON，从中提取我们需要的字段
                    if isinstance(parsed_json, dict):
                        # 应用空格处理函数
                        title = parsed_json.get('标题', parsed_json.get('title', ''))
                        content = parsed_json.get('正文', parsed_json.get('content', ''))
                        title = TextUtils.ensure_space_around_english_and_numbers(title)
                        content = TextUtils.ensure_space_around_english_and_numbers(content)
                        
                        # 优先从文本解析结果中获取日期，如果为空或"未提供"则从原始数据中获取
                        date_from_parsed = parsed_json.get('日期', '')
                        if date_from_parsed and date_from_parsed != '未提供':
                            date_time = date_from_parsed
                        else:
                            date_time = original_item.get('published_date', original_item.get('date_time', ''))
                        
                        structured_data = {
                            'title': title,
                            'content': content,
                            'author': parsed_json.get('作者', parsed_json.get('author', '')),
                            'date_time': date_time,
                            'source': 'crunchbase.com',
                            'source_url': original_item.get('url', ''),
                            'company': parsed_json.get('公司', parsed_json.get('company', '')),
                            'funding_round': parsed_json.get('融资轮次', parsed_json.get('funding_round', '')),
                            'funding_amount': parsed_json.get('融资金额', parsed_json.get('funding_amount', '')),
                            'investors': parsed_json.get('投资方', parsed_json.get('investors', '')),
                            'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        
                        # 生成唯一ID
                        id_text = f"crunchbase.com_{structured_data['source_url']}"
                        structured_data['id'] = generate_id(id_text)
                        
                        return structured_data
            except Exception as e:
                logger.warning(f"JSON解析失败(Crunchbase)，回退到文本解析: {e}")
            
            # 如果JSON解析失败，回退到文本解析
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
            
            # 应用空格处理函数
            title = TextUtils.ensure_space_around_english_and_numbers(parsed.get('title', ''))
            content = TextUtils.ensure_space_around_english_and_numbers(parsed.get('content', ''))
            
            # 优先从文本解析结果中获取日期，如果为空或"未提供"则从原始数据中获取
            date_from_parsed = parsed.get('date_time', '')
            if date_from_parsed and date_from_parsed != '未提供':
                date_time = date_from_parsed
            else:
                date_time = original_item.get('published_date', original_item.get('date_time', ''))
            
            # 构建最终结构化数据
            structured_data = {
                'title': title,
                'content': content,
                'author': parsed.get('author', original_item.get('author', '')),
                'date_time': date_time,
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
    import platform
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