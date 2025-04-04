#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据清洗主模块 - 负责协调各个数据源的清洗流程
"""

import time
import logging
import traceback
from src.utils.log_handler import get_logger
from src.clean.cleandata import XDataProcessor, CrunchbaseDataProcessor
from src.clean.storage import get_unprocessed_data, update_processed_data, clear_temp_files

# 创建日志记录器
logger = get_logger("cleaner")

class CleaningService:
    """清洗服务类，整合不同来源的数据处理器"""
    
    def __init__(self):
        self.x_processor = XDataProcessor()
        self.crunchbase_processor = CrunchbaseDataProcessor()
    
    def clean_x_data(self, item):
        """清洗X数据"""
        return self.x_processor._process_x_item(item)
    
    def clean_crunchbase_data(self, item):
        """清洗Crunchbase数据"""
        return self.crunchbase_processor._process_crunchbase_item(item)
    
    def clean_default_data(self, item):
        """默认清洗方法"""
        logger.warning(f"使用默认处理器处理未知来源数据: {item.get('source', 'unknown')}")
        if 'x' in item.get('source', '').lower():
            return self.clean_x_data(item)
        elif 'crunchbase' in item.get('source', '').lower():
            return self.clean_crunchbase_data(item)
        else:
            logger.error(f"无法处理的数据来源: {item.get('source', 'unknown')}")
            return None

def start_cleaner():
    """开始数据清洗过程"""
    logger.info("开始数据清洗流程")
    
    try:
        # 初始化清洗服务
        cleaner = CleaningService()
        
        # 获取未处理数据（从临时文件）
        unprocessed_data = get_unprocessed_data()
        total = len(unprocessed_data)
        logger.info(f"找到 {total} 条未处理数据")
        
        if total == 0:
            logger.info("没有需要处理的数据，清洗流程结束")
            return True
        
        # 创建数据存储实例 - 批量处理模式
        from src.clean.storage import DataStorage
        storage = DataStorage()
        
        # 用于收集清洗成功的数据
        cleaned_data_list = []
        
        # 处理每条数据
        processed = 0
        failed = 0
        
        for item in unprocessed_data:
            try:
                # 提取原始数据信息
                source = item.get('source', 'unknown')
                source_url = item.get('source_url', '')
                
                # 获取原始文本，根据数据源不同，字段可能不同
                if 'x' in source.lower():
                    original_text = item.get('raw', {}).get('text', '') or item.get('text', '')
                    logger.info(f"X数据结构: {item.keys()}")
                    if 'raw' in item:
                        logger.info(f"X raw数据结构: {item['raw'].keys() if isinstance(item['raw'], dict) else type(item['raw'])}")
                else:  # crunchbase
                    original_text = item.get('content', '')
                
                logger.info(f"正在处理来自 {source} 的数据: {source_url}")
                
                # 根据来源选择不同的清洗方法
                if 'x' in source.lower():
                    try:
                        result = cleaner.clean_x_data(item)
                    except Exception as e:
                        logger.error(f"X数据处理异常: {str(e)}")
                        logger.error(traceback.format_exc())
                        result = None
                elif 'crunchbase' in source.lower():
                    try:
                        result = cleaner.clean_crunchbase_data(item)
                    except Exception as e:
                        logger.error(f"Crunchbase数据处理异常: {str(e)}")
                        logger.error(traceback.format_exc())
                        result = None
                else:
                    logger.warning(f"未知的数据源: {source}，使用默认清洗方法")
                    try:
                        result = cleaner.clean_default_data(item)
                    except Exception as e:
                        logger.error(f"默认处理异常: {str(e)}")
                        logger.error(traceback.format_exc())
                        result = None
                
                # 收集处理后的数据，等待批量保存
                if result:
                    # 确保清洗后的数据包含源URL
                    if 'source_url' not in result and source_url:
                        result['source_url'] = source_url
                    
                    # 确保清洗后的数据包含来源
                    if 'source' not in result:
                        result['source'] = source
                    
                    # 添加到批量保存列表
                    cleaned_data_list.append(result)
                    processed += 1
                    logger.info(f"成功处理数据: {source_url}")
                else:
                    failed += 1
                    logger.warning(f"处理数据失败: {source_url}")
                
                # 防止频繁调用API
                time.sleep(1)
                
            except Exception as e:
                failed += 1
                logger.error(f"处理数据出错: {source_url}, 错误: {str(e)}")
                logger.error(traceback.format_exc())
                continue
        
        # 批量保存所有处理好的数据
        saved_count = 0
        if cleaned_data_list:
            logger.info(f"开始批量保存 {len(cleaned_data_list)} 条处理后的数据...")
            saved_count = storage.save_articles(cleaned_data_list)
            logger.info(f"批量保存完成，成功保存 {saved_count} 条数据")
        
        # 输出处理结果
        logger.info(f"数据清洗完成: 总计 {total} 条, 成功处理 {processed} 条, 失败 {failed} 条, 成功保存 {saved_count} 条")
        
        # 清空临时文件
        if processed > 0:
            cleared = clear_temp_files()
            if cleared:
                logger.info("已清空临时文件")
            else:
                logger.warning("清空临时文件失败")
        
        return True
        
    except Exception as e:
        logger.error(f"数据清洗过程发生错误: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("直接启动清洗器")
    start_cleaner() 