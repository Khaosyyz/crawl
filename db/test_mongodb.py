from mongodb import MongoDB

def test_connection():
    """测试MongoDB连接"""
    try:
        # 创建MongoDB实例
        db = MongoDB()
        print("MongoDB连接测试开始...")
        
        # 测试插入数据
        test_doc = {
            "title": "测试文章",
            "content": "这是一篇测试文章",
            "author": "测试作者",
            "source": "test",
            "source_url": "http://test.com/1",
            "date_time": "2024-03-26 12:00:00"
        }
        
        # 插入测试文档
        success = db.insert_one(test_doc)
        if success:
            print("测试文档插入成功")
        
        # 查询测试
        results = db.find_by_source("test")
        print(f"查询到 {len(results)} 条测试数据")
        
        # 搜索测试
        search_results = db.search_text("测试")
        print(f"搜索到 {len(search_results)} 条包含'测试'的数据")
        
        print("MongoDB连接测试完成")
        
    except Exception as e:
        print(f"测试失败: {str(e)}")
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    test_connection() 