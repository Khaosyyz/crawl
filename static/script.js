document.addEventListener('DOMContentLoaded', function() {
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
        
        fetch('/api/news')
            .then(response => {
                // 检查HTTP状态
                if (!response.ok) {
                    throw new Error(`HTTP错误 ${response.status}: ${response.statusText}`);
                }
                return response.json();
            })
            .then(result => {
                // 标记加载完成
                isLoading = false;
                
                // 恢复刷新按钮
                if (refreshButton) {
                    refreshButton.disabled = false;
                    refreshButton.classList.remove('disabled');
                }
                
                if (result.status === 'error') {
                    showError(result.message);
                    return;
                }

                // 保存所有数据
                allNewsData = result.data || [];

                // 重置为第一页
                currentPage = 1;
                
                // 根据当前选中的标签过滤并显示新闻
                filterAndDisplayNews();
            })
            .catch(error => {
                // 标记加载完成
                isLoading = false;
                
                // 恢复刷新按钮
                if (refreshButton) {
                    refreshButton.disabled = false;
                    refreshButton.classList.remove('disabled');
                }
                
                console.error('获取数据失败:', error);
                showError('获取数据失败，请稍后再试: ' + error.message);
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
            filterAndDisplayNews();
            return;
        }

        // 使用后端API进行搜索
        fetch(`/api/search?q=${encodeURIComponent(query)}`)
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

                // 获取搜索结果并根据当前标签过滤
                if (result.no_results) {
                    showError(`没有和"${query}"相关的资讯`);
                } else {
                    const searchData = result.data || [];
                    // 根据当前选中的标签再次过滤搜索结果
                    const filteredSearchData = filterBySource(searchData);
                    
                    if (filteredSearchData.length === 0) {
                        showError(`没有和"${query}"相关的${getSourceName(currentSource)}资讯`);
                    } else {
                        // 处理分页
                        processAndDisplayNews(filteredSearchData, true);
                    }
                }
            })
            .catch(error => {
                console.error('搜索失败:', error);
                showError('搜索处理失败，请稍后再试: ' + error.message);
            });
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
            // 其他来源使用原有的分页逻辑
            groupedNewsByDate = groupNewsByDate(newsData);
            dateKeys = Object.keys(groupedNewsByDate).sort().reverse();
            displayCurrentPageNews(isSearchResult);
        }
    }
    
    // 显示 Crunchbase 新闻
    function displayCrunchbaseNews() {
        const newsContainer = document.getElementById('news-container');
        if (!newsContainer) return;

        // 清空现有内容
        newsContainer.innerHTML = '';

        // 显示指定数量的新闻
        const displayNews = crunchbaseNews.slice(0, crunchbaseDisplayCount);
        displayNews.forEach(news => {
            const newsCard = createNewsCard(news);
            newsContainer.appendChild(newsCard);
        });

        // 如果还有更多新闻，显示"显示更多"按钮
        if (crunchbaseDisplayCount < crunchbaseNews.length) {
            const loadMoreButton = document.createElement('button');
            loadMoreButton.className = 'load-more-button';
            loadMoreButton.textContent = '显示更多';
            loadMoreButton.onclick = () => {
                crunchbaseDisplayCount += 3;
                displayCrunchbaseNews();
            };
            newsContainer.appendChild(loadMoreButton);
        }

        // 隐藏分页控件
        if (paginationContainer) {
            paginationContainer.style.display = 'none';
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
        if (!dateKeys || dateKeys.length === 0) {
            showError(isSearchResult ? '没有找到匹配的结果' : '暂无资讯数据');
            return;
        }
        
        // 计算当前页应该显示的日期范围
        const startIndex = (currentPage - 1) * DATES_PER_PAGE;
        const endIndex = Math.min(startIndex + DATES_PER_PAGE, dateKeys.length);
        
        // 获取当前页的日期
        const currentPageDates = dateKeys.slice(startIndex, endIndex);
        
        // 遍历当前页的每个日期组
        currentPageDates.forEach(date => {
            // 创建日期分组标题
            const dateHeader = document.createElement('div');
            dateHeader.className = 'date-header';
            dateHeader.textContent = formatDate(date);
            dateHeader.dataset.date = date;  // 添加日期数据属性，用于后续处理
            
            newsContainer.appendChild(dateHeader);
        
            const dateGroup = groupedNewsByDate[date];
        
            // 创建新闻卡片容器
            const groupContainer = document.createElement('div');
            // 根据当前数据源设置不同的布局方式
            if (currentSource === 'crunchbase.com') {
                groupContainer.className = 'news-group crunchbase-style';
            } else {
                groupContainer.className = 'news-group';
            }
            groupContainer.dataset.date = date;
        
            // 是否需要"展开更多"按钮
            const needsExpansion = dateGroup.length > DEFAULT_NEWS_PER_DATE;
        
            // 添加初始可见的新闻
            const initialItems = dateGroup.slice(0, DEFAULT_NEWS_PER_DATE);
            initialItems.forEach(news => {
                const newsCard = createNewsCard(news);
                groupContainer.appendChild(newsCard);
            });
        
            newsContainer.appendChild(groupContainer);
        
            // 如果有更多新闻，添加展开按钮和隐藏的新闻容器
            if (needsExpansion) {
                // 创建隐藏的容器用于存放额外的新闻
                const hiddenContainer = document.createElement('div');
                // 根据当前数据源设置不同的布局方式
                if (currentSource === 'crunchbase.com') {
                    hiddenContainer.className = 'news-group hidden-news crunchbase-style';
                } else {
                    hiddenContainer.className = 'news-group hidden-news';
                }
                hiddenContainer.id = `hidden-news-${date.replace(/[^a-zA-Z0-9]/g, '-')}`;
                hiddenContainer.style.display = 'none';
        
                // 添加剩余的新闻
                const hiddenItems = dateGroup.slice(DEFAULT_NEWS_PER_DATE);
                hiddenItems.forEach(news => {
                    const newsCard = createNewsCard(news);
                    hiddenContainer.appendChild(newsCard);
                });
        
                newsContainer.appendChild(hiddenContainer);
        
                // 创建"展开更多"按钮
                const expandButton = document.createElement('div');
                expandButton.className = 'expand-button';
                expandButton.innerHTML = `<button>展开更多 (${hiddenItems.length})</button>`;
                expandButton.dataset.date = date;
                expandButton.dataset.expanded = 'false';
        
                // 添加点击事件
                expandButton.addEventListener('click', function() {
                    const dateKey = this.dataset.date;
                    const hiddenNewsId = `hidden-news-${dateKey.replace(/[^a-zA-Z0-9]/g, '-')}`;
                    const hiddenNews = document.getElementById(hiddenNewsId);
        
                    if (this.dataset.expanded === 'false') {
                        // 根据当前数据源使用不同的展开方式
                        if (currentSource === 'crunchbase.com') {
                            hiddenNews.style.display = 'flex';  // 使用flex布局而不是grid
                        } else {
                            hiddenNews.style.display = 'grid';
                        }
                        this.querySelector('button').textContent = '收起';
                        this.dataset.expanded = 'true';
                    } else {
                        hiddenNews.style.display = 'none';
                        this.querySelector('button').textContent = `展开更多 (${hiddenItems.length})`;
                        this.dataset.expanded = 'false';
                    }
                });
        
                newsContainer.appendChild(expandButton);
            }
        });
    }

    // 按日期分组新闻
    function groupNewsByDate(newsData) {
        const grouped = {};
        
        newsData.forEach(news => {
            // 优先使用 date_time 字段，如果不存在则尝试使用 published_date 或 published_at 字段
            let dateStr = '未知日期';
            
            if (news.date_time) {
                // 处理 date_time 格式（可能包含时间部分）
                dateStr = news.date_time.split(' ')[0];
            } else if (news.published_date) {
                // 直接使用 published_date（通常只有日期部分）
                dateStr = news.published_date;
            } else if (news.published_at) {
                // 使用 published_at 字段（X.com数据使用这个字段）
                dateStr = news.published_at.split(' ')[0];
            }
            
            if (!grouped[dateStr]) {
                grouped[dateStr] = [];
            }
            
            grouped[dateStr].push(news);
        });
        
        return grouped;
    }

    // 格式化日期显示
    function formatDate(dateStr) {
        if (dateStr === '未知日期') return dateStr;

        try {
            const date = new Date(dateStr);
            const now = new Date();
            const yesterday = new Date(now);
            yesterday.setDate(now.getDate() - 1);

            // 如果是今天或昨天，显示特殊文本
            if (isSameDay(date, now)) {
                return '今天 · ' + dateStr;
            } else if (isSameDay(date, yesterday)) {
                return '昨天 · ' + dateStr;
            } else {
                // 否则显示常规日期格式
                return dateStr;
            }
        } catch (e) {
            return dateStr;
        }
    }

    // 判断两个日期是否是同一天
    function isSameDay(d1, d2) {
        return d1.getFullYear() === d2.getFullYear() &&
               d1.getMonth() === d2.getMonth() &&
               d1.getDate() === d2.getDate();
    }

    // 创建新闻卡片
    function createNewsCard(news) {
        const newsCard = document.createElement('div');
        newsCard.className = 'news-card';

        // 获取时间部分 (HH:MM)
        let timeStr = '';
        if (news.date_time) {
            timeStr = news.date_time.split(' ')[1] || '';
        } else if (news.published_at && news.source === 'x.com') {
            // 对于X.com数据，从published_at获取时间部分
            timeStr = news.published_at.split(' ')[1] || '';
        }

        // 格式化内容，保留链接
        const formattedContent = formatContent(news.content);
        
        // 创建卡片内容HTML
        let cardHTML = `
            <div class="news-header">
                <h2 class="news-title">${escapeHtml(news.title)}</h2>
                <div class="news-time">${timeStr}</div>
            </div>`;
        
        // 为Crunchbase内容添加特殊处理
        if (news.source === 'crunchbase.com') {
            const contentId = `content-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
            cardHTML += `
                <div id="${contentId}" class="news-content collapsed">${formattedContent}</div>
                <div class="content-toggle" data-content-id="${contentId}">显示更多</div>
            `;
        } else {
            cardHTML += `<div class="news-content">${formattedContent}</div>`;
        }
        
        // 创建底部信息 - 根据来源显示不同信息
        if (news.source === 'crunchbase.com') {
            // 为Crunchbase内容创建专用的底部信息
            
            // 直接使用数据库中的字段，而不是从内容中提取
            const investmentAmount = news.investment_amount || 'N/A';
            const investors = Array.isArray(news.investors) ? news.investors : [];
            const companyProduct = news.company_product || '未知';
            const sourceUrl = news.source_url || ''; // 获取来源URL
            
            // 创建唯一ID用于展开/收起投资者信息
            const investorsId = `investors-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
            // 创建唯一ID用于展开/收起投资金额信息
            const amountId = `amount-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
            
            // 改进投资者列表展示逻辑
            let previewInvestors = '';
            let moreInvestors = '';
            let hasMoreInvestors = false;
            
            if (investors.length > 0) {
                if (investors.length > 2) {
                    // 只显示前两个，其余作为"更多"内容
                    previewInvestors = investors.slice(0, 2).join(', ');
                    moreInvestors = investors.slice(2).join(', ');
                    hasMoreInvestors = true;
                } else {
                    previewInvestors = investors.join(', ');
                }
            } else {
                previewInvestors = '无数据';
            }
            
            // 添加投资金额展示逻辑
            const MAX_AMOUNT_LENGTH = 30; // 设置最大显示长度
            let previewAmount = '';
            let moreAmount = '';
            let hasMoreAmount = false;
            
            if (investmentAmount && investmentAmount !== 'N/A' && investmentAmount.length > MAX_AMOUNT_LENGTH) {
                previewAmount = investmentAmount.substring(0, MAX_AMOUNT_LENGTH);
                moreAmount = investmentAmount.substring(MAX_AMOUNT_LENGTH);
                hasMoreAmount = true;
            } else {
                previewAmount = investmentAmount;
            }
            
            // 构建卡片HTML
            cardHTML += `
                <div class="news-footer crunchbase-footer">
                    <div class="news-author">${escapeHtml(news.author)}</div>
                    <div class="news-investment-info">
                        <div class="investment-row">
                            <span class="info-label">公司/产品:</span>
                            <span class="info-value">${escapeHtml(companyProduct)}</span>
                        </div>
                        <div class="investment-row">
                            <span class="info-label">投资金额:</span>
                            <div class="investor-container">
                                <span class="info-value investors-preview">${previewAmount}</span>
                                ${hasMoreAmount ? 
                                    `<span class="more-indicator">...</span>
                                     <span class="investors-toggle" data-state="collapsed" data-id="${amountId}">展开</span>
                                     <div id="${amountId}" class="more-investors" style="display: none;">
                                        <span class="more-content">${moreAmount}</span>
                                        <span class="investors-toggle" data-state="expanded" data-id="${amountId}">收起</span>
                                     </div>` 
                                    : ''}
                            </div>
                        </div>
                        <div class="investment-row">
                            <span class="info-label">投资方:</span>
                            <div class="investor-container">
                                <span class="info-value investors-preview">${previewInvestors}</span>
                                ${hasMoreInvestors ? 
                                    `<span class="more-indicator">...</span>
                                     <span class="investors-toggle" data-state="collapsed" data-id="${investorsId}">展开</span>
                                     <div id="${investorsId}" class="more-investors" style="display: none;">
                                        <span class="more-content">, ${moreInvestors}</span>
                                        <span class="investors-toggle" data-state="expanded" data-id="${investorsId}">收起</span>
                                     </div>` 
                                    : ''}
                            </div>
                        </div>
                    </div>
                    ${sourceUrl ? `<div class="news-source-link">来源：<a href="${sourceUrl}" target="_blank" rel="noopener noreferrer">${formatUrlForDisplay(sourceUrl)}</a></div>` : ''}
                </div>
            `;
        } else {
            // 保持X平台的原有显示方式，但添加来源链接
            const sourceUrl = news.source_url || ''; // 获取来源URL
            
            cardHTML += `
                <div class="news-footer">
                    <div class="news-author">${escapeHtml(news.author)}</div>
                    <div class="news-stats">
                        <span>粉丝: ${formatNumber(news.meta?.followers || news.stats?.followers_count || 0)}</span>
                        <span>点赞: ${formatNumber(news.meta?.likes || news.stats?.favorite_count || 0)}</span>
                        <span>转发: ${formatNumber(news.meta?.retweets || news.stats?.retweet_count || 0)}</span>
                    </div>
                    ${sourceUrl ? `<div class="news-source-link">来源：<a href="${sourceUrl}" target="_blank" rel="noopener noreferrer">${formatUrlForDisplay(sourceUrl)}</a></div>` : ''}
                </div>
            `;
        }
        
        newsCard.innerHTML = cardHTML;
        
        // 为Crunchbase内容添加展开/折叠事件处理
        if (news.source === 'crunchbase.com') {
            // 添加内容展开/折叠功能
            const toggleButton = newsCard.querySelector('.content-toggle');
            if (toggleButton) {
                toggleButton.addEventListener('click', function() {
                    const contentId = this.getAttribute('data-content-id');
                    const contentElement = document.getElementById(contentId);
                    
                    if (contentElement.classList.contains('collapsed')) {
                        contentElement.classList.remove('collapsed');
                        this.textContent = '收起';
                    } else {
                        contentElement.classList.add('collapsed');
                        this.textContent = '显示更多';
                    }
                });
            }
            
            // 改进投资者信息展开/折叠功能
            const investorsToggles = newsCard.querySelectorAll('.investors-toggle');
            if (investorsToggles.length > 0) {
                investorsToggles.forEach(toggle => {
                    toggle.addEventListener('click', function() {
                        const toggleId = this.getAttribute('data-id');
                        const moreContent = document.getElementById(toggleId);
                        const moreIndicator = this.closest('.investor-container').querySelector('.more-indicator');
                        const state = this.getAttribute('data-state');
                        
                        if (state === 'collapsed') {
                            // 展开显示
                            moreContent.style.display = 'inline';
                            if (moreIndicator) moreIndicator.style.display = 'none';
                            // 隐藏"展开"按钮
                            const collapsedButtons = this.closest('.investor-container').querySelectorAll('.investors-toggle[data-state="collapsed"]');
                            collapsedButtons.forEach(btn => btn.style.display = 'none');
                        } else {
                            // 收起显示
                            moreContent.style.display = 'none';
                            if (moreIndicator) moreIndicator.style.display = 'inline';
                            // 显示"展开"按钮
                            const collapsedButtons = this.closest('.investor-container').querySelectorAll('.investors-toggle[data-state="collapsed"]');
                            collapsedButtons.forEach(btn => btn.style.display = 'inline');
                        }
                    });
                });
            }
        }

        return newsCard;
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