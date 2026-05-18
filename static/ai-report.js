/**
 * AI Report Component
 * 
 * Provides the UI for generating and displaying AI-powered log analysis reports.
 * Integrated into the Findings tab.
 */

class AIReportManager {
    constructor() {
        this.currentFileId = null;
        this.currentReportId = null;
        this.reportHistory = [];
        this.models = [];
        this.isConfigured = false;
        this.container = null;
        this.isGenerating = false;
        this.hasReport = false;
        this.autoGenerateEnabled = true;
        this._timerInterval = null;
        this.currentProvider = 'gemini';

        this.init();
    }
    
    init() {
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.setup());
        } else {
            this.setup();
        }
    }
    
    setup() {
        // Load models
        this.loadModels();
        
        // Check if configured
        this.checkConfig();
        
        // Set callback for config modal
        if (window.aiConfigModal) {
            window.aiConfigModal.onConfigSaved = (config) => {
                this.isConfigured = config.is_configured;
                if (config.provider) {
                    this.currentProvider = String(config.provider).toLowerCase();
                }
                this.renderSection();
                // Auto-generate if we have a file and just got configured
                if (this.isConfigured && this.currentFileId && !this.hasReport) {
                    this.autoGenerate();
                }
            };
        }
        
        // Setup sub-tab switching
        this.setupSubTabs();
    }
    
    setupSubTabs() {
        document.addEventListener('click', (e) => {
            const subTab = e.target.closest('.findings-sub-tab');
            if (subTab) {
                const targetId = subTab.dataset.subtab;
                
                // Update active tab
                document.querySelectorAll('.findings-sub-tab').forEach(t => t.classList.remove('active'));
                subTab.classList.add('active');
                
                // Show corresponding content
                document.querySelectorAll('.findings-subtab-content').forEach(c => c.classList.remove('active'));
                const targetContent = document.getElementById(targetId);
                if (targetContent) {
                    targetContent.classList.add('active');
                }
            }
        });
    }
    
    updateStatusBadge(status, text = '') {
        const badge = document.getElementById('insightsStatusBadge');
        if (!badge) return;
        
        badge.className = 'insights-status';
        
        switch (status) {
            case 'loading':
                badge.classList.add('loading');
                badge.innerHTML = '<span style="animation: pulse 1s infinite;">⏳</span>';
                badge.title = 'Generating insights...';
                break;
            case 'ready':
                badge.classList.add('ready');
                badge.textContent = '✓';
                badge.title = 'Insights ready';
                break;
            case 'error':
                badge.classList.add('error');
                badge.textContent = '!';
                badge.title = text || 'Error generating insights';
                break;
            case 'none':
            default:
                badge.textContent = '';
                badge.title = '';
                break;
        }
    }
    
    async syncProviderFromServer() {
        await this.checkConfig();
        await this.loadModels();
    }

    _isLMStudioActive() {
        return (this.currentProvider || '').toLowerCase() === 'lmstudio';
    }

    async loadModels() {
        try {
            // Models are loaded based on current provider config
            const response = await fetch('/api/llm/models?recommended_only=true');
            if (response.ok) {
                const data = await response.json();
                this.models = data.models;
                this.currentProvider = (data.provider || 'gemini').toLowerCase();
            }
        } catch (error) {
            console.error('Failed to load models:', error);
        }
    }
    
    async checkConfig() {
        try {
            const response = await fetch('/api/llm/config');
            if (response.ok) {
                const config = await response.json();
                this.isConfigured = config.is_configured;
                this.defaultModel = config.default_model || null;
                this.webSearchEnabled = config.web_search_enabled || false;
                this.currentProvider = (config.provider || 'gemini').toLowerCase();
            }
        } catch (error) {
            this.isConfigured = false;
            this.defaultModel = null;
            this.webSearchEnabled = false;
        }
    }
    
    /**
     * Render the AI Report section in the Findings tab
     * @param {HTMLElement} container - Container element to render into
     * @param {number} fileId - Current file ID
     */
    render(container, fileId) {
        this.container = container;
        this.currentFileId = fileId;
        this.renderSection();
        
        // Don't race GET with in-flight auto-generation POST
        if (!this.isGenerating) {
            this.checkExistingReport();
        }
    }
    
    renderSection() {
        if (!this.container) return;
        
        this.container.innerHTML = `
            <div class="ai-report-section">
                <div class="ai-report-header">
                    <h3>
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" fill="currentColor">
                            <path d="M327.5 85.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 128l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 128l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 64 426.8 7.5C425.1 3 420.8 0 416 0s-9.1 3-10.8 7.5L384 64 327.5 85.2zM9.3 240C3.6 242.6 0 248.3 0 254.6s3.6 11.9 9.3 14.5L26.3 277l8.1 3.7 .6 .3 88.3 40.8L164.1 410l.3 .6 3.7 8.1 7.9 17.1c2.6 5.7 8.3 9.3 14.5 9.3s11.9-3.6 14.5-9.3l7.9-17.1 3.7-8.1 .3-.6 40.8-88.3L346 281l.6-.3 8.1-3.7 17.1-7.9c5.7-2.6 9.3-8.3 9.3-14.5s-3.6-11.9-9.3-14.5l-17.1-7.9-8.1-3.7-.6-.3-88.3-40.8L217 99.1l-.3-.6L213 90.3l-7.9-17.1c-2.6-5.7-8.3-9.3-14.5-9.3s-11.9 3.6-14.5 9.3l-7.9 17.1-3.7 8.1-.3 .6-40.8 88.3L35.1 228.1l-.6 .3-8.1 3.7L9.3 240zM384 384l-56.5 21.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 448l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 448l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 384l-21.2-56.5c-1.7-4.5-6-7.5-10.8-7.5s-9.1 3-10.8 7.5L384 384z"/>
                        </svg>
                        Insights Report
                        <span class="ai-report-type-badge" id="aiReportTypeBadge"></span>
                    </h3>
                    <div class="ai-report-controls">
                        <div class="ai-history-dropdown" id="aiHistoryDropdown" style="display: none;">
                            <button class="ai-history-btn" id="aiHistoryBtn" title="View report history">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <circle cx="12" cy="12" r="10"/>
                                    <polyline points="12 6 12 12 16 14"/>
                                </svg>
                                <span id="aiHistoryCount">0</span>
                            </button>
                            <div class="ai-history-menu" id="aiHistoryMenu">
                                <div class="ai-history-header">Report History</div>
                                <div class="ai-history-list" id="aiHistoryList"></div>
                            </div>
                        </div>
                        <div class="ai-report-meta-inline" id="aiReportMetaInline" style="display: none;">
                            <span class="meta-model" id="metaModelInline"></span>
                            <span class="meta-tokens" id="metaTokensInline"></span>
                            <span class="meta-cost" id="metaCostInline"></span>
                        </div>
                        <button class="ai-delete-btn" id="aiDeleteReportBtn" style="display: none;" title="Delete this report">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="3 6 5 6 21 6"/>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                            </svg>
                        </button>
                        <button class="ai-export-btn-header" id="aiExportDocxBtnHeader" style="display: none;" title="Export as Word document">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                <polyline points="14 2 14 8 20 8"/>
                                <line x1="12" y1="18" x2="12" y2="12"/>
                                <line x1="9" y1="15" x2="12" y2="18"/>
                                <line x1="15" y1="15" x2="12" y2="18"/>
                            </svg>
                            Export
                        </button>
                        <button class="ai-generate-btn" id="aiGenerateBtn" ${!this.isConfigured || this.isGenerating ? 'disabled' : ''}>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
                            </svg>
                            Generate Report
                        </button>
                    </div>
                </div>
                <div class="ai-report-body" id="aiReportBody">
                    ${!this.isConfigured ? this.getNotConfiguredHTML() : this.isGenerating ? this.getAutoGeneratingBodyHTML() : this.getPlaceholderHTML()}
                </div>
            </div>
        `;
        
        // Bind events
        this.bindEvents();

        if (this.isGenerating && this.isConfigured) {
            const generateBtn = document.getElementById('aiGenerateBtn');
            if (generateBtn) {
                generateBtn.disabled = true;
                generateBtn.innerHTML = `
                    <div class="ai-btn-spinner"></div>
                    Generating...
                `;
            }
            // Tab switches re-run renderSection; keep one timer across remounts
            if (this._timerInterval) {
                this._syncTimerDisplay();
            } else {
                this._startTimer();
            }
            this.updateStatusBadge('loading');
        }
    }

    getAutoGeneratingBodyHTML() {
        return `
            <div class="ai-report-loading">
                <div class="ai-loading-spinner"></div>
                <p>Auto-generating AI insights...</p>
                <div class="ai-generation-timer" id="aiGenerationTimer">0s</div>
                <div class="ai-progress-status">
                    <span class="ai-progress-phase" id="aiProgressPhase">Preparing</span>
                    <span class="ai-progress-detail" id="aiProgressDetail"></span>
                </div>
                <div class="cost-estimate">Using default model settings</div>
            </div>
        `;
    }

    /** Push loading markup into the report body if the panel is mounted (container may exist before first paint). */
    _applyGeneratingBodyToDom() {
        if (!this.container) return;
        const body = document.getElementById('aiReportBody');
        if (body) {
            body.innerHTML = this.getAutoGeneratingBodyHTML();
        }
    }

    _resetGenerateButtonHtml() {
        const generateBtn = document.getElementById('aiGenerateBtn');
        if (!generateBtn) return;
        generateBtn.disabled = !this.isConfigured;
        generateBtn.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
            Generate Report
        `;
    }
    
    getPlaceholderHTML() {
        return `
            <div class="ai-report-placeholder">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
                    <path d="M9 12h6M9 16h6"/>
                </svg>
                <p>Click "Generate Report" to analyze this log with AI</p>
                <span class="hint">The AI will review the log summary and provide insights and recommendations</span>
            </div>
        `;
    }
    
    getNotConfiguredHTML() {
        return `
            <div class="ai-not-configured">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                    <path d="M7 11V7a5 5 0 0110 0v4"/>
                </svg>
                <p>Configure your OpenRouter API key to enable AI-powered insights</p>
                <button class="ai-configure-btn" id="aiConfigureBtn">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="3"/>
                        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
                    </svg>
                    Configure AI
                </button>
            </div>
        `;
    }
    
    bindEvents() {
        // Generate button
        const generateBtn = document.getElementById('aiGenerateBtn');
        if (generateBtn) {
            generateBtn.addEventListener('click', () => this.generateReport(true)); // Always regenerate when clicked
        }
        
        // Configure button (when not configured)
        const configureBtn = document.getElementById('aiConfigureBtn');
        if (configureBtn) {
            configureBtn.addEventListener('click', () => {
                if (window.aiConfigModal) {
                    window.aiConfigModal.open();
                }
            });
        }
        
        // Export button in header
        const exportBtnHeader = document.getElementById('aiExportDocxBtnHeader');
        if (exportBtnHeader) {
            exportBtnHeader.addEventListener('click', () => this.exportDocx());
        }
        
        // Delete button
        const deleteBtn = document.getElementById('aiDeleteReportBtn');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', () => this.deleteCurrentReport());
        }
        
        // History dropdown toggle
        const historyBtn = document.getElementById('aiHistoryBtn');
        if (historyBtn) {
            historyBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const menu = document.getElementById('aiHistoryMenu');
                menu.classList.toggle('open');
            });
        }
        
        // Close history menu when clicking outside
        document.addEventListener('click', () => {
            const menu = document.getElementById('aiHistoryMenu');
            if (menu) menu.classList.remove('open');
        });
    }
    
    async loadHistory() {
        if (!this.currentFileId) return;
        
        try {
            const response = await fetch(`/api/llm/report/${this.currentFileId}/history`);
            if (response.ok) {
                const data = await response.json();
                this.reportHistory = data.reports || [];
                this.updateHistoryUI();
            }
        } catch (error) {
            console.error('Failed to load report history:', error);
        }
    }
    
    updateHistoryUI() {
        const dropdown = document.getElementById('aiHistoryDropdown');
        const countBadge = document.getElementById('aiHistoryCount');
        const historyList = document.getElementById('aiHistoryList');
        
        if (!dropdown || !this.reportHistory.length) {
            if (dropdown) dropdown.style.display = 'none';
            return;
        }
        
        dropdown.style.display = 'flex';
        countBadge.textContent = this.reportHistory.length;
        
        // Build history list
        historyList.innerHTML = this.reportHistory.map(report => {
            const date = new Date(report.generated_at);
            const dateStr = date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
            const modelShort = report.model_used.includes('/') 
                ? report.model_used.split('/').pop() 
                : report.model_used;
            const costStr = report.cost_usd === 0 ? 'FREE' : `$${report.cost_usd.toFixed(4)}`;
            const isActive = report.report_id === this.currentReportId;
            
            return `
                <div class="ai-history-item ${isActive ? 'active' : ''}" data-report-id="${report.report_id}">
                    <div class="history-item-main" onclick="window.aiReportManager.loadReportById(${report.report_id})">
                        <div class="history-item-model">${modelShort}</div>
                        <div class="history-item-meta">
                            <span>${dateStr}</span>
                            <span>${report.prompt_tokens + report.completion_tokens} tokens</span>
                            <span class="${report.cost_usd === 0 ? 'cost-free' : ''}">${costStr}</span>
                        </div>
                    </div>
                    <div class="history-item-actions">
                        <button class="history-export-btn" onclick="event.stopPropagation(); window.aiReportManager.exportReportById(${report.report_id})" title="Export">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                                <polyline points="7 10 12 15 17 10"/>
                                <line x1="12" y1="15" x2="12" y2="3"/>
                            </svg>
                        </button>
                        <button class="history-delete-btn" onclick="event.stopPropagation(); window.aiReportManager.deleteReportById(${report.report_id})" title="Delete">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="3 6 5 6 21 6"/>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                            </svg>
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    }
    
    async loadReportById(reportId) {
        try {
            const response = await fetch(`/api/llm/report/by-id/${reportId}`);
            if (response.ok) {
                const report = await response.json();
                this.currentReportId = reportId;
                this.displayReport(report);
                this.updateHistoryUI(); // Update active state
                
                // Close menu
                const menu = document.getElementById('aiHistoryMenu');
                if (menu) menu.classList.remove('open');
            }
        } catch (error) {
            console.error('Failed to load report:', error);
        }
    }
    
    async exportReportById(reportId) {
        if (!this.currentFileId) return;
        
        try {
            const response = await fetch(`/api/llm/report/${this.currentFileId}/export/${reportId}`);
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                const disposition = response.headers.get('Content-Disposition');
                const filenameMatch = disposition && disposition.match(/filename=([^;]+)/);
                a.download = filenameMatch ? filenameMatch[1] : 'report.docx';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
            }
        } catch (error) {
            console.error('Export failed:', error);
            window.showModal('Export Failed', `<p style="color: #ef4444;">Export failed: ${error.message}</p>`, null);
        }
    }
    
    async deleteReportById(reportId) {
        window.showModal(
            'Delete Report',
            `<p>Delete this report?</p>
             <p style="font-size: 0.85em; color: #9ca3af; margin-top: 8px;">This cannot be undone.</p>`,
            async () => {
                try {
                    const response = await fetch(`/api/llm/report/${reportId}`, { method: 'DELETE' });
                    if (response.ok) {
                        // Reload history
                        await this.loadHistory();
                        
                        // If we deleted the current report, load the newest one or show placeholder
                        if (reportId === this.currentReportId) {
                            if (this.reportHistory.length > 0) {
                                await this.loadReportById(this.reportHistory[0].report_id);
                            } else {
                                this.currentReportId = null;
                                this.hasReport = false;
                                const body = document.getElementById('aiReportBody');
                                if (body) body.innerHTML = this.getPlaceholderHTML();
                                
                                // Hide meta/export/delete buttons
                                const metaInline = document.getElementById('aiReportMetaInline');
                                const exportBtn = document.getElementById('aiExportDocxBtnHeader');
                                const deleteBtn = document.getElementById('aiDeleteReportBtn');
                                if (metaInline) metaInline.style.display = 'none';
                                if (exportBtn) exportBtn.style.display = 'none';
                                if (deleteBtn) deleteBtn.style.display = 'none';
                            }
                        }
                    }
                } catch (error) {
                    console.error('Delete failed:', error);
                    window.showModal('Delete Failed', `<p style="color: #ef4444;">Delete failed: ${error.message}</p>`, null);
                }
            },
            { confirmText: 'Delete', danger: true }
        );
    }
    
    async deleteCurrentReport() {
        if (this.currentReportId) {
            await this.deleteReportById(this.currentReportId);
        }
    }
    
    async checkExistingReport() {
        if (!this.currentFileId || !this.isConfigured) return;
        
        try {
            const response = await fetch(`/api/llm/report/${this.currentFileId}`);
            if (response.ok) {
                const data = await response.json();
                // Check if report exists (new format returns {exists: true/false})
                if (data.exists === false) {
                    return; // No existing report
                }
                this.displayReport(data);
            }
        } catch (error) {
            // No existing report, that's fine
        }
    }
    
    _startTimer() {
        this._stopTimer();
        this._timerStart = Date.now();
        this._syncTimerDisplay();
        this._timerInterval = setInterval(() => {
            this._syncTimerDisplay();
        }, 1000);
        this._startProgressPolling();
    }

    _syncTimerDisplay() {
        const el = document.getElementById('aiGenerationTimer');
        if (!el || this._timerStart == null) return;
        const elapsed = Math.floor((Date.now() - this._timerStart) / 1000);
        el.textContent = elapsed < 60 ? `${elapsed}s` : `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`;
    }
    
    _stopTimer() {
        if (this._timerInterval) {
            clearInterval(this._timerInterval);
            this._timerInterval = null;
        }
        this._stopProgressPolling();
    }

    _startProgressPolling() {
        this._stopProgressPolling();
        if (!this.currentFileId) return;
        this._progressInterval = setInterval(() => this._pollProgress(), 2500);
    }

    _stopProgressPolling() {
        if (this._progressInterval) {
            clearInterval(this._progressInterval);
            this._progressInterval = null;
        }
    }

    async _pollProgress() {
        if (!this.currentFileId || !this.isGenerating) return;
        try {
            const resp = await fetch(`/api/llm/report/${this.currentFileId}/progress`);
            if (!resp.ok) return;
            const data = await resp.json();
            if (!data || data.phase === 'idle') return;
            this._updateProgressUI(data);
        } catch (e) {
            // Ignore polling errors
        }
    }

    _updateProgressUI(progress) {
        const detailEl = document.getElementById('aiProgressDetail');
        const phaseEl = document.getElementById('aiProgressPhase');
        if (!detailEl && !phaseEl) return;

        const phaseLabels = {
            preparing: 'Preparing',
            building_prompt: 'Building prompt',
            generating: 'Generating',
            done: 'Finalizing',
            error: 'Error',
        };
        const label = phaseLabels[progress.phase] || progress.phase;

        if (phaseEl) phaseEl.textContent = label;
        if (detailEl) {
            let detail = progress.detail || '';
            if (progress.phase === 'generating' && progress.est_prompt_tokens) {
                detail = `Sent ~${progress.est_prompt_tokens.toLocaleString()} tokens to ${progress.provider || 'model'}`;
                if (progress.model && progress.model !== 'default') {
                    const short = progress.model.includes('/') ? progress.model.split('/').pop() : progress.model;
                    detail += ` (${short})`;
                }
            }
            detailEl.textContent = detail;
        }
    }

    /**
     * Show a focus mode selection dialog. Returns a Promise that resolves
     * to the chosen focus_mode string, or null if the user cancels.
     */
    _showFocusDialog() {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'ai-focus-overlay';
            overlay.innerHTML = `
                <div class="ai-focus-dialog">
                    <h3>Choose Analysis Focus</h3>
                    <p class="ai-focus-subtitle">This log has no errors or performance data. What would you like the report to focus on?</p>
                    <div class="ai-focus-options">
                        <button class="ai-focus-option" data-focus="general_review">
                            <span class="ai-focus-icon">📋</span>
                            <span class="ai-focus-label">General Review</span>
                            <span class="ai-focus-desc">Health, drivers, connectivity, configuration overview</span>
                        </button>
                        <button class="ai-focus-option" data-focus="performance">
                            <span class="ai-focus-icon">⚡</span>
                            <span class="ai-focus-label">Performance Analysis</span>
                            <span class="ai-focus-desc">Throughput, batch efficiency, tuning opportunities</span>
                        </button>
                        <button class="ai-focus-option" data-focus="errors">
                            <span class="ai-focus-icon">🔍</span>
                            <span class="ai-focus-label">Error Analysis</span>
                            <span class="ai-focus-desc">Warnings, latent risks, preventive recommendations</span>
                        </button>
                        <button class="ai-focus-option" data-focus="configuration">
                            <span class="ai-focus-icon">⚙️</span>
                            <span class="ai-focus-label">Configuration Review</span>
                            <span class="ai-focus-desc">Settings, best practices, optimization opportunities</span>
                        </button>
                    </div>
                    <button class="ai-focus-cancel">Cancel</button>
                </div>
            `;

            overlay.querySelector('.ai-focus-cancel').addEventListener('click', () => {
                overlay.remove();
                resolve(null);
            });
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) { overlay.remove(); resolve(null); }
            });
            overlay.querySelectorAll('.ai-focus-option').forEach(btn => {
                btn.addEventListener('click', () => {
                    const mode = btn.dataset.focus;
                    overlay.remove();
                    resolve(mode);
                });
            });

            document.body.appendChild(overlay);
        });
    }

    async generateReport(regenerate = false) {
        if (!this.currentFileId) return;
        
        await this.syncProviderFromServer();

        // Preflight: check if data is sparse and ask for focus
        let focusMode = null;
        try {
            const pf = await fetch(`/api/llm/report/${this.currentFileId}/preflight`);
            if (pf.ok) {
                const pfData = await pf.json();
                if (pfData.needs_focus) {
                    focusMode = await this._showFocusDialog();
                    if (focusMode === null) return; // User cancelled
                }
            }
        } catch (e) {
            // Preflight failed — proceed without focus
        }
        this._currentFocusMode = focusMode;

        this._manualGeneration = true;
        const body = document.getElementById('aiReportBody');
        const generateBtn = document.getElementById('aiGenerateBtn');
        if (!body || !generateBtn) {
            if (typeof window.showToast === 'function') {
                window.showToast('Open the Resources tab (Insights) to generate a report.', 'warning', 3500);
            }
            return;
        }
        
        // Hide meta info during generation
        const metaInline = document.getElementById('aiReportMetaInline');
        const exportBtnHeader = document.getElementById('aiExportDocxBtnHeader');
        if (metaInline) metaInline.style.display = 'none';
        if (exportBtnHeader) exportBtnHeader.style.display = 'none';
        
        // Show loading state
        this.isGenerating = true;
        generateBtn.disabled = true;
        generateBtn.innerHTML = `
            <div class="ai-btn-spinner"></div>
            Generating...
        `;
        body.innerHTML = `
            <div class="ai-report-loading">
                <div class="ai-loading-spinner"></div>
                <p>Generating AI insights...</p>
                <div class="ai-generation-timer" id="aiGenerationTimer">0s</div>
                <div class="ai-progress-status">
                    <span class="ai-progress-phase" id="aiProgressPhase">Preparing</span>
                    <span class="ai-progress-detail" id="aiProgressDetail"></span>
                </div>
                <div class="cost-estimate" id="aiCostEstimate">Estimating cost...</div>
            </div>
        `;

        // Toast: provider-aware start notification (persistent until done)
        if (typeof window.showToast === 'function') {
            const isLocal = this._isLMStudioActive();
            const msg = isLocal
                ? '⏳ Generating report with local model — may take 30–120 s'
                : '⚡ Generating report…';
            window.showToast(msg, isLocal ? 'warning' : 'info', 0);
        }

        this._startTimer();
        
        // Get cost estimate
        try {
            const estimateUrl = `/api/llm/report/${this.currentFileId}/estimate`;
            const estimateResp = await fetch(estimateUrl);
            if (estimateResp.ok) {
                const estimate = await estimateResp.json();
                const costDiv = document.getElementById('aiCostEstimate');
                if (costDiv) {
                    if (estimate.estimated_cost_usd === 0) {
                        costDiv.innerHTML = `Estimated: ~${estimate.total_tokens.toLocaleString()} tokens <span style="color: #22c55e; font-weight: 600;">FREE</span>`;
                    } else {
                        costDiv.textContent = `Estimated: ~${estimate.total_tokens.toLocaleString()} tokens ($${estimate.estimated_cost_usd.toFixed(4)})`;
                    }
                }
            }
        } catch (e) {
            // Ignore estimate errors
        }
        
        // Generate report - uses default model and web search from config
        try {
            const response = await fetch(`/api/llm/report/${this.currentFileId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    regenerate: regenerate,
                    quick: false,
                    web_search: this.webSearchEnabled || false,
                    focus_mode: this._currentFocusMode || null
                })
            });
            
            if (response.ok) {
                const report = await response.json();
                if (typeof window.hideToast === 'function') window.hideToast();
                if (typeof window.showToast === 'function') {
                    window.showToast('✓ Report generated', 'success', 3000);
                }
                this.displayReport(report);
            } else {
                const error = await response.json();
                if (typeof window.hideToast === 'function') window.hideToast();
                if (typeof window.showToast === 'function') {
                    window.showToast('Report generation failed', 'error', 4000);
                }
                this.showError(error.detail || 'Failed to generate report');
            }
        } catch (error) {
            if (typeof window.hideToast === 'function') window.hideToast();
            if (typeof window.showToast === 'function') {
                window.showToast('Network error — report not generated', 'error', 4000);
            }
            this.showError('Network error: ' + error.message);
        } finally {
            this._stopTimer();
            this.isGenerating = false;
            // Always query fresh node: renderSection() may have replaced the DOM (tab switch, config save)
            this._resetGenerateButtonHtml();
        }
    }
    
    displayReport(report) {
        const body = document.getElementById('aiReportBody');
        this.hasReport = true;
        this.currentReportId = report.report_id || null;
        
        // Dispatch event to notify other components (like Log Summary) that report is ready
        window.dispatchEvent(new CustomEvent('aiReportReady', { 
            detail: { fileId: this.currentFileId, report: report, manual: this._manualGeneration || false }
        }));

        // Show report type badge when a focus mode was used
        const typeBadge = document.getElementById('aiReportTypeBadge');
        if (typeBadge) {
            const focusLabels = {
                general_review: 'General Review',
                performance: 'Performance Analysis',
                errors: 'Error Analysis',
                configuration: 'Configuration Review',
            };
            const label = focusLabels[report.focus_mode];
            if (label) {
                typeBadge.textContent = label;
                typeBadge.style.display = 'inline-block';
            } else {
                typeBadge.textContent = '';
                typeBadge.style.display = 'none';
            }
        }

        // Update header meta info
        const metaInline = document.getElementById('aiReportMetaInline');
        const metaModel = document.getElementById('metaModelInline');
        const metaTokens = document.getElementById('metaTokensInline');
        const metaCost = document.getElementById('metaCostInline');
        const exportBtnHeader = document.getElementById('aiExportDocxBtnHeader');
        const deleteBtn = document.getElementById('aiDeleteReportBtn');
        
        if (metaInline) {
            // Extract just the model name (without provider prefix)
            const modelName = report.model_used.includes('/') 
                ? report.model_used.split('/').pop() 
                : report.model_used;
            
            metaModel.textContent = modelName;
            metaTokens.textContent = `${report.prompt_tokens.toLocaleString()} / ${report.completion_tokens.toLocaleString()}`;
            metaCost.innerHTML = report.cost_usd === 0 
                ? '<span class="cost-free">FREE</span>'
                : `$${report.cost_usd.toFixed(4)}`;
            metaInline.style.display = 'flex';
        }
        
        if (exportBtnHeader) {
            exportBtnHeader.style.display = 'flex';
        }
        
        if (deleteBtn) {
            deleteBtn.style.display = 'flex';
        }
        
        // Convert markdown to HTML
        const htmlContent = this.markdownToHtml(report.report_content);
        
        let extraSections = '';

        // References section (KB + Release Notes)
        extraSections += this.buildReferencesSection(report);

        // Latency chart image (collapsed)
        if (report.chart_image_base64) {
            extraSections += `
                <div class="ai-report-appendix" style="margin-top:24px;border-top:1px solid #374151;padding-top:16px">
                    <details>
                        <summary style="font-size:0.9rem;color:#e5e7eb;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:6px;list-style:none;margin-bottom:10px">
                            <svg width="14" height="14" viewBox="0 0 16 16" fill="#9ca3af" style="transition:transform .2s"><path d="M6 12l4-4-4-4"/></svg>
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="#3b82f6"><path d="M1 11a1 1 0 011-1h2a1 1 0 011 1v3a1 1 0 01-1 1H2a1 1 0 01-1-1v-3zM6 7a1 1 0 011-1h2a1 1 0 011 1v7a1 1 0 01-1 1H7a1 1 0 01-1-1V7zM11 3a1 1 0 011-1h2a1 1 0 011 1v11a1 1 0 01-1 1h-2a1 1 0 01-1-1V3z"/></svg>
                            Latency Chart (sent to model)
                        </summary>
                        <img src="data:image/png;base64,${report.chart_image_base64}"
                             alt="Latency Over Time" style="width:100%;border-radius:6px;border:1px solid #374151" />
                    </details>
                </div>`;
        }

        // Log summary
        const summary = window.logSummaryData;
        if (summary) {
            const dur = summary.duration || '';
            const src = summary.source_endpoint || '';
            const tgt = summary.target_endpoint || '';
            const ver = summary.version || '';
            const errs = summary.error_count != null ? summary.error_count : (summary.errors_total != null ? summary.errors_total : '');
            const taskName = summary.task_name || '';
            let sumRows = '';
            if (taskName) sumRows += `<tr><td style="color:#9ca3af;padding:3px 12px 3px 0;font-size:0.75rem">Task</td><td style="font-size:0.75rem;color:#e5e7eb">${taskName}</td></tr>`;
            if (ver) sumRows += `<tr><td style="color:#9ca3af;padding:3px 12px 3px 0;font-size:0.75rem">Version</td><td style="font-size:0.75rem;color:#e5e7eb">${ver}</td></tr>`;
            if (src) sumRows += `<tr><td style="color:#9ca3af;padding:3px 12px 3px 0;font-size:0.75rem">Source</td><td style="font-size:0.75rem;color:#10b981">${src}</td></tr>`;
            if (tgt) sumRows += `<tr><td style="color:#9ca3af;padding:3px 12px 3px 0;font-size:0.75rem">Target</td><td style="font-size:0.75rem;color:#f59e0b">${tgt}</td></tr>`;
            if (dur) sumRows += `<tr><td style="color:#9ca3af;padding:3px 12px 3px 0;font-size:0.75rem">Duration</td><td style="font-size:0.75rem;color:#e5e7eb">${dur}</td></tr>`;
            if (errs !== '') sumRows += `<tr><td style="color:#9ca3af;padding:3px 12px 3px 0;font-size:0.75rem">Errors</td><td style="font-size:0.75rem;color:${errs > 0 ? '#f38ba8' : '#10b981'}">${errs}</td></tr>`;
            if (sumRows) {
                extraSections += `
                    <div class="ai-report-appendix" style="margin-top:16px;border-top:1px solid #374151;padding-top:16px">
                        <h3 style="font-size:0.9rem;color:#e5e7eb;margin:0 0 10px;display:flex;align-items:center;gap:6px">
                            <svg width="16" height="16" viewBox="0 0 512 512" fill="#8b5cf6"><path d="M327.5 85.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 128l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 128l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 64 426.8 7.5C425.1 3 420.8 0 416 0s-9.1 3-10.8 7.5L384 64 327.5 85.2z"/></svg>
                            Log Summary
                        </h3>
                        <table style="border-collapse:collapse">${sumRows}</table>
                    </div>`;
            }
        }

        if (body) {
            body.innerHTML = `<div class="ai-report-content">${htmlContent}</div>${extraSections}`;
        }
        
        this.updateStatusBadge('ready');
        
        // Load history to update dropdown
        this.loadHistory();
    }

    buildReferencesSection(report) {
        const hasKb = report.kb_references && report.kb_references.length > 0;
        const hasRn = report.release_notes_references && report.release_notes_references.length > 0;
        if (!hasKb && !hasRn) return '';

        const dbIcon = '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="#10b981" stroke-width="1.3" title="Indexed (ChromaDB)"><ellipse cx="8" cy="3" rx="6" ry="2.5"/><path d="M2 3v10c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5V3"/><path d="M2 8c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5"/></svg>';
        const webIcon = '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="#60a5fa" stroke-width="1.3" title="Web search"><circle cx="8" cy="8" r="6.5"/><path d="M1.5 8h13M8 1.5c2 2.2 3 4.8 3 6.5s-1 4.3-3 6.5c-2-2.2-3-4.8-3-6.5s1-4.3 3-6.5"/></svg>';

        let html = '<div class="ai-report-appendix" style="margin-top:24px;border-top:1px solid #374151;padding-top:16px">';
        html += '<details style="cursor:pointer"><summary style="font-size:0.9rem;color:#e5e7eb;font-weight:600;margin-bottom:10px;list-style:none;display:flex;align-items:center;gap:6px">';
        html += '<svg width="14" height="14" viewBox="0 0 16 16" fill="#9ca3af" style="transition:transform .2s"><path d="M6 12l4-4-4-4"/></svg>';
        html += 'References</summary>';

        if (hasKb) {
            html += '<div style="margin-bottom:12px"><div style="font-size:0.75rem;color:#9ca3af;text-transform:uppercase;margin-bottom:6px;font-weight:600">Knowledge Base Articles</div>';
            for (const kb of report.kb_references) {
                const icon = kb.source === 'web' ? webIcon : dbIcon;
                const link = kb.url
                    ? `<a href="${kb.url}" target="_blank" style="color:#60a5fa;text-decoration:none;font-size:0.8rem">${kb.title}</a>`
                    : `<span style="color:#e5e7eb;font-size:0.8rem">${kb.title}</span>`;
                html += `<div style="display:flex;align-items:flex-start;gap:6px;padding:4px 0">${icon} ${link}</div>`;
            }
            html += '</div>';
        }

        if (hasRn) {
            html += '<div><div style="font-size:0.75rem;color:#9ca3af;text-transform:uppercase;margin-bottom:6px;font-weight:600">Release Notes</div>';
            for (const rn of report.release_notes_references) {
                const icon = rn.source === 'web' ? webIcon : dbIcon;
                const fixTag = rn.fix_id ? ` <span style="padding:1px 4px;background:#06b6d4;color:#111827;border-radius:2px;font-size:0.6rem;font-weight:bold">${rn.fix_id}</span>` : '';
                const verTag = rn.version ? ` <span style="color:#6b7280;font-size:0.7rem">(${rn.version})</span>` : '';
                const link = rn.url
                    ? `<a href="${rn.url}" target="_blank" style="color:#60a5fa;text-decoration:none;font-size:0.8rem">${rn.title}</a>`
                    : `<span style="color:#e5e7eb;font-size:0.8rem">${rn.title}</span>`;
                html += `<div style="display:flex;align-items:flex-start;gap:6px;padding:4px 0">${icon} ${link}${fixTag}${verTag}</div>`;
            }
            html += '</div>';
        }

        html += '</details></div>';
        return html;
    }
    
    async exportDocx() {
        if (!this.currentFileId || !this.currentReportId) return;
        await this.exportReportById(this.currentReportId);
    }
    
    showError(message) {
        const body = document.getElementById('aiReportBody');
        this.updateStatusBadge('error', message);
        if (!body) return;
        body.innerHTML = `
            <div class="ai-report-placeholder" style="color: #f38ba8;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M15 9l-6 6M9 9l6 6"/>
                </svg>
                <p>${message}</p>
                <button class="ai-generate-btn" onclick="window.aiReportManager.generateReport()" style="margin-top: 12px;">
                    Try Again
                </button>
            </div>
        `;
    }
    
    /**
     * Enhanced markdown to HTML converter with better formatting
     */
    markdownToHtml(markdown) {
        if (!markdown) return '';
        
        let html = markdown;
        
        // Normalize line endings
        html = html.replace(/\r\n/g, '\n');
        
        // Escape HTML (but preserve some structure)
        html = html.replace(/&/g, '&amp;')
                   .replace(/</g, '&lt;')
                   .replace(/>/g, '&gt;');
        
        // Code blocks (must be before inline code)
        html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
        
        // Inline code
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
        
        // Headers - add classes for styling
        html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
        html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
        html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
        html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
        
        // Bold and italic
        html = html.replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em>$1</em></strong>');
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
        html = html.replace(/__([^_]+)__/g, '<strong>$1</strong>');
        html = html.replace(/_([^_]+)_/g, '<em>$1</em>');
        
        // Horizontal rules (allow spaces; don’t rely on --- only)
        html = html.replace(/^[\t ]*(?:-{3,}|\*{3,}|_{3,})[\t ]*$/gm, '<hr>');
        
        // Blockquotes
        html = html.replace(/^&gt;\s+(.+)$/gm, '<blockquote>$1</blockquote>');
        
        // Process lists - handle nested lists
        const lines = html.split('\n');
        let inList = false;
        let listType = null;
        let result = [];
        
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            const unorderedMatch = line.match(/^(\s*)[-*]\s+(.+)$/);
            const orderedMatch = line.match(/^(\s*)\d+\.\s+(.+)$/);
            
            if (unorderedMatch) {
                if (!inList || listType !== 'ul') {
                    if (inList) result.push(`</${listType}>`);
                    result.push('<ul>');
                    inList = true;
                    listType = 'ul';
                }
                result.push(`<li>${unorderedMatch[2]}</li>`);
            } else if (orderedMatch) {
                if (!inList || listType !== 'ol') {
                    if (inList) result.push(`</${listType}>`);
                    result.push('<ol>');
                    inList = true;
                    listType = 'ol';
                }
                result.push(`<li>${orderedMatch[2]}</li>`);
            } else {
                if (inList && line.trim() === '') {
                    // Empty line might end the list
                    const nextLine = lines[i + 1] || '';
                    if (!nextLine.match(/^(\s*)[-*]\s+/) && !nextLine.match(/^(\s*)\d+\.\s+/)) {
                        result.push(`</${listType}>`);
                        inList = false;
                        listType = null;
                    }
                } else if (inList && !line.match(/^\s/)) {
                    // Non-indented non-list line ends the list
                    result.push(`</${listType}>`);
                    inList = false;
                    listType = null;
                }
                result.push(line);
            }
        }
        if (inList) result.push(`</${listType}>`);
        html = result.join('\n');
        
        // Tables - improved handling
        html = html.replace(/^\|(.+)\|$/gm, (match, content) => {
            // Skip separator rows
            if (content.match(/^[\s\-:|]+$/)) return '';
            const cells = content.split('|').map(c => c.trim());
            const cellsHtml = cells.map(c => `<td>${c}</td>`).join('');
            return `<tr>${cellsHtml}</tr>`;
        });
        
        // Wrap consecutive table rows
        html = html.replace(/(<tr>[\s\S]*?<\/tr>\n?)+/g, '<table>$&</table>');
        
        // Convert remaining plain text lines to paragraphs
        // But don't wrap lines that are already HTML tags or empty
        html = html.split('\n').map(line => {
            const trimmed = line.trim();
            if (!trimmed) return '';
            if (trimmed.startsWith('<')) return line;
            return `<p>${line}</p>`;
        }).join('\n');
        
        // Clean up multiple empty lines and redundant tags
        html = html.replace(/<p><\/p>/g, '');
        html = html.replace(/<p>\s*<\/p>/g, '');
        html = html.replace(/\n{3,}/g, '\n\n');
        
        // Add semantic classes for common patterns
        html = html.replace(/\b(Healthy|OK|Good|Success)\b/gi, '<span class="status-healthy">$1</span>');
        html = html.replace(/\b(Warning|Caution|Moderate)\b/gi, '<span class="status-warning">$1</span>');
        html = html.replace(/\b(Critical|Error|Failed|Severe)\b/gi, '<span class="status-critical">$1</span>');
        
        return html;
    }
    
    /**
     * Update the file being analyzed
     */
    setFileId(fileId) {
        this.currentFileId = fileId;
        this.hasReport = false;
        this.updateStatusBadge('none');
        
        if (this.container) {
            this.renderSection();
        }
        
        // Auto-generate insights when a new file is loaded (await config inside autoGenerate)
        if (fileId && this.autoGenerateEnabled) {
            this.autoGenerate();
        }
    }
    
    /**
     * Auto-generate report in background when file is loaded
     */
    async autoGenerate() {
        if (!this.currentFileId || this.isGenerating) return;
        await this.syncProviderFromServer();
        if (!this.isConfigured || !this.autoGenerateEnabled) return;
        this._manualGeneration = false;

        // Loading state during cache GET and POST (fixes empty UI when config was still loading or container mounted late)
        this.isGenerating = true;
        this.updateStatusBadge('loading');
        this._applyGeneratingBodyToDom();
        this._startTimer();

        try {
            // Cached report?
            try {
                const response = await fetch(`/api/llm/report/${this.currentFileId}`);
                if (response.ok) {
                    const data = await response.json();
                    if (data.exists !== false) {
                        this.hasReport = true;
                        this.updateStatusBadge('ready');
                        if (this.container) {
                            this.displayReport(data);
                        }
                        return;
                    }
                }
            } catch (e) {
                // No cache, generate below
            }

            // Preflight: auto-gen defaults to general_review when data is sparse
            let autoFocus = null;
            try {
                const pf = await fetch(`/api/llm/report/${this.currentFileId}/preflight`);
                if (pf.ok) {
                    const pfData = await pf.json();
                    if (pfData.needs_focus) autoFocus = 'general_review';
                }
            } catch (e) { /* proceed without focus */ }

            // No cached report — show start toast before the POST
            if (typeof window.showToast === 'function') {
                const isLocal = this._isLMStudioActive();
                const msg = isLocal
                    ? '⏳ Generating report with local model — may take 30–120 s'
                    : '⚡ Generating report…';
                window.showToast(msg, isLocal ? 'warning' : 'info', 0);
            }

            const response = await fetch(`/api/llm/report/${this.currentFileId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model: null,
                    regenerate: false,
                    quick: false,
                    web_search: this.webSearchEnabled || false,
                    focus_mode: autoFocus,
                }),
            });

            if (response.ok) {
                const report = await response.json();
                if (typeof window.hideToast === 'function') window.hideToast();
                if (typeof window.showToast === 'function') {
                    window.showToast('✓ Report generated', 'success', 3000);
                }
                this.hasReport = true;
                this.updateStatusBadge('ready');
                if (this.container) {
                    this.displayReport(report);
                }
            } else {
                const error = await response.json();
                if (typeof window.hideToast === 'function') window.hideToast();
                if (typeof window.showToast === 'function') {
                    window.showToast('Report generation failed', 'error', 4000);
                }
                this.updateStatusBadge('error', error.detail || 'Generation failed');
                if (this.container) {
                    this.showError(error.detail || 'Failed to auto-generate report');
                }
            }
        } catch (error) {
            if (typeof window.hideToast === 'function') window.hideToast();
            if (typeof window.showToast === 'function') {
                window.showToast('Network error — report not generated', 'error', 4000);
            }
            this.updateStatusBadge('error', error.message);
            if (this.container) {
                this.showError('Network error: ' + error.message);
            }
        } finally {
            this._stopTimer();
            this.isGenerating = false;
            this._resetGenerateButtonHtml();
        }
    }
}

// Add CSS animation for loading pulse
const style = document.createElement('style');
style.textContent = `
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }
`;
document.head.appendChild(style);

// Create singleton instance
window.aiReportManager = new AIReportManager();

