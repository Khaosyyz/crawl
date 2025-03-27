import sys
import json
from pathlib import Path
import traceback

# 添加项目根目录到 Python 路径
project_root = str(Path(__file__).parent)
sys.path.append(project_root)

# 导入 MongoDB 连接
try:
    from db.mongodb import MongoDB
    from api.articles import Handler
    
    class MockRequest:
        def __init__(self, path):
            self.path = path
    
    class MockHandler(Handler):
        def __init__(self, path):
            self.path = path
            self.wfile = None
            self.headers = {}
        
        def send_response(self, code):
            self.response_code = code
            
        def send_header(self, key, value):
            self.headers[key] = value
            
        def end_headers(self):
            pass
            
        def get_response(self):
            """模拟处理请求并返回响应"""
            class WFile:
                def __init__(self):
                    self.response = None
                    
                def write(self, data):
                    self.response = data
                    
            self.wfile = WFile()
            self.do_GET()
            return json.loads(self.wfile.response.decode()) if self.wfile.response else None
    
    def test_x_com_api():
        """测试x.com API的分页功能"""
        print("===== 测试 x.com API =====")
        
        # 测试第一页
        handler = MockHandler("/api/articles?source=x.com&date_page=1&page=1")
        response = handler.get_response()
        
        if response and response.get('status') == 'success':
            print(f"总文章数: {response.get('total')}")
            print(f"当前日期页: {response.get('date_page')}")
            print(f"总日期页数: {response.get('total_date_pages')}")
            print(f"当前页内日期: {response.get('dates_in_page')}")
            
            # 打印每个日期的文章分页信息
            for date, date_info in response.get('date_articles', {}).items():
                print(f"\n日期: {date}")
                print(f"  文章总数: {date_info.get('total')}")
                print(f"  总页数: {date_info.get('total_pages')}")
                print(f"  当前页: {date_info.get('current_page')}")
                print(f"  是否有更多: {date_info.get('has_more')}")
                print(f"  文章数量: {len(date_info.get('articles', []))}")
                
                # 打印文章预览
                print("  文章预览:")
                for i, article in enumerate(date_info.get('articles', [])[:3]):
                    print(f"    {i+1}. {article.get('title')} ({article.get('date_time')})")
                    if i >= 2:
                        remaining = len(date_info.get('articles', [])) - 3
                        if remaining > 0:
                            print(f"    ... 还有 {remaining} 篇文章 ...")
                        break
        else:
            print("API请求失败:", response)
        
        # 测试第二页
        print("\n----- 测试第二页 -----")
        handler = MockHandler("/api/articles?source=x.com&date_page=1&page=2")
        response = handler.get_response()
        
        if response and response.get('status') == 'success':
            print(f"当前页: {response.get('page')}")
            for date, date_info in response.get('date_articles', {}).items():
                print(f"\n日期: {date}")
                print(f"  当前页: {date_info.get('current_page')}")
                print(f"  文章数量: {len(date_info.get('articles', []))}")
        else:
            print("API请求失败:", response)
            
    def test_crunchbase_api():
        """测试crunchbase API的分页功能"""
        print("\n===== 测试 crunchbase API =====")
        
        # 测试第一页
        handler = MockHandler("/api/articles?source=crunchbase&page=1")
        response = handler.get_response()
        
        if response and response.get('status') == 'success':
            print(f"总文章数: {response.get('total')}")
            print(f"当前页: {response.get('page')}")
            print(f"总页数: {response.get('total_pages')}")
            print(f"每页显示: {response.get('per_page')}")
            print(f"分页模式: {response.get('pagination_mode')}")
            
            # 打印文章预览
            articles = response.get('data', [])
            print(f"文章数量: {len(articles)}")
            
            if articles:
                print("文章预览:")
                for i, article in enumerate(articles[:3]):
                    print(f"  {i+1}. {article.get('title')} ({article.get('date_time')})")
                    if i >= 2:
                        remaining = len(articles) - 3
                        if remaining > 0:
                            print(f"  ... 还有 {remaining} 篇文章 ...")
                        break
        else:
            print("API请求失败:", response)

    # 运行测试
    print("开始测试API分页功能...")
    test_x_com_api()
    test_crunchbase_api()
    print("测试完成!")

except Exception as e:
    print("测试脚本执行失败:")
    print(str(e))
    print(traceback.format_exc())

if __name__ == "__main__":
    pass  # 测试已在导入时运行 