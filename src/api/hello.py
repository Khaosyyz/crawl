#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Hello World API路由
"""

from fastapi import APIRouter, Request
from src.utils.log_handler import get_logger

# 创建路由器
router = APIRouter(prefix="/hello", tags=["hello"])

# 创建日志记录器
logger = get_logger("api.hello")

@router.get("/")
async def hello(request: Request):
    """
    Hello World API
    """
    logger.info(f"Hello API访问: {request.client.host}")
    return {
        "status": "success",
        "message": "Hello World from AI News Crawler",
        "path": request.url.path
    } 