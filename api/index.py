from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import json
import os
import sys
import traceback
from pathlib import Path

# 添加项目根目录到Python路径
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
        # API首页
        response_data = {
            'status': 'success',
            'message': 'API服务正常',
            'endpoints': [
                '/api/hello - 测试端点',
                '/api/articles - 文章列表',
                '/api/stats - 统计数据'
            ],
            'path': self.path
        }
            
        # 发送响应
        self.wfile.write(json.dumps(response_data).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

def handler(request):
    """简单的测试函数"""
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps({
            "message": "Hello from index.py",
            "path": request.get('path', 'unknown')
        })
    } 