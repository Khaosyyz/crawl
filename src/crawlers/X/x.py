#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

# 将项目根目录添加到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import time
import json
import pickle
import random
import re
import string
import base64
import requests
import traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from datetime import datetime
import pytz
import os
from openai import OpenAI
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# 导入路径常量
from src.utils.paths import X_TEMP_DATA_PATH, DATA_DIR

# 常量定义
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# 获取 X 目录路径 - 修正为当前目录
X_DIR = os.path.dirname(os.path.abspath(__file__))
if not os.path.exists(X_DIR):
    os.makedirs(X_DIR)

# 无效账号文件路径
INVALID_ACCOUNTS_FILE = os.path.join(X_DIR, "x_invalid_account.txt")

# 多账号配置
ACCOUNTS = [
    {
        "username": "DraytonJou66802",
        "password": "w2dLpQX94pkIndqR",
        "two_factor_secret": "7GHWOCQWZZTM24IK"
    },
    {
        "username": "sexytbello",
        "password": "X2Y8puZApDEvPhJ6JNmJ",
        "two_factor_secret": "JWDF4XXGHTPVICEK"
    },
]

def load_invalid_accounts():
    """加载已知的无效账号列表"""
    invalid_accounts = set()
    if os.path.exists(INVALID_ACCOUNTS_FILE):
        with open(INVALID_ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                invalid_accounts.add(line.strip())
    return invalid_accounts


def mark_account_as_invalid(username):
    """将账号标记为无效"""
    with open(INVALID_ACCOUNTS_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{username}\n")
    print(f"账号 {username} 已被标记为无效，将从可用账号列表中移除")


def get_valid_accounts():
    """获取有效的账号列表，排除已知的无效账号"""
    invalid_usernames = load_invalid_accounts()
    valid_accounts = [account for account in ACCOUNTS if account["username"] not in invalid_usernames]
    
    if not valid_accounts:
        print("警告: 所有账号均已标记为无效，将重置无效账号列表")
        # 如果所有账号都无效，则清空无效账号列表，重新尝试所有账号
        with open(INVALID_ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
            f.write("")
        return ACCOUNTS
    
    return valid_accounts

class RateLimitException(Exception):
    """自定义异常，表示达到速率限制"""
    pass

class XCrawler:
    def __init__(self):
        # 获取有效账号列表
        valid_accounts = get_valid_accounts()
        
        if not valid_accounts:
            raise Exception("没有可用账号，爬虫无法启动")
            
        # 随机选择一个有效账号
        self.selected_account = random.choice(valid_accounts)
        self.USERNAME = self.selected_account["username"]
        self.PASSWORD = self.selected_account["password"]
        self.TWO_FACTOR_SECRET = self.selected_account["two_factor_secret"]
        
        # 登录尝试次数
        self.login_attempts = 0
        self.MAX_LOGIN_ATTEMPTS = 2

        # 为选中的账号设置固定的用户数据目录，不再使用随机UUID
        # 这确保了每次运行可以重用之前的cookie
        self.USER_DATA_DIR = os.path.join(os.path.expanduser("~"), f"twitter_profile_{self.USERNAME}")
        
        # 创建cookies目录
        self.COOKIES_DIR = os.path.join(X_DIR, "cookies")
        if not os.path.exists(self.COOKIES_DIR):
            os.makedirs(self.COOKIES_DIR)
        
        # 账号专属cookie文件
        self.COOKIES_FILE = os.path.join(self.COOKIES_DIR, f"{self.USERNAME}_cookies.json")
        
        # 记录最后一次cookie更新时间的文件
        self.COOKIE_TIME_FILE = os.path.join(self.COOKIES_DIR, f"{self.USERNAME}_last_update.txt")
        
        # 移除删除其他账号cookie的逻辑，保留所有账号的cookie文件
        print(f"使用账号 {self.USERNAME} 的cookie文件: {self.COOKIES_FILE}")
        
        
        # 确保用户数据目录存在
        if not os.path.exists(self.USER_DATA_DIR):
            os.makedirs(self.USER_DATA_DIR)
            print(f"创建新的用户数据目录: {self.USER_DATA_DIR}")
        else:
            print(f"使用现有用户数据目录: {self.USER_DATA_DIR}")
        
        # 初始化driver
        self.driver = self.setup_driver()
        print(f"使用账号 {self.USERNAME} 进行操作")

        # 添加关闭标志，用于协调超时检测和账号切换
        self.is_shutting_down = False

    def setup_driver(self):
        """初始化并配置WebDriver - 使用高级无头模式欺骗技术"""
        options = webdriver.ChromeOptions()
        
        # 用户数据目录设置
        options.add_argument(f"--user-data-dir={self.USER_DATA_DIR}")
        options.add_argument("--profile-directory=Default")
        
        # 基础稳定性参数
        options.add_argument("--no-sandbox") 
        options.add_argument("--disable-dev-shm-usage")
        
        # 无头模式配置 - 使用最新的方法
        options.add_argument("--headless=new")
        
        # 窗口大小和物理显示配置
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")
        
        # 禁用自动化标志
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        
        # 模拟真实用户的配置
        options.add_experimental_option("prefs", {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.notifications": 2,
            # 禁用图片可提高速度，但可能增加检测风险
            # "profile.managed_default_content_settings.images": 2
        })
        
        # 设置高质量用户代理
        user_agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        ]
        selected_user_agent = random.choice(user_agents)
        options.add_argument(f"--user-agent={selected_user_agent}")
        
        # 语言和地区设置
        options.add_argument("--lang=zh-CN,zh,en-US,en")
        options.add_argument("--accept-lang=zh-CN,zh,en-US,en")
        
        # 启用性能日志记录
        options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        
        # 使用本地已安装的ChromeDriver
        service = Service()
        
        # 清理可能残留的Chrome进程
        self._clean_chrome_processes()
        
        # 创建Chrome实例，添加重试机制
        for attempt in range(3):
            try:
                print(f"尝试创建Chrome实例，第{attempt+1}次...")
                try:
                    # 首先尝试使用指定的ChromeDriver路径
                    driver = webdriver.Chrome(service=service, options=options)
                    print("Chrome实例创建成功")
                except Exception as e:
                    # 如果失败，尝试使用系统默认的ChromeDriver
                    print(f"使用指定ChromeDriver失败: {e}")
                    print("尝试使用系统默认ChromeDriver...")
                    driver = webdriver.Chrome(options=options)
                    print("Chrome实例创建成功 (使用系统默认ChromeDriver)")
                
                try:
                    # 高级CDP命令 - 必须在浏览器启动后执行
                    
                    # 1. 修改navigator属性 - 更全面的方法
                    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                        "source": """
                        // 覆盖webdriver属性
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => false,
                            configurable: true
                        });
                        
                        // 创建假的navigator.plugins - 模拟真实浏览器
                        const makePluginsLookReal = () => {
                            const plugins = [
                                {description: "Portable Document Format", filename: "internal-pdf-viewer", name: "PDF Viewer", MimeTypes: []},
                                {description: "Chrome PDF Viewer", filename: "internal-pdf-viewer", name: "Chrome PDF Viewer", MimeTypes: []},
                                {description: "Native Client", filename: "internal-nacl-plugin", name: "Native Client", MimeTypes: []}
                            ];
                            
                            // 创建模拟的插件和MIME类型
                            plugins.forEach(plugin => {
                                plugin.MimeTypes.forEach(mime => {
                                    navigator.mimeTypes[mime.type] = {
                                        type: mime.type,
                                        suffixes: mime.suffixes,
                                        description: mime.description,
                                        enabledPlugin: plugin
                                    };
                                });
                            });
                            
                            // 修改插件长度属性
                            Object.defineProperty(navigator, 'plugins', {
                                get: () => {
                                    const pluginArray = Array.from(plugins);
                                    // 添加模拟的属性
                                    pluginArray.item = index => pluginArray[index];
                                    pluginArray.namedItem = name => pluginArray.find(plugin => plugin.name === name);
                                    pluginArray.refresh = () => {};
                                    // 设置长度
                                    Object.defineProperty(pluginArray, 'length', {
                                        get: () => plugins.length
                                    });
                                    return pluginArray;
                                }
                            });
                        };
                        
                        // 应用插件修改
                        makePluginsLookReal();
                        
                        // 修改语言特征 - 基于用户代理
                        Object.defineProperty(navigator, 'languages', {
                            get: () => ['zh-CN', 'zh', 'en-US', 'en']
                        });
                        
                        // 随机化硬件并发特征
                        Object.defineProperty(navigator, 'hardwareConcurrency', {
                            get: () => Math.floor(Math.random() * 8) + 4 // 4-12核
                        });
                        
                        // 随机化设备内存特征 
                        Object.defineProperty(navigator, 'deviceMemory', {
                            get: () => Math.floor(Math.random() * 8) + 4 // 4-12GB
                        });
                        
                        // 修改连接类型特征
                        Object.defineProperty(navigator, 'connection', {
                            get: () => ({
                                rtt: Math.floor(Math.random() * 100) + 50,
                                downlink: Math.floor(Math.random() * 10) + 5,
                                effectiveType: '4g'
                            })
                        });
                        
                        // 修改Headless标记
                        const originalUserAgent = navigator.userAgent;
                        Object.defineProperty(navigator, 'userAgent', {
                            get: () => originalUserAgent.replace('Headless', '')
                        });
                        
                        // 模拟完整的chrome运行时
                        if (!window.chrome) {
                            window.chrome = {};
                        }
                        
                        const createFakeChrome = () => {
                            return {
                                app: {
                                    isInstalled: false,
                                    InstallState: {
                                        DISABLED: 'disabled',
                                        INSTALLED: 'installed',
                                        NOT_INSTALLED: 'not_installed'
                                    },
                                    RunningState: {
                                        CANNOT_RUN: 'cannot_run',
                                        READY_TO_RUN: 'ready_to_run', 
                                        RUNNING: 'running'
                                    }
                                },
                                runtime: {
                                    OnInstalledReason: {
                                        CHROME_UPDATE: 'chrome_update',
                                        INSTALL: 'install',
                                        SHARED_MODULE_UPDATE: 'shared_module_update',
                                        UPDATE: 'update'
                                    },
                                    OnRestartRequiredReason: {
                                        APP_UPDATE: 'app_update',
                                        OS_UPDATE: 'os_update',
                                        PERIODIC: 'periodic'
                                    },
                                    PlatformArch: {
                                        ARM: 'arm',
                                        ARM64: 'arm64',
                                        MIPS: 'mips',
                                        MIPS64: 'mips64',
                                        X86_32: 'x86-32',
                                        X86_64: 'x86-64'
                                    },
                                    PlatformNaclArch: {
                                        ARM: 'arm',
                                        MIPS: 'mips',
                                        MIPS64: 'mips64',
                                        X86_32: 'x86-32',
                                        X86_64: 'x86-64'
                                    },
                                    PlatformOs: {
                                        ANDROID: 'android',
                                        CROS: 'cros',
                                        LINUX: 'linux',
                                        MAC: 'mac',
                                        OPENBSD: 'openbsd',
                                        WIN: 'win'
                                    },
                                    RequestUpdateCheckStatus: {
                                        NO_UPDATE: 'no_update',
                                        THROTTLED: 'throttled',
                                        UPDATE_AVAILABLE: 'update_available'
                                    },
                                    connect: function(extensionId, connectInfo) {},
                                    sendMessage: function(extensionId, message, options, responseCallback) {},
                                    getManifest: function() { return {}; }
                                }
                            };
                        };
                        
                        // 应用模拟的Chrome对象
                        Object.assign(window.chrome, createFakeChrome());
                        
                        // 模拟CSS媒体查询以绕过无头检测
                        // 无头浏览器返回错误的颜色深度
                        Object.defineProperty(screen, 'colorDepth', {
                            get: () => 24
                        });
                        
                        // 处理打印检测
                        const originalMatchMedia = window.matchMedia;
                        window.matchMedia = query => {
                            if (query.includes('print')) {
                                return {
                                    matches: false,
                                    media: query,
                                    onchange: null,
                                    addListener: function() {},
                                    removeListener: function() {},
                                    addEventListener: function() {},
                                    removeEventListener: function() {},
                                    dispatchEvent: function() {}
                                };
                            }
                            return originalMatchMedia(query);
                        };
                        
                        // 模拟权限API
                        const originalQuery = window.navigator.permissions.query;
                        window.navigator.permissions.query = parameters => (
                            parameters.name === 'notifications' ?
                            Promise.resolve({ state: Notification.permission, onchange: null }) :
                            originalQuery(parameters)
                        );
                        
                        // WebGL指纹混淆
                        const getParameterProxies = {};
                        
                        // Hook WebGL to prevent fingerprinting
                        const hookWebGL = () => {
                            // Original getParameter functions for both WebGL and WebGL2
                            const addProxy = (ctx, webGlType) => {
                                if (!getParameterProxies[webGlType]) {
                                    const proto = ctx.constructor.prototype;
                                    if (!proto) return;
                                    
                                    // 保存原始方法
                                    const originalGetParameter = proto.getParameter;
                                    
                                    // 创建代理
                                    proto.getParameter = function(parameter) {
                                        // 特殊处理某些参数，以避免指纹识别
                                        if (parameter === ctx.VENDOR) {
                                            return 'Google Inc. (NVIDIA)';
                                        } else if (parameter === ctx.RENDERER) {
                                            return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 2080 Direct3D11 vs_5_0 ps_5_0)';
                                        } else if (parameter === ctx.VERSION) {
                                            return 'WebGL 2.0 (OpenGL ES 3.0 Chromium)';
                                        } else if (parameter === ctx.SHADING_LANGUAGE_VERSION) {
                                            return 'WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)';
                                        }
                                        
                                        // 对于其他参数，使用原始方法
                                        return originalGetParameter.apply(this, arguments);
                                    };
                                    
                                    getParameterProxies[webGlType] = true;
                                }
                            };
                            
                            // 替换getContext方法来拦截WebGL上下文创建
                            HTMLCanvasElement.prototype.getContext = (function(originalGetContext) {
                                return function(type, attributes) {
                                    const ctx = originalGetContext.apply(this, arguments);
                                    
                                    if (ctx && (type.includes('webgl') || type.includes('experimental-webgl'))) {
                                        // 为两种WebGL类型添加代理
                                        addProxy(ctx, type);
                                    }
                                    
                                    return ctx;
                                };
                            })(HTMLCanvasElement.prototype.getContext);
                        };
                        
                        // 应用WebGL钩子
                        hookWebGL();
                        
                        // 随机生成Canvas指纹
                        const oldToDataURL = HTMLCanvasElement.prototype.toDataURL;
                        HTMLCanvasElement.prototype.toDataURL = function(type) {
                            if (type === 'image/png' && this.width === 16 && this.height === 16) {
                                // 很可能是指纹检测，返回随机值
                                const randomValues = new Uint8ClampedArray(64);
                                for(let i = 0; i < 64; i++){
                                    randomValues[i] = Math.floor(Math.random() * 256);
                                }
                                return 'data:image/png;base64,' + btoa(String.fromCharCode.apply(null, randomValues));
                            }
                            return oldToDataURL.apply(this, arguments);
                        };
                        
                        // 定义"已修补"变量，防止多次注入
                        window._patchedWebdriver = true;
                        """
                    })
                    
                    # 2. 修改Document属性以绕过检测
                    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                        "source": """
                        // 隐藏自动化控制痕迹
                        Object.defineProperty(document, 'webdriver', {
                            get: () => false,
                            configurable: true
                        });
                        
                        // 处理自动化相关的DOM痕迹
                        if (document.documentElement) {
                            document.documentElement.setAttribute('webdriver', false);
                        }
                        """
                    })
                    
                    # 3. 修改键盘和鼠标行为以模拟真实用户
                    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                        "source": """
                        // 模拟更真实的鼠标行为
                        const randomizeTouchSupport = () => {
                            // 随机决定是否支持触摸
                            const hasTouch = Math.random() > 0.2; // 80% 概率支持触摸
                            
                            if (!hasTouch) {
                                // 移除触摸支持
                                delete navigator.maxTouchPoints;
                                Object.defineProperty(navigator, 'maxTouchPoints', {
                                    get: () => 0
                                });
                                
                                delete navigator.msMaxTouchPoints; 
                                Object.defineProperty(navigator, 'msMaxTouchPoints', {
                                    get: () => 0
                                });
                                
                                // 标记为不支持触摸
                                window.TouchEvent = undefined;
                                window.ontouchstart = undefined;
                            } else {
                                // 添加随机触摸点
                                const touchPoints = Math.floor(Math.random() * 5) + 1;
                                Object.defineProperty(navigator, 'maxTouchPoints', {
                                    get: () => touchPoints
                                });
                            }
                        };
                        
                        // 应用触摸支持随机化
                        randomizeTouchSupport();
                        """
                    })
                    
                    # 4. 覆盖时间API以避免基于时间的模式检测
                    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                        "source": """
                        // 添加微小的随机延迟来避免检测到过于完美的时间模式
                        const originalPerformance = window.performance;
                        const originalNow = window.performance.now;
                        let lastNow = 0;
                        
                        window.performance.now = function() {
                            const calculatedNow = originalNow.call(originalPerformance);
                            const noise = 0.01 + Math.random() * 0.4; // 很小的随机波动
                            lastNow = calculatedNow + noise;
                            return lastNow;
                        };
                        """
                    })
                    
                    # 5. 设置Network用户代理
                    driver.execute_cdp_cmd("Network.setUserAgentOverride", {
                        "userAgent": selected_user_agent,
                        "acceptLanguage": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                        "platform": "macOS" if "Macintosh" in selected_user_agent else "Windows"
                    })
                    
                except Exception as e:
                    print(f"应用CDP命令时出错: {e}")
                
                # 增加初始页面交互以模拟真实用户行为
                try:
                    # 先导航到一个真实页面
                    driver.get("https://twitter.com")
                    time.sleep(3)
                    
                    # 模拟随机滚动行为
                    driver.execute_script("""
                    // 模拟随机滚动
                    const randomScroll = () => {
                        const maxY = Math.max(document.body.scrollHeight, 1000);
                        const randomY = Math.floor(Math.random() * maxY / 2);
                        window.scrollTo(0, randomY);
                    };
                    
                    // 执行随机滚动
                    randomScroll();
                    """)
                    
                    time.sleep(1)
                    
                except Exception as e:
                    print(f"初始页面交互时出错: {e}")
                
                return driver
                
            except Exception as e:
                print(f"创建Chrome实例失败，错误: {e}")
                if attempt < 2:  # 除了最后一次尝试，其他都重试
                    print(f"等待5秒后重试...")
                    time.sleep(5)
                    # 再次尝试清理进程
                    self._clean_chrome_processes()
                else:
                    raise  # 重试多次后仍然失败，向上抛出异常
                    
    def _clean_chrome_processes(self):
        """清理可能残留的Chrome进程和锁定文件"""
        try:
            import subprocess
            import platform
            import signal
            
            print(f"尝试清理可能占用用户数据目录的Chrome进程: {self.USER_DATA_DIR}")
            
            # 在Mac上使用适当的方法查找和终止进程
            if platform.system() == "Darwin":  # macOS
                # 先查找可能的Chrome进程
                ps_cmd = ["ps", "aux"]
                grep_cmd = ["grep", self.USER_DATA_DIR]
                ps_process = subprocess.Popen(ps_cmd, stdout=subprocess.PIPE)
                grep_process = subprocess.Popen(grep_cmd, stdin=ps_process.stdout, stdout=subprocess.PIPE)
                ps_process.stdout.close()
                output, _ = grep_process.communicate()
                
                # 从输出中提取PID并终止进程
                for line in output.decode('utf-8').split('\n'):
                    if self.USER_DATA_DIR in line and 'grep' not in line:
                        try:
                            # 提取PID (通常是第二列)
                            parts = line.strip().split()
                            if len(parts) > 1:
                                pid = int(parts[1])
                                print(f"终止Chrome进程: {pid}")
                                os.kill(pid, signal.SIGTERM)
                        except Exception as e:
                            print(f"终止进程时出错: {e}")
            else:  # 其他系统
                print("不支持的操作系统，跳过Chrome进程清理")
                
            # 清理锁定文件
            self._clean_lock_files()
                            
            # 等待系统释放资源
            time.sleep(2)
            
        except Exception as e:
            print(f"清理Chrome进程时出错: {e}")
    
    def _clean_lock_files(self):
        """清理浏览器锁定文件"""
        if os.path.exists(self.USER_DATA_DIR):
            # 只移除锁定文件，保留其他文件以维持cookie等数据
            lock_files = [
                os.path.join(self.USER_DATA_DIR, "SingletonLock"),
                os.path.join(self.USER_DATA_DIR, "SingletonCookie"),
                os.path.join(self.USER_DATA_DIR, "Default", "Cookies-journal")
            ]
            for lock_file in lock_files:
                if os.path.exists(lock_file):
                    try:
                        os.remove(lock_file)
                        print(f"移除锁定文件: {lock_file}")
                    except Exception as e:
                        print(f"移除锁定文件时出错: {e}")
        else:
            print(f"用户数据目录不存在: {self.USER_DATA_DIR}")

    def _is_browser_alive(self):
        """检查浏览器是否仍然活跃"""
        try:
            # 尝试获取当前URL，如果浏览器已关闭会抛出异常
            current_url = self.driver.current_url
            return True
        except:
            return False
            
    def _recreate_browser(self):
        """重新创建浏览器实例"""
        try:
            print("尝试重新创建浏览器...")
            # 确保旧浏览器已关闭
            try:
                if self.driver:
                    self.driver.quit()
            except:
                pass
                
            # 重新初始化driver
            self.driver = self.setup_driver()
            
            if not self.driver:
                print("重新创建浏览器失败")
                return False
                
            print("重新创建浏览器成功")
            
            # 重新登录
            if not self.login_xcom():
                print("重新登录失败")
                return False
                
            print("重新登录成功")
            return True
        except Exception as e:
            print(f"重新创建浏览器出错: {e}")
            return False

    def _update_cookie_timestamp(self):
        """更新cookie时间戳"""
        try:
            # 检查浏览器是否已关闭
            if not self._is_browser_alive():
                print("浏览器已关闭，无法更新cookie时间戳")
                return False
                
            # 获取当前时间
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 保存时间戳到文件
            with open(self.COOKIE_TIME_FILE, 'w', encoding='utf-8') as f:
                f.write(current_time)
            
            print(f"已更新cookie时间戳: {current_time}")
            
            # 保存当前的cookies
            return self._save_cookies()
        except Exception as e:
            print(f"更新cookie时间戳出错: {e}")
            return False

    def _save_cookies(self):
        """保存当前浏览器的cookies到文件"""
        try:
            # 检查浏览器是否已关闭
            if not self._is_browser_alive():
                print("浏览器已关闭，无法保存cookies")
                return False
                
            # 获取当前的cookies
            cookies = self.driver.get_cookies()
            
            # 创建一个干净的cookie字典，按名称保存，确保每个cookie只有最新的版本
            cookie_dict = {}
            for cookie in cookies:
                if 'name' in cookie:
                    cookie_dict[cookie['name']] = cookie
            
            # 将字典值转换回列表
            clean_cookies = list(cookie_dict.values())
            
            # 创建一个单一的合并cookie对象，包含所有cookie信息
            merged_cookie = {
                "session_data": {
                    "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "username": self.USERNAME,
                    "cookies": clean_cookies
                }
            }
            
            # 保存到文件 - 每次都覆盖旧文件
            with open(self.COOKIES_FILE, 'w', encoding='utf-8') as f:
                json.dump(merged_cookie, f, ensure_ascii=False, indent=2)
            
            print(f"已保存 {len(clean_cookies)} 个cookies到文件: {self.COOKIES_FILE}")
            return True
        except Exception as e:
            print(f"保存cookies出错: {e}")
            return False

    def _load_cookies(self):
        """从文件加载cookies到浏览器"""
        if not os.path.exists(self.COOKIES_FILE):
            print(f"未找到cookie文件: {self.COOKIES_FILE}")
            return False
            
        try:
            # 确保浏览器处于活跃状态
            if not self._is_browser_alive():
                print("浏览器未处于活跃状态，重新创建浏览器...")
                if not self._recreate_browser():
                    print("重新创建浏览器失败，无法加载cookies")
                    return False
                    
            # 先访问Twitter域名，以便能添加cookies
            self.driver.get("https://twitter.com")
            time.sleep(1)
            
            # 从文件加载cookies
            with open(self.COOKIES_FILE, 'r', encoding='utf-8') as f:
                cookie_data = json.load(f)
            
            # 处理新格式的cookie
            if isinstance(cookie_data, dict) and "session_data" in cookie_data:
                cookies = cookie_data["session_data"]["cookies"]
                print(f"正在加载新格式的cookie，保存时间: {cookie_data['session_data']['timestamp']}")
            else:
                # 兼容旧格式
                cookies = cookie_data
                print("正在加载旧格式的cookie")
            
            # 先清除所有现有cookies
            self.driver.delete_all_cookies()
            
            # 添加cookies到浏览器
            for cookie in cookies:
                try:
                    # 有些cookie可能不能直接添加，需要处理异常
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    print(f"添加cookie '{cookie.get('name', 'unknown')}' 时出错: {str(e)[:100]}")
                    pass
            
            print(f"已加载 {len(cookies)} 个cookies")
            return True
        except Exception as e:
            print(f"加载cookies出错: {e}")
            # 如果加载失败且是由于会话ID无效，尝试重新创建浏览器
            if "invalid session id" in str(e).lower():
                print("检测到无效会话ID错误，尝试重新创建浏览器...")
                if self._recreate_browser():
                    print("浏览器重新创建成功，尝试重新加载cookies")
                    # 递归调用但要防止无限递归
                    return self._load_cookies()
            return False

    def _refresh_cookie(self):
        """
        刷新cookie的有效期
        通过访问一些不敏感的页面来保持cookie活跃
        """
        try:
            print("正在刷新cookie...")
            # 访问首页
            self.driver.get("https://twitter.com/home")
            time.sleep(2)
            
            # 访问探索页面
            self.driver.get("https://twitter.com/explore")
            time.sleep(2)
            
            # 更新cookie时间戳
            self._update_cookie_timestamp()
            print("cookie刷新完成")
        except Exception as e:
            print(f"刷新cookie时出错: {e}")

    def _safe_update_cookie(self):
        """安全地更新cookie，处理浏览器可能已关闭的情况"""
        try:
            if self._is_browser_alive():
                self._update_cookie_timestamp()
            else:
                print("浏览器已关闭，无法更新cookie")
        except Exception as e:
            print(f"安全更新cookie时出错: {e}")

    def check_login_status(self):
        """检查是否已登录推特"""
        try:
            self.driver.get("https://x.com/home")
            time.sleep(3)

            # 通过URL判断
            if "x.com/home" in self.driver.current_url or "twitter.com/home" in self.driver.current_url:
                print(f"账号 {self.USERNAME} 已检测到登录状态，无需重新登录")
                # 记录上次验证成功的时间
                self._update_cookie_timestamp()
                return True

            # 通过登录入口判断
            login_elements = self.driver.find_elements(By.XPATH, '//a[@href="/login"] | //form[@action="/sessions"]')
            if login_elements:
                print(f"账号 {self.USERNAME} 发现登录入口，当前未登录")
                return False

            # 通过导航元素判断
            nav_elements = self.driver.find_elements(By.XPATH,
                                                    '//a[contains(@href, "/notifications") or contains(@href, "/messages")]')
            if nav_elements:
                print(f"账号 {self.USERNAME} 检测到已登录的导航元素")
                # 记录上次验证成功的时间
                self._update_cookie_timestamp()
                return True

            print(f"账号 {self.USERNAME} 登录状态不明确，将执行完整登录流程")
            return False
        except Exception as e:
            print(f"检查登录状态时出错: {e}")
            # 如果是会话无效错误，尝试重新创建浏览器
            if "invalid session id" in str(e).lower():
                print("检测到无效会话ID错误，尝试重新创建浏览器...")
                if self._recreate_browser():
                    print("浏览器重新创建成功，重新检查登录状态")
                    return self.check_login_status()
            return False

    def handle_2fa(self):
        """处理Twitter的两因素认证"""
        try:
            main_window = self.driver.current_window_handle

            # 打开2FA.live获取验证码
            print("打开2FA.live获取验证码...")
            self.driver.execute_script("window.open('');")
            self.driver.switch_to.window(self.driver.window_handles[1])
            self.driver.get("https://2fa.live")
            time.sleep(3)

            # 输入密钥
            input_box = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, "listToken"))
            )
            input_box.clear()
            input_box.send_keys(self.TWO_FACTOR_SECRET)

            # 获取验证码
            submit_button = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.ID, "submit"))
            )
            submit_button.click()
            time.sleep(3)

            # 尝试从网络响应中提取验证码
            token = None
            logs = self.driver.get_log('performance')
            for log in logs:
                try:
                    message = json.loads(log['message'])['message']
                    if message['method'] == 'Network.responseReceived':
                        response = message['params']['response']
                        if 'url' in response and self.TWO_FACTOR_SECRET in response['url']:
                            request_id = message['params']['requestId']
                            response_body = self.driver.execute_cdp_cmd('Network.getResponseBody',
                                                                        {'requestId': request_id})
                            if 'body' in response_body:
                                data = json.loads(response_body['body'])
                                token = data['token']
                                break
                except:
                    continue

            # 如果网络提取失败，尝试从页面元素获取
            if not token:
                try:
                    token_elements = self.driver.find_elements(By.XPATH,
                                                              '//*[contains(@class, "token") or contains(@id, "token")]')
                    for elem in token_elements:
                        text = elem.text.strip()
                        if text and len(text) >= 6 and text.isdigit():
                            token = text
                            break
                except:
                    pass

            if not token:
                raise ValueError("无法提取2FA验证码")

            # 返回主窗口输入验证码
            self.driver.switch_to.window(main_window)
            code_input = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.NAME, "text"))
            )
            code_input.clear()
            code_input.send_keys(token)

            # 提交验证码
            next_button = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, '//button[@data-testid="ocfEnterTextNextButton"]'))
            )
            next_button.click()
            time.sleep(5)

            # 关闭2FA标签页
            try:
                self.driver.switch_to.window(self.driver.window_handles[1])
                self.driver.close()
                self.driver.switch_to.window(main_window)
            except:
                self.driver.switch_to.window(main_window)

            print("2FA验证流程完成")
            return True
        except Exception as e:
            print(f"2FA验证过程出错: {e}")
            try:
                self.driver.switch_to.window(main_window)
            except:
                pass
            return False

    def login_xcom(self):
        """登录 X.com (Twitter)"""
        self.login_attempts += 1
        
        # 尝试加载保存的cookies
        if os.path.exists(self.COOKIES_FILE):
            print("尝试使用保存的cookies登录...")
            self._load_cookies()
            
        # 检查登录状态
        if self.check_login_status():
            return True

        print(f"开始为账号 {self.USERNAME} 执行完整登录流程...")
        
        try:
            self.driver.get("https://x.com/login")
            time.sleep(3)

            # 输入用户名
            username_input = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.NAME, "text"))
            )
            username_input.clear()
            username_input.send_keys(self.USERNAME)

            # 点击下一步
            next_button = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, '//button[.//text()[contains(., "下一步")]]'))
            )
            next_button.click()
            time.sleep(3)

            # 输入密码
            password_input = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.NAME, "password"))
            )
            password_input.clear()
            password_input.send_keys(self.PASSWORD)

            # 点击登录
            login_button = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, '//button[@data-testid="LoginForm_Login_Button"]'))
            )
            login_button.click()
            time.sleep(3)

            # 处理2FA
            print("正在执行2FA验证流程...")
            self.handle_2fa()

            # 验证登录成功
            success = False
            for _ in range(5):
                if "x.com/home" in self.driver.current_url:
                    success = True
                    break
                time.sleep(3)

            if success:
                print(f"账号 {self.USERNAME} 登录流程完成，已成功到达首页")
                # 登录成功，更新cookie信息
                self._update_cookie_timestamp()
                return True
            else:
                print(f"账号 {self.USERNAME} 登录可能未成功，当前URL: {self.driver.current_url}")
                # 检查是否出现人机验证或邮箱验证等异常情况
                if self.login_attempts >= self.MAX_LOGIN_ATTEMPTS:
                    print(f"账号 {self.USERNAME} 多次尝试登录失败，可能存在人机验证或邮箱验证")
                    mark_account_as_invalid(self.USERNAME)
                    self.close()
                    return False
                    
                return self.check_login_status()
        except Exception as e:
            print(f"账号 {self.USERNAME} 登录过程出现错误: {e}")
            if self.login_attempts >= self.MAX_LOGIN_ATTEMPTS:
                print(f"账号 {self.USERNAME} 多次尝试登录失败")
                mark_account_as_invalid(self.USERNAME)
                self.close()
            return False

    def extract_tweets_from_response(self, response_text):
        """从API响应中提取推文数据"""
        tweets = []
        try:
            data = json.loads(response_text)
            
            # 识别不同的API响应结构
            entries = None
            if 'data' in data:
                if 'home' in data['data']:
                    entries = data['data']['home']['home_timeline_urt']['instructions'][0]['entries']
                elif 'search_by_raw_query' in data['data']:
                    entries = data['data']['search_by_raw_query']['search_timeline']['timeline']['instructions'][0]['entries']
                elif 'user' in data['data']:
                    entries = data['data']['user']['result']['timeline_v2']['timeline']['instructions'][0]['entries']
                else:
                    return tweets

            if not entries:
                return tweets

            # 处理每条推文
            for entry in entries:
                try:
                    if 'content' in entry and 'itemContent' in entry['content']:
                        item = entry['content']['itemContent']
                        if 'tweet_results' in item and 'result' in item['tweet_results']:
                            result = item['tweet_results']['result']
                            if 'legacy' in result:
                                # 提取推文数据
                                legacy = result['legacy']
                                user_result = result['core']['user_results']['result']
                                user_legacy = user_result['legacy']

                                # 基本信息
                                tweet_id = legacy.get('id_str', '')
                                user_screen_name = user_legacy.get('screen_name', '')
                                text = legacy.get('full_text', '').replace('\n', ' ')

                                # 链接和统计数据
                                url = f"https://x.com/{user_screen_name}/status/{tweet_id}"
                                user_url = f"https://x.com/{user_screen_name}"
                                user_name = user_legacy.get('name', '')
                                followers_count = user_legacy.get('followers_count', 0)
                                favorite_count = legacy.get('favorite_count', 0)
                                retweet_count = legacy.get('retweet_count', 0)
                                reply_count = legacy.get('reply_count', 0)
                                created_at = legacy.get('created_at', '')

                                # 提取媒体URL
                                media_urls = []
                                if 'entities' in legacy and 'media' in legacy['entities']:
                                    for media in legacy['entities']['media']:
                                        if 'media_url_https' in media:
                                            media_urls.append(media['media_url_https'])

                                # 添加到结果列表
                                tweet_data = {
                                    'url': url,
                                    'user_url': user_url,
                                    'username': user_screen_name,
                                    'name': user_name,
                                    'text': text,
                                    'created_at': created_at,
                                    'retweet_count': retweet_count,
                                    'favorite_count': favorite_count,
                                    'reply_count': reply_count,
                                    'followers_count': followers_count,
                                    'media_urls': media_urls
                                }
                                
                                tweets.append(tweet_data)
                except Exception as e:
                    print(f"处理单条推文时出错: {e}")
                    continue
        except Exception as e:
            print(f"提取推文过程中出错: {e}")
        
        return tweets

    def crawl_posts(self):
        """
        爬取Twitter帖子 - 使用高效简洁的爬取方法
        从x1.py移植的高效爬取逻辑
        """
        posts = []
        
        # 检查浏览器状态
        if not self._is_browser_alive():
            print("浏览器已关闭，尝试重新创建")
            if not self._recreate_browser():
                print("无法重新创建浏览器，终止爬取")
                return posts
        
        # 访问搜索页面
        try:
            print("开始爬取推文...")
            url = "https://x.com/search?q=AI&src=typed_query"
            print(f"访问搜索页面: {url}")
            self.driver.get(url)
            time.sleep(7)  # 增加初始页面加载等待时间
            
            # 初始滚动以触发更多内容加载 - 使用更强的初始滚动
            print("执行初始页面滚动以激活内容加载...")
            self.driver.execute_script("""
                // 强制加载更多内容的初始滚动
                function triggerInitialLoad() {
                    // 先滚动到一定位置
                    window.scrollTo(0, 500);
                    
                    // 短暂延迟后再滚动回来，以触发加载
                    setTimeout(() => {
                        window.scrollTo(0, 400);
                        // 再滚动到更深的位置
                        setTimeout(() => {
                            window.scrollTo(0, 1000);
                        }, 300);
                    }, 500);
                }
                
                triggerInitialLoad();
            """)
            time.sleep(4)  # 增加初始滚动后的等待时间
        except Exception as e:
            print(f"访问搜索页面失败: {e}")
            return posts
        
        # 设置爬取参数
        seen_urls = set()
        max_scroll_attempts = 15  # 限制最大滚动次数为15次（从10次增加到15次）
        scroll_count = 0
        
        # 启用网络监控，用于后续获取API响应
        try:
            self.driver.execute_cdp_cmd('Network.enable', {})
            print("已启用网络监控")
        except Exception as e:
            print(f"启用网络监控失败: {e}")
        
        # 滚动页面直到收集足够的推文
        print(f"开始滚动页面收集推文，最大滚动次数: {max_scroll_attempts}")
        while len(posts) < 50 and scroll_count < max_scroll_attempts:
            try:
                # 滚动页面 - 修改为更激进的滚动模式以确保内容加载
                print(f"执行页面滚动 {scroll_count+1}/{max_scroll_attempts}")
                
                # 计算当前滚动高度
                current_height = self.driver.execute_script("return document.documentElement.scrollHeight")
                visible_height = self.driver.execute_script("return window.innerHeight")
                current_scroll_position = self.driver.execute_script("return window.scrollY")
                
                # 输出当前状态
                print(f"当前页面高度: {current_height}, 可视区域高度: {visible_height}, 当前滚动位置: {current_scroll_position}")
                
                # 使用更有效的滚动策略
                if scroll_count == 0:
                    # 第一次滚动，使用较大的滚动距离并进行多次小滚动
                    target_position = min(current_height - visible_height, current_scroll_position + 2000)
                    self.driver.execute_script(f"""
                        // 分步滚动以确保内容加载
                        let currentPos = {current_scroll_position};
                        let targetPos = {target_position};
                        let steps = 8;
                        let stepSize = (targetPos - currentPos) / steps;
                        
                        function doScroll(step) {{
                            if (step >= steps) return;
                            currentPos += stepSize;
                            window.scrollTo(0, currentPos);
                            setTimeout(() => doScroll(step + 1), 150);
                        }}
                        
                        doScroll(0);
                    """)
                else:
                    # 后续滚动，尝试滚动到底部
                    scroll_distance = min(2500, current_height - current_scroll_position - visible_height)
                    self.driver.execute_script(f"""
                        // 强力滚动到新内容
                        window.scrollBy(0, {scroll_distance});
                        // 轻微反弹以触发加载
                        setTimeout(() => window.scrollBy(0, -50), 400);
                        setTimeout(() => window.scrollBy(0, 50), 700);
                    """)
                
                scroll_count += 1
                
                # 延长等待时间以确保内容加载完成
                wait_time = 5 + (random.random() * 2)  # 5-7秒
                print(f"等待 {wait_time:.1f} 秒以确保内容加载...")
                time.sleep(wait_time)
                
                # 每次滚动后报告当前推文数量
                print(f"当前已收集 {len(posts)} 个推文")
                
                # 额外的激活动作 - 轻微的鼠标移动模拟
                if scroll_count > 1 and len(posts) < 20:
                    print("执行额外的页面激活动作...")
                    self.driver.execute_script("""
                        // 模拟鼠标移动和轻微的来回滚动
                        window.scrollBy(0, 30);
                        setTimeout(() => window.scrollBy(0, -30), 200);
                    """)
                    time.sleep(1)
                
            except Exception as e:
                print(f"滚动页面时出错: {e}")
                if not self._is_browser_alive():
                    print("浏览器已关闭，无法继续滚动")
                    break
                time.sleep(2)
                continue
            
            # 获取网络日志并处理 - 添加重试机制
            max_log_attempts = 3
            for attempt in range(max_log_attempts):
                try:
                    logs = self.driver.get_log('performance')
                    tweet_found_in_current_scroll = False
                    break
                except Exception as e:
                    print(f"获取性能日志尝试 {attempt+1}/{max_log_attempts} 失败: {e}")
                    if attempt < max_log_attempts - 1:
                        time.sleep(1)
                    else:
                        print("多次尝试获取性能日志失败，跳过此次滚动")
                        continue
            
            # 获取日志后等待一小段时间，确保所有响应都已处理
            time.sleep(1)
            
            # 处理日志以获取推文
            timeline_request_found = False
            for log in logs:
                if 'Network.responseReceived' not in log['message']:
                    continue
                
                try:
                    message = json.loads(log['message'])
                    if 'message' not in message or 'params' not in message['message']:
                        continue
                        
                    params = message['message']['params']
                    if 'response' not in params:
                        continue
                        
                    response = params['response']
                    
                    # 过滤相关的GraphQL响应 - 更详细的日志
                    response_url = response.get('url', '')
                    
                    # 检查是否是Timeline相关的请求
                    if 'graphql' in response_url and ('SearchTimeline' in response_url or 
                                                     'UserTweets' in response_url or
                                                     'HomeLatestTimeline' in response_url):
                        timeline_request_found = True
                        print(f"找到Timeline API响应: {response_url}")
                        
                        request_id = params['requestId']
                        try:
                            # 尝试获取响应体
                            body = self.driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                            if not body or 'body' not in body:
                                continue
                                
                            # 提取推文
                            tweets = self.extract_tweets_from_response(body['body'])
                            
                            if tweets:
                                tweet_found_in_current_scroll = True
                                print(f"此次提取到 {len(tweets)} 条推文")
                            
                            # 添加不重复的推文
                            new_tweets_count = 0
                            for tweet in tweets:
                                if tweet['url'] not in seen_urls and len(posts) < 50:
                                    seen_urls.add(tweet['url'])
                                    posts.append(tweet)
                                    new_tweets_count += 1
                            
                            if new_tweets_count > 0:
                                print(f"新增 {new_tweets_count} 条推文，当前总数: {len(posts)}")
                        except Exception as e:
                            print(f"处理响应体时出错: {e}")
                            continue
                except Exception as e:
                    print(f"处理日志条目时出错: {e}")
                    continue
            
            # 报告当前滚动的结果
            if not tweet_found_in_current_scroll:
                print(f"滚动 #{scroll_count} 未找到新推文")
                if not timeline_request_found:
                    print("警告: 未找到任何Timeline请求，可能需要调整滚动策略")
            
            # 检查是否达到目标
            if len(posts) >= 50:
                print("已收集足够的帖子，达到目标数量")
                break
        
        print(f"爬取完成，共收集到 {len(posts)} 个帖子")
        return posts[:50]  # 确保最多返回50个

    def format_posts_for_saving(self, posts):
        """将帖子格式化为保存格式"""
        formatted_posts = []
        for post in posts:
            # 处理创建时间 - Twitter的格式通常是 "Wed Oct 10 20:19:24 +0000 2018"
            created_at = post.get('created_at', '')
            formatted_date_time = ''
            
            # 尝试转换为标准格式 "YYYY-MM-DD HH:MM"
            if created_at:
                try:
                    # 解析Twitter时间格式
                    created_time = datetime.strptime(created_at, '%a %b %d %H:%M:%S +0000 %Y')
                    # 转换为北京时间
                    beijing_time = created_time.replace(tzinfo=pytz.UTC).astimezone(BEIJING_TZ)
                    # 格式化为标准格式
                    formatted_date_time = beijing_time.strftime('%Y-%m-%d %H:%M')
                except Exception as e:
                    print(f"时间格式转换出错: {e}")
                    formatted_date_time = datetime.now().strftime('%Y-%m-%d %H:%M')
            else:
                formatted_date_time = datetime.now().strftime('%Y-%m-%d %H:%M')
                
            # 构建格式化的文本，包含所有原始信息
            formatted_text = (f"{post['text']} [作者: {post.get('name', '')} "
                              f"(@{post['username']}), 时间: {formatted_date_time}, "
                              f"粉丝: {post.get('followers_count', 0)}, 点赞: {post.get('favorite_count', 0)}, "
                              f"转发: {post.get('retweet_count', 0)}]")
            
            # 确保URL中不包含特殊字符，并且有效
            source_url = post.get('url', '')
            if source_url:
                # 移除URL中可能导致问题的字符
                source_url = re.sub(r'[\n\r\t]', '', source_url)
            
            formatted_posts.append({
                'text': formatted_text,
                'raw': post,
                'date_time': formatted_date_time,  # 添加标准格式的日期时间
                'crawl_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'source': 'x.com',
                'source_url': source_url,  # 添加source_url字段，用于前端显示
                'formatted_for_readability': False  # 标记尚未经过cleandata格式化处理
            })
        return formatted_posts

    def save_to_temp_storage(self, posts):
        """将文章保存到临时存储文件"""
        if not posts:
            return

        try:
            # 使用paths.py中定义的常量路径
            temp_file_path = X_TEMP_DATA_PATH
            
            # 确保目录存在
            if not os.path.exists(os.path.dirname(temp_file_path)):
                os.makedirs(os.path.dirname(temp_file_path))
                
            # 读取现有数据
            existing_data = []
            if os.path.exists(temp_file_path) and os.path.getsize(temp_file_path) > 0:
                try:
                    with open(temp_file_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            existing_data = json.loads(content)
                except json.JSONDecodeError as e:
                    print(f"解析现有数据出错: {e}，将创建新文件")
            
            # 合并并保存数据
            combined_data = existing_data + posts
            with open(temp_file_path, 'w', encoding='utf-8') as f:
                json.dump(combined_data, f, ensure_ascii=False, indent=2)

            print(f"成功保存 {len(posts)} 篇文章到临时存储文件: {temp_file_path}")
        except Exception as e:
            print(f"保存到临时存储时出错: {e}")
            import traceback
            traceback.print_exc()

    def follow_blogger(self, blogger_url):
        """关注博主"""
        # 该方法不再需要，但为了保持代码结构，保留其签名，内部代码移除
        print("博主关注功能已被禁用")
        return False

    def close(self):
        """关闭浏览器并清理资源"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass

    def _get_existing_posts(self):
        """获取已存在的帖子数据，避免重复爬取"""
        try:
            # 使用paths.py中定义的常量路径
            temp_file_path = X_TEMP_DATA_PATH
            
            # 读取现有数据
            if os.path.exists(temp_file_path) and os.path.getsize(temp_file_path) > 0:
                try:
                    with open(temp_file_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            return json.loads(content)
                except json.JSONDecodeError as e:
                    print(f"解析现有数据出错: {e}")
            
            return []
        except Exception as e:
            print(f"获取已存在帖子时出错: {e}")
            return []
            
    def retry_with_another_account(self):
        """使用另一个账号重试"""
        # 检查是否正在关闭爬虫
        if self.is_shutting_down:
            print("爬虫正在关闭，跳过账号切换")
            return 0
            
        print("正在尝试使用另一个账号重试...")
        
        try:
            # 获取当前账号的用户名，以便排除
            current_username = self.USERNAME
            
            # 排除当前失败的账号
            mark_account_as_invalid(current_username)
            
            # 关闭当前浏览器
            self.close()
            
            # 获取其他可用账号
            valid_accounts = get_valid_accounts()
            if not valid_accounts:
                print("没有其他可用账号，无法继续")
                return 0
                
            # 过滤掉当前账号
            other_accounts = [acc for acc in valid_accounts if acc['username'] != current_username]
            if not other_accounts:
                print("没有其他可用账号，无法继续")
                return 0
                
            # 随机选择一个其他账号
            print(f"找到 {len(other_accounts)} 个其他可用账号")
            new_account = random.choice(other_accounts)
            print(f"选择账号 {new_account['username']} 继续爬取")
            
            # 创建新的爬虫实例并运行
            new_crawler = XCrawler()
            return new_crawler.run()
        except Exception as e:
            print(f"切换到另一个账号时出错: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def run(self):
        """
        运行爬虫的主函数
        
        爬虫流程：
        - 登录X.com
        - 搜索AI相关资讯
        - 滚动页面爬取50条推文
        - 将推文保存到临时文件 x_tempdata.json
        """
        try:
            # 登录X.com，会自动更新cookie
            if not self.login_xcom():
                print("登录失败，尝试切换账号")
                return self.retry_with_another_account()
            
            # 刷新cookie - 访问一些安全的页面来确保cookie活跃
            self._refresh_cookie()

            print("\n===== 爬取资讯 =====")
            
            # 先获取已有的数据，避免重复爬取
            existing_posts = self._get_existing_posts()
            existing_urls = set(post.get('source_url', '') for post in existing_posts if 'source_url' in post)
            print(f"已有 {len(existing_urls)} 条推文URL在数据库中")
            
            # 爬取推文
            posts = self.crawl_posts()
            
            # 过滤已爬取过的推文
            new_posts = [post for post in posts if post.get('url', '') not in existing_urls]
            print(f"新增推文 {len(new_posts)}/{len(posts)} 条")
            
            # 如果需要，可以继续筛选新推文
            posts = new_posts
            
            print(f"成功爬取 {len(posts)} 条资讯")
            
            # 如果没有爬取到任何帖子，则退出
            if not posts:
                print("未能爬取到任何帖子，任务结束")
                return 0

            # 保存数据到临时存储
            formatted_posts = self.format_posts_for_saving(posts)
            self.save_to_temp_storage(formatted_posts)
            print(f"已将 {len(formatted_posts)} 条资讯保存到临时存储")
            
            # 任务完成后，再次更新cookie
            self._safe_update_cookie()
            
            print(f"\n爬虫任务完成! 爬取了 {len(posts)} 条资讯")
            return len(posts)

        except Exception as e:
            print(f"爬虫运行出错: {e}")
            import traceback
            traceback.print_exc()
            return 0
        finally:
            self.close()

def main():
    """主函数，执行爬虫任务"""
    try:
        start_time = time.time()
        print(f"开始执行X爬虫任务，时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 创建爬虫实例
        crawler = XCrawler()
        
        try:
            # 运行爬虫
            posts_count = crawler.run()
            end_time = time.time()
            total_time = end_time - start_time
            print(f"爬虫任务完成，总耗时: {total_time:.2f}秒")
            return posts_count
        except Exception as e:
            print(f"爬虫执行过程中出错: {e}")
            import traceback
            traceback.print_exc()
            return 0
        finally:
            # 确保浏览器正常关闭
            try:
                crawler.close()
            except:
                pass
    except Exception as e:
        print(f"爬虫初始化时出错: {e}")
        import traceback
        traceback.print_exc()
        return 0


if __name__ == "__main__":
    main()
