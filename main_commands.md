# AI资讯聚合系统命令指南

## 基本用法

```
python3 main.py [命令]
```

## 可用命令

### 服务管理命令

- `start` - 启动所有服务（API、数据清洗、定时爬虫）
- `stop` - 停止所有运行中的服务
- `restart` - 重启所有服务
- `status` - 显示所有服务的运行状态

### 单独服务命令

- `api` - 仅启动API服务（包含前端Web界面，访问 http://localhost:8080）
- `cleaner` - 仅启动数据清洗服务
- `scheduler` - 仅启动爬虫定时任务服务

### 爬虫命令

- `crawler` - 立即运行一次爬虫（爬取X和Crunchbase数据）

## 示例

```bash
# 启动所有服务
python3 main.py start

# 只启动前端服务（API）
python3 main.py api

# 查看所有服务状态
python3 main.py status

# 停止所有服务
python3 main.py stop
```

## 注意事项

- API服务包含前端界面，默认在 http://localhost:8080 访问
- 数据存储在 data/data.jsonl 文件中
- 日志文件位于 logs/ 目录
- 调度器已设置不同的爬虫运行周期：
  - X爬虫 (x.py) 每3小时运行一次
  - Crunchbase爬虫 (crunchbase.py) 每12小时运行一次
- 两个爬虫都添加了10分钟超时控制，若运行超过10分钟会自动终止 

## 管理服务的命令

以下是管理服务的命令：

### 启动服务

```bash
python3 main.py start
```

这将启动Web服务器和爬虫调度器。Web服务器将运行在http://localhost:8000

### 停止服务

```bash
python3 main.py stop
```

这将停止Web服务器和爬虫调度器。

### 检查服务状态

```bash
python3 main.py status
```

这将显示Web服务器和爬虫调度器的运行状态。

### 示例

```bash
python3 main.py start  # 启动所有服务
python3 main.py stop   # 停止所有服务
python3 main.py status # 检查服务状态
```

## 爬虫调度周期

系统中的爬虫有不同的运行周期：
- X爬虫 (x.py) 每3小时运行一次
- Crunchbase爬虫 (crunchbase.py) 每12小时运行一次

这些调度时间可以在main.py文件中修改。

## 超时控制与自动重启机制

系统为爬虫添加了超时控制和自动重启机制：

1. **超时检测**：
   - 根据临时数据文件(`x_tempdata.json`/`cru_tempdata.json`)的更新时间判断爬虫是否处于活动状态
   - 如果超过10分钟没有更新临时文件，判定爬虫卡死

2. **自动重启**：
   - 爬虫卡死后会自动关闭并在下次调度时重启
   - 调度器会持续监控爬虫进程状态，确保数据采集的稳定性

3. **强制超时**：
   - 如果爬虫总运行时间超过20分钟，会强制终止
   - 这可以防止爬虫无限运行消耗系统资源

这些机制使系统更加健壮，能够自动从错误状态中恢复。 