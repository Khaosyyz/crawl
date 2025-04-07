#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
每日热门资讯爬虫
获取前一天下午2点到今天上午10点的热门X资讯，生成每日报告
"""

import os
import sys
import json
import time
import logging
import datetime
import pytz
from typing import List, Dict, Any, Optional
import traceback
from openai import OpenAI

from src.utils.log_handler import get_logger
from src.db.mongodb import MongoDB
from src.utils.paths import DATA_DIR

# 创建日志记录器
logger = get_logger("hotnews_crawler")

# 常量定义
API_KEY = 'p9mtsT4ioDYm1'
API_BASE_URL = 'https://ai.liaobots.work/v1'
SEARCH_MODEL_NAME = 'grok-3-deepresearch'  # 用于搜索和生成报告
PROCESS_MODEL_NAME = 'deepseek-v3-0324'    # 用于处理结果

# 控制API请求频率的参数
API_REQUEST_TIMEOUT = 180  # 秒，增加timeout以适应搜索过程

# 输出文件路径
HOTNEWS_OUTPUT_PATH = os.path.join(DATA_DIR, "hotnews_data.json")

class HotNewsCrawler:
    """每日热门资讯爬虫类"""
    
    def __init__(self):
        """初始化爬虫"""
        # 初始化数据库连接
        try:
            self.db = MongoDB()
            logger.info("MongoDB连接初始化成功")
        except Exception as e:
            logger.error(f"MongoDB连接初始化失败: {e}")
            self.db = None
            raise
        
        # 初始化OpenAI客户端
        try:
            self.client = OpenAI(
                api_key=API_KEY,
                base_url=API_BASE_URL,
                timeout=API_REQUEST_TIMEOUT
            )
            logger.info(f"OpenAI客户端初始化成功，搜索模型: {SEARCH_MODEL_NAME}, 处理模型: {PROCESS_MODEL_NAME}")
        except Exception as e:
            logger.error(f"OpenAI客户端初始化失败: {e}")
            self.client = None
            raise
    
    def get_time_range(self) -> tuple:
        """获取时间范围：前一天下午2点到今天上午10点
        
        Returns:
            (start_time, end_time): 开始和结束时间
        """
        # 使用上海时区
        shanghai_tz = pytz.timezone('Asia/Shanghai')
        
        # 获取当前时间（上海时区）
        now = datetime.datetime.now(shanghai_tz)
        
        # 计算今天上午10点
        end_time = now.replace(hour=10, minute=0, second=0, microsecond=0)
        
        # 如果当前时间早于上午10点，使用昨天的10点
        if now < end_time:
            end_time = end_time - datetime.timedelta(days=1)
        
        # 计算前一天下午2点
        start_time = end_time - datetime.timedelta(days=1)
        start_time = start_time.replace(hour=14, minute=0, second=0, microsecond=0)
        
        # 输出时间范围
        logger.info(f"获取时间范围: {start_time.isoformat()} 到 {end_time.isoformat()}")
        
        return start_time, end_time
    
    def fetch_top_articles(self, limit: int = 3) -> List[Dict[str, Any]]:
        """获取指定时间范围内点赞量最高的X资讯
        
        Args:
            limit: 获取的文章数量，默认3条
            
        Returns:
            热门文章列表
        """
        if not self.db:
            logger.error("数据库连接不可用，无法获取文章")
            return []
        
        try:
            # 获取时间范围
            start_time, end_time = self.get_time_range()
            
            # 格式化为字符串，因为数据库中存储的是字符串格式
            start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
            end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
            
            # 构建查询条件：X资讯，在时间范围内
            query = {
                'source': 'x.com',
                'date_time': {'$gte': start_time_str, '$lte': end_time_str}
            }
            
            # 查询数据库，按点赞量排序，获取前limit条
            articles = self.db.get_articles(
                query=query,
                limit=limit,
                sort=[('likes', -1)]  # 按点赞量降序排序
            )
            
            logger.info(f"获取到 {len(articles)} 条热门X资讯")
            if len(articles) > 0:
                for i, article in enumerate(articles):
                    logger.info(f"热门资讯 {i+1}: {article.get('title', '无标题')} - 点赞数: {article.get('likes', 0)}")
            
            return articles
            
        except Exception as e:
            logger.error(f"获取热门文章失败: {e}")
            logger.error(traceback.format_exc())
            return []
    
    def generate_search_report(self, top_articles: List[Dict[str, Any]]) -> Optional[str]:
        """使用grok-3-deepresearch模型搜索相关资讯并生成报告
        
        Args:
            top_articles: 热门文章列表
            
        Returns:
            生成的报告内容，失败返回None
        """
        if not top_articles:
            logger.error("没有热门文章，无法生成报告")
            return None
        
        try:
            # 提取前三篇文章的信息，构建JSON字符串
            articles_json = json.dumps(top_articles[:3], ensure_ascii=False, indent=2)
            
            # 构建提示词
            prompt = f"尽可能多的搜索「{articles_json}」相关的资讯，并整理出来一篇报告。"
            
            logger.info("开始生成资讯报告...")
            
            # 调用API
            response = self.client.chat.completions.create(
                model=SEARCH_MODEL_NAME,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            # 提取结果
            if response.choices and len(response.choices) > 0:
                report = response.choices[0].message.content
                logger.info(f"成功生成资讯报告，长度: {len(report)}")
                return report
            else:
                logger.warning("API返回结果为空或格式不正确")
                return None
                
        except Exception as e:
            logger.error(f"生成资讯报告失败: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def process_final_report(self, raw_report: str) -> Optional[Dict[str, Any]]:
        """使用deepseek-v3-0324模型处理报告，提取标题和内容
        
        Args:
            raw_report: 原始报告内容
            
        Returns:
            处理后的报告数据（JSON格式），失败返回None
        """
        if not raw_report:
            logger.error("原始报告为空，无法处理")
            return None
        
        try:
            # 构建提示词
            prompt = """你是一个严格遵循指令的文本处理工具，请根据以下规则处理输入内容：\n\n1. 输入内容 = 用户提供的完整文本（包含思维过程和最终答案）\n\n2. 处理步骤：\n   - 步骤1：删除所有最终答案(Final Answer)之前的内容\n   - 步骤2：完全保留最终答案的原始内容（不作任何修改，包括格式/空格/标点/换行）\n   - 步骤3：自动提取内容中的日期（格式化为YYYY-MM-DD HH:MM）\n   - 步骤4：自拟不超过20字的标题\n\n3. 禁止行为：\n   - 禁止修改/重写/优化最终答案内容\n   - 禁止删除表格/链接/特殊符号\n   - 禁止猜测或补充日期\n   - 禁止添加任何分析性内容\n\n4. 必选输出格式（严格JSON）：\n```json\n{\n  \"title\": \"自拟标题\",\n  \"content\": \"完整未修改的最终答案\",\n  \"date\": \"提取的日期\",\n  \"source\": \"hotnews\"\n}\n```

以下是需要处理的文本:
"""
            prompt += raw_report
            
            logger.info("开始处理最终报告...")
            
            # 调用API
            response = self.client.chat.completions.create(
                model=PROCESS_MODEL_NAME,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            # 提取结果
            if response.choices and len(response.choices) > 0:
                result_text = response.choices[0].message.content
                logger.info(f"成功处理最终报告，结果长度: {len(result_text)}")
                
                # 尝试提取JSON部分
                try:
                    # 找到JSON开始和结束位置
                    json_start = result_text.find('{')
                    json_end = result_text.rfind('}') + 1
                    
                    if json_start >= 0 and json_end > json_start:
                        json_str = result_text[json_start:json_end]
                        processed_report = json.loads(json_str)
                        
                        # 确保包含所有必要字段
                        required_fields = ['title', 'content', 'date', 'source']
                        for field in required_fields:
                            if field not in processed_report:
                                logger.error(f"处理结果缺少必要字段: {field}")
                                return None
                        
                        # 确保source字段为"hotnews"
                        if processed_report['source'] != "hotnews":
                            processed_report['source'] = "hotnews"
                        
                        # 添加时间戳字段
                        processed_report['date_time'] = processed_report['date']
                        processed_report['processed_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        
                        return processed_report
                    else:
                        logger.error("无法从结果中提取JSON")
                        return None
                except Exception as json_e:
                    logger.error(f"解析JSON结果失败: {json_e}")
                    logger.error(f"原始结果: {result_text}")
                    return None
            else:
                logger.warning("API返回结果为空或格式不正确")
                return None
                
        except Exception as e:
            logger.error(f"处理最终报告失败: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def save_to_database(self, report: Dict[str, Any]) -> bool:
        """将处理后的报告保存到数据库
        
        Args:
            report: 处理后的报告数据
            
        Returns:
            是否成功保存
        """
        if not self.db:
            logger.error("数据库连接不可用，无法保存报告")
            return False
        
        if not report:
            logger.error("报告数据为空，无法保存")
            return False
        
        try:
            # 生成source_url字段，使用日期作为唯一标识
            date_str = report.get('date', '').replace(' ', '_').replace(':', '-')
            report['source_url'] = f"hotnews://{date_str}"
            
            # 保存到数据库
            result = self.db.insert_articles([report])
            if result > 0:
                logger.info(f"成功保存报告到数据库: {report.get('title', '无标题')}")
                return True
            else:
                logger.warning("保存报告到数据库失败")
                return False
                
        except Exception as e:
            logger.error(f"保存报告到数据库失败: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def run(self) -> bool:
        """运行爬虫流程
        
        Returns:
            是否成功完成
        """
        try:
            logger.info("开始运行每日热门资讯爬虫...")
            
            # 1. 获取热门文章
            top_articles = self.fetch_top_articles(limit=3)
            if not top_articles:
                logger.warning("没有找到热门文章，任务终止")
                return False
            
            # 2. 生成报告
            raw_report = self.generate_search_report(top_articles)
            if not raw_report:
                logger.error("生成报告失败，任务终止")
                return False
            
            # 3. 处理最终报告
            processed_report = self.process_final_report(raw_report)
            if not processed_report:
                logger.error("处理最终报告失败，任务终止")
                return False
            
            # 4. 保存到数据库
            saved = self.save_to_database(processed_report)
            if not saved:
                logger.error("保存报告到数据库失败，任务终止")
                return False
            
            # 5. 备份原始报告到本地文件（可选）
            try:
                with open(HOTNEWS_OUTPUT_PATH, 'w', encoding='utf-8') as f:
                    json.dump({
                        "raw_report": raw_report,
                        "processed_report": processed_report
                    }, f, ensure_ascii=False, indent=2)
                logger.info(f"已保存原始和处理后的报告到: {HOTNEWS_OUTPUT_PATH}")
            except Exception as e:
                logger.warning(f"保存报告到本地文件失败: {e}")
                # 不中断流程，继续执行
            
            logger.info("每日热门资讯爬虫运行完成")
            return True
            
        except Exception as e:
            logger.error(f"运行每日热门资讯爬虫失败: {e}")
            logger.error(traceback.format_exc())
            return False

def run_hotnews_crawler():
    """运行每日热门资讯爬虫的入口函数"""
    try:
        crawler = HotNewsCrawler()
        result = crawler.run()
        return result
    except Exception as e:
        logger.error(f"运行每日热门资讯爬虫出错: {e}")
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    logger.info("直接启动每日热门资讯爬虫")
    run_hotnews_crawler() 