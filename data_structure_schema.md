# 数据结构规范文档

本文档记录了系统中使用的数据结构格式，包括各数据源的字段定义、格式要求和示例。所有爬虫和清洗服务必须遵循此规范，确保输出数据与前端展示兼容。

## 通用字段

所有数据源共享以下基础字段：

| 字段名 | 类型 | 描述 | 示例 |
|-------|------|------|------|
| _id | ObjectId | MongoDB自动生成的唯一ID | "67e534f2ff31146f279651aa" |
| id | String | 基于源和URL生成的MD5哈希值 | "8adf28ff2eb9ac4764a3697f47e3cdc5" |
| title | String | 文章标题 | "用户关注 OpenAI 新模型发布动向" |
| content | String | 经过清洗的文章正文 | "OpenAI 的新模型是什么情况？我得去看看。" |
| author | String | 作者姓名或用户名 | "aida (@aidaa_soufi)" |
| date_time | String | 发布日期和时间 | "2025-03-27 17:58" |
| source | String | 来源平台 | "x.com" 或 "crunchbase.com" |
| source_url | String | 原始文章URL | "https://x.com/aidaa_soufi/status/1905197841074524257" |
| processed_at | String | 数据处理时间 | "2025-03-27 19:22:26" |

## X.com 数据结构

X.com数据源特有的字段：

| 字段名 | 类型 | 描述 | 示例 |
|-------|------|------|------|
| likes | Number | 点赞数 | 42 |
| retweets | Number | 转发数 | 10 |
| followers | Number | 作者粉丝数 | 1561 |

### X.com 样例数据

```json
{
  "_id": {"$oid": "67e534f2ff31146f279651aa"},
  "title": "用户关注 OpenAI 新模型发布动向",
  "content": "OpenAI 的新模型是什么情况？我得去看看。",
  "author": "aida (@aidaa_soufi)",
  "date_time": "2025-03-27 17:58",
  "source": "x.com",
  "source_url": "https://x.com/aidaa_soufi/status/1905197841074524257",
  "likes": 0,
  "retweets": 0,
  "followers": 1561,
  "processed_at": "2025-03-27 19:22:26",
  "id": "8adf28ff2eb9ac4764a3697f47e3cdc5"
}
```

## Crunchbase 数据结构

Crunchbase数据源特有的字段：

| 字段名 | 类型 | 描述 | 示例 |
|-------|------|------|------|
| company | String | 公司名称 | "OpenAI" |
| funding_round | String | 融资轮次 | "C轮" |
| funding_amount | String | 融资金额 | "2.5亿美元" |
| investors | String | 投资方 | "黑石集团, 红杉资本" |

### Crunchbase 样例数据

```json
{
  "_id": {"$oid": "67e60e25650f2ea519975702"},
  "title": "QuEra Computing 2.3 亿美元未提供轮次融资",
  "content": "上个月，量子计算初创公司 QuEra Computing 锁定了来自软银愿景基金和谷歌量子AI的2.3亿美元融资。仅几周后，总部位于以色列的Quantum Machines又获得了由PSG Equity领投的1.7亿美元C轮融资。如果去年是任何迹象，这些只会是今年量子初创公司的众多大轮融资的第一批。事实上，2024年为量子领域的风险投资创下了新高。",
  "author": "Chris Metinko",
  "date_time": "2024-03-27",
  "source": "crunchbase.com",
  "source_url": "https://news.crunchbase.com/venture/quantum-computing-quera-funding/",
  "company": "QuEra Computing",
  "funding_round": "未提供",
  "funding_amount": "2.3 亿美元",
  "investors": "软银愿景基金, 谷歌量子AI",
  "processed_at": "2025-03-28 10:49:09",
  "id": "6bf480fc47c518a685612d84575af96e"
}
```

## 爬虫输出格式要求

爬虫脚本应输出包含以下字段的JSON或JSONL文件：

### X.com爬虫输出

```json
{
  "text": "原始推文内容",
  "date_time": "YYYY-MM-DD HH:MM",
  "source_url": "推文URL",
  "raw": {
    "name": "用户全名",
    "username": "用户名",
    "followers_count": 12345,
    "favorite_count": 42,
    "retweet_count": 10,
    "url": "推文URL"
  }
}
```

### Crunchbase爬虫输出

```json
{
  "title": "原始文章标题",
  "content": "原始文章内容",
  "author": "作者名称",
  "date_time": "YYYY-MM-DD HH:MM:SS",
  "url": "文章URL"
}
```

## 清洗服务处理规范

清洗服务必须遵循以下规范处理数据：

1. **标题处理**：
   - 必须翻译为中文
   - 长度不超过25-30个字
   - 必须简洁明了，包含关键信息
   - Crunchbase标题格式为"公司名+融资金额+轮次"

2. **正文处理**：
   - 必须翻译为中文
   - 保持专业性和准确性
   - 保留重要专业术语和英文原文
   - URLs格式化为：原文中的URL应替换为"——报告链接：@URL"格式
   - 分段合理，删除冗余信息
   - 确保句子和段落完整

3. **数据过滤**：
   - 只处理与AI、人工智能、机器学习等相关的内容
   - 对于Crunchbase，重点关注AI相关公司的融资信息

## 数据存储规范

所有处理后的数据都将存储在MongoDB中，集合名为"articles"，以下字段必须是唯一的：

- `source_url`: 使用唯一索引确保不重复存储同一文章
- `id`: 基于source和source_url生成的哈希值 