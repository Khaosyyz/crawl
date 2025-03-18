# 使crawlers成为一个Python包
# 导入所有爬虫模块
try:
    from crawlers.X.x import XCrawler
except ImportError:
    pass

try:
    from crawlers.Crunchbase.crunchbase import CrunchbaseCrawler
except ImportError:
    pass

__all__ = ['XCrawler', 'CrunchbaseCrawler']