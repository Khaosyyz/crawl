document.addEventListener('DOMContentLoaded', function() {
    // 脚本版本检查
    const scriptVersion = '1.0.1'; // 更新版本号
    const lastVersion = localStorage.getItem('scriptVersion');
    
    // 如果版本不匹配，清除缓存并刷新
    if (lastVersion !== scriptVersion) {
        console.log(`版本更新: ${lastVersion || '无'} -> ${scriptVersion}`);
        localStorage.setItem('scriptVersion', scriptVersion);
        
        // 清除缓存相关的存储
        try {
            // 清除可能与卡片渲染相关的缓存数据
            if (caches && caches.delete) {
                caches.delete('news-data-cache').then(() => {
                    console.log('清除缓存成功');
                }).catch(e => {
                    console.error('清除缓存失败:', e);
                });
            }
        } catch (e) {
            console.error('缓存操作失败:', e);
        }
    }

    // 获取DOM元素
    const newsContainer = document.getElementById('news-container');
    const searchInput = document.getElementById('search-input');
    const clearSearchButton = document.getElementById('clear-search');
    const tabButtons = document.querySelectorAll('.tab-button');
    const refreshButton = document.getElementById('refresh-button');
    const paginationContainer = document.getElementById('pagination');

    // 存储所有新闻数据
    let allNewsData = [];
    // 当前选中的数据源，默认为x.com
    let currentSource = 'x.com';
    // 当前搜索关键词
    let currentSearchQuery = '';
    // 防抖定时器
    let fetchDebounceTimer = null;
    // 搜索防抖定时器
    let searchDebounceTimer = null;
    // 是否正在加载数据
    let isLoading = false;
    // 分页相关变量
    let currentPage = 1;
    let totalPages = 1;
    let groupedNewsByDate = {};
    let dateKeys = [];
    // 每页显示的最大日期数量
    const DATES_PER_PAGE = 2;
    // 每个日期默认显示的新闻数量
    const DEFAULT_NEWS_PER_DATE = 9;
    // Crunchbase 显示更多相关变量
    let crunchbaseDisplayCount = 3;
    let crunchbaseNews = [];
    let currentDatePage = 1;
    // 全局变量
    let lastError = null;

    // 设置X标签为默认选中
    if (tabButtons.length > 0) {
        tabButtons[0].classList.add('active');
    }

    // 在页面加载时强制刷新数据，而不是简单调用fetchData
    function forceRefreshData() {
        // 如果已经在加载中，则忽略
        if (isLoading) return;
        
        // 禁用刷新按钮（如果存在）
        if (refreshButton) {
            refreshButton.disabled = true;
            refreshButton.classList.add('disabled');
        }
        
        // 使用防抖函数调用fetchData
        if (fetchDebounceTimer) {
            clearTimeout(fetchDebounceTimer);
        }
        
        fetchDebounceTimer = setTimeout(() => {
            fetchData();
        }, 300);
    }

    // 初始加载时执行强制刷新
    forceRefreshData();

    console.log('脚本初始化完成，准备加载数据');

    // 添加页面可见性变化监听器，当页面从隐藏变为可见时刷新数据
    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible') {
            // 页面变为可见时刷新数据
            forceRefreshData();
        }
    });

    // 添加页面重新加载事件监听器
    window.addEventListener('pageshow', function(event) {
        // 当页面从缓存加载（浏览器前进/后退）时也刷新数据
        if (event.persisted) {
            forceRefreshData();
        }
    });

    // 刷新按钮点击事件 - 强制忽略缓存
    if (refreshButton) {
        refreshButton.addEventListener('click', function() {
            // 清除相关缓存
            const cacheKeysToRemove = [];
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                if (key && key.startsWith('news-data-' + currentSource)) {
                    cacheKeysToRemove.push(key);
                }
            }
            
            // 删除缓存
            cacheKeysToRemove.forEach(key => localStorage.removeItem(key));
            
            // 强制刷新
            forceRefreshData();
            
            // 显示刷新提示
            const refreshMsg = document.createElement('div');
            refreshMsg.className = 'refresh-message';
            refreshMsg.textContent = '数据已刷新！';
            document.body.appendChild(refreshMsg);
            
            // 2秒后自动消失
            setTimeout(() => {
                refreshMsg.style.opacity = '0';
                setTimeout(() => refreshMsg.remove(), 500);
            }, 2000);
        });
    }

    // 搜索输入框输入事件 - 实时搜索
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            // 清除之前的防抖定时器
            if (searchDebounceTimer) {
                clearTimeout(searchDebounceTimer);
            }
            
            // 设置新的防抖定时器，延迟300毫秒执行搜索
            searchDebounceTimer = setTimeout(() => {
                currentPage = 1; // 重置为第一页
                performSearch();
            }, 300);
        });
    }

    // 清除搜索按钮点击事件
    if (clearSearchButton) {
        clearSearchButton.addEventListener('click', clearSearch);
    }

    // 标签切换事件
    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            // 更新选中状态
            tabButtons.forEach(btn => btn.classList.remove('active'));
            this.classList.add('active');
            
            // 完全清除现有内容和数据
            newsContainer.innerHTML = '';
            allNewsData = [];
            
            // 更新当前数据源
            currentSource = this.dataset.source;
            
            // 重置为第一页
            currentPage = 1;
            currentDatePage = 1;
            
            // 显示加载中提示
            const loadingMsg = document.createElement('div');
            loadingMsg.className = 'loading';
            loadingMsg.textContent = '正在加载资讯...';
            newsContainer.appendChild(loadingMsg);
            
            // 如果是 Crunchbase，重置显示数量
            if (currentSource === 'crunchbase.com') {
                crunchbaseDisplayCount = 3;
            }
            
            // 强制刷新数据
            setTimeout(() => {
                forceRefreshData();
            }, 100);
        });
    });

    // 显示加载状态
    function showLoading(container) {
        // 创建加载指示器如果不存在
        let loadingIndicator = document.getElementById('loading-indicator');
        if (!loadingIndicator) {
            loadingIndicator = document.createElement('div');
            loadingIndicator.id = 'loading-indicator';
            loadingIndicator.innerHTML = `
                <div class="spinner"></div>
                <p>加载中，请稍候...</p>
            `;
            container.appendChild(loadingIndicator);
        } else {
            loadingIndicator.style.display = 'flex';
        }
    }

    // 隐藏加载状态
    function hideLoading() {
        const loadingIndicator = document.getElementById('loading-indicator');
        if (loadingIndicator) {
            loadingIndicator.style.display = 'none';
        }
    }

    // 显示错误信息
    function showError(container, errorMessage) {
        // 创建错误提示如果不存在
        let errorElement = document.getElementById('error-message');
        if (!errorElement) {
            errorElement = document.createElement('div');
            errorElement.id = 'error-message';
            errorElement.className = 'error-container';
            container.appendChild(errorElement);
        }
        
        errorElement.innerHTML = `
            <p>${errorMessage}</p>
            <button id="retry-button" class="retry-button">重试</button>
        `;
        errorElement.style.display = 'block';
        
        // 添加重试按钮事件
        document.getElementById('retry-button').addEventListener('click', () => {
            errorElement.style.display = 'none';
            fetchData();
        });
    }

    // 获取新闻数据
    function fetchData() {
        try {
            console.log('开始获取数据，当前源:', currentSource);
            // 设置加载状态
            isLoading = true;
            // 显示加载指示器
            showLoading(newsContainer);
            
            // 清空当前新闻
            newsContainer.innerHTML = '';
            
            // 创建一个唯一的、缓存无关的时间戳
            const timestamp = Date.now();
            
            // 检查缓存
            const cacheKey = `news-data-${currentSource}-${currentPage}-${currentDatePage}`;
            const cachedData = localStorage.getItem(cacheKey);
            const cacheTimestampKey = `${cacheKey}-timestamp`;
            const cacheTimestamp = localStorage.getItem(cacheTimestampKey);
            const cacheValidityMinutes = 10; // 缓存有效期10分钟
            
            // 如果有缓存，并且缓存未过期，使用缓存数据
            if (cachedData && cacheTimestamp) {
                const cacheAge = (Date.now() - parseInt(cacheTimestamp)) / (1000 * 60);
                if (cacheAge < cacheValidityMinutes) {
                    console.log(`使用缓存数据，缓存年龄: ${cacheAge.toFixed(2)}分钟`);
                    const parsedData = JSON.parse(cachedData);
                    allNewsData = parsedData.data || parsedData;
                    console.log('从缓存加载的数据:', allNewsData);
                    isLoading = false;
                    hideLoading();
                    processAndDisplayNews(Array.isArray(allNewsData) ? allNewsData : []);
                    return;
                } else {
                    console.log(`缓存已过期，缓存年龄: ${cacheAge.toFixed(2)}分钟`);
                }
            }
            
            // 加载中的提示
            const loadingMessage = document.createElement('div');
            loadingMessage.className = 'loading-message';
            loadingMessage.innerHTML = `<p>正在从服务器获取最新数据...</p>`;
            newsContainer.appendChild(loadingMessage);
            
            // 构建API URL
            // 如果是Crunchbase，添加日期页参数
            const apiUrl = currentSource === 'crunchbase.com' 
                ? `https://crawl-beta.vercel.app/api/articles?source=${currentSource}&date_page=${currentDatePage}&_=${timestamp}`
                : `https://crawl-beta.vercel.app/api/articles?source=${currentSource}&_=${timestamp}`;
                
            console.log(`获取数据: ${apiUrl}`);
            
            // 发送请求
            fetch(apiUrl)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`获取数据失败，HTTP状态码 ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log("数据获取成功:", data);
                    
                    // 存储数据到缓存
                    localStorage.setItem(cacheKey, JSON.stringify(data));
                    localStorage.setItem(cacheTimestampKey, Date.now().toString());
                    
                    // 更新全局数据
                    if (data && data.data && Array.isArray(data.data)) {
                        allNewsData = data.data;
                        console.log('从API获取的文章数:', allNewsData.length);
                    } else {
                        console.error('API返回的数据结构异常:', data);
                        allNewsData = [];
                    }
                    
                    // 如果是Crunchbase类型的数据，可能有特定的处理逻辑
                    if (currentSource === 'crunchbase.com') {
                        // 设置总页数
                        if (data.total_date_pages) {
                            totalPages = data.total_date_pages;
                            console.log('设置总页数:', totalPages);
                        }
                    }
                    
                    // 处理和显示数据
                    processAndDisplayNews(allNewsData);
                })
                .catch(error => {
                    // 如果API请求失败，但有缓存数据，使用缓存数据
                    if (cachedData) {
                        console.log("API请求失败，使用可能过期的缓存数据");
                        const parsedData = JSON.parse(cachedData);
                        allNewsData = parsedData.data || parsedData;
                        processAndDisplayNews(Array.isArray(allNewsData) ? allNewsData : []);
                        
                        // 显示轻微的错误提示
                        const warningBar = document.createElement('div');
                        warningBar.className = 'warning-bar';
                        warningBar.innerHTML = `
                            <p>注意：无法获取最新数据，显示的是缓存数据。错误信息: ${error.message}</p>
                        `;
                        document.body.insertBefore(warningBar, document.body.firstChild);
                        
                        // 3秒后自动消失
                        setTimeout(() => {
                            warningBar.style.opacity = '0';
                            setTimeout(() => warningBar.remove(), 500);
                        }, 3000);
                    } else {
                        // 如果没有缓存数据，显示错误
                        console.error("获取数据错误:", error);
                        showError(newsContainer, `获取数据失败: ${error.message}`);
                        lastError = error;
                    }
                })
                .finally(() => {
                    // 完成加载
                    isLoading = false;
                    hideLoading();
                    
                    // 移除加载消息
                    const loadingMessage = document.querySelector('.loading-message');
                    if (loadingMessage) {
                        loadingMessage.remove();
                    }
                    
                    // 重新启用刷新按钮
                    if (refreshButton) {
                        refreshButton.disabled = false;
                        refreshButton.classList.remove('disabled');
                    }
                });
        } catch (error) {
            console.error("fetchData异常:", error);
            showError(newsContainer, `获取数据时发生异常: ${error.message}`);
            isLoading = false;
        }
    }

    // 执行搜索
    function performSearch() {
        if (!searchInput) {
            console.error('搜索输入框不存在');
            return;
        }

        const query = searchInput.value.trim();
        currentSearchQuery = query;

        if (!query) {
            // 如果查询为空，直接显示全部数据
            forceRefreshData();
            return;
        }

        // 显示加载状态
        newsContainer.innerHTML = '<div class="loading">正在搜索...</div>';
        
        // 在本地用简单的方法实现搜索
        if (allNewsData && allNewsData.length > 0) {
            // 对已加载的数据进行客户端过滤
            const filteredResults = allNewsData.filter(item => {
                // 检查标题、内容和作者中是否包含搜索关键词
                const searchTermLower = query.toLowerCase();
                const titleMatch = item.title && item.title.toLowerCase().includes(searchTermLower);
                const contentMatch = item.content && item.content.toLowerCase().includes(searchTermLower);
                const authorMatch = item.author && item.author.toLowerCase().includes(searchTermLower);
                
                return titleMatch || contentMatch || authorMatch;
            });
            
            if (filteredResults.length === 0) {
                showError(newsContainer, `没有和"${query}"相关的资讯`);
            } else {
                // 使用过滤后的结果
                const sourceFilteredResults = filteredResults.filter(item => item.source === currentSource);
                
                if (sourceFilteredResults.length === 0) {
                    showError(newsContainer, `在${getSourceName(currentSource)}中没有和"${query}"相关的资讯`);
                } else {
                    // 更新数据
                    allNewsData = sourceFilteredResults;
                    
                    // 重置为第一页
                    currentPage = 1;
                    
                    // 显示搜索结果
                    displayCurrentPageNews(true);
                }
            }
        } else {
            showError(newsContainer, '请先加载数据，然后再搜索');
        }
    }

    // 根据数据源过滤数据
    function filterBySource(data) {
        if (currentSource === 'all') {
            return data;
        }
        return data.filter(item => {
            // 检查数据来源是否匹配当前选中的标签
            return item.source === currentSource;
        });
    }

    // 获取数据源名称（用于显示错误消息）
    function getSourceName(source) {
        switch(source) {
            case 'x.com': return 'X平台';
            case 'crunchbase.com': return 'Crunchbase';
            case 'all': return '';
            default: return source;
        }
    }

    // 过滤并显示新闻
    function filterAndDisplayNews() {
        const filteredData = filterBySource(allNewsData);
        
        if (filteredData.length === 0) {
            showError(newsContainer, `暂无${getSourceName(currentSource)}资讯数据`);
        } else {
            // 处理分页
            processAndDisplayNews(filteredData);
        }
    }

    // 清除搜索
    function clearSearch() {
        if (searchInput) {
            searchInput.value = '';
            currentSearchQuery = '';
            // 重置为第一页
            currentPage = 1;
            filterAndDisplayNews();
        }
    }
    
    // 处理数据并显示新闻（包括分页）
    function processAndDisplayNews(newsData, isSearchResult = false) {
        // 更新总新闻数据
        allNewsData = newsData;
        
        // 不再区分不同来源，全部使用相同的日期分组显示逻辑
        displayCurrentPageNews(isSearchResult);
    }
    
    // 显示当前页的新闻 - 统一处理所有来源
    function displayCurrentPageNews(isSearchResult = false) {
        // 确保newsContainer存在
        if (!newsContainer) {
            console.error('无法找到新闻容器元素');
            return;
        }
        
        // 清空容器
        newsContainer.innerHTML = '';
        
        // 检查是否有数据
        if (!allNewsData || allNewsData.length === 0) {
            // 如果没有数据，尝试重新获取
            if (currentSource === 'crunchbase.com') {
                // 强制重新获取Crunchbase数据
                console.log('没有数据，尝试获取Crunchbase数据');
                const timestamp = new Date().getTime() + Math.random().toString(36).substring(2, 8);
                const apiUrl = `https://crawl-beta.vercel.app/api/articles?source=${currentSource}&date_page=${currentDatePage}&_=${timestamp}`;
                
                console.log(`正在获取数据: date_page=${currentDatePage}, 时间戳=${timestamp}`);
                newsContainer.innerHTML = '<div class="loading">正在加载资讯...</div>';
                
                fetch(apiUrl, {
                    method: 'GET',
                    mode: 'cors',
                    cache: 'no-store',
                    headers: {
                        'Content-Type': 'application/json',
                        'Cache-Control': 'no-cache, no-store, must-revalidate',
                        'Pragma': 'no-cache',
                        'Expires': '0'
                    },
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP错误 ${response.status}: ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(result => {
                    if (result.status === 'error') {
                        showError(newsContainer, result.message);
                        return;
                    }
                    
                    console.log('重新获取Crunchbase数据成功:', result);
                    
                    // 更新数据
                    if (result && result.data && Array.isArray(result.data)) {
                        allNewsData = result.data;
                        console.log('获取到数据条数:', allNewsData.length);
                    } else {
                        console.error('API响应格式异常:', result);
                        showError(newsContainer, '获取到的数据格式错误');
                        return;
                    }
                    
                    totalPages = result.total_date_pages || 15;
                    
                    console.log(`获取到数据: ${allNewsData.length}条, 日期范围: ${result.date_range.start} - ${result.date_range.end}`);
                    
                    // 递归调用自身，显示获取到的数据
                    displayCurrentPageNews(isSearchResult);
                })
                .catch(error => {
                    showError(newsContainer, `获取数据失败: ${error.message}`);
                    console.error('API错误:', error);
                });
                return;
            } else {
                showError(newsContainer, isSearchResult ? '没有找到匹配的结果' : '暂无资讯数据');
                return;
            }
        }
        
        console.log('开始处理显示数据，当前有效数据条数:', allNewsData.length);
        
        // 按日期分组数据
        groupedNewsByDate = groupNewsByDate(allNewsData);
        dateKeys = Object.keys(groupedNewsByDate).sort().reverse();
        
        console.log('数据分组完成，日期组数:', dateKeys.length);
        
        // 检查是否有日期数据
        if (dateKeys.length === 0) {
            showError(newsContainer, isSearchResult ? '没有找到匹配的结果' : '暂无资讯数据');
            return;
        }
        
        // 不显示日期导航，以前的代码已被CSS隐藏
        
        console.log('开始创建卡片，日期组:', dateKeys);

        // 为X标签页实现分页，根据当前页计算需要显示的日期
        if (currentSource === 'x.com') {
            // 计算当前页应显示的日期范围
            const startIndex = (currentPage - 1) * DATES_PER_PAGE;
            const endIndex = Math.min(startIndex + DATES_PER_PAGE, dateKeys.length);
            
            // 获取当前页的日期
            const currentPageDates = dateKeys.slice(startIndex, endIndex);
            console.log(`当前页 ${currentPage} 显示日期:`, currentPageDates);
            
            // 只遍历当前页的日期
            currentPageDates.forEach(date => {
                // 创建日期分组标题
                const dateHeader = document.createElement('div');
                dateHeader.className = 'date-header';
                dateHeader.textContent = formatDate(date);
                dateHeader.dataset.date = date;  // 添加日期数据属性，用于后续处理
                
                newsContainer.appendChild(dateHeader);
            
                const dateGroup = groupedNewsByDate[date];
                console.log(`日期 ${date} 的文章数:`, dateGroup.length);
            
                // 创建新闻卡片容器
                const groupContainer = document.createElement('div');
                groupContainer.className = 'news-group';
                groupContainer.dataset.date = date;
            
                // 初始显示前N条新闻 (X显示9条)
                const initialCount = 9;
                const initialNews = dateGroup.slice(0, Math.min(initialCount, dateGroup.length));
                
                if (initialNews.length === 0) {
                    console.warn(`日期 ${date} 没有可显示的文章`);
                }
                
                initialNews.forEach((news, index) => {
                    try {
                        console.log(`创建卡片 ${index+1}/${initialNews.length}，标题:`, news.title);
                        const newsCard = createNewsCard(news);
                        if (newsCard) {
                            groupContainer.appendChild(newsCard);
                        } else {
                            console.error('创建卡片失败，返回值为空');
                        }
                    } catch (error) {
                        console.error('创建卡片时出错:', error);
                    }
                });
                
                // 检查是否实际添加了卡片
                if (groupContainer.children.length === 0) {
                    console.warn(`日期 ${date} 的卡片容器为空，未能创建有效卡片`);
                    groupContainer.innerHTML = '<div class="empty-message">此日期没有可显示的内容</div>';
                }
            
                newsContainer.appendChild(groupContainer);

                // 创建按钮容器
                const buttonContainer = document.createElement('div');
                buttonContainer.className = 'news-buttons-container';
                newsContainer.appendChild(buttonContainer);

                // 如果该日期组有超过初始显示数量的新闻，添加"显示更多"按钮
                if (dateGroup.length > initialCount) {
                    const loadMoreButton = document.createElement('button');
                    loadMoreButton.className = 'load-more-button';
                    loadMoreButton.textContent = `显示更多 (${dateGroup.length - initialCount}条)`;
                    loadMoreButton.dataset.date = date;
                    
                    // 额外的新闻卡片容器 (用于存放剩余新闻)
                    const extraNewsContainer = document.createElement('div');
                    extraNewsContainer.className = 'extra-news-container';
                    extraNewsContainer.style.display = 'none'; // 初始隐藏
                    extraNewsContainer.dataset.date = date;
                    
                    // 准备剩余的新闻卡片
                    const remainingNews = dateGroup.slice(initialCount);
                    remainingNews.forEach((news, index) => {
                        try {
                            console.log(`创建额外卡片 ${index+1}/${remainingNews.length}`);
                            const newsCard = createNewsCard(news);
                            if (newsCard) {
                                extraNewsContainer.appendChild(newsCard);
                            }
                        } catch (error) {
                            console.error('创建额外卡片时出错:', error);
                        }
                    });
                    
                    // 将额外的新闻容器添加到DOM中
                    groupContainer.after(extraNewsContainer);
                    
                    // 创建收起按钮但初始不显示
                    const collapseButton = document.createElement('button');
                    collapseButton.className = 'collapse-button';
                    collapseButton.textContent = '收起';
                    collapseButton.dataset.date = date;
                    collapseButton.style.display = 'none'; // 初始隐藏
                    
                    // 点击显示更多按钮时的逻辑
                    loadMoreButton.onclick = () => {
                        // 显示额外的新闻
                        extraNewsContainer.style.display = 'grid';
                        // 隐藏显示更多按钮
                        loadMoreButton.style.display = 'none';
                        // 显示收起按钮
                        collapseButton.style.display = 'block';
                    };
                    
                    // 点击收起按钮时的逻辑
                    collapseButton.onclick = () => {
                        // 隐藏额外的新闻
                        extraNewsContainer.style.display = 'none';
                        // 显示显示更多按钮
                        loadMoreButton.style.display = 'block';
                        // 隐藏收起按钮
                        collapseButton.style.display = 'none';
                    };
                    
                    // 添加按钮到按钮容器
                    buttonContainer.appendChild(loadMoreButton);
                    buttonContainer.appendChild(collapseButton);
                }
            });
        } else {
            // Crunchbase的原始渲染逻辑
            // 遍历每个日期组
            dateKeys.forEach(date => {
                // 创建日期分组标题
                const dateHeader = document.createElement('div');
                dateHeader.className = 'date-header';
                dateHeader.textContent = formatDate(date);
                dateHeader.dataset.date = date;  // 添加日期数据属性，用于后续处理
                
                newsContainer.appendChild(dateHeader);
            
                const dateGroup = groupedNewsByDate[date];
                console.log(`日期 ${date} 的文章数:`, dateGroup.length);
            
                // 创建新闻卡片容器
                const groupContainer = document.createElement('div');
                groupContainer.className = 'news-group';
                
                // 为Crunchbase添加特殊类
                if (currentSource === 'crunchbase.com') {
                    groupContainer.classList.add('cb-news-group');
                }
                
                groupContainer.dataset.date = date;
            
                // 初始显示前N条新闻 (Crunchbase显示3条)
                const initialCount = 3;
                const initialNews = dateGroup.slice(0, Math.min(initialCount, dateGroup.length));
                
                if (initialNews.length === 0) {
                    console.warn(`日期 ${date} 没有可显示的文章`);
                }
                
                initialNews.forEach((news, index) => {
                    try {
                        console.log(`创建卡片 ${index+1}/${initialNews.length}，标题:`, news.title);
                        const newsCard = createNewsCard(news);
                        if (newsCard) {
                            groupContainer.appendChild(newsCard);
                        } else {
                            console.error('创建卡片失败，返回值为空');
                        }
                    } catch (error) {
                        console.error('创建卡片时出错:', error);
                    }
                });
                
                // 检查是否实际添加了卡片
                if (groupContainer.children.length === 0) {
                    console.warn(`日期 ${date} 的卡片容器为空，未能创建有效卡片`);
                    groupContainer.innerHTML = '<div class="empty-message">此日期没有可显示的内容</div>';
                }
            
                newsContainer.appendChild(groupContainer);

                // 创建按钮容器
                const buttonContainer = document.createElement('div');
                buttonContainer.className = 'news-buttons-container';
                newsContainer.appendChild(buttonContainer);

                // 如果该日期组有超过初始显示数量的新闻，添加"显示更多"按钮
                if (dateGroup.length > initialCount) {
                    const loadMoreButton = document.createElement('button');
                    loadMoreButton.className = 'load-more-button';
                    loadMoreButton.textContent = `显示更多 (${dateGroup.length - initialCount}条)`;
                    loadMoreButton.dataset.date = date;
                    
                    // 额外的新闻卡片容器 (用于存放剩余新闻)
                    const extraNewsContainer = document.createElement('div');
                    extraNewsContainer.className = 'extra-news-container';
                    if (currentSource === 'crunchbase.com') {
                        extraNewsContainer.classList.add('cb-extra-news');
                    }
                    extraNewsContainer.style.display = 'none'; // 初始隐藏
                    extraNewsContainer.dataset.date = date;
                    
                    // 准备剩余的新闻卡片
                    const remainingNews = dateGroup.slice(initialCount);
                    remainingNews.forEach((news, index) => {
                        try {
                            console.log(`创建额外卡片 ${index+1}/${remainingNews.length}`);
                            const newsCard = createNewsCard(news);
                            if (newsCard) {
                                extraNewsContainer.appendChild(newsCard);
                            }
                        } catch (error) {
                            console.error('创建额外卡片时出错:', error);
                        }
                    });
                    
                    // 将额外的新闻容器添加到DOM中
                    groupContainer.after(extraNewsContainer);
                    
                    // 创建收起按钮但初始不显示
                    const collapseButton = document.createElement('button');
                    collapseButton.className = 'collapse-button';
                    collapseButton.textContent = '收起';
                    collapseButton.dataset.date = date;
                    collapseButton.style.display = 'none'; // 初始隐藏
                    
                    // 点击显示更多按钮时的逻辑
                    loadMoreButton.onclick = () => {
                        // 显示额外的新闻
                        extraNewsContainer.style.display = 'grid';
                        // 隐藏显示更多按钮
                        loadMoreButton.style.display = 'none';
                        // 显示收起按钮
                        collapseButton.style.display = 'block';
                    };
                    
                    // 点击收起按钮时的逻辑
                    collapseButton.onclick = () => {
                        // 隐藏额外的新闻
                        extraNewsContainer.style.display = 'none';
                        // 显示显示更多按钮
                        loadMoreButton.style.display = 'block';
                        // 隐藏收起按钮
                        collapseButton.style.display = 'none';
                    };
                    
                    // 添加按钮到按钮容器
                    buttonContainer.appendChild(loadMoreButton);
                    buttonContainer.appendChild(collapseButton);
                }
            });
        }
        
        console.log('卡片渲染完成');
        
        // 更新分页控件
        updatePagination();
    }

    // 更新分页控件 - 修复分页逻辑问题
    function updatePagination() {
        if (!paginationContainer) return;
        
        paginationContainer.innerHTML = '';
        
        // 如果是Crunchbase，使用date_page分页
        if (currentSource === 'crunchbase.com') {
            // 设置Crunchbase特有的分页逻辑
            if (totalPages <= 1) {
                paginationContainer.style.display = 'none';
                return;
            }
            
            paginationContainer.style.display = 'flex';
            
            // 前一页按钮
            const prevBtn = document.createElement('button');
            prevBtn.innerHTML = '&laquo;';
            prevBtn.title = '上一页';
            
            if (currentDatePage > 1) {
                prevBtn.addEventListener('click', () => {
                    currentDatePage--;
                    // 强制重新获取数据
                    allNewsData = [];
                    // 强制调用获取数据函数
                    fetchData();
                    window.scrollTo(0, 0);
                });
            } else {
                prevBtn.classList.add('disabled');
            }
            paginationContainer.appendChild(prevBtn);
            
            // 最多显示5个页码按钮
            let startPage = Math.max(1, currentDatePage - 2);
            let endPage = Math.min(totalPages, startPage + 4);
            
            // 调整起始页以确保显示5个页码按钮（如果有这么多页）
            if (endPage - startPage < 4 && totalPages > 5) {
                startPage = Math.max(1, endPage - 4);
            }
            
            // 添加页码按钮
            for (let i = startPage; i <= endPage; i++) {
                const pageBtn = document.createElement('button');
                pageBtn.textContent = i.toString();
                if (i === currentDatePage) {
                    pageBtn.classList.add('active');
                } else {
                    pageBtn.addEventListener('click', () => {
                        currentDatePage = i;
                        // 强制重新获取数据
                        allNewsData = [];
                        // 强制调用获取数据函数
                        fetchData();
                        window.scrollTo(0, 0);
                    });
                }
                paginationContainer.appendChild(pageBtn);
            }
            
            // 后一页按钮
            const nextBtn = document.createElement('button');
            nextBtn.innerHTML = '&raquo;';
            nextBtn.title = '下一页';
            
            if (currentDatePage < totalPages) {
                nextBtn.addEventListener('click', () => {
                    currentDatePage++;
                    // 强制重新获取数据
                    allNewsData = [];
                    // 强制调用获取数据函数
                    fetchData();
                    window.scrollTo(0, 0);
                });
            } else {
                nextBtn.classList.add('disabled');
            }
            paginationContainer.appendChild(nextBtn);
        } else {
            // X标签页使用日期分页
            // 计算总页数 - 每页显示最多两个日期组
            const totalDatePages = Math.ceil(dateKeys.length / DATES_PER_PAGE);
            
            // 如果只有一页，不显示分页控件
            if (totalDatePages <= 1) {
                paginationContainer.style.display = 'none';
                return;
            }
            
            paginationContainer.style.display = 'flex';
            
            // 前一页按钮
            const prevBtn = document.createElement('button');
            prevBtn.innerHTML = '&laquo;';
            prevBtn.title = '上一页';
            
            if (currentPage > 1) {
                prevBtn.addEventListener('click', () => {
                    goToPage(currentPage - 1);
                });
            } else {
                prevBtn.classList.add('disabled');
            }
            paginationContainer.appendChild(prevBtn);
            
            // 添加页码按钮
            for (let i = 1; i <= totalDatePages; i++) {
                const pageBtn = document.createElement('button');
                pageBtn.textContent = i.toString();
                if (i === currentPage) {
                    pageBtn.classList.add('active');
                } else {
                    pageBtn.addEventListener('click', () => {
                        goToPage(i);
                    });
                }
                paginationContainer.appendChild(pageBtn);
            }
            
            // 后一页按钮
            const nextBtn = document.createElement('button');
            nextBtn.innerHTML = '&raquo;';
            nextBtn.title = '下一页';
            
            if (currentPage < totalDatePages) {
                nextBtn.addEventListener('click', () => {
                    goToPage(currentPage + 1);
                });
            } else {
                nextBtn.classList.add('disabled');
            }
            paginationContainer.appendChild(nextBtn);
        }
    }
    
    // 跳转到指定页
    function goToPage(page) {
        if (page < 1 || page === currentPage) return;
        
        currentPage = page;
        // 更新分页控件显示
        updatePagination();
        // 显示当前页的新闻
        displayCurrentPageNews();
        // 滚动到页面顶部
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    }

    // 按日期分组新闻
    function groupNewsByDate(newsData) {
        const grouped = {};
        
        // 确保newsData是数组
        if (!Array.isArray(newsData)) {
            console.error("groupNewsByDate: newsData不是数组", newsData);
            return grouped;
        }
        
        newsData.forEach(news => {
            // 从日期时间字段中提取日期部分
            let dateStr = '未知日期';
            
            if (news.date_time) {
                dateStr = extractDate(news.date_time);
            } else if (news.published_date) {
                dateStr = news.published_date;
            } else if (news.published_at) {
                dateStr = extractDate(news.published_at);
            }
            
            if (!grouped[dateStr]) {
                grouped[dateStr] = [];
            }
            
            grouped[dateStr].push(news);
        });
        
        return grouped;
    }

    // 提取日期部分（YY/MM/DD）
    function extractDate(dateTimeStr) {
        if (!dateTimeStr) return '未知日期';
        
        // 如果包含空格，说明有日期和时间，取第一部分作为日期
        if (dateTimeStr.includes(' ')) {
            return dateTimeStr.split(' ')[0];
        }
        
        // 否则直接返回，可能只有日期
        return dateTimeStr;
    }

    // 提取时间部分（HH:MM）
    function extractTime(dateTimeStr) {
        if (!dateTimeStr || !dateTimeStr.includes(' ')) return '';
        
        // 分离出时间部分
        const timePart = dateTimeStr.split(' ')[1];
        
        // 返回时间部分（可能需要进一步处理格式）
        return timePart;
    }

    // 安全地从日期字符串中获取日期部分
    function getDateFromString(dateString) {
        try {
            // 检查日期字符串是否有效
            if (!dateString) return null;
            
            // 尝试提取日期部分 (YYYY-MM-DD)
            const match = dateString.match(/^\d{4}-\d{2}-\d{2}/);
            if (match) {
                return match[0];
            }
            
            // 尝试创建日期对象并格式化
            const date = new Date(dateString);
            if (!isNaN(date.getTime())) {
                return date.toISOString().split('T')[0];
            }
            
            return null;
        } catch (e) {
            console.error("Error parsing date:", e);
            return null;
        }
    }

    // 格式化日期显示
    function formatDateForDisplay(dateString) {
        try {
            if (!dateString) return "未知日期";
            
            const date = new Date(dateString);
            if (isNaN(date.getTime())) return dateString;
            
            const year = date.getFullYear();
            const month = date.getMonth() + 1;
            const day = date.getDate();
            
            return `${year}年${month}月${day}日`;
        } catch (e) {
            console.error("Error formatting date:", e);
            return dateString;
        }
    }

    // 格式化日期显示
    function formatDate(dateStr) {
        if (!dateStr || dateStr === '未知日期') return dateStr;

        try {
            // 确保只处理日期部分
            const dateOnly = extractDate(dateStr);
            
            const date = new Date(dateOnly);
            const now = new Date();
            const yesterday = new Date(now);
            yesterday.setDate(now.getDate() - 1);

            // 如果是今天或昨天，显示特殊文本
            if (isSameDay(date, now)) {
                return '今天 · ' + dateOnly;
            } else if (isSameDay(date, yesterday)) {
                return '昨天 · ' + dateOnly;
            } else {
                // 格式化日期为YYYY-MM-DD
                return dateOnly;
            }
        } catch (e) {
            console.error('日期格式化错误:', e);
            return dateStr;
        }
    }

    // 格式化时间显示
    function formatTime(timeStr) {
        if (!timeStr) return '';
        
        // 基础格式化，未来可以根据需要增加AM/PM等
        return timeStr;
    }

    // 判断两个日期是否是同一天
    function isSameDay(d1, d2) {
        return d1.getFullYear() === d2.getFullYear() &&
               d1.getMonth() === d2.getMonth() &&
               d1.getDate() === d2.getDate();
    }

    // 创建单个新闻卡片
    function createNewsCard(news) {
        try {
            if (!news) {
                console.error('createNewsCard收到空的news对象');
                return document.createElement('div');
            }

            // 获取日期和时间
            let dateDisplay = "未知日期";
            let timeDisplay = "";
            if (news.date_time) {
                try {
                    // 拆分日期和时间
                    const dateParts = news.date_time.split(' ');
                    if (dateParts.length >= 2) {
                        dateDisplay = formatDateForDisplay(dateParts[0]);
                        timeDisplay = dateParts[1].substring(0, 5); // 只取HH:MM
                    } else {
                        dateDisplay = formatDateForDisplay(news.date_time);
                    }
                } catch (e) {
                    console.error("Error parsing date in createNewsCard:", e);
                }
            }

            // 创建卡片包装器
            const cardWrapper = document.createElement('div');
            cardWrapper.className = 'news-card';
            
            // 创建统一的三段式卡片结构
            const cardHeader = document.createElement('div');
            cardHeader.className = 'news-card-header';
            
            const cardContent = document.createElement('div');
            cardContent.className = 'news-card-content';
            
            const cardFooter = document.createElement('div');
            cardFooter.className = 'news-card-footer';
            
            // 根据来源填充内容
            if (news.source === 'Twitter' || news.source === 'X' || news.source === 'x.com') {
                // X/Twitter卡片内容
                const title = escapeHTML(news.title) || '无标题';
                const content = formatContent(escapeHTML(news.content) || '无内容');
                
                // 收起超过200字符的内容
                const isLongContent = content.length > 200;
                
                // 标题部分
                cardHeader.innerHTML = `<h2 class="news-title">${title}</h2>`;
                
                // 内容部分 - 修改为使用新的渐变蒙版样式
                if (isLongContent) {
                    cardContent.innerHTML = `
                        <div class="news-content">
                            <p class="content-text collapsed">${content.substring(0, 200)}...</p>
                            <div class="full-content" style="display: none;">
                                <p>${content}</p>
                            </div>
                            <button class="toggle-content-btn">显示全部</button>
                        </div>
                    `;
                } else {
                    cardContent.innerHTML = `
                        <div class="news-content">
                            <p class="content-text">${content}</p>
                        </div>
                    `;
                }
                
                // 底部信息部分
                cardFooter.innerHTML = `
                    <div class="news-meta">
                        ${news.author ? `<div class="news-author">${escapeHTML(news.author)} ${timeDisplay ? `· ${timeDisplay}` : ''}</div>` : ''}
                    </div>
                    ${news.likes || news.retweets || news.followers ? `
                    <div class="news-social-stats">
                        ${news.followers ? `<span>粉丝: ${formatNumber(news.followers)}</span>` : '<span>-</span>'}
                        ${news.likes ? `<span>喜欢: ${formatNumber(news.likes)}</span>` : '<span>-</span>'}
                        ${news.retweets ? `<span>转发: ${formatNumber(news.retweets)}</span>` : '<span>-</span>'}
                    </div>` : ''}
                    ${news.url || news.source_url ? `
                    <a href="${news.url || news.source_url}" target="_blank" class="view-original-btn">查看原文</a>
                    ` : ''}
                `;
            } else if (news.source === 'Crunchbase' || news.source === 'crunchbase.com') {
                // Crunchbase卡片内容
                const title = escapeHTML(news.title) || '无标题';
                const content = escapeHTML(news.content) || '无内容';
                
                // 收起超过200字符的内容
                const isLongContent = content.length > 200;
                
                // 标题部分
                cardHeader.innerHTML = `<h2 class="news-title">${title}</h2>`;
                
                // 内容部分 - 修改为使用新的渐变蒙版样式
                if (isLongContent) {
                    cardContent.innerHTML = `
                        <div class="news-content">
                            <p class="content-text collapsed">${content.substring(0, 200)}...</p>
                            <div class="full-content" style="display: none;">
                                <p>${content}</p>
                            </div>
                            <button class="toggle-content-btn">显示全部</button>
                        </div>
                    `;
                } else {
                    cardContent.innerHTML = `
                        <div class="news-content">
                            <p class="content-text">${content}</p>
                        </div>
                    `;
                }
                
                // 底部信息部分
                cardFooter.innerHTML = `
                    <div class="news-meta">
                        ${news.author ? `<div class="news-author">作者: ${escapeHTML(news.author)}</div>` : ''}
                    </div>
                    ${news.company || news.funding_round || news.funding_amount || news.investors ? `
                    <div class="news-investment-info">
                        ${news.company ? `<div class="investment-row"><span class="info-label">公司:</span> <span class="info-value">${escapeHTML(news.company)}</span></div>` : ''}
                        ${news.funding_round ? `<div class="investment-row"><span class="info-label">轮次:</span> <span class="info-value">${escapeHTML(news.funding_round)}</span></div>` : ''}
                        ${news.funding_amount ? `<div class="investment-row"><span class="info-label">金额:</span> <span class="info-value">${escapeHTML(news.funding_amount)}</span></div>` : ''}
                        ${news.investors ? `<div class="investment-row"><span class="info-label">投资方:</span> <span class="info-value">${escapeHTML(news.investors)}</span></div>` : ''}
                    </div>` : ''}
                    ${news.url || news.source_url ? `
                    <a href="${news.url || news.source_url}" target="_blank" class="view-original-btn">查看原文</a>
                    ` : ''}
                `;
            } else {
                // 默认卡片样式
                const title = escapeHTML(news.title) || '无标题';
                const content = formatContent(escapeHTML(news.content) || '无内容');
                
                // 标题部分
                cardHeader.innerHTML = `<h2 class="news-title">${title}</h2>`;
                
                // 内容部分
                cardContent.innerHTML = `
                    <div class="news-content">
                        <p>${content}</p>
                    </div>
                `;
                
                // 底部信息部分
                cardFooter.innerHTML = `
                    <div class="news-meta">
                        ${news.author ? `<div class="news-author">作者: ${escapeHTML(news.author)}</div>` : ''}
                    </div>
                    ${news.url || news.source_url ? `
                    <a href="${news.url || news.source_url}" target="_blank" class="view-original-btn">查看原文</a>
                    ` : ''}
                `;
            }
            
            // 组装卡片
            cardWrapper.appendChild(cardHeader);
            cardWrapper.appendChild(cardContent);
            cardWrapper.appendChild(cardFooter);
            
            return cardWrapper;
        } catch (error) {
            console.error("创建新闻卡片时发生错误:", error, "新闻对象:", news);
            // 返回一个空的div作为fallback
            const errorDiv = document.createElement('div');
            errorDiv.className = 'news-card error-card';
            errorDiv.innerHTML = `<div class="error-message">加载卡片出错</div>`;
            return errorDiv;
        }
    }

    // 格式化内容，识别链接
    function formatContent(content) {
        if (!content) return '';

        // 为Crunchbase内容特殊处理
        if (currentSource === 'crunchbase.com' && !content.includes('<br/>')) {
            // 只有当内容中没有已处理的<br/>标签时才执行额外格式化
            // 检测Crunchbase特有的内容格式，确保有适当的换行
            content = content.replace(/([.:!?]) ([A-Z])/g, '$1\n$2');
        }

        // 链接识别正则表达式
        const urlRegex = /(https?:\/\/[^\s]+)/g;
        return content.replace(urlRegex, url => {
            return `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`;
        });
    }

    // HTML转义，防止XSS攻击
    function escapeHTML(text) {
        if (!text) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // 格式化数字，如1000 -> 1K
    function formatNumber(num) {
        if (!num || isNaN(num)) return '0';

        if (num >= 1000000) {
            return (num / 1000000).toFixed(1) + 'M';
        } else if (num >= 1000) {
            return (num / 1000).toFixed(1) + 'K';
        }

        return num.toString();
    }

    // 格式化URL，用于显示
    function formatUrlForDisplay(url) {
        if (!url) return '';
        return url.length > 50 ? url.substring(0, 50) + '...' : url;
    }

    // 滚动按钮功能
    const scrollToTopBtn = document.getElementById('scrollToTopBtn');
    const scrollToBottomBtn = document.getElementById('scrollToBottomBtn');
    
    // 检查滚动位置，显示/隐藏按钮
    function checkScrollPosition() {
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        const scrollHeight = document.documentElement.scrollHeight;
        const clientHeight = document.documentElement.clientHeight;
        const topThreshold = 200; // 顶部冗余空间
        const bottomThreshold = 200; // 底部冗余空间
        
        // 只在页面中间部分显示按钮，靠近顶部或底部时隐藏
        if (scrollTop > topThreshold && scrollTop + clientHeight < scrollHeight - bottomThreshold) {
            // 两个按钮同时显示
            scrollToTopBtn.classList.add('visible');
            scrollToBottomBtn.classList.add('visible');
        } else {
            // 两个按钮同时隐藏
            scrollToTopBtn.classList.remove('visible');
            scrollToBottomBtn.classList.remove('visible');
        }
    }
    
    // 滚动到顶部
    scrollToTopBtn.addEventListener('click', function() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });
    
    // 滚动到底部
    scrollToBottomBtn.addEventListener('click', function() {
        window.scrollTo({
            top: document.documentElement.scrollHeight,
            behavior: 'smooth'
        });
    });
    
    // 监听滚动事件
    window.addEventListener('scroll', checkScrollPosition);
    
    // 初始检查
    checkScrollPosition();

    // 事件委托处理
    document.addEventListener('click', function(event) {
        // 处理内容展开/收起逻辑
        if (event.target.className === 'toggle-content-btn') {
            event.stopPropagation();
            
            // 处理内容展开/收起逻辑
            const contentContainer = event.target.closest('.news-content');
            const collapsedText = contentContainer.querySelector('.content-text');
            const fullContent = contentContainer.querySelector('.full-content');
            
            if (fullContent.style.display === 'none') {
                // 展开内容
                collapsedText.style.display = 'none';
                fullContent.style.display = 'block';
                event.target.textContent = '收起内容';
            } else {
                // 收起内容
                collapsedText.style.display = 'block';
                fullContent.style.display = 'none';
                event.target.textContent = '显示全部';
            }
        }
    });
});