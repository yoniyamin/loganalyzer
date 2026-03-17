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
    
    async loadModels() {
        try {
            // Models are loaded based on current provider config
            const response = await fetch('/api/llm/models?recommended_only=true');
            if (response.ok) {
                const data = await response.json();
                this.models = data.models;
                this.currentProvider = data.provider || 'gemini';
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
        
        // Check for existing report
        this.checkExistingReport();
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
                        <button class="ai-generate-btn" id="aiGenerateBtn" ${!this.isConfigured ? 'disabled' : ''}>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
                            </svg>
                            Generate Report
                        </button>
                    </div>
                </div>
                <div class="ai-report-body" id="aiReportBody">
                    ${this.isConfigured ? this.getPlaceholderHTML() : this.getNotConfiguredHTML()}
                </div>
            </div>
        `;
        
        // Bind events
        this.bindEvents();
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
    
    async generateReport(regenerate = false) {
        if (!this.currentFileId) return;
        
        const body = document.getElementById('aiReportBody');
        const generateBtn = document.getElementById('aiGenerateBtn');
        
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
                <div class="cost-estimate" id="aiCostEstimate">Estimating cost...</div>
            </div>
        `;
        
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
                    web_search: this.webSearchEnabled || false
                })
            });
            
            if (response.ok) {
                const report = await response.json();
                this.displayReport(report);
            } else {
                const error = await response.json();
                this.showError(error.detail || 'Failed to generate report');
            }
        } catch (error) {
            this.showError('Network error: ' + error.message);
        } finally {
            this.isGenerating = false;
            generateBtn.disabled = false;
            generateBtn.innerHTML = `
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
                </svg>
                Generate Report
            `;
        }
    }
    
    displayReport(report) {
        const body = document.getElementById('aiReportBody');
        this.hasReport = true;
        this.currentReportId = report.report_id || null;
        
        // Dispatch event to notify other components (like Log Summary) that report is ready
        window.dispatchEvent(new CustomEvent('aiReportReady', { 
            detail: { fileId: this.currentFileId, report: report }
        }));
        
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
        
        // Just show the report content - no footer meta
        body.innerHTML = `<div class="ai-report-content">${htmlContent}</div>`;
        
        this.updateStatusBadge('ready');
        
        // Load history to update dropdown
        this.loadHistory();
    }
    
    async exportDocx() {
        if (!this.currentFileId || !this.currentReportId) return;
        await this.exportReportById(this.currentReportId);
    }
    
    showError(message) {
        const body = document.getElementById('aiReportBody');
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
        
        // Horizontal rules
        html = html.replace(/^---+$/gm, '<hr>');
        html = html.replace(/^\*\*\*+$/gm, '<hr>');
        
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
        
        // Auto-generate insights when a new file is loaded
        if (fileId && this.isConfigured && this.autoGenerateEnabled) {
            this.autoGenerate();
        }
    }
    
    /**
     * Auto-generate report in background when file is loaded
     */
    async autoGenerate() {
        if (!this.currentFileId || !this.isConfigured || this.isGenerating) return;
        
        // First check if we already have a cached report
        try {
            const response = await fetch(`/api/llm/report/${this.currentFileId}`);
            if (response.ok) {
                const data = await response.json();
                // Check if report exists (new format returns {exists: true/false})
                if (data.exists !== false) {
                    this.hasReport = true;
                    this.updateStatusBadge('ready');
                    // If container is rendered, show the report
                    if (this.container) {
                        this.displayReport(data);
                    }
                    return;
                }
            }
        } catch (e) {
            // No cached report, continue to generate
        }
        
        // Generate new report
        this.isGenerating = true;
        this.updateStatusBadge('loading');
        
        // Update UI if container is rendered
        if (this.container) {
            const body = document.getElementById('aiReportBody');
            if (body) {
                body.innerHTML = `
                    <div class="ai-report-loading">
                        <div class="ai-loading-spinner"></div>
                        <p>Auto-generating AI insights...</p>
                        <div class="cost-estimate">Using default model settings</div>
                    </div>
                `;
            }
        }
        
        try {
            const response = await fetch(`/api/llm/report/${this.currentFileId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model: null, // Use default model
                    regenerate: false,
                    quick: false
                })
            });
            
            if (response.ok) {
                const report = await response.json();
                this.hasReport = true;
                this.updateStatusBadge('ready');
                
                // Display report if container is rendered
                if (this.container) {
                    this.displayReport(report);
                }
            } else {
                const error = await response.json();
                this.updateStatusBadge('error', error.detail || 'Generation failed');
                
                if (this.container) {
                    this.showError(error.detail || 'Failed to auto-generate report');
                }
            }
        } catch (error) {
            this.updateStatusBadge('error', error.message);
            
            if (this.container) {
                this.showError('Network error: ' + error.message);
            }
        } finally {
            this.isGenerating = false;
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

