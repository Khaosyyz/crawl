"""
测试本地API服务器
"""
import http.server
import socketserver
import threading
import time
import requests
import json
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = str(Path(__file__).parent)
sys.path.append(project_root)

# API端点列表
API_ENDPOINTS = [
    "/api/hello",
    "/api/articles",
    "/api/stats"
]

# 本地服务器端口
PORT = 8000

class TestAPIHandler(http.server.BaseHTTPRequestHandler):
    """处理测试请求的HTTP处理程序"""
    
    def log_message(self, format, *args):
        """覆盖默认的日志方法，使输出更简洁"""
        return
    
    def do_GET(self):
        """处理GET请求"""
        # 根据请求路径分发到相应的API处理程序
        if self.path.startswith("/api/hello"):
            from api.hello import Handler
            Handler.do_GET(self)
        elif self.path.startswith("/api/articles"):
            from api.articles import Handler
            Handler.do_GET(self)
        elif self.path.startswith("/api/stats"):
            from api.stats import Handler
            Handler.do_GET(self)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

def start_server():
    """启动本地HTTP服务器"""
    handler = TestAPIHandler
    httpd = socketserver.TCPServer(("", PORT), handler)
    print(f"启动本地测试服务器在端口 {PORT}...")
    httpd_thread = threading.Thread(target=httpd.serve_forever)
    httpd_thread.daemon = True
    httpd_thread.start()
    return httpd

def test_api_endpoints():
    """测试API端点"""
    print("=== 测试API端点 ===")
    
    all_tests_passed = True
    
    for endpoint in API_ENDPOINTS:
        print(f"\n测试API端点: {endpoint}")
        try:
            response = requests.get(f"http://localhost:{PORT}{endpoint}")
            
            print(f"状态码: {response.status_code}")
            if response.status_code == 200:
                # 尝试解析JSON
                try:
                    data = response.json()
                    print(f"返回数据: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}...")
                    print("测试通过: 可以成功解析JSON响应")
                except json.JSONDecodeError:
                    print("错误: 返回的不是有效的JSON")
                    all_tests_passed = False
            else:
                print(f"错误: 返回非200状态码 ({response.status_code})")
                print(f"响应内容: {response.text[:200]}...")
                all_tests_passed = False
                
        except requests.RequestException as e:
            print(f"请求错误: {e}")
            all_tests_passed = False
            
        print(f"端点 {endpoint} 测试{'成功' if response.status_code == 200 else '失败'}")
    
    return all_tests_passed

if __name__ == "__main__":
    try:
        # 启动测试服务器
        httpd = start_server()
        
        # 等待服务器启动
        time.sleep(1)
        
        # 测试API端点
        success = test_api_endpoints()
        
        # 关闭服务器
        httpd.shutdown()
        
        if success:
            print("\n全部API测试通过!")
            sys.exit(0)
        else:
            print("\n部分API测试失败!")
            sys.exit(1)
            
    except Exception as e:
        print(f"测试过程出错: {e}")
        sys.exit(1) 