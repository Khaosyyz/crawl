import requests
import json
from pprint import pprint

BASE_URL = 'http://localhost:8080'

def test_get_articles():
    """测试获取文章列表"""
    print("\n测试获取文章列表:")
    response = requests.get(f'{BASE_URL}/api/articles')
    print(f"状态码: {response.status_code}")
    try:
        data = response.json()
        print("响应数据:")
        pprint(data)
    except json.JSONDecodeError as e:
        print(f"JSON解析错误: {e}")
        print("原始响应:")
        print(response.text)

def test_get_article_by_id():
    """测试获取单篇文章"""
    print("\n测试获取单篇文章:")
    # 先获取一篇文章的ID
    response = requests.get(f'{BASE_URL}/api/articles')
    print(f"状态码: {response.status_code}")
    try:
        data = response.json()
        if data['data']:
            article_id = data['data'][0]['_id']
            response = requests.get(f'{BASE_URL}/api/articles/{article_id}')
            print(f"状态码: {response.status_code}")
            data = response.json()
            if data['status'] == 'success':
                print("\n文章详情:")
                pprint(data['data'])
    except json.JSONDecodeError as e:
        print(f"JSON解析错误: {e}")
        print("原始响应:")
        print(response.text)

def test_search_articles():
    """测试搜索文章"""
    print("\n测试搜索文章:")
    query = "AI"  # 测试搜索关键词
    response = requests.get(f'{BASE_URL}/api/search', params={'q': query})
    print(f"状态码: {response.status_code}")
    try:
        data = response.json()
        print(f"搜索关键词: {query}")
        print(f"匹配文章数: {data['total']}")
        if data['data']:
            print("\n第一篇匹配文章示例:")
            pprint(data['data'][0])
    except json.JSONDecodeError as e:
        print(f"JSON解析错误: {e}")
        print("原始响应:")
        print(response.text)

def test_get_stats():
    """测试获取统计信息"""
    print("\n测试获取统计信息:")
    response = requests.get(f'{BASE_URL}/api/stats')
    print(f"状态码: {response.status_code}")
    try:
        data = response.json()
        if data['status'] == 'success':
            print("\n统计信息:")
            pprint(data['data'])
    except json.JSONDecodeError as e:
        print(f"JSON解析错误: {e}")
        print("原始响应:")
        print(response.text)

def main():
    """运行所有测试"""
    print("开始测试 API 服务...")
    
    try:
        test_get_articles()
        test_get_article_by_id()
        test_search_articles()
        test_get_stats()
        print("\n所有测试完成!")
    except requests.exceptions.ConnectionError:
        print("\n错误: 无法连接到 API 服务，请确保服务已启动")
    except Exception as e:
        print(f"\n测试过程中出现错误: {e}")

if __name__ == '__main__':
    main() 