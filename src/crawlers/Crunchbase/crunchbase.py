#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

# 将项目根目录添加到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from datetime import datetime
import pytz
import time
import json
import os
import random
import re
import logging
import threading
from src.utils.paths import CRU_TEMP_DATA_PATH, DATA_DIR, CRU_URLS_PATH, CRU_URLS_DEBUG_PATH, LOGS_DIR

# 常量定义
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# 配置日志 - 只使用标准输出，避免与调度器指定的日志冲突
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # 只使用标准输出，日志会被重定向到调度器指定的文件
    ]
)
logger = logging.getLogger("crunchbase_crawler")

class CrunchbaseCrawler:
    def __init__(self):
        self.driver = self.setup_driver()
        # 使用paths.py中定义的常量路径
        self.url_table_path = CRU_URLS_PATH
        # 确保目录存在
        if not os.path.exists(os.path.dirname(self.url_table_path)):
            os.makedirs(os.path.dirname(self.url_table_path))
        
    def setup_driver(self):
        """初始化并配置WebDriver"""
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")
        
        # 启用无头模式和禁止GPU
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        
        return webdriver.Chrome(options=options)
    
    def crawl_posts(self):
        """爬取Crunchbase数据，直接使用HTML解析方法"""
        try:
            logger.info("开始爬取Crunchbase文章...")
            
            # 添加超时控制
            start_time = time.time()
            timeout_minutes = 10  # 设置10分钟超时
            
            posts = self.crawl_posts_via_html()
            logger.info(f"总共爬取到 {len(posts)} 篇文章")
            return posts
        except Exception as e:
            logger.error(f"爬取过程出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def crawl_posts_via_html(self):
        """通过HTML解析爬取文章"""
        logger.info("使用HTML解析方法爬取文章...")
        urls = []
        
        try:
            # 打开AI新闻页面
            logger.info("正在访问 https://news.crunchbase.com/sections/ai/ ...")
            self.driver.get("https://news.crunchbase.com/sections/ai/")
            
            # 等待页面加载，增加等待时间
            try:
                logger.info("等待页面加载完成...")
                WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".category-short-post"))
                )
                # 额外等待，确保动态内容加载完成
                time.sleep(5)
            except TimeoutException:
                logger.warning("等待文章元素超时，保存页面源码以供分析")
                self.save_page_source("timeout_page.html")
                # 尝试继续执行，即使没有找到预期元素

            # 记录页面标题信息，用于调试
            logger.info(f"页面标题: {self.driver.title}")
            
            # 基于用户提供的HTML结构，使用更精确的选择器
            # 1. 尝试获取主文章（如果有的话）
            try:
                main_article = self.driver.find_element(By.CSS_SELECTOR, ".category-post__title")
                main_article_link = main_article.find_element(By.TAG_NAME, "a")
                main_url = main_article_link.get_attribute('href')
                if main_url:
                    logger.info(f"找到主文章URL: {main_url}")
                    urls.append(main_url)
            except (NoSuchElementException, Exception) as e:
                logger.warning(f"获取主文章链接失败: {e}")
                
            # 2. 获取文章列表
            article_elements = self.driver.find_elements(By.CSS_SELECTOR, ".category-short-post")
            logger.info(f"找到 {len(article_elements)} 个文章元素")
            
            for article in article_elements:
                try:
                    # 直接在each文章元素内查找链接
                    link_elem = article.find_element(By.TAG_NAME, "a")
                    url = link_elem.get_attribute('href')
                    if url:
                        logger.info(f"找到文章URL: {url}")
                        urls.append(url)
                except (NoSuchElementException, Exception) as e:
                    logger.warning(f"获取文章链接失败: {e}")
            
            # 如果以上方法都未找到链接，尝试更通用的选择器
            if not urls:
                logger.warning("未找到文章链接，尝试备用选择器")
                
                # 尝试直接查找所有带href的a标签
                all_links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='news.crunchbase.com']")
                for link in all_links:
                    url = link.get_attribute('href')
                    if url and '/news.crunchbase.com/' in url:
                        logger.info(f"通过备用方法找到URL: {url}")
                        urls.append(url)
            
            # 过滤并去重URL
            urls = list(set(urls))
            logger.info(f"收集到 {len(urls)} 个有效文章URL")
            
            # 保存URL列表，便于调试
            debug_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'cru_urls_debug.json'
            )
            with open(debug_path, 'w', encoding='utf-8') as f:
                json.dump(urls, f, ensure_ascii=False, indent=2)
            
            # 如果没有找到任何URL，返回空列表
            if not urls:
                logger.warning("未找到任何文章URL，爬取结束")
                return []
                
            # 检查URL表，确定需要爬取的新URL
            new_urls = self.check_url_table(urls)
            
            if not new_urls:
                logger.info("没有新文章，终止爬取")
                return []
            
            # 爬取新文章的内容
            articles = []
            for url in new_urls:
                article = self.scrape_article(url)
                if article:
                    articles.append(article)
                    # 更新URL表，标记为已爬取
                    self.update_url_table(url, True)
                    # 添加随机延迟避免请求过快
                    time.sleep(random.uniform(2, 5))
            
            return articles
        except Exception as e:
            logger.error(f"HTML爬取过程出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.save_page_source("error_page.html")
            return []
    
    def save_page_source(self, filename):
        """保存页面源码，用于调试"""
        try:
            # 修改保存路径到data/crunchbase/debug目录
            debug_dir = os.path.join(DATA_DIR, 'crunchbase', 'debug')
            if not os.path.exists(debug_dir):
                os.makedirs(debug_dir)
                
            filepath = os.path.join(debug_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
                
            logger.info(f"页面源码已保存到 {filepath}")
        except Exception as e:
            logger.error(f"保存页面源码出错: {e}")
    
    def check_url_table(self, current_urls):
        """检查URL表，确定哪些URL需要爬取"""
        # 读取现有URL表
        if os.path.exists(self.url_table_path):
            try:
                with open(self.url_table_path, 'r', encoding='utf-8') as f:
                    url_table = json.load(f)
                    # 确保 url_table 是字典格式
                    if isinstance(url_table, list):
                        logger.warning("URL表是列表格式，转换为字典格式")
                        url_table = {"last_check": "", "urls": {}}
                    elif not isinstance(url_table, dict):
                        logger.warning("URL表格式不是字典，创建新表")
                        url_table = {"last_check": "", "urls": {}}
                    # 确保 url_table 包含所需的键
                    if "last_check" not in url_table:
                        url_table["last_check"] = ""
                    if "urls" not in url_table:
                        url_table["urls"] = {}
            except json.JSONDecodeError:
                logger.warning("URL表格式错误，将创建新表")
                url_table = {"last_check": "", "urls": {}}
        else:
            url_table = {"last_check": "", "urls": {}}
        
        # 更新最后检查时间
        url_table["last_check"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 检查新URL
        existing_urls = set(url_table["urls"].keys())
        new_urls = [url for url in current_urls if url not in existing_urls]
        
        # 如果没有新URL，检查是否是首次运行
        if not new_urls and not existing_urls:
            logger.info("首次运行，爬取所有URL")
            new_urls = current_urls
        
        # 将新URL添加到表中，标记为未爬取
        for url in new_urls:
            url_table["urls"][url] = {
                "scraped": False,
                "first_seen": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        # 保存更新后的URL表
        with open(self.url_table_path, 'w', encoding='utf-8') as f:
            json.dump(url_table, f, ensure_ascii=False, indent=2)
        
        logger.info(f"发现 {len(new_urls)} 个新URL需要爬取")
        return new_urls
    
    def update_url_table(self, url, scraped=True):
        """更新URL的爬取状态"""
        with open(self.url_table_path, 'r', encoding='utf-8') as f:
            url_table = json.load(f)
        
        if url in url_table["urls"]:
            url_table["urls"][url]["scraped"] = scraped
            url_table["urls"][url]["last_scraped"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        with open(self.url_table_path, 'w', encoding='utf-8') as f:
            json.dump(url_table, f, ensure_ascii=False, indent=2)
    
    def scrape_article(self, url):
        """爬取单篇文章的详细内容"""
        try:
            logger.info(f"爬取文章: {url}")
            self.driver.get(url)
            
            # 等待文章内容加载，增加更多等待时间
            try:
                WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.TAG_NAME, "article"))
                )
                # 额外等待确保所有内容（包括动态内容）完全加载
                time.sleep(5)
            except TimeoutException:
                logger.warning(f"等待文章内容加载超时: {url}")
                self.save_page_source(f"article_timeout_{url.split('/')[-1]}.html")
                # 继续执行，尝试其他方法获取内容
            
            # 尝试不同的选择器提取标题
            title = ""
            for selector in ["article h1", "h1.post-title", ".article-title", "header h1", "h1"]:
                try:
                    title_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    title = title_elem.text.strip()
                    if title:
                        logger.info(f"从选择器 '{selector}' 找到标题: {title}")
                        break
                except NoSuchElementException:
                    continue
            
            if not title:
                title = "Untitled Crunchbase Article"
                logger.warning(f"未能找到文章标题: {url}")
            
            # 提取发布日期，确保只包含YYYY-MM-DD格式
            published_date = datetime.now().strftime('%Y-%m-%d')
            for selector in ["time", ".post-date", ".article-date", "article .date", "article time"]:
                try:
                    date_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    date_text = date_element.get_attribute("datetime") or date_element.text
                    if date_text:
                        # 尝试提取YYYY-MM-DD格式的日期
                        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_text)
                        if date_match:
                            published_date = date_match.group(1)
                            logger.info(f"从选择器 '{selector}' 找到日期: {published_date}")
                        break
                except NoSuchElementException:
                    continue
            
            # 提取文章内容 - 改进内容提取，尝试多种选择器并组合结果
            content_parts = []
            
            # 优先使用文章正文内容容器
            selectors = [
                "article .post-content", 
                ".article-content", 
                "article .content",
                ".post-body",
                "article",
                "main"
            ]
            
            content_container = None
            for selector in selectors:
                try:
                    content_container = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if content_container:
                        logger.info(f"找到内容容器: {selector}")
                        break
                except NoSuchElementException:
                    continue
            
            if content_container:
                # 从内容容器中提取所有段落
                try:
                    paragraphs = content_container.find_elements(By.TAG_NAME, "p")
                    for p in paragraphs:
                        text = p.text.strip()
                        if text:
                            content_parts.append(text)
                    
                    logger.info(f"从内容容器中提取了 {len(content_parts)} 个段落")
                except Exception as e:
                    logger.warning(f"从内容容器提取段落失败: {e}")
            
            # 如果内容部分为空，尝试使用最通用的段落选择器
            if not content_parts:
                logger.warning(f"未通过内容容器找到段落，尝试直接查找所有p标签")
                try:
                    paragraphs = self.driver.find_elements(By.TAG_NAME, "p")
                    for p in paragraphs:
                        # 过滤掉很短的段落，比如广告或者页脚文本
                        text = p.text.strip()
                        if text and len(text) > 20:  # 只保留长度大于20的段落
                            content_parts.append(text)
                    
                    logger.info(f"从全局段落中提取了 {len(content_parts)} 个段落")
                except Exception as e:
                    logger.warning(f"提取全局段落失败: {e}")
            
            # 如果仍然没有内容，尝试获取整个页面文本，但排除导航和页脚等区域
            if not content_parts:
                logger.warning(f"未能找到文章段落，尝试获取页面主体文本")
                try:
                    # 尝试获取main或article标签的文本，排除header和footer
                    for elem_tag in ["main", "article", "body"]:
                        try:
                            main_elem = self.driver.find_element(By.TAG_NAME, elem_tag)
                            text = main_elem.text
                            if text and len(text) > 100:  # 确保文本长度合理
                                # 使用启发式方法分割段落
                                lines = text.split('\n')
                                for line in lines:
                                    line = line.strip()
                                    if line and len(line) > 30:  # 只保留有意义的长行
                                        content_parts.append(line)
                                break
                        except:
                            continue
                except Exception as e:
                    logger.error(f"获取页面主体文本失败: {e}")
            
            # 检查内容是否为空
            content = "\n".join(content_parts) if content_parts else ""
            
            # 如果获取的内容太短，尝试一种备用方法
            if len(content) < 200:
                logger.warning(f"获取的内容太短，尝试JavaScript方法提取文本")
                try:
                    # 使用JavaScript获取所有可见文本内容
                    js_content = self.driver.execute_script("""
                        function getVisibleText() {
                            // 排除脚本、样式等标签
                            const skipTags = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'META', 'LINK']);
                            // 结果数组
                            const textBlocks = [];
                            
                            // 递归遍历DOM树
                            function extract(node) {
                                if (node.nodeType === Node.TEXT_NODE) {
                                    const text = node.textContent.trim();
                                    if (text && text.length > 20) {
                                        textBlocks.push(text);
                                    }
                                } else if (node.nodeType === Node.ELEMENT_NODE && !skipTags.has(node.tagName)) {
                                    // 检查元素是否可见
                                    const style = window.getComputedStyle(node);
                                    if (style.display !== 'none' && style.visibility !== 'hidden') {
                                        // 递归处理所有子节点
                                        for (const child of node.childNodes) {
                                            extract(child);
                                        }
                                    }
                                }
                            }
                            
                            // 获取主要内容区域
                            const mainContent = document.querySelector('article') || 
                                               document.querySelector('main') || 
                                               document.body;
                            
                            extract(mainContent);
                            return textBlocks.join("\\n");
                        }
                        return getVisibleText();
                    """)
                    
                    if js_content and len(js_content) > 200:
                        content = js_content
                        logger.info("成功使用JavaScript方法提取到内容")
                except Exception as e:
                    logger.error(f"JavaScript提取内容失败: {e}")
            
            if not content:
                logger.warning(f"所有方法均未能找到文章内容: {url}")
                content = f"无法提取文章内容，请访问原始链接查看: {url}"
            
            # 提取作者信息
            author = "Crunchbase Staff"
            for selector in ["article .byline a", ".author", ".article-author", ".post-author"]:
                try:
                    author_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if author_elem.text:
                        author = author_elem.text.strip()
                        logger.info(f"找到作者: {author}")
                        break
                except NoSuchElementException:
                    continue
            
            # 提取投资相关信息
            investment_amount = self.extract_investment_amount(content)
            investors = self.extract_investors(content)
            
            # 提取公司/产品信息
            company_product = self.extract_company_product(content)
            
            # 记录内容长度信息
            content_length = len(content)
            logger.info(f"提取到的内容长度: {content_length} 字符")
            
            # 记录几句内容示例
            if content_length > 0:
                content_sample = content[:200] + "..." if content_length > 200 else content
                logger.info(f"内容示例: {content_sample}")
            
            article = {
                "title": title,
                "content": content,
                "url": url,
                "source": "crunchbase.com",
                "published_date": published_date,
                "author": author,
                "investment_amount": investment_amount,
                "investors": investors,
                "company_product": company_product,
                "content_length": content_length  # 添加内容长度字段，便于调试
            }
            
            logger.info(f"成功爬取文章: {title}")
            return article
        except Exception as e:
            logger.error(f"爬取文章 {url} 出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.save_page_source(f"error_article_{url.split('/')[-1]}.html")
            return None
    
    def extract_investment_amount(self, content):
        """从文章内容中提取投资金额"""
        if not content:
            return "N/A"
            
        # 查找常见的投资金额模式
        patterns = [
            r'\$\s*(\d+(?:\.\d+)?)\s*(million|billion|m|b)', 
            r'raised\s*\$\s*(\d+(?:\.\d+)?)\s*(million|billion|m|b)',
            r'funding.*?\$\s*(\d+(?:\.\d+)?)\s*(million|billion|m|b)',
            r'investment.*?\$\s*(\d+(?:\.\d+)?)\s*(million|billion|m|b)',
            r'valuation.*?\$\s*(\d+(?:\.\d+)?)\s*(million|billion|m|b)'
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                value = float(match.group(1))
                unit = match.group(2).lower()
                if 'b' in unit:
                    return f"${value}B"
                else:
                    return f"${value}M"
        
        return "N/A"
    
    def extract_investors(self, content):
        """从文章内容中提取投资方"""
        if not content:
            return []
            
        # 常见的投资方模式
        patterns = [
            r'led by ([A-Z][A-Za-z0-9\s]+)',
            r'from ([A-Z][A-Za-z0-9\s]+)',
            r'investor[s]? ([A-Z][A-Za-z0-9\s,]+) participated',
            r'backed by ([A-Z][A-Za-z0-9\s,]+)',
            r'([A-Z][A-Za-z0-9\s]+) led the round',
            r'([A-Z][A-Za-z0-9\s]+) invested in'
        ]
        
        investors = []
        for pattern in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                investor = match.group(1).strip()
                # 处理可能的多个投资方，用逗号分隔
                if ',' in investor:
                    for i in investor.split(','):
                        if i.strip() and i.strip() not in investors:
                            investors.append(i.strip())
                else:
                    if investor not in investors:
                        investors.append(investor)
        
        return investors[:3]  # 限制投资方数量，避免误报
    
    def extract_company_product(self, content):
        """从文章内容中提取公司或产品信息"""
        if not content:
            return "未知"
            
        # 常见的公司提及模式
        patterns = [
            r'([A-Z][A-Za-z0-9\s]+) announced',
            r'([A-Z][A-Za-z0-9\s]+) raised',
            r'([A-Z][A-Za-z0-9\s]+) secured',
            r'([A-Z][A-Za-z0-9\s]+) closed',
            r'([A-Z][A-Za-z0-9\s]+), a [a-z]+ company',
            r'([A-Z][A-Za-z0-9\s]+), a startup'
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                company = match.group(1).strip()
                if len(company.split()) <= 5:  # 避免提取过长的匹配
                    return company
        
        # 如果没有匹配，尝试提取标题中的公司名称（通常首个词组是公司名）
        title_match = re.search(r'^([A-Z][A-Za-z0-9\s]+):', content)
        if title_match:
            return title_match.group(1).strip()
                
        return "未知"
    
    def format_posts_for_saving(self, posts):
        """将帖子格式化为保存格式"""
        formatted_posts = []
        for post in posts:
            # 提取公司/产品信息
            company_product = post.get('company_product', self.extract_company_product(post.get('content', '')))
            
            # 构造格式化的文本，包含公司/产品和投资信息
            investment_amount = post.get('investment_amount', 'N/A')
            investors = post.get('investors', [])
            
            if investment_amount != 'N/A' or investors:
                investment_info = (f"[投资金额: {investment_amount}, " +
                                  f"投资方: {', '.join(investors)}], " +
                                  f"公司/产品: {company_product}")
            else:
                investment_info = f"公司/产品：{company_product}"
                
            formatted_text = (f"{post.get('title', '')}: {post.get('content', '')} " + investment_info)
            
            # 确保公司/产品信息被包含在raw数据中
            if 'company_product' not in post:
                post['company_product'] = company_product
                
            formatted_posts.append({
                'text': formatted_text,
                'raw': post,
                'crawl_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'source': 'crunchbase.com'
            })
        
        return formatted_posts
    
    def _save_to_temp_storage(self, article_data):
        """将爬取的文章数据保存到临时存储"""
        if not article_data:
            return
        
        try:
            # 使用paths.py中定义的常量路径
            temp_file = CRU_TEMP_DATA_PATH
            
            # 确保目录存在
            if not os.path.exists(os.path.dirname(temp_file)):
                os.makedirs(os.path.dirname(temp_file))
            
            # 读取现有数据
            existing_data = []
            if os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
                try:
                    with open(temp_file, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            existing_data = json.loads(content)
                except json.JSONDecodeError as e:
                    logger.error(f"解析现有数据出错: {e}，将创建新文件")
            
            # 合并并保存数据
            if isinstance(article_data, list):
                combined_data = existing_data + article_data
            else:
                combined_data = existing_data + [article_data]
                
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(combined_data, f, ensure_ascii=False)
            
            # 更新存储时间戳
            self.last_save_time = time.time()
            logger.info(f"成功保存文章数据到临时存储: {temp_file}")
            
        except Exception as e:
            logger.error(f"保存到临时存储时出错: {e}")
    
    def process_and_save_in_batches(self, posts, batch_size=10):
        """将大量文章数据批量处理并只保存到临时存储，不再直接写入data.jsonl"""
        if not posts:
            logger.warning("没有数据需要处理")
            return 0
            
        logger.info(f"开始处理 {len(posts)} 篇文章，每批 {batch_size} 篇")
        
        # 格式化所有帖子
        formatted_posts = self.format_posts_for_saving(posts)
        
        # 保存到临时存储
        logger.info(f"批量处理完成，将所有 {len(formatted_posts)} 篇文章保存到临时存储")
        self._save_to_temp_storage([post['raw'] for post in formatted_posts])
        
        return len(formatted_posts)
    
    def close(self):
        """关闭浏览器并清理资源"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
    
    def run(self):
        """运行爬虫的主函数"""
        try:
            # 确保logs目录存在
            if not os.path.exists(LOGS_DIR):
                os.makedirs(LOGS_DIR)
                
            # 爬取帖子
            logger.info("开始爬取Crunchbase文章...")
            posts = self.crawl_posts()
            
            # 判断是否需要分批处理
            # 如果文章数量超过15，或者这是首次运行（判断cru_tempdata.json是否存在）
            is_first_run = not os.path.exists(CRU_TEMP_DATA_PATH) or os.path.getsize(CRU_TEMP_DATA_PATH) < 100
            
            if len(posts) > 15 or is_first_run:
                logger.info("检测到大量文章或首次运行，使用分批处理模式")
                saved_count = self.process_and_save_in_batches(posts)
            else:
                # 保存数据到临时存储
                self._save_to_temp_storage(posts)
                saved_count = len(posts)
                
            logger.info(f"爬虫执行完毕，处理了 {saved_count} 条数据")
            return saved_count
            
        except Exception as e:
            logger.error(f"爬虫运行出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 0
        finally:
            self.close()

def main():
    """主函数，执行爬虫任务"""
    try:
        # 添加全局超时控制
        start_time = time.time()
        last_check_time = start_time
        
        crawler = CrunchbaseCrawler()
        # 将开始时间传递给爬虫实例
        crawler.start_time = start_time
        crawler.last_save_time = start_time
        
        try:
            # 运行爬虫
            crawler_thread = threading.Thread(target=crawler.run)
            crawler_thread.daemon = True
            crawler_thread.start()
            
            # 检查是否有新数据写入
            temp_file = CRU_TEMP_DATA_PATH
            
            # 超时监控循环
            while crawler_thread.is_alive():
                # 每30秒检查一次
                time.sleep(30)
                
                current_time = time.time()
                
                # 检查文件是否存在和最后修改时间
                if os.path.exists(temp_file):
                    file_mod_time = os.path.getmtime(temp_file)
                    
                    # 如果超过10分钟没有更新文件，判断为爬虫卡死
                    if (current_time - file_mod_time > 600) and (current_time - last_check_time > 600):
                        logger.warning("警告: 超过10分钟没有新数据写入tempdata.json，判断爬虫卡死")
                        crawler.close()
                        logger.warning("强制关闭爬虫并退出监控")
                        return
                
                # 如果总运行时间超过20分钟，也强制退出
                if current_time - start_time > 1200:  # 20分钟
                    logger.warning(f"警告: 爬虫总运行时间超过20分钟，强制终止")
                    crawler.close()
                    return
                
                # 更新最后检查时间
                last_check_time = current_time
                
            # 爬虫正常结束
            logger.info("爬虫线程已正常完成")
            
        finally:
            # 确保关闭浏览器
            crawler.close()
        
        # 检查总运行时间
        end_time = time.time()
        total_time = end_time - start_time
        logger.info(f"爬虫运行完成，总耗时：{total_time:.2f}秒")
        
    except Exception as e:
        logger.error(f"爬虫执行出错: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main() 