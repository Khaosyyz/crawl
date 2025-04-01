#!/usr/bin/env python3
"""
AI资讯聚合系统主程序
提供项目所有组件的启动、停止和管理功能
"""

import argparse
import os
import signal
import subprocess
import sys
import time
import glob
from datetime import datetime
import logging
import socket
import importlib.util
import traceback

# 设置日志记录 - 修改为只记录错误和警告信息
logging.basicConfig(
    level=logging.WARNING,  # 改为WARNING级别,只记录警告和错误
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join("logs", "main.log")),  # 存储在logs目录下
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("main")

# 目录和文件配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.join(BASE_DIR, "api")
CLEAN_DIR = os.path.join(BASE_DIR, "clean")
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")
VENV_PYTHON = sys.executable  # 使用当前Python解释器
CRAWLER_DIR = os.path.join(BASE_DIR, "crawlers")

# 确保各目录存在
os.makedirs(API_DIR, exist_ok=True)
os.makedirs(CLEAN_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(CRAWLER_DIR, exist_ok=True)

# 进程ID文件
# API_PID_FILE = os.path.join(LOG_DIR, "api.pid")
CLEANER_PID_FILE = os.path.join(LOG_DIR, "cleaner.pid")
SCHEDULER_PID_FILE = os.path.join(LOG_DIR, "scheduler.pid")

# 日志文件
SCHEDULER_LOG_FILE = os.path.join(LOG_DIR, "scheduler.log")

# 服务端口
# API_PORT = 8080

# 全局变量
scheduler_running = False

# 全局变量记录最后一次爬虫运行时间
last_x_crawler_run = 0
last_crunchbase_crawler_run = 0
x_crawler_process = None
crunchbase_crawler_process = None


def write_pid(pid_file, pid):
    """将进程ID写入文件"""
    with open(pid_file, 'w') as f:
        f.write(str(pid))


def read_pid(pid_file):
    """从文件读取进程ID"""
    if not os.path.exists(pid_file):
        return None
    try:
        with open(pid_file, 'r') as f:
            return int(f.read().strip())
    except (IOError, ValueError):
        return None


def is_pid_running(pid):
    """检查指定的PID是否正在运行"""
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ProcessLookupError, ValueError):
        return False


def is_process_running(pid):
    """检查进程是否运行中"""
    return is_pid_running(pid)


def is_port_in_use(port):
    """检查指定端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def get_pid_by_port(port):
    """通过端口获取进程ID列表"""
    try:
        # 使用lsof命令查找使用指定端口的进程，只查找LISTEN状态的连接
        cmd = ["lsof", "-i", f":{port}", "-s", "TCP:LISTEN", "-t"]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, _ = process.communicate()
        if output:
            # 处理可能的多行输出（多个PID）
            pids = [int(pid.strip()) for pid in output.decode().strip().split('\n') if pid.strip()]
            # 如果有PID，返回第一个
            if pids:
                return pids[0]
        return None
    except Exception as e:
        logger.error(f"获取端口 {port} 的进程ID时出错: {e}")
        return None


def kill_process_by_port(port):
    """杀死占用指定端口的进程"""
    pid = get_pid_by_port(port)
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
            if is_pid_running(pid):
                os.kill(pid, signal.SIGKILL)
            logger.info(f"已终止占用端口 {port} 的进程 (PID: {pid})")
            
            # 再次检查端口是否仍被占用
            return not is_port_in_use(port)
        except OSError as e:
            logger.error(f"终止进程 (PID: {pid}) 时出错: {e}")
            return False
    return False  # 如果没有找到PID，则操作未成功


def start_cleaner_service():
    """启动数据清洗服务"""
    # 检查是否已经在运行
    pid = read_pid(CLEANER_PID_FILE)
    if pid and is_pid_running(pid):
        logger.info(f"数据清洗服务已经在运行中 (PID: {pid})")
        print(f"数据清洗服务已经在运行中 (PID: {pid})")
        return True

    log_file = os.path.join(LOG_DIR, "cleaner.log")
    with open(log_file, 'a') as log:
        try:
            # 确保数据清洗文件存在且可执行
            cleaner_script = os.path.join(CLEAN_DIR, 'cleandata.py')
            if not os.path.isfile(cleaner_script):
                error_msg = f"找不到数据清洗服务文件: {cleaner_script}"
                logger.error(error_msg)
                print(f"错误: {error_msg}")
                return False
                
            # 启动前记录日志
            print("正在启动数据清洗服务...")
            log.write(f"\n\n{'-'*50}\n")
            log.write(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            log.write(f"{'-'*50}\n\n")
            log.flush()
            
            # 创建定时运行清洗服务的脚本内容
            loop_script = '''
import os
import sys
import time
import logging
import importlib.util
import traceback

# 日志目录
LOG_DIR = "''' + LOG_DIR + '''"
os.makedirs(LOG_DIR, exist_ok=True)

# 尝试导入自定义日志处理模块
try:
    sys.path.append(LOG_DIR)
    from log_handler import setup_logger, start_log_cleanup_thread
    
    # 配置日志记录
    logger = setup_logger(
        name="cleaner_loop",
        log_file=os.path.join(LOG_DIR, "cleaner_loop.log"),
        level=logging.INFO,
        console_output=True
    )
    
    # 启动日志清理线程
    cleanup_thread = start_log_cleanup_thread(LOG_DIR)
    
except ImportError:
    # 如果导入失败，回退到标准日志配置
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(os.path.join(LOG_DIR, "cleaner_loop.log")),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger("cleaner_loop")
    logger.warning("无法导入自定义日志处理模块，使用标准日志配置")

# 清洗脚本路径
CLEANER_SCRIPT = "''' + cleaner_script + '''"

def main():
    """主函数，循环运行清洗服务"""
    logger.info("清洗服务循环启动")
    
    try:
        # 动态导入清洗模块
        spec = importlib.util.spec_from_file_location("cleandata", CLEANER_SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载清洗脚本: {CLEANER_SCRIPT}")
            
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        while True:
            logger.info("启动清洗服务...")
            
            try:
                # 直接调用清洗模块的process_data函数
                module.process_data()
                logger.info("清洗服务执行完成，等待下一次执行")
            except Exception as e:
                logger.error(f"清洗服务执行失败: {e}")
                logger.error(traceback.format_exc())
            
            # 等待一段时间再次执行
            wait_time = 60  # 1分钟
            logger.info(f"等待 {wait_time} 秒后再次执行清洗服务...")
            time.sleep(wait_time)
            
    except KeyboardInterrupt:
        logger.info("收到中断信号，清洗服务循环退出")
    except Exception as e:
        logger.error(f"清洗服务循环发生错误: {e}")
    
    logger.info("清洗服务循环结束")

if __name__ == "__main__":
    main()
'''
            
            # 启动循环脚本
            process = subprocess.Popen(
                [VENV_PYTHON, "-c", loop_script],
                stdout=log,
                stderr=log
            )
            
            # 等待一下,确保进程启动
            time.sleep(2)
            
            # 验证进程是否启动
            if process.poll() is not None:
                # 进程已经退出
                error_msg = f"数据清洗服务启动后立即退出,返回码: {process.returncode}"
                logger.error(error_msg)
                print(f"错误: {error_msg}")
                return False
            
            # 保存PID
            write_pid(CLEANER_PID_FILE, process.pid)
            
            # 再次验证进程是否仍在运行
            if is_pid_running(process.pid):
                success_msg = f"数据清洗服务已成功启动 (PID: {process.pid})"
                logger.info(success_msg)
                print(success_msg)
                return True
            else:
                error_msg = "数据清洗服务无法持续运行"
                logger.error(error_msg)
                print(f"错误: {error_msg}")
                return False
                
        except Exception as e:
            error_msg = f"启动数据清洗服务时出错: {e}"
            logger.error(error_msg)
            print(f"错误: {error_msg}")
            return False


def run_crawler(crawler_module=None):
    """运行指定的爬虫或默认爬虫(x.py)"""
    if crawler_module is None:
        # 默认运行 x.py
        crawler_module = "crawlers.X.x"
    
    # 提取模块名称作为日志文件名
    module_name = crawler_module.split('.')[-1]
    log_file = os.path.join(LOG_DIR, f"{module_name}_crawler_{datetime.now().strftime('%Y%m%d%H%M%S')}.log")
    
    with open(log_file, 'w') as log:
        process = subprocess.Popen(
            [VENV_PYTHON, "-m", crawler_module],
            stdout=log,
            stderr=log
        )
    
    print(f"爬虫 {module_name} 已启动,日志保存在 {log_file}")
    return process


def discover_crawlers():
    """发现crawlers目录下所有可用的爬虫模块"""
    crawler_modules = []
    
    # 检查根目录下的爬虫
    crawler_files = glob.glob(os.path.join(CRAWLER_DIR, "*.py"))
    for file_path in crawler_files:
        filename = os.path.basename(file_path)
        if filename.startswith('_') or not filename.endswith('.py'):
            continue
        
        module_name = filename[:-3]  # 去掉.py后缀
        crawler_modules.append(f"crawlers.{module_name}")
    
    # 检查X目录下的爬虫
    x_crawler_files = glob.glob(os.path.join(CRAWLER_DIR, "X", "*.py"))
    for file_path in x_crawler_files:
        filename = os.path.basename(file_path)
        if filename.startswith('_') or not filename.endswith('.py'):
            continue
        
        module_name = filename[:-3]  # 去掉.py后缀
        crawler_modules.append(f"crawlers.X.{module_name}")
    
    # 检查Crunchbase目录下的爬虫
    cb_files = glob.glob(os.path.join(CRAWLER_DIR, "Crunchbase", "*.py"))
    for file_path in cb_files:
        filename = os.path.basename(file_path)
        if filename.startswith('_') or not filename.endswith('.py'):
            continue
        
        module_name = filename[:-3]  # 去掉.py后缀
        crawler_modules.append(f"crawlers.Crunchbase.{module_name}")
    
    return crawler_modules


def run_all_crawlers():
    """运行所有发现的爬虫"""
    crawlers = discover_crawlers()
    for crawler in crawlers:
        try:
            run_crawler(crawler)
            time.sleep(1)  # 避免同时启动太多进程
        except Exception as e:
            logger.error(f"启动爬虫 {crawler} 失败: {e}")
    
    return len(crawlers)


def stop_service(service_name, pid_file, port=None):
    """停止指定服务"""
    logger.info(f"正在尝试停止 {service_name}...") # 添加日志
    # 先通过PID文件停止服务
    pid = read_pid(pid_file)
    pid_stopped = False
    
    if pid and is_process_running(pid):
        try:
            # 先发送SIGTERM信号
            os.kill(pid, signal.SIGTERM)
            # 等待进程退出
            for _ in range(10):
                if not is_process_running(pid):
                    pid_stopped = True
                    break
                time.sleep(0.5)
            else:
                # 如果进程没有退出,发送SIGKILL信号
                logger.warning(f"{service_name}未响应SIGTERM,发送SIGKILL")
                os.kill(pid, signal.SIGKILL)
                pid_stopped = True
        except OSError as e:
            logger.error(f"停止{service_name}时出错: {e}")
    
    # 如果有指定端口，也检查端口是否被占用
    if port and is_port_in_use(port):
        port_pid = get_pid_by_port(port)
        if port_pid and (not pid or port_pid != pid):
            try:
                os.kill(port_pid, signal.SIGTERM)
                time.sleep(1)
                if is_pid_running(port_pid):
                    os.kill(port_pid, signal.SIGKILL)
                logger.info(f"已终止占用端口 {port} 的进程 (PID: {port_pid})") # 保持日志
            except OSError as e:
                logger.error(f"终止进程 (PID: {port_pid}) 时出错: {e}")
            # 即使出错，也尝试继续清除 PID 文件

    # 清除PID文件
    if os.path.exists(pid_file):
        try: # 添加 try-except 块
            os.remove(pid_file)
            logger.info(f"已移除 {service_name} 的 PID 文件: {pid_file}")
        except OSError as e:
            logger.error(f"移除 PID 文件 {pid_file} 时出错: {e}")
    else:
        logger.warning(f"未找到 {service_name} 的 PID 文件: {pid_file}") # 添加警告

    final_status_stopped = pid_stopped or (port and not is_port_in_use(port))
    logger.info(f"{service_name} 停止操作完成，最终状态: {'已停止' if final_status_stopped else '可能仍在运行'}")
    return final_status_stopped # 返回最终状态


def check_dependencies():
    """检查系统依赖文件和目录是否存在"""
    # 检查是否已安装必要的Python包
    # 确保添加 Flask 和 Flask-Cors
    required_packages = ['schedule', 'pytz', 'selenium', 'requests', 'pymongo']
    missing_packages = []
    
    try:
        try:
            import pkg_resources
            for package in required_packages:
                try:
                    pkg_resources.get_distribution(package)
                except pkg_resources.DistributionNotFound:
                    missing_packages.append(package)
        except ImportError:
            print("警告: 无法导入pkg_resources模块,跳过Python包依赖检查")
            print("提示: 这通常意味着setuptools包未正确安装")
    except Exception as e:
        print(f"警告: 检查Python包依赖时出错: {e}")
    
    if missing_packages:
        print(f"警告: 缺少以下Python包: {', '.join(missing_packages)}")
        print("请使用以下命令安装缺失的包:")
        print(f"pip install {' '.join(missing_packages)}")
    
    required_files = [
        # os.path.join(API_DIR, 'api.py'),
        os.path.join(CLEAN_DIR, 'cleandata.py'),
    ]
    
    required_dirs = [
        'static',
        CRAWLER_DIR,
        LOG_DIR,
        DATA_DIR,
        API_DIR,
        CLEAN_DIR
    ]
    
    # 检查目录
    for dir_path in required_dirs:
        if not os.path.isdir(dir_path):
            logger.error(f"缺少必要的目录: {dir_path}")
            print(f"错误: 缺少必要的目录 {dir_path}")
            return False
            
    # 检查文件
    for file_path in required_files:
        if not os.path.isfile(file_path):
            logger.error(f"缺少必要的文件: {file_path}")
            print(f"错误: 缺少必要的文件 {file_path}")
            return False
    
    # 检查是否有爬虫文件
    crawlers = discover_crawlers()
    if not crawlers:
        logger.warning("未发现任何爬虫脚本,系统仍将启动,但无爬虫服务")
        print("警告: 未发现任何爬虫脚本")
    
    return True


def start_all():
    """启动所有本地服务 (Cleaner & Scheduler)"""
    print("正在启动本地后台服务...")

    # 首先检查依赖
    if not check_dependencies():
        print("启动失败: 系统缺少必要的文件、目录或依赖库")
        return False

    # 启动数据清洗服务
    print("正在启动数据清洗服务...")
    cleaner_success = start_cleaner_service()

    # 启动爬虫定时任务
    print("正在启动爬虫定时任务...")
    scheduler_success = start_scheduler()

    # 打印启动结果汇总
    print("\n===== 本地服务启动结果汇总 =====")

    # 读取进程ID
    # api_pid = read_pid(API_PID_FILE) # 移除
    cleaner_pid = read_pid(CLEANER_PID_FILE)
    scheduler_pid = read_pid(SCHEDULER_PID_FILE)

    # API服务状态 (移除)
    # if api_success and api_pid and is_pid_running(api_pid) and is_port_in_use(API_PORT):
    # ...

    # 数据清洗服务状态
    if cleaner_success and cleaner_pid and is_pid_running(cleaner_pid):
        print(f"数据清洗服务: 成功启动 (PID: {cleaner_pid})")
    else:
        print(f"数据清洗服务: 启动失败 ✗ - 请检查logs/cleaner.log获取更多信息")

    # 爬虫定时任务状态
    if scheduler_success and scheduler_pid and is_pid_running(scheduler_pid):
        print(f"爬虫定时任务: 成功启动 (PID: {scheduler_pid})")
    else:
        print(f"爬虫定时任务: 启动失败 ✗ - 请检查logs/scheduler.log获取更多信息")

    # 服务启动总结
    if cleaner_success and scheduler_success: # 移除 api_success
        print("\n所有本地核心服务已尝试启动成功！")
        return True
    else:
        print("\n警告: 部分本地核心服务未能成功启动,请检查日志文件了解详情")
        return False


def stop_all():
    """停止所有本地服务 (Cleaner & Scheduler)"""
    print("正在停止所有本地服务...")
    # api_stopped = stop_api_service() # 移除
    cleaner_stopped = stop_cleaner_service()
    scheduler_stopped = stop_scheduler()

    print("\n所有本地服务已尝试停止")
    return 0


def status():
    """查看本地服务状态"""
    # 检查API服务 (移除)
    # api_pid = read_pid(API_PID_FILE)
    # ...

    # 检查清洗服务
    cleaner_pid = read_pid(CLEANER_PID_FILE)
    cleaner_running = cleaner_pid and is_process_running(cleaner_pid)

    # 检查调度器
    scheduler_pid = read_pid(SCHEDULER_PID_FILE)
    scheduler_running = scheduler_pid and is_process_running(scheduler_pid)

    # 打印状态
    print("===== 本地服务状态 =====")

    # API服务状态 (移除)
    # print(api_status_str)

    # 清洗服务状态
    print(f"数据清洗服务: {'运行中' if cleaner_running else '已停止'} " +
          (f"(PID: {cleaner_pid})" if cleaner_running else ""))

    # 调度器状态
    print(f"爬虫定时任务: {'运行中' if scheduler_running else '已停止'} " +
         (f"(PID: {scheduler_pid})" if scheduler_running else ""))


def start_scheduler():
    """启动定时任务调度器 (运行 scheduler_loop.py)"""
    # 检查是否已经在运行
    pid = read_pid(SCHEDULER_PID_FILE)
    if pid and is_pid_running(pid):
        logger.warning("调度器已经在运行中")
        print(f"爬虫定时任务调度器已经在运行中 (PID: {pid})")
        return True

    # 运行外部 scheduler_loop.py 脚本
    scheduler_loop_script = os.path.join(BASE_DIR, 'scheduler_loop.py')
    if not os.path.isfile(scheduler_loop_script):
        error_msg = f"找不到调度器脚本文件: {scheduler_loop_script}"
        logger.error(error_msg)
        print(f"错误: {error_msg}")
        return False

    log_file = SCHEDULER_LOG_FILE # Use the same log file defined earlier
    with open(log_file, 'a') as log:
        try:
            # 记录启动信息
            print("正在启动爬虫定时任务调度器 (scheduler_loop.py)...")
            log.write(f"\n\n{'-'*50}\n")
            log.write(f"启动时间 (由 main.py 发起): {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            log.write(f"{'-'*50}\n\n")
            log.flush()

            # 使用 subprocess 运行 scheduler_loop.py
            process = subprocess.Popen(
                [VENV_PYTHON, scheduler_loop_script], # 直接运行脚本
                stdout=log,
                stderr=log,
                cwd=BASE_DIR, # Set working directory
                start_new_session=True # Run in a new session to detach from main.py's lifecycle if needed
            )

            # 等待 scheduler_loop.py 创建自己的 PID 文件并启动
            time.sleep(3)  # 给调度器脚本一些启动时间

            # 检查调度器 PID 文件是否存在且进程在运行
            scheduler_pid = read_pid(SCHEDULER_PID_FILE)
            if scheduler_pid and is_pid_running(scheduler_pid):
                # 确认启动的进程 PID 与文件中的 PID 一致
                if process.pid == scheduler_pid:
                     print(f"定时任务调度器已启动 (PID: {scheduler_pid})")
                     logger.info(f"定时任务调度器 (scheduler_loop.py) 启动成功，PID: {scheduler_pid}")
                     return True
                else:
                    # PID 不匹配，可能 scheduler_loop.py 内部启动失败或 PID 文件写入延迟
                    logger.error(f"启动的进程 PID ({process.pid}) 与调度器 PID 文件中的 PID ({scheduler_pid}) 不匹配。")
                    # 尝试终止我们启动的进程
                    process.terminate()
                    return False
            elif process.poll() is not None:
                # 如果我们启动的 Popen 进程已经退出，说明 scheduler_loop.py 启动失败
                stdout, stderr = process.communicate()
                error_message = stderr.decode('utf-8') if stderr else f"进程退出码: {process.returncode}"
                print(f"定时任务调度器启动失败: {error_message}")
                logger.error(f"启动 scheduler_loop.py 失败: {error_message}")
                return False
            else:
                # 进程仍在运行，但 PID 文件未找到或 PID 无效
                logger.warning(f"调度器进程 (PID: {process.pid}) 可能正在运行，但无法通过 PID 文件确认。请检查日志。")
                # 我们可以选择返回 True 并假设它在运行，或者返回 False 表示不确定
                # 暂时返回 True，但提示用户检查
                print(f"警告: 调度器进程 (PID: {process.pid}) 已启动，但状态确认不完整。请检查日志。")
                return True # Or False depending on desired strictness

        except Exception as e:
            error_msg = f"启动定时任务调度器 (scheduler_loop.py) 时出错: {e}"
            print(error_msg)
            logger.error(error_msg)
            log.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {error_msg}\n")
            return False


def stop_scheduler():
    """停止定时任务调度器 (scheduler_loop.py)"""
    # 停止逻辑保持不变，因为它依赖于 SCHEDULER_PID_FILE，
    # 而 scheduler_loop.py 负责创建和删除这个文件。
    pid = read_pid(SCHEDULER_PID_FILE)
    if pid and is_process_running(pid):
        print("正在停止定时任务调度器...") # Add print statement here
        stopped = stop_service("定时任务调度器", SCHEDULER_PID_FILE)
        if stopped:
            print("定时任务调度器已停止")
        else:
            print("定时任务调度器停止操作可能未完全成功，请检查进程")
        return stopped
    else:
        print("定时任务调度器未运行或无法找到 PID 文件")
        # Ensure PID file is removed if process is not running but file exists
        if os.path.exists(SCHEDULER_PID_FILE):
            try:
                os.remove(SCHEDULER_PID_FILE)
                logger.warning(f"调度器未运行，但 PID 文件存在，已移除: {SCHEDULER_PID_FILE}")
            except OSError as e:
                 logger.error(f"尝试移除无效调度器的 PID 文件时出错: {e}")
        return True # Consider it stopped if not running


def start(args=None):
    """启动系统的本地组件 (Cleaner & Scheduler)"""
    print("正在启动本地服务...")

    # 检查依赖 (不再检查 Flask)
    # ...

    # # 不再启动API服务
    # success_api = start_api_service() # 注释掉

    # 启动数据清洗服务
    success_cleaner = start_cleaner_service()

    # 启动爬虫定时任务
    success_scheduler = start_scheduler()

    # 显示启动结果摘要
    print("\n===== 本地服务启动结果汇总 =====")
    # print(f"API服务: ...") # 移除 API 状态显示
    print(f"数据清洗服务: {'成功启动 (PID: ' + str(read_pid(CLEANER_PID_FILE)) + ')' if success_cleaner else '启动失败 ✗ - 请检查logs/cleaner.log获取更多信息'}")
    print(f"爬虫定时任务: {'成功启动 (PID: ' + str(read_pid(SCHEDULER_PID_FILE)) + ')' if success_scheduler else '启动失败 ✗ - 请检查logs/scheduler.log获取更多信息'}")

    if not (success_cleaner and success_scheduler): # 移除 success_api
        print("\n警告: 部分本地服务未能成功启动,请检查日志文件了解详情")
        return 1

    print("\n本地服务启动完成! 使用 'python main.py status' 查看状态")
    return 0

def stop(args=None):
    """停止系统的本地组件 (Cleaner & Scheduler)"""
    print("正在停止本地服务...")

    # # 不再停止API服务
    # stop_api_service() # 注释掉

    # 停止数据清洗服务
    stop_cleaner_service()

    # 停止爬虫定时任务
    stop_scheduler()

    print("\n本地服务已尝试停止")
    return 0

def main():
    """主函数,解析命令行参数并执行相应操作"""
    parser = argparse.ArgumentParser(description="AI资讯聚合系统 - 后台服务控制程序")
    # 更新描述和选项，移除 API 相关
    parser.add_argument('action', choices=['start', 'stop', 'restart', 'status', 'crawler', 'cleaner', 'scheduler'],
                        help='要执行的操作: start启动所有本地服务 (cleaner, scheduler), stop停止所有本地服务, ' +
                             'restart重启所有本地服务, status查看本地服务状态, crawler运行所有爬虫一次, ' +
                             'cleaner仅启动清洗服务, scheduler仅启动调度器')
    
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    
    args = parser.parse_args()
    
    if args.action == 'start':
        # start_all() 现在只启动本地服务
        if not start_all():
            sys.exit(1)
    elif args.action == 'stop':
        # stop_all() 现在只停止本地服务
        stop_all()
    elif args.action == 'restart':
        stop_all()
        time.sleep(2)
        if not start_all():
            sys.exit(1)
    elif args.action == 'status':
        # status() 现在只显示本地服务状态
        status()
    elif args.action == 'crawler':
        # ... (crawler 逻辑不变，假设其下有代码或 pass)
        # 如果这里也被注释了，也需要加 pass
        # 检查依赖
        if not check_dependencies():
             print("启动爬虫失败: 系统缺少必要的文件或目录")
             sys.exit(1)
        run_all_crawlers()
    elif args.action == 'cleaner':
        # ... (cleaner 逻辑不变，假设其下有代码或 pass)
        # 如果这里也被注释了，也需要加 pass
        cleaner_script = os.path.join(CLEAN_DIR, 'cleandata.py')
        if os.path.isfile(cleaner_script):
             start_cleaner_service()
             print(f"数据清洗服务已启动 (PID: {read_pid(CLEANER_PID_FILE)})\")")
        else:
             print(f"错误: 找不到 {cleaner_script} 文件")
             sys.exit(1)
    elif args.action == 'scheduler':
        # ... (scheduler 逻辑不变，假设其下有代码或 pass)
        # 如果这里也被注释了，也需要加 pass
        if not discover_crawlers():
             print("错误: 未发现任何爬虫脚本")
             sys.exit(1)
        start_scheduler()
        print("爬虫定时任务已启动, 配置见 schedule_config.json") # 更新提示

# 确保这部分在顶层，没有额外缩进
if __name__ == "__main__":
    main() 