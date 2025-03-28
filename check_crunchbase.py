#!/usr/bin/env python3
"""
检查数据库中的Crunchbase文章
"""

import os
import sys
import logging
import json
import argparse
from pathlib import Path
import pprint
from datetime import datetime, timedelta

# 设置日志记录
logging.basicConfig(level=logging.INFO,
                  format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("check_crunchbase")

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

try:
    from db.mongodb import MongoDB
except ImportError as e:
    logger.error(f"导入MongoDB模块失败: {e}")
    sys.exit(1)

def check_crunchbase_articles(check_schema=False, count_only=False, date_start=None, date_end=None):
    """检查数据库中的Crunchbase文章"""
    try:
        # 连接MongoDB
        db = MongoDB()
        logger.info("MongoDB连接成功")
        
        # 获取文章总数
        collection = db.collection
        total_count = collection.count_documents({})
        crunchbase_count = collection.count_documents({"source": "crunchbase.com"})
        
        logger.info(f"数据库中共有 {total_count} 篇文章")
        logger.info(f"其中Crunchbase来源的文章有 {crunchbase_count} 篇")
        
        if count_only:
            return True
            
        # 构建查询条件
        query = {"source": "crunchbase.com"}
        
        # 添加日期范围查询
        if date_start or date_end:
            date_query = {}
            if date_start:
                date_query["$gte"] = date_start
            if date_end:
                date_query["$lte"] = date_end
            
            if date_query:
                query["date_time"] = date_query
                logger.info(f"使用日期范围查询: {date_start} 到 {date_end}")
                # 查询匹配的文章数
                matching_count = collection.count_documents(query)
                logger.info(f"在指定日期范围内找到 {matching_count} 篇Crunchbase文章")
        
        if crunchbase_count > 0:
            # 获取一篇Crunchbase文章作为样本
            article = collection.find_one(query)
            
            if article:  # 确保找到了文章
                if check_schema:
                    logger.info("Crunchbase文章样本:")
                    print("\n===== Crunchbase文章字段结构 =====")
                    pprint.pprint(article)
                    
                    # 打印字段列表
                    if article:
                        print("\n===== 字段列表 =====")
                        for field in sorted(article.keys()):
                            field_type = type(article[field]).__name__
                            print(f"{field}: {field_type}")
                
                # 特别检查关键字段
                print("\n===== 关键字段 =====")
                print(f"标题: {article.get('title', 'Missing')}")
                print(f"内容: {article.get('content', 'Missing')[:100]}...")
                print(f"来源: {article.get('source', 'Missing')}")
                print(f"URL: {article.get('source_url', 'Missing')}")
                print(f"日期: {article.get('date_time', 'Missing')}")
                
                # 检查可能特有的字段
                print("\n===== 特有字段 =====")
                print(f"公司: {article.get('company', 'Missing')}")
                print(f"融资轮次: {article.get('funding_round', 'Missing')}")
                print(f"融资金额: {article.get('funding_amount', 'Missing')}")
                print(f"投资方: {article.get('investors', 'Missing')}")
            else:
                logger.warning(f"使用查询条件 {query} 未找到任何文章")
                print("\n===== 查询结果 =====")
                print("未找到符合条件的文章，请尝试其他查询参数")
            
            # 显示最近的10篇文章
            print("\n===== 最近的Crunchbase文章 =====")
            recent_articles = list(collection.find(
                {"source": "crunchbase.com"}, 
                {"title": 1, "date_time": 1, "_id": 0}
            ).sort("date_time", -1).limit(10))
            
            for idx, art in enumerate(recent_articles, 1):
                print(f"{idx}. {art.get('title', 'No Title')} ({art.get('date_time', 'No Date')})")
        else:
            logger.info("数据库中没有Crunchbase来源的文章")
        
        # 关闭连接
        db.client.close()
        logger.info("MongoDB连接已关闭")
        
        return True
    except Exception as e:
        logger.error(f"检查Crunchbase文章出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    parser = argparse.ArgumentParser(description='检查数据库中的Crunchbase文章')
    parser.add_argument('--check-schema', action='store_true', help='检查并显示数据库字段结构')
    parser.add_argument('--count', action='store_true', help='只计算文章数量')
    parser.add_argument('--date-start', type=str, help='起始日期 (YYYY-MM-DD)')
    parser.add_argument('--date-end', type=str, help='结束日期 (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    logger.info("开始检查Crunchbase文章...")
    success = check_crunchbase_articles(
        check_schema=args.check_schema,
        count_only=args.count,
        date_start=args.date_start,
        date_end=args.date_end
    )
    
    if success:
        logger.info("Crunchbase文章检查完成")
    else:
        logger.error("Crunchbase文章检查失败")
        sys.exit(1)

if __name__ == "__main__":
    main()