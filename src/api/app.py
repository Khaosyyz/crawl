#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
API服务模块，提供网页和API接口
"""

import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from src.utils.log_handler import get_logger
from src.utils.paths import ROOT_DIR

# 导入API路由
from src.api.api import app as flask_app
from src.api.hello import router as hello_router
from src.api.index import router as index_router
from src.api.stats import router as stats_router

# 创建FastAPI应用
app = FastAPI(title="AI新闻爬虫系统", 
             description="提供AI相关新闻数据的API服务",
             version="1.0.0")

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置静态文件
static_dir = os.path.join(ROOT_DIR, "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 配置模板
templates_dir = os.path.join(static_dir, "templates")
templates = Jinja2Templates(directory=templates_dir)

# 日志记录器
logger = get_logger("api")

# 添加路由
app.include_router(hello_router)
app.include_router(index_router)
app.include_router(stats_router)

# 添加Flask API路由（兼容旧版本）
from fastapi.middleware.wsgi import WSGIMiddleware
app.mount("/api", WSGIMiddleware(flask_app))

@app.get("/")
async def root(request: Request):
    """首页路由"""
    logger.info("访问首页")
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        logger.error(f"渲染首页失败: {str(e)}")
        raise HTTPException(status_code=500, detail="内部服务器错误")

@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 