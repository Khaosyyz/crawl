# AI 相关新闻爬虫与数据清洗系统

本项目包含一套自动化爬取、清洗和展示AI相关新闻的系统，为用户提供高质量的AI行业动态信息。

## 项目结构

```
.
├── main.py             # 主入口文件
├── launch.sh           # 服务启动脚本
├── static/             # 静态文件（前端页面）
├── logs/               # 日志文件夹
├── src/                # 源代码目录
│   ├── api/            # API 服务
│   │   └── app.py      # API 应用
│   ├── clean/          # 数据清洗模块
│   ├── config/         # 配置文件目录
│   ├── crawlers/       # 爬虫模块
│   │   ├── X/          # Twitter/X 爬虫
│   │   ├── Crunchbase/ # Crunchbase 爬虫
│   │   └── run_crawler.py # 爬虫运行脚本
│   ├── data/           # 数据存储
│   ├── db/             # 数据库操作
│   └── utils/          # 工具函数
│       └── scheduler_loop.py # 调度器
└── vercel.json         # Vercel 部署配置
```

## 功能

- 自动抓取 X(Twitter) 和 Crunchbase 上的 AI 相关新闻
- 使用大语言模型进行内容清洗和翻译
- 提供 API 接口供前端调用
- 基于时间和分页的新闻展示

## 使用方法

### 安装依赖

```bash
pip install -r requirements.txt
```

### 使用启动脚本

```bash
./launch.sh start      # 启动所有服务
./launch.sh stop       # 停止所有服务
./launch.sh status     # 查看服务状态
./launch.sh crawler x  # 运行X爬虫
./launch.sh cleaner    # 运行数据清洗
```

### 使用 Python 命令

```bash
# 启动/停止服务
python3 main.py start   # 启动所有服务
python3 main.py stop    # 停止所有服务
python3 main.py status  # 查看服务状态

# 运行爬虫
python3 main.py crawl
python3 main.py crawl --crawler x  # 只运行 X 爬虫

# 运行数据清洗
python3 main.py clean
```

## 部署

项目使用 Vercel 进行部署，基于 Python 运行时。前端静态文件位于 `static` 目录。 