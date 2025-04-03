document.addEventListener('DOMContentLoaded', () => {
    // --- Global State ---
    const state = {
        x: { currentPage: 1, currentDatePage: 1, currentSource: 'x.com' },
        crunchbase: { currentPage: 1, currentDatePage: 1, currentSource: 'crunchbase.com' }, // 数据库中实际存储的源ID
        activeSource: 'x' // 'x' or 'crunchbase'
    };

    // --- Constants ---
    const API_BASE_URL = '/api/articles'; // 使用相对路径，指向 Vercel 上的 API
    const TEST_API_URL = '/api/all-articles'; // 测试API端点，不进行日期过滤
    const USE_TEST_API = true; // 保持使用测试API端点
    const ARTICLES_PER_PAGE = { x: 9, crunchbase: 3 }; // Different sources per page articles

    // 缓存配置
    const CACHE_ENABLED = true; // 全局缓存开关
    const CACHE_EXPIRY = {
        DEFAULT: 30 * 60 * 1000, // 默认30分钟
        HOME_PAGE: 15 * 60 * 1000, // 首页15分钟
        ARCHIVE: 24 * 60 * 60 * 1000 // 归档内容24小时
    };
    const DB_VERSION = 1; // 数据库版本号，用于升级
    const DB_NAME = 'crawArticleCache'; // 数据库名称

    // --- DOM Elements ---
    const loadingIndicator = document.getElementById('loading-indicator');
    const errorMessageDiv = document.getElementById('error-message');
    const tabLinks = document.querySelectorAll('.tab-link');
    const tabContents = document.querySelectorAll('.tab-content');

    // Map elements for easier access (add more as needed)
    const elements = {
        x: {
            container: document.getElementById('articles-x'),
            contentDiv: document.getElementById('x-content'),
            pagination: document.getElementById('pagination-x'), // Article pagination container
            prevDateBtn: document.getElementById('prev-date-page-x'), // Previous date page button
            nextDateBtn: document.getElementById('next-date-page-x'), // Next date page button
            dateInfo: document.getElementById('date-page-info-x') // Date information display
        },
        crunchbase: {
            container: document.getElementById('articles-crunchbase'),
            contentDiv: document.getElementById('crunchbase-content'),
            pagination: document.getElementById('pagination-crunchbase'), // Article pagination container
            prevDateBtn: document.getElementById('prev-date-page-crunchbase'), // Previous date page button
            nextDateBtn: document.getElementById('next-date-page-crunchbase'), // Next date page button
            dateInfo: document.getElementById('date-page-info-crunchbase') // Date information display
        }
    };

    // --- UI Helper Functions ---
    function showLoading() {
        if (loadingIndicator) loadingIndicator.style.display = 'block';
    }

    function hideLoading() {
        if (loadingIndicator) loadingIndicator.style.display = 'none';
    }

    function showError(message) {
        if (errorMessageDiv) {
            errorMessageDiv.textContent = message;
            errorMessageDiv.style.display = 'block';
        }
    }

    function hideError() {
        if (errorMessageDiv) errorMessageDiv.style.display = 'none';
    }

    function clearContainer(sourceKey) {
        if (elements[sourceKey]) {
            if (elements[sourceKey].container) {
                elements[sourceKey].container.innerHTML = '';
            }
            if (elements[sourceKey].pagination) { // Clear article pagination
                elements[sourceKey].pagination.innerHTML = '';
            }
            if (elements[sourceKey].dateInfo) { // Reset date information
                elements[sourceKey].dateInfo.textContent = 'Date range';
            }
             // Initialize date buttons disabled
             if(elements[sourceKey].prevDateBtn) elements[sourceKey].prevDateBtn.disabled = true;
             if(elements[sourceKey].nextDateBtn) elements[sourceKey].nextDateBtn.disabled = true;
        }
    }

    // --- Date Information and Pagination Button Update Functions ---
    function updateDateInfo(sourceKey, dateRange, currentDatePage, totalDatePages) {
         const dateInfoEl = elements[sourceKey].dateInfo;
         if (dateInfoEl) {
            if (dateRange && dateRange.start && dateRange.end) {
                // Use total_date_pages from API
                dateInfoEl.textContent = `Date: ${dateRange.start} ~ ${dateRange.end} (Page ${currentDatePage} / ${totalDatePages || 'Unknown'} of ${totalDatePages || 'Unknown'} pages)`;
            } else {
                dateInfoEl.textContent = `Date range not available (Page ${currentDatePage} / ${totalDatePages || 'Unknown'} of ${totalDatePages || 'Unknown'} pages)`;
            }
        } else {
             console.warn(`Date information element not found for source ${sourceKey}`);
         }
    }

    function updateDatePaginationButtons(sourceKey, currentDatePage, totalDatePages) {
        const prevBtn = elements[sourceKey].prevDateBtn;
        const nextBtn = elements[sourceKey].nextDateBtn;
        if (prevBtn) {
            prevBtn.disabled = currentDatePage <= 1;
        }
        if (nextBtn) {
             // totalDatePages can be 0 or 1, ensure >= check is correct
            nextBtn.disabled = !totalDatePages || currentDatePage >= totalDatePages;
        }
    }

    // --- 文章分组辅助函数 ---
    function groupArticlesByDate(articles) {
        const grouped = {};
        if (!articles || !Array.isArray(articles)) return grouped;

        articles.forEach(article => {
            // 尝试从 date_time 获取日期 YYYY-MM-DD
            let dateStr = '未知日期';
            if (article.date_time) {
                try {
                    // 假设 date_time 是 ISO 格式或 YYYY-MM-DD HH:MM:SS
                    dateStr = article.date_time.substring(0, 10);
                } catch (e) {
                    console.error("解析日期时出错:", article.date_time, e);
                }
            }
            if (!grouped[dateStr]) {
                grouped[dateStr] = [];
            }
            grouped[dateStr].push(article);
        });
        return grouped;
    }

    // --- 卡片创建函数 ---
    function createXCard(article) {
        const card = document.createElement('div');
        card.className = 'news-card x-card'; // 添加 x-card 类以区分样式

        const title = article.title || '无标题';
        let content = article.content || '无内容';
        const author = article.author || '未知作者';
        const dateTime = article.date_time || '未知时间';
        const timePart = dateTime.includes(' ') ? dateTime.split(' ')[1].substring(0, 5) : ''; // HH:MM
        const url = article.source_url || '#';

        // 链接处理 (简单替换，可优化)
        content = content.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');

        card.innerHTML = `
            <div class="news-card-header">
                <h3 class="news-title">${title}</h3>
            </div>
            <div class="news-card-content">
                <p>${content}</p>
            </div>
            <div class="news-card-footer">
                <div class="news-meta-row">
                    <div class="news-author"><i class="fas fa-user"></i> ${author}</div>
                    <div class="news-time"><i class="fas fa-clock"></i> ${timePart}</div>
                </div>
                <div class="news-stats-row">
                    <div class="news-stat-item" title="粉丝数"><i class="fas fa-users"></i> ${formatNumber(article.followers || 0)}</div>
                    <div class="news-stat-item" title="点赞数"><i class="fas fa-heart"></i> ${formatNumber(article.likes || 0)}</div>
                    <div class="news-stat-item" title="转发数"><i class="fas fa-retweet"></i> ${formatNumber(article.retweets || 0)}</div>
                </div>
                <div class="news-action-row">
                    <a href="${url}" target="_blank" class="read-original-btn" title="阅读原文"><i class="fas fa-external-link-alt"></i> 阅读原文</a>
                </div>
            </div>
        `;
        return card;
    }

    function createCrunchbaseCard(article) {
        const card = document.createElement('div');
        card.className = 'news-card crunchbase-card';

        const title = article.title || '无标题';
        let content = article.content || '无内容';
        const author = article.author || '未提供';
        const date = article.date_time ? article.date_time.substring(0, 10) : '未知日期';
        const url = article.source_url || '#';

        const company = article.company || '未提供';
        const fundingRound = article.funding_round || '未提供';
        const fundingAmount = article.funding_amount || '未提供';
        const investors = article.investors || '未提供';

        const isLongContent = content.length > 250;

        content = content.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');

        card.innerHTML = `
            <div class="news-card-header">
                <h3 class="news-title">${title}</h3>
                <div class="news-meta-cb">
                    ${author !== '未提供' ? `<span class="author"><i class="fas fa-user"></i> ${author}</span>` : ''}
                    <span class="date"><i class="fas fa-calendar-alt"></i> ${date}</span>
                </div>
            </div>
            <div class="news-card-content content-collapsible ${isLongContent ? 'collapsed' : ''}" style="white-space: pre-line;">
                <p>${content}</p>
                ${isLongContent ? '<div class="content-fade-button">展开</div>' : ''}
            </div>
            <div class="news-card-footer">
                <div class="investment-details">
                    ${company !== '未提供' ? `<div><span class="label">公司:</span> ${company}</div>` : ''}
                    ${fundingRound !== '未提供' ? `<div><span class="label">轮次:</span> ${fundingRound}</div>` : ''}
                    ${fundingAmount !== '未提供' ? `<div><span class="label">金额:</span> ${fundingAmount}</div>` : ''}
                    ${investors !== '未提供' ? `<div><span class="label">投资方:</span> ${investors}</div>` : ''}
                </div>
                <div class="news-action-row">
                    <a href="${url}" target="_blank" class="read-original-btn" title="阅读原文">
                        <i class="fas fa-external-link-alt"></i>
                        阅读原文
                    </a>
                </div>
            </div>
        `;

        // 为长内容添加展开/收起功能
        if (isLongContent) {
            const contentDiv = card.querySelector('.content-collapsible');
            const fadeButton = contentDiv.querySelector('.content-fade-button');
            
            fadeButton.addEventListener('click', () => {
                const isCollapsed = contentDiv.classList.contains('collapsed');
                contentDiv.classList.toggle('collapsed');
                fadeButton.textContent = isCollapsed ? '收起' : '展开';
            });
        }

        return card;
    }

    // --- 数字格式化辅助函数 ---
    function formatNumber(num) {
        if (typeof num !== 'number') return num; // 或返回 '0' 或 '-'
        if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
        if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
        return num.toString();
    }

    // --- 渲染函数 (实现) ---
    function renderXArticles(articles, sourceKey) {
        const container = elements[sourceKey].container;
        container.innerHTML = '';
        if (!articles || articles.length === 0) {
            container.innerHTML = '<p class="no-articles">当前日期范围内没有找到资讯。</p>';
            return;
        }

        console.log(`准备渲染 ${articles.length} 篇文章`);

        // 按日期分组
        const groupedArticles = groupArticlesByDate(articles);
        const dateKeys = Object.keys(groupedArticles).sort().reverse();

        console.log(`按日期分组后有 ${dateKeys.length} 个日期组`);

        // 渲染每个日期组
        dateKeys.forEach(date => {
            const articlesForDate = groupedArticles[date];
            console.log(`日期 ${date} 有 ${articlesForDate.length} 篇文章`);
            
            const dateHeader = document.createElement('h4');
            dateHeader.className = 'date-group-header';
            dateHeader.textContent = date;
            container.appendChild(dateHeader);

            const groupContainer = document.createElement('div');
            groupContainer.className = 'news-group x-group';
            groupContainer.dataset.dateGroup = date; // Link container to date
            container.appendChild(groupContainer);

            const initialCount = 9; // X 默认显示 9 条
            const initialArticles = articlesForDate.slice(0, initialCount);
            const remainingArticles = articlesForDate.slice(initialCount);

            // 渲染初始卡片
            initialArticles.forEach(article => {
                const card = createXCard(article);
                groupContainer.appendChild(card);
            });

            // 如果有剩余卡片，添加"显示更多"逻辑
            if (remainingArticles.length > 0) {
                const extraCardsContainer = document.createElement('div');
                extraCardsContainer.className = 'news-group x-group extra-cards'; // Use same grid layout
                extraCardsContainer.style.display = 'none'; // Initially hidden
                extraCardsContainer.dataset.dateGroup = date; // Link to date

                remainingArticles.forEach(article => {
                    const card = createXCard(article);
                    extraCardsContainer.appendChild(card);
                });

                // Insert extra container right after the initial group container
                groupContainer.after(extraCardsContainer);

                // 创建按钮容器
                const buttonContainer = document.createElement('div');
                buttonContainer.className = 'date-group-buttons';
                buttonContainer.dataset.dateGroup = date;

                const showMoreBtn = document.createElement('button');
                showMoreBtn.className = 'show-more-btn';
                showMoreBtn.dataset.action = 'show-more';
                showMoreBtn.dataset.targetGroup = date; // Link button to date group
                showMoreBtn.innerHTML = `<i class="fas fa-chevron-down"></i> 显示更多 (${remainingArticles.length}条)`;

                const collapseBtn = document.createElement('button');
                collapseBtn.className = 'collapse-btn';
                collapseBtn.dataset.action = 'collapse';
                collapseBtn.dataset.targetGroup = date; // Link button to date group
                collapseBtn.innerHTML = `<i class="fas fa-chevron-up"></i> 收起`;
                collapseBtn.style.display = 'none'; // Initially hidden

                buttonContainer.appendChild(showMoreBtn);
                buttonContainer.appendChild(collapseBtn);

                // Insert button container after the extra cards container
                extraCardsContainer.after(buttonContainer);
            }
        });
    }

    function renderCrunchbaseArticles(articles, sourceKey) {
        const container = elements[sourceKey].container;
        container.innerHTML = '';
         if (!articles || articles.length === 0) {
            container.innerHTML = '<p class="no-articles">当前日期范围内没有找到资讯。</p>';
                        return;
                    }
                    
        const groupContainer = document.createElement('div');
        groupContainer.className = 'news-group crunchbase-group';
        container.appendChild(groupContainer);

        const initialCount = 3; // Crunchbase 默认显示 3 条
        const initialArticles = articles.slice(0, initialCount);
        const remainingArticles = articles.slice(initialCount);

        // 渲染初始卡片
        initialArticles.forEach(article => {
            const card = createCrunchbaseCard(article);
            groupContainer.appendChild(card);
        });

        // 如果有剩余卡片，添加"显示更多"逻辑
        if (remainingArticles.length > 0) {
            const extraCardsContainer = document.createElement('div');
            extraCardsContainer.className = 'news-group crunchbase-group extra-cards';
            extraCardsContainer.style.display = 'none';

            remainingArticles.forEach(article => {
                const card = createCrunchbaseCard(article);
                extraCardsContainer.appendChild(card);
            });

            groupContainer.after(extraCardsContainer);

        const buttonContainer = document.createElement('div');
            buttonContainer.className = 'date-group-buttons'; // Reuse class, maybe rename later

            const showMoreBtn = document.createElement('button');
            showMoreBtn.className = 'show-more-btn';
            showMoreBtn.dataset.action = 'show-more';
            showMoreBtn.innerHTML = `<i class="fas fa-chevron-down"></i> 显示更多 (${remainingArticles.length}条)`;

            const collapseBtn = document.createElement('button');
            collapseBtn.className = 'collapse-btn';
            collapseBtn.dataset.action = 'collapse';
            collapseBtn.innerHTML = `<i class="fas fa-chevron-up"></i> 收起`;
            collapseBtn.style.display = 'none';

            buttonContainer.appendChild(showMoreBtn);
            buttonContainer.appendChild(collapseBtn);

            extraCardsContainer.after(buttonContainer);
        }
    }

    // --- 文章分页渲染 ---
    function renderArticlePagination(sourceKey, currentPage, totalPages) {
        const paginationContainer = elements[sourceKey].pagination;
        if (!paginationContainer) return;
        paginationContainer.innerHTML = ''; // 清空旧按钮
        
            if (totalPages <= 1) {
            paginationContainer.style.display = 'none'; // 如果只有一页或没有页，隐藏分页
                        return;
                    }
                    
        paginationContainer.style.display = 'flex'; // 确保显示
        
        // 首页按钮
        const firstBtn = document.createElement('button');
        firstBtn.innerHTML = '&laquo;'; // «
        firstBtn.title = '首页';
        firstBtn.disabled = currentPage <= 1;
        firstBtn.dataset.page = 1;
        firstBtn.classList.add('page-btn', 'page-nav');
        paginationContainer.appendChild(firstBtn);
        
        // 上一页按钮
            const prevBtn = document.createElement('button');
        prevBtn.innerHTML = '&lsaquo;'; // ‹
            prevBtn.title = '上一页';
        prevBtn.disabled = currentPage <= 1;
        prevBtn.dataset.page = currentPage - 1;
        prevBtn.classList.add('page-btn', 'page-nav');
            paginationContainer.appendChild(prevBtn);
            
        // 计算要显示的页码范围
        const maxVisiblePages = 5; // 最多显示5个页码按钮
        let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
        let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);
        
        // 确保显示足够数量的页码
        if (endPage - startPage + 1 < maxVisiblePages) {
            startPage = Math.max(1, endPage - maxVisiblePages + 1);
        }
        
        // 添加 "1..." 如果不从第一页开始
        if (startPage > 1) {
            const firstPageBtn = document.createElement('button');
            firstPageBtn.textContent = '1';
            firstPageBtn.dataset.page = 1;
            firstPageBtn.classList.add('page-btn');
            paginationContainer.appendChild(firstPageBtn);
            
            if (startPage > 2) {
                const ellipsis = document.createElement('span');
                ellipsis.textContent = '...';
                ellipsis.classList.add('page-ellipsis');
                paginationContainer.appendChild(ellipsis);
            }
        }

        // 页码按钮
            for (let i = startPage; i <= endPage; i++) {
                const pageBtn = document.createElement('button');
            pageBtn.textContent = i;
            pageBtn.dataset.page = i;
            pageBtn.classList.add('page-btn');
            if (i === currentPage) {
                    pageBtn.classList.add('active');
                pageBtn.disabled = true; // 当前页按钮不可点击
                }
                paginationContainer.appendChild(pageBtn);
            }
            
        // 添加 "...N" 如果不到最后一页
        if (endPage < totalPages) {
            if (endPage < totalPages - 1) {
                const ellipsis = document.createElement('span');
                ellipsis.textContent = '...';
                ellipsis.classList.add('page-ellipsis');
                paginationContainer.appendChild(ellipsis);
            }
            
            const lastPageBtn = document.createElement('button');
            lastPageBtn.textContent = totalPages;
            lastPageBtn.dataset.page = totalPages;
            lastPageBtn.classList.add('page-btn');
            paginationContainer.appendChild(lastPageBtn);
        }

        // 下一页按钮
            const nextBtn = document.createElement('button');
        nextBtn.innerHTML = '&rsaquo;'; // ›
            nextBtn.title = '下一页';
        nextBtn.disabled = currentPage >= totalPages;
        nextBtn.dataset.page = currentPage + 1;
        nextBtn.classList.add('page-btn', 'page-nav');
            paginationContainer.appendChild(nextBtn);
        
        // 末页按钮
        const lastBtn = document.createElement('button');
        lastBtn.innerHTML = '&raquo;'; // »
        lastBtn.title = '末页';
        lastBtn.disabled = currentPage >= totalPages;
        lastBtn.dataset.page = totalPages;
        lastBtn.classList.add('page-btn', 'page-nav');
        paginationContainer.appendChild(lastBtn);
    }

    // --- API 请求函数 (最终) ---
    async function fetchArticles(sourceKey, source, page = 1, dateRange = null) {
        showLoading();
        hideError();
        clearContainer(sourceKey);

        const sourceState = state[sourceKey];
        // 根据USE_TEST_API决定使用哪个API端点
        const apiBaseUrl = USE_TEST_API ? TEST_API_URL : API_BASE_URL;
        const apiUrl = `${apiBaseUrl}?source=${sourceState.currentSource}&page=${sourceState.currentPage}${USE_TEST_API ? '&per_page=' + ARTICLES_PER_PAGE[sourceKey] : '&date_page=' + sourceState.currentDatePage}`;

        console.log(`请求数据 (${sourceKey}): ${apiUrl}`);

        // 添加时间戳参数，确保浏览器请求新数据
        const timestamp = new Date().getTime();
        const refreshedApiUrl = `${apiUrl}&_=${timestamp}`;

        // 最大重试次数
        const maxRetries = 2;
        let retryCount = 0;
        let success = false;

        while (retryCount <= maxRetries && !success) {
            try {
                const response = await fetch(refreshedApiUrl);
                if (!response.ok) {
                    let apiErrorMsg = `HTTP 错误! 状态: ${response.status}`;
                    throw new Error(apiErrorMsg);
                }
                const data = await response.json();
                console.log(`收到数据 (${sourceKey}):`, data);

                // 缓存数据
                if (CACHE_ENABLED && data.status === 'success') {
                    const cacheDateRange = USE_TEST_API ? null : data.date_range;
                    cacheManager.saveToCache(
                        sourceKey, 
                        sourceState.currentSource, 
                        sourceState.currentPage, 
                        cacheDateRange, 
                        data
                    );
                }

                if (data.status === 'success') {
                    // 成功获取数据，处理响应
                    success = true;
                    
                    // 根据API端点不同处理不同的返回数据结构
                    if (USE_TEST_API) {
                        // 测试API处理逻辑保持不变
                        const defaultDateRange = {
                            start: '2025-03-01',
                            end: '2025-04-01'
                        };
                        updateDateInfo(sourceKey, defaultDateRange, 1, 1);
                        updateDatePaginationButtons(sourceKey, 1, 1);
                        
                        // 调用实际的渲染函数
                        if (sourceKey === 'x') {
                            renderXArticles(data.data, sourceKey);
            } else {
                            renderCrunchbaseArticles(data.data, sourceKey);
                        }
                        
                        // 渲染文章分页
                        const totalArticlePages = data.total > 0 ? Math.ceil(data.total / ARTICLES_PER_PAGE[sourceKey]) : 0;
                        renderArticlePagination(sourceKey, sourceState.currentPage, totalArticlePages);
                    } else {
                        // 原始API处理逻辑保持不变
                        updateDateInfo(sourceKey, data.date_range, sourceState.currentDatePage, data.total_date_pages);
                        updateDatePaginationButtons(sourceKey, sourceState.currentDatePage, data.total_date_pages);

                        // 调用实际的渲染函数
                        if (sourceKey === 'x') {
                            renderXArticles(data.data, sourceKey);
                        } else {
                            renderCrunchbaseArticles(data.data, sourceKey);
                        }

                        // 渲染文章分页
                        const totalArticlePages = data.total_in_date_range > 0 ? Math.ceil(data.total_in_date_range / ARTICLES_PER_PAGE[sourceKey]) : 0;
                        renderArticlePagination(sourceKey, sourceState.currentPage, totalArticlePages);
                    }
                } else {
                    throw new Error(data.message || 'API 返回错误状态');
                }
            } catch (error) {
                console.error(`获取数据错误 (尝试 ${retryCount + 1}/${maxRetries + 1}): ${error.message}`);
                retryCount++;
                
                // 如果达到最大重试次数，显示错误
                if (retryCount > maxRetries) {
                    showError(`获取数据失败: ${error.message}`);
                }
            }
        }
        
        hideLoading();
    }

    // --- Tab 切换逻辑 --- (无变化)
    window.openSource = function(event, contentId) {
        // 阻止默认事件
        if (event) event.preventDefault();
        
        // 隐藏所有标签内容
        tabContents.forEach(content => {
            content.style.display = 'none';
        });
        
        // 移除所有标签链接的活动类
        tabLinks.forEach(link => {
            link.classList.remove('active');
        });
        
        // 显示当前标签内容
        const activeContent = document.getElementById(contentId);
        if (activeContent) activeContent.style.display = 'block';
        
        // 添加活动类到当前标签链接
        if (event) {
            event.currentTarget.classList.add('active');
            } else {
            // 初始化调用时没有事件对象
            const linkForContent = document.querySelector(`[onclick*="${contentId}"]`);
            if (linkForContent) linkForContent.classList.add('active');
        }
        
        // 更新当前活动源
        state.activeSource = contentId.split('-')[0]; // 'x-content' -> 'x'
        
        // 加载对应数据
        fetchArticles(state.activeSource);
    }

    // --- 事件监听器设置 ---
    function setupEventListeners() {
        // 日期分页监听器
        ['x', 'crunchbase'].forEach(sourceKey => {
            const prevDateBtn = elements[sourceKey].prevDateBtn;
            const nextDateBtn = elements[sourceKey].nextDateBtn;
            
            if (prevDateBtn) {
                prevDateBtn.addEventListener('click', () => {
                    if (!prevDateBtn.disabled) {
                        state[sourceKey].currentDatePage--;
                        state[sourceKey].currentPage = 1; // 重置文章页码
                        fetchArticles(sourceKey);
                    }
                });
            }
            
            if (nextDateBtn) {
                nextDateBtn.addEventListener('click', () => {
                    if (!nextDateBtn.disabled) {
                        state[sourceKey].currentDatePage++;
                        state[sourceKey].currentPage = 1; // 重置文章页码
                        fetchArticles(sourceKey);
                    }
                });
            }
        });

        // 文章分页监听器 (使用事件委托)
        ['x', 'crunchbase'].forEach(sourceKey => {
            const paginationContainer = elements[sourceKey].pagination;
            if (paginationContainer) {
                 paginationContainer.addEventListener('click', (event) => {
                     // 确保点击的是按钮且有 data-page 属性
                     if (event.target.tagName === 'BUTTON' && event.target.dataset.page) {
                         const newPage = parseInt(event.target.dataset.page, 10);
                         // 只有当页码改变时才执行
                         if (!isNaN(newPage) && newPage !== state[sourceKey].currentPage) {
                             state[sourceKey].currentPage = newPage;
                             fetchArticles(sourceKey);
                             // 可选：滚动到文章区域顶部
                             elements[sourceKey].contentDiv.scrollIntoView({ behavior: 'smooth' });
                         }
                     }
                 });
            }
        });

        // 新增："显示更多"/"收起" 按钮监听器 (使用事件委托)
        document.addEventListener('click', (event) => {
            const target = event.target.closest('button.show-more-btn, button.collapse-btn');
            if (!target) return; // 点击的不是目标按钮

            const action = target.dataset.action;
            const buttonContainer = target.parentElement;
            let extraCardsContainer;

            // 根据按钮找到对应的 extra-cards 容器
            // For X, use date group. For Crunchbase, find previous sibling.
            const dateGroup = target.dataset.targetGroup; // Only set for X
            if (dateGroup) {
                // Find the extra container associated with this date group
                 extraCardsContainer = buttonContainer.previousElementSibling;
                 if (!extraCardsContainer || !extraCardsContainer.classList.contains('extra-cards') || extraCardsContainer.dataset.dateGroup !== dateGroup) {
                     // Fallback or alternative search if structure changes
                     console.error("Could not find extra cards container for date group:", dateGroup);
                     return;
                 }
                } else {
                 // For Crunchbase (no date group), assume it's the direct previous sibling
                 extraCardsContainer = buttonContainer.previousElementSibling;
                 if (!extraCardsContainer || !extraCardsContainer.classList.contains('extra-cards')) {
                      console.error("Could not find extra cards container for Crunchbase.");
                      return;
                 }
            }

            const showMoreBtn = buttonContainer.querySelector('.show-more-btn');
            const collapseBtn = buttonContainer.querySelector('.collapse-btn');

            if (action === 'show-more') {
                extraCardsContainer.style.display = 'grid'; // Or 'flex' for crunchbase? Match group style.
                if(extraCardsContainer.classList.contains('crunchbase-group')) {
                    extraCardsContainer.style.display = 'flex';
                }
                showMoreBtn.style.display = 'none';
                collapseBtn.style.display = 'inline-flex'; // Or block
            } else if (action === 'collapse') {
                extraCardsContainer.style.display = 'none';
                showMoreBtn.style.display = 'inline-flex'; // Or block
                collapseBtn.style.display = 'none';
            }
        });
    }

    // --- 页面初始化 ---
    setupEventListeners();
    const initialTabButton = document.querySelector('.tab-link.active');
    const initialContentId = initialTabButton ? initialTabButton.getAttribute('onclick').match(/openSource\(event, '(.*?)'\)/)[1] : 'x-content';
    window.openSource(null, initialContentId);

    // --- IndexedDB缓存管理类 ---
    class CacheManager {
        constructor() {
            this.db = null;
            this.isInitialized = false;
            this._init();
        }

        async _init() {
            if (!CACHE_ENABLED || !window.indexedDB) {
                console.log('缓存未启用或浏览器不支持IndexedDB');
                return;
            }

            try {
                // 打开数据库
                const request = indexedDB.open(DB_NAME, DB_VERSION);
                
                // 数据库升级事件
                request.onupgradeneeded = (event) => {
                    const db = event.target.result;
                    // 创建存储对象，按数据源分类
                    if (!db.objectStoreNames.contains('xArticles')) {
                        const xStore = db.createObjectStore('xArticles', { keyPath: 'cacheKey' });
                        xStore.createIndex('timestamp', 'timestamp', { unique: false });
                    }
                    
                    if (!db.objectStoreNames.contains('crunchbaseArticles')) {
                        const cbStore = db.createObjectStore('crunchbaseArticles', { keyPath: 'cacheKey' });
                        cbStore.createIndex('timestamp', 'timestamp', { unique: false });
                    }
                    
                    console.log('数据库架构初始化完成');
                };
                
                // 数据库打开成功
                request.onsuccess = (event) => {
                    this.db = event.target.result;
                    this.isInitialized = true;
                    console.log('缓存数据库连接成功');
                    
                    // 连接成功后启动缓存清理
                    this._cleanupExpiredCache();
                };
                
                // 错误处理
                request.onerror = (event) => {
                    console.error('打开缓存数据库失败:', event.target.error);
                    this.isInitialized = false;
                };
            } catch (error) {
                console.error('初始化缓存系统时发生错误:', error);
                this.isInitialized = false;
            }
        }
        
        // 生成缓存键
        _generateCacheKey(sourceKey, source, page, dateRange) {
            const dateStr = dateRange ? `${dateRange.start}_${dateRange.end}` : 'all';
            return `${sourceKey}_${source}_${dateStr}_page${page}`;
        }
        
        // 获取存储对象名称
        _getStoreName(sourceKey) {
            return sourceKey === 'x' ? 'xArticles' : 'crunchbaseArticles';
        }
        
        // 从缓存获取数据
        async getFromCache(sourceKey, source, page, dateRange) {
            if (!this.isInitialized || !CACHE_ENABLED) {
                return null;
            }
            
            const cacheKey = this._generateCacheKey(sourceKey, source, page, dateRange);
            const storeName = this._getStoreName(sourceKey);
            
            try {
                return new Promise((resolve, reject) => {
                    const transaction = this.db.transaction([storeName], 'readonly');
                    const store = transaction.objectStore(storeName);
                    const request = store.get(cacheKey);
                    
                    request.onsuccess = (event) => {
                        const cachedData = event.target.result;
                        
                        // 检查缓存是否存在且未过期
                        if (cachedData && Date.now() - cachedData.timestamp < cachedData.expiryTime) {
                            console.log(`命中缓存: ${cacheKey}`);
                            
                            // 更新缓存访问时间戳，用于LRU策略
                            this._updateAccessTimestamp(sourceKey, cacheKey);
                            
                            resolve(cachedData.data);
                        } else {
                            if (cachedData) {
                                console.log(`缓存已过期: ${cacheKey}`);
                                // 删除过期缓存
                                this._removeFromCache(sourceKey, cacheKey);
                            } else {
                                console.log(`缓存未命中: ${cacheKey}`);
                            }
                            resolve(null);
                        }
                    };
                    
                    request.onerror = (event) => {
                        console.error(`读取缓存失败: ${cacheKey}`, event.target.error);
                        resolve(null);
                    };
                });
            } catch (error) {
                console.error('从缓存获取数据时出错:', error);
                return null;
            }
        }
        
        // 将数据保存到缓存
        async saveToCache(sourceKey, source, page, dateRange, data) {
            if (!this.isInitialized || !CACHE_ENABLED) {
                return false;
            }
            
            const cacheKey = this._generateCacheKey(sourceKey, source, page, dateRange);
            const storeName = this._getStoreName(sourceKey);
            
            // 决定缓存过期时间
            let expiryTime = CACHE_EXPIRY.DEFAULT;
            if (page === 1 && (!dateRange || this._isRecentDate(dateRange))) {
                expiryTime = CACHE_EXPIRY.HOME_PAGE; // 首页/最新内容
            } else if (dateRange && this._isOldDate(dateRange)) {
                expiryTime = CACHE_EXPIRY.ARCHIVE; // 归档内容
            }
            
            const cacheItem = {
                cacheKey,
                data,
                timestamp: Date.now(),
                lastAccessed: Date.now(),
                expiryTime,
                size: JSON.stringify(data).length
            };
            
            try {
                return new Promise((resolve, reject) => {
                    const transaction = this.db.transaction([storeName], 'readwrite');
                    const store = transaction.objectStore(storeName);
                    const request = store.put(cacheItem);
                    
                    request.onsuccess = () => {
                        console.log(`已缓存: ${cacheKey}`);
                        resolve(true);
                    };
                    
                    request.onerror = (event) => {
                        console.error(`缓存失败: ${cacheKey}`, event.target.error);
                        resolve(false);
                    };
                });
            } catch (error) {
                console.error('保存数据到缓存时出错:', error);
                return false;
            }
        }
        
        // 更新缓存访问时间戳
        async _updateAccessTimestamp(sourceKey, cacheKey) {
            if (!this.isInitialized) return;
            
            const storeName = this._getStoreName(sourceKey);
            
            try {
                const transaction = this.db.transaction([storeName], 'readwrite');
                const store = transaction.objectStore(storeName);
                const request = store.get(cacheKey);
                
                request.onsuccess = (event) => {
                    const cacheItem = event.target.result;
                    if (cacheItem) {
                        cacheItem.lastAccessed = Date.now();
                        store.put(cacheItem);
                    }
                };
        } catch (error) {
                console.error('更新缓存访问时间戳失败:', error);
            }
        }
        
        // 从缓存中移除项目
        async _removeFromCache(sourceKey, cacheKey) {
            if (!this.isInitialized) return;
            
            const storeName = this._getStoreName(sourceKey);
            
            try {
                const transaction = this.db.transaction([storeName], 'readwrite');
                const store = transaction.objectStore(storeName);
                store.delete(cacheKey);
            } catch (error) {
                console.error('从缓存移除项目失败:', error);
            }
        }
        
        // 清理过期缓存
        async _cleanupExpiredCache() {
            if (!this.isInitialized) return;
            
            const storeNames = ['xArticles', 'crunchbaseArticles'];
            const now = Date.now();
            
            for (const storeName of storeNames) {
                try {
                    const transaction = this.db.transaction([storeName], 'readwrite');
                    const store = transaction.objectStore(storeName);
                    const cursorRequest = store.openCursor();
                    
                    cursorRequest.onsuccess = (event) => {
                        const cursor = event.target.result;
                        if (cursor) {
                            const cacheItem = cursor.value;
                            // 删除过期项目
                            if (now - cacheItem.timestamp > cacheItem.expiryTime) {
                                store.delete(cursor.key);
                                console.log(`已清理过期缓存: ${cursor.key}`);
                            }
                            cursor.continue();
                        }
                    };
                } catch (error) {
                    console.error(`清理${storeName}过期缓存失败:`, error);
                }
            }
            
            // 每6小时执行一次清理
            setTimeout(() => this._cleanupExpiredCache(), 6 * 60 * 60 * 1000);
        }
        
        // 判断是否为最近日期范围
        _isRecentDate(dateRange) {
            if (!dateRange || !dateRange.start) return false;
            
            const startDate = new Date(dateRange.start);
            const now = new Date();
            const daysDiff = Math.floor((now - startDate) / (1000 * 60 * 60 * 24));
            
            return daysDiff <= 7; // 最近7天内的内容
        }
        
        // 判断是否为较早日期范围
        _isOldDate(dateRange) {
            if (!dateRange || !dateRange.start) return false;
            
            const startDate = new Date(dateRange.start);
            const now = new Date();
            const daysDiff = Math.floor((now - startDate) / (1000 * 60 * 60 * 24));
            
            return daysDiff >= 30; // 30天前的内容
        }
        
        // 清空所有缓存
        async clearAllCache() {
            if (!this.isInitialized) return;
            
            const storeNames = ['xArticles', 'crunchbaseArticles'];
            
            for (const storeName of storeNames) {
                try {
                    const transaction = this.db.transaction([storeName], 'readwrite');
                    const store = transaction.objectStore(storeName);
                    store.clear();
                    console.log(`已清空${storeName}缓存`);
                } catch (error) {
                    console.error(`清空${storeName}缓存失败:`, error);
                }
            }
        }
    }

    // 创建全局缓存管理器实例
    const cacheManager = new CacheManager();
});

// GSAP 动画 (无变化)
// ...