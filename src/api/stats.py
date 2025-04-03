#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统计信息API路由
"""

import json
import traceback
from fastapi import APIRouter, Request, HTTPException
from src.utils.log_handler import get_logger
from src.db.mongodb import MongoDB

# 创建路由器
router = APIRouter(prefix="/stats", tags=["statistics"])

# 创建日志记录器
logger = get_logger("api.stats")

@router.get("/")
async def get_stats(request: Request):
    """
    获取系统统计信息
    """
    logger.info(f"统计信息API访问: {request.client.host}")
    
    try:
        # 初始化数据库连接
        db = MongoDB()
        
        # 获取总文章数
        total_articles = db.get_article_count()
        
        # 获取各数据源的文章数
        sources = {}
        for source in ['x', 'crunchbase']:
            count = db.get_article_count({'source': source})
            sources[source] = count
            
        # 获取最新更新时间
        latest_article = db.get_articles(limit=1, sort=[('date_time', -1)])
        last_update = latest_article[0]['date_time'] if latest_article else None
        
        return {
            'status': 'success',
            'data': {
                'total_articles': total_articles,
                'sources': sources,
                'last_update': last_update
            }
        }
        
    except Exception as e:
        logger.error(f"获取统计信息失败: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500, 
            detail={
                'status': 'error',
                'message': '获取统计信息失败，请稍后再试',
                'error': str(e)
            }
        ) 