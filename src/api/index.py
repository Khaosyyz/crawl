#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
API索引路由
"""

from fastapi import APIRouter, Request
from src.utils.log_handler import get_logger

# 创建路由器
router = APIRouter(prefix="/api", tags=["api"])

# 创建日志记录器
logger = get_logger("api.index")

@router.get("/")
async def api_index(request: Request):
    """
    API首页，列出所有可用端点
    """
    logger.info(f"API首页访问: {request.client.host}")
    
    return {
        'status': 'success',
        'message': 'API服务正常',
        'endpoints': [
            '/api/hello - 测试端点',
            '/api/articles - 文章列表',
            '/api/stats - 统计数据'
        ],
        'path': request.url.path
    } 