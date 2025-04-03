#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
爬虫运行脚本 - 用于启动X或Crunchbase爬虫
"""

import sys
import argparse
import logging
from typing import Optional

from src.utils.log_handler import get_logger
from src.crawlers.X.x import XCrawler
from src.crawlers.Crunchbase.crunchbase import CrunchbaseCrawler

# 创建日志记录器
logger = get_logger("crawler_runner")

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="爬虫运行脚本")
    parser.add_argument("--name", type=str, choices=["x", "crunchbase", "all"], 
                        default="all", help="要运行的爬虫名称")
    return parser.parse_args()

def run_crawler(name: Optional[str] = None):
    """运行指定的爬虫"""
    logger.info(f"准备运行爬虫: {name if name else 'all'}")
    
    if name is None or name == "all" or name == "x":
        logger.info("正在启动X爬虫...")
        try:
            x_crawler = XCrawler()
            x_crawler.run()
            logger.info("X爬虫运行完成")
        except Exception as e:
            logger.error(f"X爬虫运行失败: {e}")
    
    if name is None or name == "all" or name == "crunchbase":
        logger.info("正在启动Crunchbase爬虫...")
        try:
            crunchbase_crawler = CrunchbaseCrawler()
            crunchbase_crawler.run()
            logger.info("Crunchbase爬虫运行完成")
        except Exception as e:
            logger.error(f"Crunchbase爬虫运行失败: {e}")
    
    logger.info("爬虫运行结束")

if __name__ == "__main__":
    args = parse_args()
    run_crawler(args.name) 