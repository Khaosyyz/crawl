"""
测试MongoDB数据库连接
"""
import sys
import traceback
from db.mongodb import MongoDB

def test_database():
    print("=== 测试MongoDB数据库连接 ===")
    try:
        print("初始化MongoDB连接...")
        db = MongoDB()
        print("MongoDB连接成功!")

        print("\n1. 测试获取文章总数...")
        count = db.get_article_count()
        print(f"当前文章总数: {count}")

        print("\n2. 测试获取一篇文章...")
        articles = db.get_articles(limit=1)
        if articles and len(articles) > 0:
            article = articles[0]
            print(f"获取到文章: {article.get('title', '无标题')}")
            print(f"来源: {article.get('source', '未知')}")
            print(f"日期: {article.get('date_time', '未知')}")
        else:
            print("未获取到任何文章")

        print("\n3. 测试按来源过滤...")
        for source in ['x.com', 'crunchbase']:
            count = db.get_article_count({'source': source})
            print(f"来源为 {source} 的文章数: {count}")

        print("\n全部测试通过!")
        return True
    except Exception as e:
        print(f"\n错误: {e}")
        print("\n错误详情:")
        print(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = test_database()
    sys.exit(0 if success else 1) 