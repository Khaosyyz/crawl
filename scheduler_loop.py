#!/usr/bin/env python3
# 爬虫调度器脚本
import os
import time
import datetime
import subprocess
import signal
import sys
import schedule
import logging
import glob
import pytz # Added for timezone awareness if needed later
import json
import traceback

# --- Determine Project Root ---
# Assumes scheduler_loop.py is in the project root alongside main.py
# If moved elsewhere, this needs adjustment.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')
CRAWLER_DIR = os.path.join(PROJECT_ROOT, 'crawlers') # Need this for crawler paths

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Add project root to path to allow importing other modules like db or utils
sys.path.append(PROJECT_ROOT)

# --- Logging Setup ---
# Standard logging setup, similar to other modules
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'scheduler.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('scheduler')
# Note: The original script tried to import a custom log_handler.
# Keeping it simple for now. Add log rotation later if needed.

# --- PID File Management ---
SCHEDULER_PID_FILE = os.path.join(LOG_DIR, "scheduler.pid")
try:
    with open(SCHEDULER_PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
except IOError as e:
    logger.error(f"无法写入 PID 文件 {SCHEDULER_PID_FILE}: {e}")
    sys.exit(1) # Exit if PID cannot be written

# --- Global State (To be refactored for dynamic crawlers) ---
# Dictionary to track running crawler processes {crawler_script_path: subprocess.Popen}
running_crawlers = {}
# Dictionary to track last run time {crawler_script_path: timestamp}
last_run_times = {}

# --- Crawler Execution Function (Refactored) ---
def run_scheduled_crawler(crawler_script_path: str):
    global running_crawlers, last_run_times

    # Check if the crawler script exists
    full_script_path = os.path.join(PROJECT_ROOT, crawler_script_path)
    if not os.path.isfile(full_script_path):
        logger.error(f"爬虫脚本未找到: {full_script_path}，跳过本次调度")
        return

    # Check if this crawler is already running
    if crawler_script_path in running_crawlers:
        process = running_crawlers[crawler_script_path]
        if process and process.poll() is None:
            logger.info(f"爬虫 {crawler_script_path} 已在运行 (PID: {process.pid})，跳过本次调度")
            return
        else:
            # Process finished or doesn't exist, remove from tracking
            logger.info(f"之前的爬虫进程 {crawler_script_path} (PID: {process.pid if process else 'N/A'}) 已结束")
            del running_crawlers[crawler_script_path]

    # Record run time
    last_run_times[crawler_script_path] = time.time()
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    # Sanitize script path for log file name
    log_file_base = crawler_script_path.replace('/', '_').replace('\\', '_').replace('.py', '')
    log_file = os.path.join(LOG_DIR, f'{log_file_base}_{timestamp}.log')

    # Simple log rotation: Keep only the latest log for this crawler
    try:
        for old_log in glob.glob(os.path.join(LOG_DIR, f'{log_file_base}_*.log')):
             if os.path.abspath(old_log) != os.path.abspath(log_file):
                 os.remove(old_log)
                 logger.info(f"删除旧日志文件: {old_log}")
    except Exception as e:
        logger.error(f"删除旧日志文件 {log_file_base}_*.log 时出错: {e}")

    logger.info(f"启动爬虫: {crawler_script_path}，日志: {log_file}")
    try:
        with open(log_file, 'w', buffering=1) as f:
            python_path = sys.executable
            process = subprocess.Popen(
                [python_path, '-u', full_script_path], # Use '-u' for unbuffered output
                stdout=f,
                stderr=subprocess.STDOUT, # Redirect stderr to stdout (logged to file)
                text=True,
                # bufsize=1, # text=True implies line buffering usually
                env=dict(os.environ, PYTHONUNBUFFERED="1") # Ensure Python is unbuffered
            )
            running_crawlers[crawler_script_path] = process
            logger.info(f"爬虫 {crawler_script_path} 已启动 (PID: {process.pid})")
    except Exception as e:
        logger.error(f"启动爬虫 {crawler_script_path} 失败: {e}")
        # Ensure it's removed from tracking if Popen failed
        if crawler_script_path in running_crawlers:
            del running_crawlers[crawler_script_path]


# --- Dynamic Crawler Discovery and Scheduling (Placeholder) ---
# This section needs refinement based on configuration strategy

def discover_and_schedule_crawlers():
    logger.info("开始发现并调度爬虫...")

    # TODO: Implement dynamic discovery and config reading
    # Option 1: Import discover_crawlers from main (requires careful path handling)
    # Option 2: Move discover_crawlers to utils.py
    # Option 3: Re-implement discovery here

    # --- Placeholder for config file approach ---
    config_file = os.path.join(PROJECT_ROOT, 'schedule_config.json')
    schedule_config = {}
    default_interval_minutes = 180 # Default: 3 hours if not specified

    try:
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                schedule_config = json.load(f)
            logger.info(f"从 {config_file} 加载调度配置")
        else:
            logger.warning(f"调度配置文件 {config_file} 未找到，将使用默认间隔或不调度")
            # Create a default config file?
            default_config = {
                "crawlers/X/x.py": {"interval_minutes": 180}, # 3 hours
                "crawlers/Crunchbase/crunchbase.py": {"interval_minutes": 720} # 12 hours
            }
            try:
                with open(config_file, 'w') as f:
                    json.dump(default_config, f, indent=4)
                logger.info(f"创建了默认调度配置文件: {config_file}")
                schedule_config = default_config
            except IOError as e:
                 logger.error(f"创建默认配置文件失败: {e}")

    except Exception as e:
        logger.error(f"加载或创建调度配置文件 {config_file} 出错: {e}")
        # Continue without config? Decide on behavior.


    # --- Simple Discovery (Re-implementing glob pattern) ---
    discovered_scripts = []
    # Using glob to find python files directly
    for pattern in [os.path.join(CRAWLER_DIR, '*.py'),
                    os.path.join(CRAWLER_DIR, '*', '*.py')]: # Covers root and one level subdir
        discovered_scripts.extend(glob.glob(pattern))

    scheduled_count = 0
    for script_path_abs in discovered_scripts:
        script_path_rel = os.path.relpath(script_path_abs, PROJECT_ROOT) # Get relative path for config key
        filename = os.path.basename(script_path_rel)

        if filename.startswith('_') or filename == '__init__.py':
            continue # Skip helper/init files

        # Get interval from config or use default
        config = schedule_config.get(script_path_rel, {})
        interval = config.get("interval_minutes", None) # Allow disabling via config

        if interval is not None and interval > 0 :
            logger.info(f"为 {script_path_rel} 设置调度任务，间隔: {interval} 分钟")
            schedule.every(interval).minutes.do(run_scheduled_crawler, crawler_script_path=script_path_rel)
            scheduled_count += 1
        elif script_path_rel in schedule_config:
             logger.info(f"爬虫 {script_path_rel} 在配置中但间隔无效或为0，将不被调度")
        else:
            logger.info(f"爬虫 {script_path_rel} 未在配置中找到，将不被调度")


    if scheduled_count == 0:
         logger.warning("没有发现任何有效的爬虫或调度配置，调度器将空闲运行")

    logger.info(f"爬虫发现和调度设置完成，共调度 {scheduled_count} 个爬虫")


# --- Signal Handling ---
def handle_signal(signum, frame):
    logger.warning(f"收到信号 {signum}，准备退出调度器...")
    # Attempt graceful shutdown? (e.g., wait for current crawlers?)
    # For now, just exit.
    # Clean up PID file before exiting
    try:
        if os.path.exists(SCHEDULER_PID_FILE):
            os.remove(SCHEDULER_PID_FILE)
            logger.info(f"已移除 PID 文件: {SCHEDULER_PID_FILE}")
    except OSError as e:
        logger.error(f"移除 PID 文件 {SCHEDULER_PID_FILE} 时出错: {e}")
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


# --- Main Loop ---
if __name__ == "__main__":
    logger.info("爬虫调度器启动")
    discover_and_schedule_crawlers()
    logger.info("调度设置完成，进入主循环")

    try:
        while True:
            schedule.run_pending()
            # Check status of running crawlers? Optional.
            # Clean up finished processes from running_crawlers dict
            finished_crawlers = []
            for script_path, process in running_crawlers.items():
                if process and process.poll() is not None:
                    logger.info(f"检测到爬虫 {script_path} (PID: {process.pid}) 已完成，返回码: {process.returncode}")
                    finished_crawlers.append(script_path)
            for script_path in finished_crawlers:
                del running_crawlers[script_path]

            time.sleep(1) # Check schedule every second
    except Exception as e:
        logger.error(f"调度器主循环发生未捕获错误: {e}")
        logger.error(traceback.format_exc())
    finally:
        # Ensure PID file is removed on unexpected exit too
        logger.warning("调度器退出")
        try:
            if os.path.exists(SCHEDULER_PID_FILE):
                os.remove(SCHEDULER_PID_FILE)
                logger.info(f"已移除 PID 文件: {SCHEDULER_PID_FILE}")
        except OSError as e:
            logger.error(f"退出时移除 PID 文件 {SCHEDULER_PID_FILE} 出错: {e}") 