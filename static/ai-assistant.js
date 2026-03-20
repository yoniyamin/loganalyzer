/**
 * Quick Insights Module
 * 
 * Provides KB-powered AI assistance for log analysis:
 * - AI panel with concise report summaries
 * - Navigation between generated reports and search threads
 * - Recommended search words for quick log navigation
 * - Per-file persistence
 */

class AIAssistant {
    constructor() {
        this.isEnabled = false;
        this.currentFileId = null;
        this.items = [];       // Combined list of reports + threads
        this.currentIndex = 0;
        this.isLoading = false;
        this.reportContentCache = {};
        
        this.aiPanel = null;
        this.aiTab = null;
        
        this.init();
    }
    
    init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.setup());
        } else {
            this.setup();
        }
    }
    
    setup() {
        this.aiPanel = document.getElementById('ai-panel');
        this.aiTab = document.querySelector('.left-panel-tab[data-panel="ai-panel"]');
        this.bindEvents();
        this.loadConfig();
    }
    
    bindEvents() {
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'a') {
                e.preventDefault();
                if (!this.isEnabled) return;
                this.switchToAITab();
            }
        });
    }
    
    async loadConfig() {
        try {
            const response = await fetch('/api/llm/config');
            if (response.ok) {
                const config = await response.json();
                this.isEnabled = config.is_configured && config.ai_enabled !== false;
                this.updateVisibility();
            }
        } catch (error) {
            console.error('Failed to load AI config:', error);
        }
    }
    
    updateVisibility() {
        if (this.aiTab) {
            this.aiTab.style.display = this.isEnabled ? '' : 'none';
        }
    }
    
    setFileId(fileId) {
        this.currentFileId = fileId;
        this.updateVisibility();
        this.reportContentCache = {};
        this.loadItems();
    }
    
    /**
     * Load both LLM reports and Smart Search threads, combining them
     * into a single navigable list (reports first, then threads).
     */
    async loadItems() {
        if (!this.currentFileId) {
            this.items = [];
            this.currentIndex = 0;
            this.renderPanel();
            return;
        }
        
        const combined = [];
        
        // Load LLM reports (from AI Insights)
        try {
            const reportRes = await fetch(`/api/llm/report/${this.currentFileId}/history`);
            if (reportRes.ok) {
                const reportData = await reportRes.json();
                for (const r of (reportData.reports || [])) {
                    combined.push({
                        id: r.report_id,
                        type: 'report',
                        title: `AI Report (${r.model_used || 'unknown'})`,
                        answer: null, // loaded lazily
                        model_used: r.model_used,
                        created_at: r.generated_at,
                        thumbs_up: false,
                        kb_articles: []
                    });
                }
            }
        } catch (e) {
            console.error('Failed to load report history:', e);
        }
        
        // Load Smart Search threads
        try {
            const threadRes = await fetch(`/api/llm/threads/${this.currentFileId}`);
            if (threadRes.ok) {
                const threadData = await threadRes.json();
                for (const t of (threadData.threads || [])) {
                    combined.push({
                        id: t.id,
                        type: 'thread',
                        title: t.question,
                        answer: t.answer,
                        model_used: 'smart_search',
                        created_at: t.created_at,
                        thumbs_up: t.thumbs_up || false,
                        kb_articles: t.kb_articles || []
                    });
                }
            }
        } catch (e) {
            console.error('Failed to load threads:', e);
        }
        
        this.items = combined;
        this.currentIndex = 0;
        
        // Load content for the first item if it's a report
        if (this.items.length > 0 && this.items[0].type === 'report') {
            await this.loadReportContent(this.items[0]);
        }
        
        this.renderPanel();
    }
    
    /**
     * Lazily load report content by ID.
     */
    async loadReportContent(item) {
        if (item.type !== 'report' || item.answer !== null) return;
        
        if (this.reportContentCache[item.id]) {
            item.answer = this.reportContentCache[item.id];
            return;
        }
        
        try {
            const res = await fetch(`/api/llm/report/by-id/${item.id}`);
            if (res.ok) {
                const data = await res.json();
                item.answer = data.report_content || '';
                item.kb_articles = (data.kb_references || []).map(ref => ({
                    title: ref.title,
                    url: ref.url || '',
                    similarity: 1.0
                }));
                this.reportContentCache[item.id] = item.answer;
            }
        } catch (e) {
            console.error('Failed to load report content:', e);
            item.answer = 'Failed to load report content.';
        }
    }
    
    switchToAITab() {
        const tabs = document.querySelectorAll('.left-panel-tab');
        const panels = document.querySelectorAll('.left-panel-content');
        
        tabs.forEach(tab => tab.classList.remove('active'));
        panels.forEach(panel => panel.classList.remove('active'));
        
        if (this.aiTab) {
            this.aiTab.classList.add('active');
            this.aiTab.classList.remove('has-new');
        }
        if (this.aiPanel) {
            this.aiPanel.classList.add('active');
        }
    }
    
    renderPanel() {
        if (!this.aiPanel) return;
        
        if (this.currentIndex >= this.items.length) {
            this.currentIndex = Math.max(0, this.items.length - 1);
        }
        if (this.currentIndex < 0) {
            this.currentIndex = 0;
        }
        
        const hasItems = this.items.length > 0;
        const canGoPrev = this.currentIndex > 0;
        const canGoNext = this.currentIndex < this.items.length - 1;
        
        let html = `
            <div class="ai-panel-header">
                <h3>
                    <svg viewBox="0 0 512 512" fill="currentColor">
                        <path d="M327.5 85.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 128l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 128l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 64 426.8 7.5C425.1 3 420.8 0 416 0s-9.1 3-10.8 7.5L384 64 327.5 85.2z"/>
                    </svg>
                    Quick Insights
                </h3>
                ${hasItems ? `
                <div class="ai-thread-navigation">
                    <button class="ai-nav-btn" id="aiNavPrev" ${canGoPrev ? '' : 'disabled'} title="Previous">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="15 18 9 12 15 6"/>
                        </svg>
                    </button>
                    <span class="ai-nav-indicator">${this.currentIndex + 1} / ${this.items.length}</span>
                    <button class="ai-nav-btn" id="aiNavNext" ${canGoNext ? '' : 'disabled'} title="Next">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="9 18 15 12 9 6"/>
                        </svg>
                    </button>
                </div>
                ` : ''}
            </div>
        `;
        
        if (!hasItems) {
            html += `
                <div class="ai-panel-empty">
                    <svg viewBox="0 0 512 512" fill="currentColor">
                        <path d="M327.5 85.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 128l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 128l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 64 426.8 7.5C425.1 3 420.8 0 416 0s-9.1 3-10.8 7.5L384 64 327.5 85.2zM9.3 240C3.6 242.6 0 248.3 0 254.6s3.6 11.9 9.3 14.5L26.3 277l8.1 3.7 .6 .3 88.3 40.8L164.1 410l.3 .6 3.7 8.1 7.9 17.1c2.6 5.7 8.3 9.3 14.5 9.3s11.9-3.6 14.5-9.3l7.9-17.1 3.7-8.1 .3-.6 40.8-88.3L346 281l.6-.3 8.1-3.7 17.1-7.9c5.7-2.6 9.3-8.3 9.3-14.5s-3.6-11.9-9.3-14.5l-17.1-7.9-8.1-3.7-.6-.3-88.3-40.8L217 99.1l-.3-.6L213 90.3l-7.9-17.1c-2.6-5.7-8.3-9.3-14.5-9.3s-11.9 3.6-14.5 9.3l-7.9 17.1-3.7 8.1-.3 .6-40.8 88.3L35.1 228.1l-.6 .3-8.1 3.7L9.3 240z"/>
                    </svg>
                    <p>No reports yet. Generate a report from the Resources tab.</p>
                    <p class="hint">Quick Insights summarizes your log analysis and KB matches.</p>
                </div>
            `;
        } else {
            const currentItem = this.items[this.currentIndex];
            html += '<div class="ai-threads-container">';
            
            if (currentItem.answer === null) {
                html += `
                    <div class="ai-loading">
                        <div class="ai-loading-spinner"></div>
                        <span class="ai-loading-text">Loading report...</span>
                    </div>
                `;
            } else {
                html += this.renderItem(currentItem);
            }
            
            html += '</div>';
        }
        
        this.aiPanel.innerHTML = html;
        this.bindPanelEvents();
    }
    
    bindPanelEvents() {
        const prevBtn = document.getElementById('aiNavPrev');
        const nextBtn = document.getElementById('aiNavNext');
        
        if (prevBtn) {
            prevBtn.addEventListener('click', async () => {
                if (this.currentIndex > 0) {
                    this.currentIndex--;
                    const item = this.items[this.currentIndex];
                    if (item.type === 'report' && item.answer === null) {
                        this.renderPanel(); // show loading
                        await this.loadReportContent(item);
                    }
                    this.renderPanel();
                }
            });
        }
        
        if (nextBtn) {
            nextBtn.addEventListener('click', async () => {
                if (this.currentIndex < this.items.length - 1) {
                    this.currentIndex++;
                    const item = this.items[this.currentIndex];
                    if (item.type === 'report' && item.answer === null) {
                        this.renderPanel(); // show loading
                        await this.loadReportContent(item);
                    }
                    this.renderPanel();
                }
            });
        }
        
        // Thread action buttons
        if (this.aiPanel) {
            this.aiPanel.querySelectorAll('.ai-thread-action-btn.save-to-findings').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const threadEl = e.currentTarget.closest('.ai-thread');
                    if (threadEl) {
                        await this.handleSaveToFindings(threadEl.dataset.threadId);
                    }
                });
            });
            
            this.aiPanel.querySelectorAll('.ai-thread-action-btn.thumbs-up').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const threadEl = e.currentTarget.closest('.ai-thread');
                    if (threadEl) {
                        await this.handleThumbsUp(threadEl.dataset.threadId);
                    }
                });
            });
            
            this.aiPanel.querySelectorAll('.ai-thread-action-btn.thumbs-down').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const threadEl = e.currentTarget.closest('.ai-thread');
                    if (threadEl) {
                        await this.handleThumbsDown(threadEl.dataset.threadId);
                    }
                });
            });
            
            // Goto tags
            this.aiPanel.querySelectorAll('.ai-goto-tag').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const pattern = e.currentTarget.dataset.searchPattern;
                    if (pattern) this.navigateLogTo(pattern);
                });
            });
        }
    }
    
    renderItem(item) {
        const timeAgo = this.formatTimeAgo(item.created_at);
        const isReport = item.type === 'report';
        
        const healthCard = this.extractHealthCard(item.answer);
        const searchWords = this.extractSearchWords(item.answer);
        const conciseAnswer = this.buildConciseAnswer(item.answer);
        
        const relevantKbArticles = (item.kb_articles || []).filter(
            article => (article.similarity || 0) > 0.01
        );
        
        let kbHtml = '';
        if (relevantKbArticles.length > 0) {
            kbHtml = `
                <div class="ai-kb-articles">
                    <div class="ai-kb-articles-title">
                        <svg viewBox="0 0 16 16" fill="currentColor">
                            <path d="M1 2.828c.885-.37 2.154-.769 3.388-.893 1.33-.134 2.458.063 3.112.752v9.746c-.935-.53-2.12-.603-3.213-.493-1.18.12-2.37.461-3.287.811V2.828zm7.5-.141c.654-.689 1.782-.886 3.112-.752 1.234.124 2.503.523 3.388.893v9.923c-.918-.35-2.107-.692-3.287-.81-1.094-.111-2.278-.039-3.213.492V2.687z"/>
                        </svg>
                        Related KB Articles
                    </div>
                    ${relevantKbArticles.map(article => `
                        <a href="${this.escapeHtml(article.url)}" target="_blank" class="ai-kb-card">
                            <div class="ai-kb-card-icon">
                                <svg viewBox="0 0 16 16" fill="currentColor">
                                    <path d="M14 4.5V14a2 2 0 01-2 2H4a2 2 0 01-2-2V2a2 2 0 012-2h5.5L14 4.5zm-3 0A1.5 1.5 0 019.5 3V1H4a1 1 0 00-1 1v12a1 1 0 001 1h8a1 1 0 001-1V4.5h-2z"/>
                                </svg>
                            </div>
                            <div class="ai-kb-card-content">
                                <div class="ai-kb-card-title">${this.escapeHtml(article.title)}</div>
                                <div class="ai-kb-card-meta">
                                    <span class="ai-kb-card-similarity">${Math.round((article.similarity || 0) * 100)}% match</span>
                                </div>
                            </div>
                        </a>
                    `).join('')}
                </div>
            `;
        }
        
        const typeBadge = isReport
            ? '<div class="ai-thread-source-badge source-report">📄 REPORT</div>'
            : '<div class="ai-thread-source-badge source-local">⚡ LOCAL</div>';
        
        // Only show thumbs/delete for threads, not full reports
        const actionsHtml = !isReport ? `
            <div class="ai-thread-actions">
                <button class="ai-thread-action-btn save-to-findings" data-action="save-to-findings" title="Save to Findings">
                    <svg viewBox="0 0 16 16" fill="currentColor">
                        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" transform="scale(0.67)"/>
                        <path d="M6 9h4M6 12h4M6 15h2" stroke="currentColor" stroke-width="1" fill="none" transform="scale(0.9) translate(1,1)"/>
                    </svg>
                </button>
                <button class="ai-thread-action-btn thumbs-up ${item.thumbs_up ? 'active' : ''}" data-action="thumbs-up" title="Helpful">
                    <svg viewBox="0 0 16 16" fill="currentColor">
                        <path d="M8.864.046C7.908-.193 7.02.53 6.956 1.466c-.072 1.051-.23 2.016-.428 2.59-.125.36-.479 1.013-1.04 1.639-.557.623-1.282 1.178-2.131 1.41C2.685 7.288 2 7.87 2 8.72v4.001c0 .845.682 1.464 1.448 1.545 1.07.114 1.564.415 2.068.723l.048.03c.272.165.578.348.97.484.397.136.861.217 1.466.217h3.5c.937 0 1.599-.477 1.934-1.064a1.86 1.86 0 00.254-.912c0-.152-.023-.312-.077-.464.201-.263.38-.578.488-.901.11-.33.172-.762.004-1.149.069-.13.12-.269.159-.403.077-.27.113-.568.113-.857 0-.288-.036-.585-.113-.856a2.144 2.144 0 00-.138-.362 1.9 1.9 0 00.234-1.734c-.206-.592-.682-1.1-1.2-1.272-.847-.282-1.803-.276-2.516-.211a9.84 9.84 0 00-.443.05 9.365 9.365 0 00-.062-4.509A1.38 1.38 0 008.864.046z"/>
                    </svg>
                </button>
                <button class="ai-thread-action-btn thumbs-down" data-action="thumbs-down" title="Remove">
                    <svg viewBox="0 0 16 16" fill="currentColor">
                        <path d="M8.864 15.674c-.956.24-1.843-.484-1.908-1.42-.072-1.05-.23-2.015-.428-2.59-.125-.36-.479-1.012-1.04-1.638-.557-.624-1.282-1.179-2.131-1.41C2.685 8.432 2 7.85 2 7V3c0-.845.682-1.464 1.448-1.546 1.07-.113 1.564-.415 2.068-.723l.048-.029c.272-.166.578-.349.97-.484C6.931.08 7.395 0 8 0h3.5c.937 0 1.599.478 1.934 1.064.164.287.254.607.254.913 0 .152-.023.312-.077.464.201.262.38.577.488.9.11.33.172.762.004 1.15.069.13.12.268.159.403.077.27.113.567.113.856 0 .289-.036.586-.113.856-.035.12-.076.237-.138.362.133.358.197.714.197 1.03 0 .292-.059.633-.234.995-.063.132-.13.254-.201.368.131.115.219.328.215.59-.004.312-.074.628-.236.895-.155.258-.393.458-.693.56-.307.105-.634.135-.983.135H8.5c-.123 0-.25-.004-.383-.012a8.89 8.89 0 00-.089 1.986c.002.36-.027.757-.14 1.138A1.38 1.38 0 018.864 15.674z"/>
                    </svg>
                </button>
            </div>
        ` : '';
        
        return `
            <div class="ai-thread current" data-thread-id="${item.id}" data-item-type="${item.type}">
                <div class="ai-thread-header">
                    <div class="ai-thread-header-top">
                        ${typeBadge}
                        ${actionsHtml}
                    </div>
                </div>
                <div class="ai-thread-body">
                    ${healthCard}
                    ${searchWords}
                    <div class="ai-thread-answer">${conciseAnswer}</div>
                    ${kbHtml}
                    <div class="ai-thread-time">
                        <svg viewBox="0 0 16 16" fill="currentColor">
                            <path d="M8 3.5a.5.5 0 00-1 0V9a.5.5 0 00.252.434l3.5 2a.5.5 0 00.496-.868L8 8.71V3.5z"/>
                            <path d="M8 16A8 8 0 108 0a8 8 0 000 16zm7-8A7 7 0 111 8a7 7 0 0114 0z"/>
                        </svg>
                        ${timeAgo}
                    </div>
                </div>
            </div>
        `;
    }
    
    /**
     * Extract a compact health/status card from the answer.
     * Reads the actual status values instead of assuming healthy.
     */
    extractHealthCard(answer) {
        if (!answer) return '';
        
        const lines = answer.split('\n');
        const healthItems = [];
        let healthTitle = '';
        let inHealthSection = false;
        
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();
            
            if (line.match(/^#{1,4}\s*.*(health|pipeline\s+health|status\s+overview)/i) ||
                line.match(/^(CDC\s+)?Pipeline\s+Health/i)) {
                healthTitle = line.replace(/^#+\s*/, '');
                inHealthSection = true;
                continue;
            }
            
            if (inHealthSection && line.match(/^[-*•]\s/)) {
                const text = line.replace(/^[-*•]\s*/, '');
                healthItems.push(text);
                continue;
            }
            
            if (inHealthSection && (line === '' || line.match(/^#{1,4}\s/))) {
                if (healthItems.length > 0) break;
                inHealthSection = false;
            }
        }
        
        if (healthItems.length === 0) return '';
        
        // Determine status from actual values, not assumptions
        const statusItem = healthItems.find(item => /status/i.test(item));
        let statusClass = 'neutral';
        if (statusItem) {
            const val = statusItem.split(':').slice(1).join(':').toLowerCase().replace(/\*/g, '').trim();
            if (val.includes('healthy')) statusClass = 'healthy';
            else if (val.includes('degraded') || val.includes('warning') || val.includes('unhealthy') || val.includes('critical')) statusClass = 'warning';
        }
        
        // Also check numeric values - non-zero warnings/disconnections indicate issues
        for (const item of healthItems) {
            const match = item.match(/(warning|disconnect|error|failure)s?\s*:\s*(\d+)/i);
            if (match && parseInt(match[2]) > 0) {
                statusClass = 'warning';
            }
        }
        
        return `
            <div class="ai-health-card ${statusClass}">
                <div class="ai-health-title">${this.escapeHtml(healthTitle || 'Pipeline Health')}</div>
                <div class="ai-health-items">
                    ${healthItems.map(item => {
                        const [key, ...valParts] = item.split(':');
                        const val = valParts.join(':').trim();
                        if (val) {
                            const cleanVal = val.replace(/\*\*/g, '');
                            const valClass = cleanVal.match(/^healthy$/i) ? 'good' :
                                           cleanVal.match(/^0$/) ? 'good' :
                                           cleanVal.match(/degraded|warning|unhealthy|critical/i) ? 'bad' :
                                           cleanVal.match(/^\d+$/) && cleanVal !== '0' ? 'warn' : '';
                            return `<div class="ai-health-item">
                                <span class="ai-health-key">${this.escapeHtml(key.trim())}</span>
                                <span class="ai-health-val ${valClass}">${this.escapeHtml(cleanVal)}</span>
                            </div>`;
                        }
                        return `<div class="ai-health-item"><span class="ai-health-key">${this.escapeHtml(item)}</span></div>`;
                    }).join('')}
                </div>
            </div>
        `;
    }
    
    /**
     * Extract recommended search words from the answer for log navigation.
     * Focuses on meaningful, actionable keywords.
     */
    extractSearchWords(answer) {
        if (!answer) return '';
        
        const tags = [];
        const seen = new Set();
        
        const addTag = (label, pattern, type) => {
            const key = pattern.toLowerCase();
            if (!seen.has(key) && key.length > 2 && key.length < 50) {
                seen.add(key);
                tags.push({ label, pattern, type });
            }
        };
        
        // Task/component names in backticks (high value)
        const codeRefs = answer.match(/`([A-Z][A-Z0-9_]+(?:\.[A-Z0-9_]+)*)`/gi);
        if (codeRefs) {
            codeRefs.forEach(ref => {
                const clean = ref.replace(/`/g, '');
                if (clean.length > 3) addTag(clean, clean, 'ref');
            });
        }
        
        // SQL/DB error codes
        const sqlErrors = answer.match(/\b(ORA-\d+|HY\d+|SQL_ERROR|SqlState\s*\S+)\b/gi);
        if (sqlErrors) {
            sqlErrors.forEach(e => addTag(e, e, 'error'));
        }
        
        // Error severity keywords with context
        const errorPhrases = answer.match(/\b(Failed to execute\b|one-by-one\s+apply|bulk\s+apply|batch\s+optimization|memory\s+warning|memory\s+limit|disconnect|reconnect|timeout|deadlock)\b/gi);
        if (errorPhrases) {
            errorPhrases.forEach(p => addTag(p.trim(), p.trim(), 'perf'));
        }
        
        // Latency references
        if (/handling\s+latency/i.test(answer)) addTag('Handling latency', 'handling latency', 'perf');
        if (/source\s+latency/i.test(answer)) addTag('Source latency', 'source latency', 'perf');
        if (/target\s+latency/i.test(answer)) addTag('Target latency', 'target latency', 'perf');
        if (/apply\s+latency/i.test(answer)) addTag('Apply latency', 'apply latency', 'perf');
        
        // Performance indicators
        if (/one-by-one/i.test(answer) && !seen.has('one-by-one')) addTag('one-by-one', 'one-by-one', 'perf');
        if (/bulk\s+finished/i.test(answer)) addTag('Bulk finished', 'Bulk finished', 'perf');
        
        const limitedTags = tags.slice(0, 8);
        if (limitedTags.length === 0) return '';
        
        return `
            <div class="ai-goto-tags">
                <span class="ai-goto-label">Recommended search words</span>
                ${limitedTags.map(tag => `
                    <button class="ai-goto-tag ${tag.type}" 
                            data-search-pattern="${this.escapeHtml(tag.pattern)}"
                            title="Search log for '${this.escapeHtml(tag.pattern)}'">
                        ${this.escapeHtml(tag.label)}
                    </button>
                `).join('')}
            </div>
        `;
    }
    
    /**
     * Build concise answer: strip meta-text, "From Previous Analysis Report",
     * health section (shown as card), and collapse excessive whitespace.
     */
    buildConciseAnswer(answer) {
        if (!answer) return '';
        
        let text = answer;
        
        // Strip preamble noise
        text = text.replace(/Smart Search could not fully answer[^\n]*\n*/gi, '');
        text = text.replace(/Context gathered from[^\n]*\n*/gi, '');
        text = text.replace(/For deeper reasoning[^\n]*\n*/gi, '');
        
        // Remove "From Previous Analysis Report" header and similar
        text = text.replace(/^#{0,4}\s*From Previous Analysis Report\s*$/gim, '');
        text = text.replace(/^#{0,4}\s*Previous Analysis Report\s*$/gim, '');
        
        const lines = text.split('\n');
        const filteredLines = [];
        let inHealthSection = false;
        
        for (let i = 0; i < lines.length; i++) {
            const trimmed = lines[i].trim();
            
            // Skip health section (rendered as a card above)
            if (trimmed.match(/^#{1,4}\s*.*(health|pipeline\s+health|status\s+overview)/i) ||
                trimmed.match(/^(CDC\s+)?Pipeline\s+Health/i)) {
                inHealthSection = true;
                continue;
            }
            
            if (inHealthSection) {
                if (trimmed.match(/^[-*•]\s/) && trimmed.match(/(status|warning|disconnect|reconnect|memory)/i)) {
                    continue;
                }
                if (trimmed === '' || trimmed.match(/^#{1,4}\s/)) {
                    inHealthSection = false;
                    if (trimmed === '') continue;
                }
            }
            
            filteredLines.push(lines[i]);
        }
        
        // Collapse runs of 3+ blank lines to 1
        let result = filteredLines.join('\n');
        result = result.replace(/\n{3,}/g, '\n\n');
        result = result.trim();
        
        return this.formatAnswer(result);
    }
    
    navigateLogTo(pattern) {
        const searchInput = document.getElementById('logQuickSearch');
        if (!searchInput) return;
        
        searchInput.value = pattern;
        searchInput.dispatchEvent(new Event('input', { bubbles: true }));
        searchInput.dispatchEvent(new KeyboardEvent('keydown', {
            key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true
        }));
        
        try {
            const clickedTag = this.aiPanel.querySelector(`.ai-goto-tag[data-search-pattern="${CSS.escape(pattern)}"]`);
            if (clickedTag) {
                clickedTag.classList.add('active');
                setTimeout(() => clickedTag.classList.remove('active'), 1500);
            }
        } catch (e) { /* CSS.escape may not match complex patterns */ }
    }
    
    async handleSaveToFindings(threadId) {
        try {
            const response = await fetch(`/api/llm/findings/from-thread/${threadId}`, { method: 'POST' });
            if (response.ok) {
                const result = await response.json();
                const btn = this.aiPanel.querySelector(`.ai-thread[data-thread-id="${threadId}"] .save-to-findings`);
                if (btn) { btn.classList.add('saved'); btn.title = 'Saved!'; }
                this.showToast('Saved to Findings!', 'success');
                document.dispatchEvent(new CustomEvent('findingSaved', { detail: result }));
            } else {
                const error = await response.json();
                this.showToast(`Failed: ${error.detail || 'Unknown error'}`, 'error');
            }
        } catch (error) {
            this.showToast('Failed to save to findings', 'error');
        }
    }
    
    showToast(message, type = 'info') {
        document.querySelectorAll('.toast-notification').forEach(t => t.remove());
        const toast = document.createElement('div');
        toast.className = `toast-notification ${type}`;
        toast.innerHTML = `${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'} <span>${message}</span>`;
        document.body.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
    
    async handleThumbsUp(threadId) {
        try {
            const response = await fetch(`/api/llm/threads/${threadId}/thumbs-up`, { method: 'POST' });
            if (response.ok) {
                const item = this.items.find(t => t.id == threadId && t.type === 'thread');
                if (item) item.thumbs_up = true;
                this.renderPanel();
            }
        } catch (error) {
            console.error('Failed to save thumbs up:', error);
        }
    }
    
    async handleThumbsDown(threadId) {
        window.showModal(
            'Delete Q&A',
            `<p>Delete this Q&A?</p><p style="font-size: 0.85em; color: #9ca3af; margin-top: 8px;">It will be removed from history.</p>`,
            async () => {
                try {
                    const response = await fetch(`/api/llm/threads/${threadId}`, { method: 'DELETE' });
                    if (response.ok) {
                        this.items = this.items.filter(t => !(t.id == threadId && t.type === 'thread'));
                        this.renderPanel();
                    }
                } catch (error) {
                    window.showModal('Error', `<p style="color: #ef4444;">Failed to delete: ${error.message}</p>`, null);
                }
            },
            { confirmText: 'Delete', danger: true }
        );
    }
    
    formatAnswer(answer) {
        if (!answer) return '';
        
        const lines = answer.split('\n');
        let html = '';
        let inList = false;
        let inCodeBlock = false;
        
        for (let i = 0; i < lines.length; i++) {
            let line = lines[i];
            
            if (line.trim().startsWith('```')) {
                if (inCodeBlock) { html += '</code></pre>'; inCodeBlock = false; }
                else { if (inList) { html += '</ul>'; inList = false; } html += '<pre class="ai-code-block"><code>'; inCodeBlock = true; }
                continue;
            }
            if (inCodeBlock) { html += this.escapeHtml(line) + '\n'; continue; }
            
            if (line.match(/^#{1,4}\s/)) {
                if (inList) { html += '</ul>'; inList = false; }
                const level = line.match(/^(#+)/)[1].length;
                const text = line.replace(/^#+\s*/, '');
                html += `<h${level + 2} class="ai-heading">${this.escapeHtml(text)}</h${level + 2}>`;
                continue;
            }
            
            if (line.match(/^\d+\.\s/)) {
                const text = line.replace(/^\d+\.\s*/, '');
                html += `<div class="ai-list-item numbered">${this.formatInline(text)}</div>`;
                continue;
            }
            
            if (line.match(/^[-*•]\s/)) {
                if (!inList) { html += '<ul class="ai-list">'; inList = true; }
                const text = line.replace(/^[-*•]\s*/, '');
                html += `<li>${this.formatInline(text)}</li>`;
                continue;
            } else if (inList && line.trim() === '') {
                html += '</ul>'; inList = false;
            }
            
            if (line.trim() === '') { html += '<br>'; continue; }
            html += `<p>${this.formatInline(line)}</p>`;
        }
        
        if (inList) html += '</ul>';
        if (inCodeBlock) html += '</code></pre>';
        return html;
    }
    
    formatInline(text) {
        let html = this.escapeHtml(text);
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
        html = html.replace(/`([^`]+)`/g, '<code class="ai-inline-code">$1</code>');
        return html;
    }
    
    formatTimeAgo(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const seconds = Math.floor((now - date) / 1000);
        if (seconds < 60) return 'Just now';
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
        if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
        return date.toLocaleDateString();
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    onConfigChanged(config) {
        this.isEnabled = config.is_configured && config.ai_enabled !== false;
        this.updateVisibility();
    }
}

window.aiAssistant = new AIAssistant();
