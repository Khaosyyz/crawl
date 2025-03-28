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

    // 刷新按钮点击事件
    if (refreshButton) {
        refreshButton.addEventListener('click', function() {
            forceRefreshData(); // 使用新的强制刷新函数
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
            
            // 更新当前数据源
            currentSource = this.dataset.source;
            
            // 重置为第一页
            currentPage = 1;
            
            // 如果是 Crunchbase，重置显示数量
            if (currentSource === 'crunchbase.com') {
                crunchbaseDisplayCount = 3;
            }
            
            // 如果有搜索内容，重新执行搜索
            if (currentSearchQuery) {
                performSearch();
            } else {
                // 否则直接过滤显示数据
                filterAndDisplayNews();
            }
        });
    });

    // 获取数据函数
    function fetchData() {
        // 标记为正在加载
        isLoading = true;
        
        // 显示加载状态
        newsContainer.innerHTML = '<div class="loading">正在加载资讯...</div>';
        
        // 构建API URL，添加date_page参数
        const apiUrl = `https://crawl-beta.vercel.app/api/articles?source=${currentSource}&date_page=${currentDatePage}`;
        
        // 执行第一个请求
        fetchAllPages(apiUrl);
    }
    
    // 获取所有页面的数据
    function fetchAllPages(apiUrl, currentPageNum = 1, allData = []) {
        fetch(`${apiUrl}&page=${currentPageNum}`, {
            method: 'GET',
            mode: 'cors',
            cache: 'no-cache',
            headers: {
                'Content-Type': 'application/json',
            },
        })
        .then(response => {
            // 检查HTTP状态
            if (!response.ok) {
                throw new Error(`HTTP错误 ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(result => {
            if (result.status === 'error') {
                showError(result.message);
                return;
            }
            
            // 将当前页面的数据添加到累积数据中
            const combinedData = [...allData, ...result.data];
            
            // 更新总页数
            totalPages = result.total_date_pages;
            
            // 如果总数大于9且当前页数小于总页数，获取下一页数据
            const total = result.total;
            const perPage = result.per_page;
            const totalNumPages = Math.ceil(total / perPage);
            
            if (currentPageNum < totalNumPages) {
                // 继续获取下一页
                fetchAllPages(apiUrl, currentPageNum + 1, combinedData);
            } else {
                // 所有页面数据获取完毕
                isLoading = false;
                
                // 恢复刷新按钮
                if (refreshButton) {
                    refreshButton.disabled = false;
                    refreshButton.classList.remove('disabled');
                }
                
                // 更新数据
                allNewsData = combinedData;
                
                // 处理并显示数据
                processAndDisplayNews(allNewsData);
                
                // 更新分页控件
                updatePagination();
            }
        })
        .catch(error => {
            // 标记加载完成
            isLoading = false;
            
            // 恢复刷新按钮
            if (refreshButton) {
                refreshButton.disabled = false;
                refreshButton.classList.remove('disabled');
            }
            
            showError(`获取数据失败: ${error.message}`);
        });
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
                showError(`没有和"${query}"相关的资讯`);
            } else {
                // 使用过滤后的结果
                const sourceFilteredResults = filteredResults.filter(item => item.source === currentSource);
                
                if (sourceFilteredResults.length === 0) {
                    showError(`在${getSourceName(currentSource)}中没有和"${query}"相关的资讯`);
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
            showError('请先加载数据，然后再搜索');
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
            showError(`暂无${getSourceName(currentSource)}资讯数据`);
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
        if (currentSource === 'crunchbase.com') {
            // 如果是 Crunchbase，使用显示更多逻辑
            crunchbaseNews = newsData;
            displayCrunchbaseNews();
        } else {
            // 其他来源使用日期分组显示
            displayCurrentPageNews(isSearchResult);
        }
    }
    
    // 显示 Crunchbase 新闻
    function displayCrunchbaseNews() {
        const newsContainer = document.getElementById('news-container');
        if (!newsContainer) return;

        // 清空现有内容
        newsContainer.innerHTML = '';

        // 如果没有数据，重新获取当前页的数据
        if (!crunchbaseNews || crunchbaseNews.length === 0) {
            isLoading = true;
            newsContainer.innerHTML = '<div class="loading">正在加载资讯...</div>';
            const apiUrl = `https://crawl-beta.vercel.app/api/articles?source=${currentSource}&date_page=${currentDatePage}`;
            fetch(`${apiUrl}`, {
                method: 'GET',
                mode: 'cors',
                cache: 'no-cache',
                headers: {
                    'Content-Type': 'application/json',
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
                    showError(result.message);
                    return;
                }
                crunchbaseNews = result.data;
                isLoading = false;
                displayCrunchbaseNews();
            })
            .catch(error => {
                isLoading = false;
                showError(`获取数据失败: ${error.message}`);
            });
            return;
        }

        // 按日期分组数据
        let dateGroups = {};
        crunchbaseNews.forEach(news => {
            // 提取日期部分 (YYYY-MM-DD)
            const dateStr = news.date_time ? news.date_time.split(' ')[0] : 'unknown';
            if (!dateGroups[dateStr]) {
                dateGroups[dateStr] = [];
            }
            dateGroups[dateStr].push(news);
        });

        // 获取所有日期并降序排序
        let allDates = Object.keys(dateGroups).sort().reverse();
        
        // 总日期页数
        const totalDatePages = Math.ceil(allDates.length / 3);
        
        // 确保当前日期页在有效范围内
        if (currentDatePage < 1) currentDatePage = 1;
        if (currentDatePage > totalDatePages) currentDatePage = totalDatePages;
        
        // 创建日期导航
        const dateNavContainer = document.createElement('div');
        dateNavContainer.className = 'date-tab-navigation';
        
        // 添加日期页导航按钮
        if (totalDatePages > 1) {
            // 前一日期页按钮
            if (currentDatePage > 1) {
                const prevDateBtn = document.createElement('button');
                prevDateBtn.className = 'date-page-btn prev-date';
                prevDateBtn.textContent = '前几天';
                prevDateBtn.addEventListener('click', () => {
                    currentDatePage--;
                    // 强制重新获取数据
                    crunchbaseNews = [];
                    displayCrunchbaseNews();
                });
                dateNavContainer.appendChild(prevDateBtn);
            }
            
            // 显示当前页/总页
            const pageInfo = document.createElement('div');
            pageInfo.className = 'date-page-info';
            pageInfo.textContent = `${currentDatePage} / ${totalDatePages}`;
            dateNavContainer.appendChild(pageInfo);
            
            // 后一日期页按钮
            if (currentDatePage < totalDatePages) {
                const nextDateBtn = document.createElement('button');
                nextDateBtn.className = 'date-page-btn next-date';
                nextDateBtn.textContent = '后几天';
                nextDateBtn.addEventListener('click', () => {
                    currentDatePage++;
                    // 强制重新获取数据
                    crunchbaseNews = [];
                    displayCrunchbaseNews();
                });
                dateNavContainer.appendChild(nextDateBtn);
            }
        }
        
        newsContainer.appendChild(dateNavContainer);
        
        // 计算当前日期页应显示的日期
        const startIdx = (currentDatePage - 1) * 3;
        const endIdx = Math.min(startIdx + 3, allDates.length);
        const currentDates = allDates.slice(startIdx, endIdx);
        
        // 遍历当前页的每个日期组
        currentDates.forEach(dateStr => {
            // 创建日期标题
            const dateHeader = document.createElement('div');
            dateHeader.className = 'date-header';
            dateHeader.textContent = formatDate(dateStr);
            newsContainer.appendChild(dateHeader);
            
            // 创建当前日期的新闻组容器
            const dateNewsContainer = document.createElement('div');
            dateNewsContainer.className = 'news-group crunchbase-style';
            dateNewsContainer.style.width = '100%'; // 确保宽度是100%
            dateNewsContainer.style.display = 'flex';
            dateNewsContainer.style.flexDirection = 'column';
            
            // 获取该日期的新闻 (每个日期最多展示3条)
            const dateNews = dateGroups[dateStr].slice(0, 3);
            dateNews.forEach(news => {
                const newsCard = createNewsCard(news);
                dateNewsContainer.appendChild(newsCard);
            });
            
            newsContainer.appendChild(dateNewsContainer);
            
            // 如果该日期有超过3条新闻，添加"查看更多"按钮
            if (dateGroups[dateStr].length > 3) {
                const moreBtn = document.createElement('div');
                moreBtn.className = 'expand-button';
                const moreLink = document.createElement('button');
                moreLink.textContent = `查看更多 (${dateGroups[dateStr].length - 3}条)`;
                
                // 创建隐藏容器，存放剩余新闻
                const hiddenContainer = document.createElement('div');
                hiddenContainer.className = 'hidden-news crunchbase-style';
                hiddenContainer.style.display = 'none';
                hiddenContainer.style.width = '100%'; // 确保宽度是100%
                hiddenContainer.style.flexDirection = 'column';
                
                // 添加剩余新闻
                dateGroups[dateStr].slice(3).forEach(news => {
                    const newsCard = createNewsCard(news);
                    hiddenContainer.appendChild(newsCard);
                });
                
                // 展开/收起切换逻辑
                moreLink.addEventListener('click', function() {
                    if (hiddenContainer.style.display === 'none') {
                        hiddenContainer.style.display = 'flex';
                        this.textContent = '收起';
                    } else {
                        hiddenContainer.style.display = 'none';
                        this.textContent = `查看更多 (${dateGroups[dateStr].length - 3}条)`;
                    }
                });
                
                moreBtn.appendChild(moreLink);
                newsContainer.appendChild(moreBtn);
                newsContainer.appendChild(hiddenContainer);
            }
        });

        // 显示分页控件，但修改为针对日期分页
        if (paginationContainer) {
            // 清空现有分页
            paginationContainer.innerHTML = '';
            
            // 总是显示分页，即使当前只有一页
            // 前一页按钮
            const prevBtn = document.createElement('button');
            prevBtn.innerHTML = '&laquo;';
            prevBtn.title = '上一页';
            
            if (currentDatePage > 1) {
                prevBtn.addEventListener('click', () => {
                    currentDatePage--;
                    // 强制重新获取数据
                    crunchbaseNews = [];
                    displayCrunchbaseNews();
                    window.scrollTo(0, 0);
                });
            } else {
                prevBtn.classList.add('disabled');
            }
            paginationContainer.appendChild(prevBtn);
            
            // 确定要显示的页码范围
            let startPage = Math.max(1, currentDatePage - 2);
            let endPage = Math.min(totalDatePages, startPage + 4);
            
            // 调整起始页以确保显示5个页码按钮（如果有这么多页）
            if (endPage - startPage < 4 && totalDatePages > 5) {
                startPage = Math.max(1, endPage - 4);
            }
            
            // 添加第一页按钮（如果不在显示范围内）
            if (startPage > 1) {
                const firstBtn = document.createElement('button');
                firstBtn.textContent = '1';
                firstBtn.addEventListener('click', () => {
                    currentDatePage = 1;
                    // 强制重新获取数据
                    crunchbaseNews = [];
                    displayCrunchbaseNews();
                    window.scrollTo(0, 0);
                });
                paginationContainer.appendChild(firstBtn);
                
                // 添加省略号（如果需要）
                if (startPage > 2) {
                    const ellipsis = document.createElement('button');
                    ellipsis.textContent = '...';
                    ellipsis.classList.add('disabled');
                    paginationContainer.appendChild(ellipsis);
                }
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
                        crunchbaseNews = [];
                        displayCrunchbaseNews();
                        window.scrollTo(0, 0);
                    });
                }
                paginationContainer.appendChild(pageBtn);
            }
            
            // 添加省略号和最后一页按钮（如果需要）
            if (endPage < totalDatePages) {
                // 添加省略号（如果需要）
                if (endPage < totalDatePages - 1) {
                    const ellipsis = document.createElement('button');
                    ellipsis.textContent = '...';
                    ellipsis.classList.add('disabled');
                    paginationContainer.appendChild(ellipsis);
                }
                
                const lastBtn = document.createElement('button');
                lastBtn.textContent = totalDatePages.toString();
                lastBtn.addEventListener('click', () => {
                    currentDatePage = totalDatePages;
                    // 强制重新获取数据
                    crunchbaseNews = [];
                    displayCrunchbaseNews();
                    window.scrollTo(0, 0);
                });
                paginationContainer.appendChild(lastBtn);
            }
            
            // 后一页按钮
            const nextBtn = document.createElement('button');
            nextBtn.innerHTML = '&raquo;';
            nextBtn.title = '下一页';
            
            if (currentDatePage < totalDatePages) {
                nextBtn.addEventListener('click', () => {
                    currentDatePage++;
                    // 强制重新获取数据
                    crunchbaseNews = [];
                    displayCrunchbaseNews();
                    window.scrollTo(0, 0);
                });
            } else {
                nextBtn.classList.add('disabled');
            }
            paginationContainer.appendChild(nextBtn);
            
            // 确保分页控件始终显示
            paginationContainer.style.display = 'flex';
        }
    }

    // 更新分页控件
    function updatePagination() {
        if (!paginationContainer) return;
        
        paginationContainer.innerHTML = '';
        
        // 如果总页数小于等于1，不显示分页控件
        if (totalPages <= 1) return;
        
        // 添加上一页按钮
        const prevBtn = document.createElement('button');
        prevBtn.innerHTML = '&laquo;';
        prevBtn.title = '上一页';
        prevBtn.classList.add(currentPage === 1 ? 'disabled' : 'prev-page');
        if (currentPage !== 1) {
            prevBtn.addEventListener('click', () => goToPage(currentPage - 1));
        }
        paginationContainer.appendChild(prevBtn);
        
        // 确定要显示的页码范围
        let startPage = Math.max(1, currentPage - 2);
        let endPage = Math.min(totalPages, startPage + 4);
        
        // 调整起始页以确保显示5个页码按钮（如果有这么多页）
        if (endPage - startPage < 4 && totalPages > 5) {
            startPage = Math.max(1, endPage - 4);
        }
        
        // 添加第一页按钮（如果不在显示范围内）
        if (startPage > 1) {
            const firstBtn = document.createElement('button');
            firstBtn.textContent = '1';
            firstBtn.addEventListener('click', () => goToPage(1));
            paginationContainer.appendChild(firstBtn);
            
            // 添加省略号（如果需要）
            if (startPage > 2) {
                const ellipsis = document.createElement('button');
                ellipsis.textContent = '...';
                ellipsis.classList.add('disabled');
                paginationContainer.appendChild(ellipsis);
            }
        }
        
        // 添加页码按钮
        for (let i = startPage; i <= endPage; i++) {
            const pageBtn = document.createElement('button');
            pageBtn.textContent = i.toString();
            if (i === currentPage) {
                pageBtn.classList.add('active');
            } else {
                pageBtn.addEventListener('click', () => goToPage(i));
            }
            paginationContainer.appendChild(pageBtn);
        }
        
        // 添加省略号和最后一页按钮（如果需要）
        if (endPage < totalPages) {
            // 添加省略号（如果需要）
            if (endPage < totalPages - 1) {
                const ellipsis = document.createElement('button');
                ellipsis.textContent = '...';
                ellipsis.classList.add('disabled');
                paginationContainer.appendChild(ellipsis);
            }
            
            const lastBtn = document.createElement('button');
            lastBtn.textContent = totalPages.toString();
            lastBtn.addEventListener('click', () => goToPage(totalPages));
            paginationContainer.appendChild(lastBtn);
        }
        
        // 添加下一页按钮
        const nextBtn = document.createElement('button');
        nextBtn.innerHTML = '&raquo;';
        nextBtn.title = '下一页';
        nextBtn.classList.add(currentPage === totalPages ? 'disabled' : 'next-page');
        if (currentPage !== totalPages) {
            nextBtn.addEventListener('click', () => goToPage(currentPage + 1));
        }
        paginationContainer.appendChild(nextBtn);
    }
    
    // 跳转到指定页
    function goToPage(page) {
        if (page < 1 || page > totalPages || page === currentPage) return;
        
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
    
    // 显示当前页的新闻
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
            showError(isSearchResult ? '没有找到匹配的结果' : '暂无资讯数据');
            return;
        }
        
        // 按日期分组数据
        groupedNewsByDate = groupNewsByDate(allNewsData);
        dateKeys = Object.keys(groupedNewsByDate).sort().reverse();
        
        // 检查是否有日期数据
        if (dateKeys.length === 0) {
            showError(isSearchResult ? '没有找到匹配的结果' : '暂无资讯数据');
            return;
        }
        
        // 遍历每个日期组
        dateKeys.forEach(date => {
            // 创建日期分组标题
            const dateHeader = document.createElement('div');
            dateHeader.className = 'date-header';
            dateHeader.textContent = formatDate(date);
            dateHeader.dataset.date = date;  // 添加日期数据属性，用于后续处理
            
            newsContainer.appendChild(dateHeader);
        
            const dateGroup = groupedNewsByDate[date];
        
            // 创建新闻卡片容器
            const groupContainer = document.createElement('div');
            groupContainer.className = 'news-group';
            groupContainer.dataset.date = date;
        
            // 初始只显示前9条新闻
            const initialNews = dateGroup.slice(0, 9);
            initialNews.forEach(news => {
                const newsCard = createNewsCard(news);
                groupContainer.appendChild(newsCard);
            });
        
            newsContainer.appendChild(groupContainer);

            // 创建按钮容器
            const buttonContainer = document.createElement('div');
            buttonContainer.className = 'news-buttons-container';
            newsContainer.appendChild(buttonContainer);

            // 如果该日期组有超过9条新闻，添加"显示更多"按钮
            if (dateGroup.length > 9) {
                const loadMoreButton = document.createElement('button');
                loadMoreButton.className = 'load-more-button';
                loadMoreButton.textContent = '显示更多';
                loadMoreButton.dataset.date = date;
                
                // 额外的新闻卡片容器 (用于存放剩余新闻)
                const extraNewsContainer = document.createElement('div');
                extraNewsContainer.className = 'extra-news-container';
                extraNewsContainer.style.display = 'none'; // 初始隐藏
                extraNewsContainer.dataset.date = date;
                
                // 准备剩余的新闻卡片
                const remainingNews = dateGroup.slice(9);
                remainingNews.forEach(news => {
                    const newsCard = createNewsCard(news);
                    extraNewsContainer.appendChild(newsCard);
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

    // 按日期分组新闻
    function groupNewsByDate(newsData) {
        const grouped = {};
        
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
            const card = document.createElement('article');
            card.className = 'news-card';
            
            // 获取新闻数据，适配新的 API 数据结构
            const source = news.source || '';
            const sourceUrl = news.source_url || '';
            const title = news.title || '';
            const content = news.content || '';
            const dateTime = news.date_time || '';
            let author = news.author || '';
            
            // 使用正确的字段名来获取统计数据
            let followersCount = news.followers || news.followers_count || 0; // 兼容两种可能的字段名
            let favoriteCount = news.likes || news.favorite_count || 0; // 兼容两种可能的字段名
            let retweetCount = news.retweets || news.retweet_count || 0; // 兼容两种可能的字段名
            
            // 根据来源设置不同的样式并构建卡片
            if (source === 'x.com') {
                card.classList.add('x-news');
                
                // 提取日期和时间部分
                const dateStr = extractDate(dateTime);
                const timeStr = extractTime(dateTime);
                
                // 构建X.com三段式卡片
                // 第一段：标题(左)和时间(右)
                let cardHTML = '<div class="news-card-header">';
                if (title) {
                    cardHTML += `<h3 class="news-title">${escapeHtml(title)}</h3>`;
                }
                if (timeStr) {
                    cardHTML += `<div class="news-time">${formatTime(timeStr)}</div>`;
                }
                cardHTML += '</div>';
                
                // 第二段：正文内容
                cardHTML += `<div class="news-content">${formatContent(content)}</div>`;
                
                // 第三段：作者、社交数据、来源
                cardHTML += '<div class="news-footer">';
                
                // 第一行：作者
                if (author) {
                    cardHTML += `<div class="news-author">作者: ${escapeHtml(author)}</div>`;
                }
                
                // 第二行：社交数据 (粉丝、点赞、转发)
                cardHTML += '<div class="news-social-stats">';
                cardHTML += `<span>粉丝数量：${formatNumber(followersCount)}</span>`;
                cardHTML += `<span>点赞数量：${formatNumber(favoriteCount)}</span>`;
                cardHTML += `<span>转发数量：${formatNumber(retweetCount)}</span>`;
                cardHTML += '</div>';
                
                // 第三行：来源地址
                cardHTML += `<div class="news-source">来源地址：<a href="${sourceUrl}" target="_blank">${formatUrlForDisplay(sourceUrl)}</a></div>`;
                
                cardHTML += '</div>'; // 结束 news-footer
                
                // 设置卡片内容
                card.innerHTML = cardHTML;
            } else if (source === 'crunchbase.com') {
                // 使用三段式结构显示Crunchbase卡片
                card.classList.add('crunchbase-news');
                card.style.width = '100%'; // 确保宽度是100%
                
                // 构建卡片 HTML
                let cardHTML = '';
                
                // 第一段：标题部分
                if (title) {
                    cardHTML += `<h3 class="news-title">${escapeHtml(title)}</h3>`;
                }
                
                // 第二段：内容部分（折叠式）
                cardHTML += `<div class="news-content collapsed">${formatContent(content)}</div>`;
                cardHTML += '<div class="content-toggle" onclick="this.previousElementSibling.classList.toggle(\'collapsed\'); this.textContent = this.previousElementSibling.classList.contains(\'collapsed\') ? \'显示全部\' : \'收起内容\';">显示全部</div>';
                
                // 第三段：元数据部分
                cardHTML += '<div class="news-footer">';
                
                // 添加作者信息（如果有）
                if (author) {
                    cardHTML += `<div class="news-author">作者: ${escapeHtml(author)}</div>`;
                }
                
                // 添加Crunchbase特有字段
                cardHTML += '<div class="news-investment-info">';
                
                // 公司信息
                if (news.company && news.company !== '未提供') {
                    cardHTML += `<div class="investment-row">
                        <span class="info-label">公司:</span>
                        <span class="info-value">${escapeHtml(news.company)}</span>
                    </div>`;
                }
                
                // 融资轮次
                if (news.funding_round && news.funding_round !== '未提供') {
                    cardHTML += `<div class="investment-row">
                        <span class="info-label">融资轮次:</span>
                        <span class="info-value">${escapeHtml(news.funding_round)}</span>
                    </div>`;
                }
                
                // 融资金额
                if (news.funding_amount && news.funding_amount !== '未提供') {
                    cardHTML += `<div class="investment-row">
                        <span class="info-label">融资金额:</span>
                        <span class="info-value">${escapeHtml(news.funding_amount)}</span>
                    </div>`;
                }
                
                // 投资方
                if (news.investors && news.investors !== '未提供') {
                    cardHTML += `<div class="investment-row">
                        <span class="info-label">投资方:</span>
                        <span class="info-value">${escapeHtml(news.investors)}</span>
                    </div>`;
                }
                
                cardHTML += '</div>'; // 结束 news-investment-info
                
                // 日期和来源链接
                cardHTML += `<div class="news-meta">
                    <div class="news-date">发布时间: ${formatDate(dateTime)}</div>
                    <div class="news-source-link">原文链接: <a href="${sourceUrl}" target="_blank">${formatUrlForDisplay(sourceUrl)}</a></div>
                </div>`;
                
                cardHTML += '</div>'; // 结束 news-footer
                
                // 设置卡片内容
                card.innerHTML = cardHTML;
            } else {
                // 其他来源的默认卡片结构
                // 构建卡片 HTML
                let cardHTML = '';
                
                // 标题部分（如果有）
                if (title) {
                    cardHTML += `<h3 class="news-title">${escapeHtml(title)}</h3>`;
                }
                
                // 内容部分
                cardHTML += `<div class="news-content">${formatContent(content)}</div>`;
                
                // 元数据部分
                cardHTML += '<div class="news-meta">';
                
                // 日期和来源
                cardHTML += `<div class="news-date">${formatDate(dateTime)}</div>`;
                cardHTML += `<div class="news-source">来源: <a href="${sourceUrl}" target="_blank">${formatUrlForDisplay(sourceUrl)}</a></div>`;
                
                cardHTML += '</div>'; // 结束 news-meta
                
                // 设置卡片内容
                card.innerHTML = cardHTML;
            }
            
            return card;
        } catch (e) {
            console.error('创建新闻卡片出错:', e, news);
            const card = document.createElement('article');
            card.className = 'news-card error-card';
            card.innerHTML = '<div class="error-message">无法显示此条资讯</div>';
            return card;
        }
    }

    // 显示错误信息
    function showError(message) {
        if (newsContainer) {
            newsContainer.innerHTML = `<div class="loading">${message}</div>`;
        } else {
            console.error('无法显示错误信息:', message);
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
    function escapeHtml(text) {
        if (!text) return '';
        return text
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
});