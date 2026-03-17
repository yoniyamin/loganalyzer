/**
 * AI Configuration Modal
 * 
 * Provides a modal dialog for configuring AI API settings:
 * - Provider selection (Gemini default, OpenRouter optional)
 * - API key input with show/hide toggle
 * - Model selection dropdown
 * - Connection testing
 * - Save/cancel functionality
 * 
 * Gemini Reference: https://ai.google.dev/gemini-api/docs/models
 */

class AIConfigModal {
    constructor() {
        this.overlay = null;
        this.isOpen = false;
        this.models = [];
        this.currentConfig = null;
        this.selectedProvider = 'gemini'; // Default to Gemini
        this.onConfigSaved = null; // Callback when config is saved
        
        this.init();
    }
    
    init() {
        // Create modal HTML
        this.createModal();
        
        // Load initial config
        this.loadConfig();
        
        // Load available models for current provider
        this.loadModels();

        // Prepare sanitization list
        this.renderSanitizationEntities();
    }
    
    createModal() {
        const modalHTML = `
            <div class="ai-modal-overlay" id="aiConfigOverlay">
                <div class="ai-modal">
                    <div class="ai-modal-header">
                        <h2>
                            <svg viewBox="0 0 512 512" fill="currentColor">
                                <path d="M327.5 85.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 128l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 128l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 64 426.8 7.5C425.1 3 420.8 0 416 0s-9.1 3-10.8 7.5L384 64 327.5 85.2zM9.3 240C3.6 242.6 0 248.3 0 254.6s3.6 11.9 9.3 14.5L26.3 277l8.1 3.7 .6 .3 88.3 40.8L164.1 410l.3 .6 3.7 8.1 7.9 17.1c2.6 5.7 8.3 9.3 14.5 9.3s11.9-3.6 14.5-9.3l7.9-17.1 3.7-8.1 .3-.6 40.8-88.3L346 281l.6-.3 8.1-3.7 17.1-7.9c5.7-2.6 9.3-8.3 9.3-14.5s-3.6-11.9-9.3-14.5l-17.1-7.9-8.1-3.7-.6-.3-88.3-40.8L217 99.1l-.3-.6L213 90.3l-7.9-17.1c-2.6-5.7-8.3-9.3-14.5-9.3s-11.9 3.6-14.5 9.3l-7.9 17.1-3.7 8.1-.3 .6-40.8 88.3L35.1 228.1l-.6 .3-8.1 3.7L9.3 240zM384 384l-56.5 21.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 448l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 448l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 384l-21.2-56.5c-1.7-4.5-6-7.5-10.8-7.5s-9.1 3-10.8 7.5L384 384z"/>
                            </svg>
                            AI Configuration
                        </h2>
                        <button class="ai-modal-close" id="aiModalClose">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M18 6L6 18M6 6l12 12"/>
                            </svg>
                        </button>
                    </div>
                    
                    <!-- Tab Navigation -->
                    <div class="ai-modal-tabs">
                        <button class="ai-modal-tab active" data-tab="config">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                                <circle cx="12" cy="12" r="3"/>
                                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
                            </svg>
                            Configuration
                        </button>
                        <button class="ai-modal-tab" data-tab="routing">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                            </svg>
                            Routing History
                        </button>
                        <button class="ai-modal-tab" data-tab="sanitization">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                                <path d="M12 1l3 5 5 3-5 3-3 5-3-5-5-3 5-3z"/>
                            </svg>
                            Sanitization
                        </button>
                    </div>
                    
                    <div class="ai-modal-body">
                        <!-- Config Tab Content -->
                        <div class="ai-tab-content active" data-tab-content="config">
                            <div class="ai-config-status not-configured" id="aiConfigStatus">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <circle cx="12" cy="12" r="10"/>
                                    <path d="M12 8v4M12 16h.01"/>
                                </svg>
                                <span>API key not configured</span>
                            </div>
                            
                            <!-- AI Enable Toggle -->
                        <div class="ai-form-group">
                            <div class="ai-toggle-row">
                                <label class="ai-toggle-label">
                                    <span>Enable AI Features</span>
                                    <span class="ai-toggle-hint">When disabled, existing reports will still be shown</span>
                                </label>
                                <label class="ai-toggle-switch">
                                    <input type="checkbox" id="aiEnabled" checked>
                                    <span class="ai-toggle-slider"></span>
                                </label>
                            </div>
                        </div>
                        
                        <!-- Auto-generate Summary Toggle -->
                        <div class="ai-form-group">
                            <div class="ai-toggle-row">
                                <label class="ai-toggle-label">
                                    <span>Auto-generate Log Summary</span>
                                    <span class="ai-toggle-hint">Automatically generate AI report when loading a file</span>
                                </label>
                                <label class="ai-toggle-switch">
                                    <input type="checkbox" id="aiAutoGenerate" checked>
                                    <span class="ai-toggle-slider"></span>
                                </label>
                            </div>
                        </div>
                        
                        <!-- Provider Selection -->
                        <div class="ai-form-group ai-provider-section" id="providerSection">
                            <label>AI Provider</label>
                            <div class="ai-provider-toggle">
                                <button type="button" class="ai-provider-btn active" data-provider="gemini" id="btnGemini">
                                    <span class="provider-icon">✨</span>
                                    <span class="provider-name">Google Gemini</span>
                                    <span class="provider-tag free">Free Tier</span>
                                </button>
                                <button type="button" class="ai-provider-btn" data-provider="openrouter" id="btnOpenRouter">
                                    <span class="provider-icon">🔀</span>
                                    <span class="provider-name">OpenRouter</span>
                                    <span class="provider-tag">Multi-Model</span>
                                </button>
                            </div>
                        </div>
                        
                        <!-- Gemini API Key Section -->
                        <div class="ai-form-group ai-gemini-section" id="geminiSection">
                            <label for="aiGeminiKey">Gemini API Key</label>
                            <div class="ai-input-wrapper">
                                <input type="password" id="aiGeminiKey" class="ai-input" 
                                       placeholder="AIza..." autocomplete="off">
                                <button class="ai-toggle-visibility" id="aiToggleGeminiKey" type="button">
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                                        <circle cx="12" cy="12" r="3"/>
                                    </svg>
                                </button>
                            </div>
                            <p class="ai-help-text">
                                Get your free API key from <a href="https://aistudio.google.com/app/apikey" target="_blank">Google AI Studio</a>
                                <br><span style="color: #22c55e;">✓ Free tier: 500 requests/day, 1M tokens/min</span>
                            </p>
                        </div>
                        
                        <!-- OpenRouter API Key Section -->
                        <div class="ai-form-group ai-openrouter-section" id="openrouterSection" style="display: none;">
                            <label for="aiApiKey">OpenRouter API Key</label>
                            <div class="ai-input-wrapper">
                                <input type="password" id="aiApiKey" class="ai-input" 
                                       placeholder="sk-or-v1-..." autocomplete="off">
                                <button class="ai-toggle-visibility" id="aiToggleKey" type="button">
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                                        <circle cx="12" cy="12" r="3"/>
                                    </svg>
                                </button>
                            </div>
                            <p class="ai-help-text">
                                Get your API key from <a href="https://openrouter.ai/keys" target="_blank">openrouter.ai/keys</a>
                            </p>
                        </div>
                        
                        <div id="aiTestResult" class="ai-test-result" style="display: none;"></div>
                        
                        <div class="ai-form-group">
                            <label for="aiDefaultModel">Default Model</label>
                            <select id="aiDefaultModel" class="ai-select">
                                <option value="gemini-2.5-flash">Loading models...</option>
                            </select>
                            <div class="ai-model-info" id="aiModelInfo">
                                <div class="model-description">Select a model to see details</div>
                                <div class="model-pricing">
                                    <span>Input: $--/M tokens</span>
                                    <span>Output: $--/M tokens</span>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Custom Model (OpenRouter only) -->
                        <div class="ai-form-group ai-custom-model-section" id="customModelSection" style="display: none;">
                            <label for="aiCustomModel">Or Enter Custom Model Route</label>
                            <div class="ai-input-wrapper">
                                <input type="text" id="aiCustomModel" class="ai-input" 
                                       placeholder="e.g., x-ai/grok-4.1-fast:free" autocomplete="off">
                            </div>
                            <p class="ai-help-text">
                                Enter any <a href="https://openrouter.ai/models" target="_blank">OpenRouter model</a> route name. 
                                Custom model overrides the dropdown selection.
                            </p>
                        </div>
                        
                        <!-- Web Search Option -->
                        <div class="ai-form-group">
                            <label class="ai-checkbox-label">
                                <input type="checkbox" id="aiWebSearchEnabled">
                                <span>Enable Web Search</span>
                            </label>
                            <p class="ai-help-text" style="margin-left: 24px;">
                                Allow the AI to search the web for additional context about errors and issues.
                                <br><span style="color: #f59e0b;">⚠️ May increase response time and cost.</span>
                            </p>
                        </div>

                        <!-- Tavily API Key -->
                        <div class="ai-form-group">
                            <label for="aiTavilyKey">Tavily API Key (for error resolutions)</label>
                            <div class="ai-input-wrapper">
                                <input type="password" id="aiTavilyKey" class="ai-input" 
                                       placeholder="tvly-..." autocomplete="off">
                                <button class="ai-toggle-visibility" id="aiToggleTavilyKey" type="button">
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                                        <circle cx="12" cy="12" r="3"/>
                                    </svg>
                                </button>
                            </div>
                            <p class="ai-help-text">
                                Used for manual error resolution searches (Tavily advanced answer).
                            </p>
                        </div>
                        </div><!-- End Config Tab -->
                        
                        <!-- Routing History Tab Content -->
                        <div class="ai-tab-content" data-tab-content="routing">
                            <div class="ai-routing-history-header">
                                <h3>Routing Feedback History</h3>
                                <p class="ai-routing-history-desc">
                                    Track how questions were routed and provide feedback to improve future routing decisions.
                                </p>
                            </div>
                            
                            <div class="ai-routing-history-filters">
                                <label class="ai-routing-filter-checkbox">
                                    <input type="checkbox" id="routingMismatchOnly">
                                    <span>Show mismatches only</span>
                                </label>
                                <button class="ai-btn ai-btn-secondary ai-btn-sm" id="routingExportBtn">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                                        <polyline points="7 10 12 15 17 10"/>
                                        <line x1="12" y1="15" x2="12" y2="3"/>
                                    </svg>
                                    Export CSV
                                </button>
                                <button class="ai-btn ai-btn-secondary ai-btn-sm" id="routingRefreshBtn">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                                        <polyline points="23 4 23 10 17 10"/>
                                        <polyline points="1 20 1 14 7 14"/>
                                        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                                    </svg>
                                    Refresh
                                </button>
                            </div>
                            
                            <div class="ai-routing-history-table-wrapper">
                                <table class="ai-routing-history-table">
                                    <thead>
                                        <tr>
                                            <th>Question</th>
                                            <th>Actual</th>
                                            <th>Suggested</th>
                                            <th>Comment</th>
                                            <th>Date</th>
                                        </tr>
                                    </thead>
                                    <tbody id="routingHistoryBody">
                                        <tr>
                                            <td colspan="5" class="ai-routing-history-empty">
                                                No routing feedback yet. Rate answers in the AI Assistant to build history.
                                            </td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                            
                            <div class="ai-routing-stats" id="routingStats">
                                <!-- Stats will be populated by JS -->
                            </div>
                        </div><!-- End Routing Tab -->

                        <!-- Sanitization Tab Content -->
                        <div class="ai-tab-content" data-tab-content="sanitization">
                            <div class="ai-sanitization-header">
                                <h3>Sanitization Rules</h3>
                                <p class="ai-sanitization-desc">
                                    Log data is sanitized before any model call. KB articles stay unmodified.
                                    Preview detections and replacements below.
                                </p>
                            </div>

                            <div class="ai-sanitization-entities" id="aiSanitizationEntities">
                                <!-- Filled by JS -->
                            </div>

                            <div class="ai-sanitization-tester">
                                <label for="aiSanitizeInput">Test redaction</label>
                                <textarea id="aiSanitizeInput" class="ai-input" rows="4" placeholder="Paste log lines to preview redactions..."></textarea>
                                <div class="ai-sanitize-actions">
                                    <button class="ai-btn ai-btn-primary ai-btn-sm" id="aiSanitizePreviewBtn">
                                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                                            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                                            <circle cx="12" cy="12" r="3"/>
                                        </svg>
                                        Preview Redactions
                                    </button>
                                </div>
                                <div class="ai-sanitize-result" id="aiSanitizeResult"></div>
                            </div>
                        </div><!-- End Sanitization Tab -->
                    </div>
                    
                    <div class="ai-modal-footer">
                        <button class="ai-btn ai-btn-secondary" id="aiTestConnection">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                                <polyline points="22 4 12 14.01 9 11.01"/>
                            </svg>
                            Test Connection
                        </button>
                        <div style="display: flex; gap: 8px;">
                            <button class="ai-btn ai-btn-secondary" id="aiCancelBtn">Cancel</button>
                            <button class="ai-btn ai-btn-primary" id="aiSaveBtn">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                                    <polyline points="17 21 17 13 7 13 7 21"/>
                                    <polyline points="7 3 7 8 15 8"/>
                                </svg>
                                Save
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Append to body
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        
        // Get references
        this.overlay = document.getElementById('aiConfigOverlay');
        
        // Bind events
        this.bindEvents();
    }
    
    bindEvents() {
        // Close button
        document.getElementById('aiModalClose').addEventListener('click', () => this.close());
        document.getElementById('aiCancelBtn').addEventListener('click', () => this.close());
        
        // Click outside to close
        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay) {
                this.close();
            }
        });
        
        // Escape key to close
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isOpen) {
                this.close();
            }
        });
        
        // Tab switching
        this.overlay.querySelectorAll('.ai-modal-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                const tabName = e.currentTarget.dataset.tab;
                this.switchTab(tabName);
            });
        });
        
        // Routing history filters and actions
        document.getElementById('routingMismatchOnly')?.addEventListener('change', () => {
            this.loadRoutingHistory();
        });
        
        document.getElementById('routingRefreshBtn')?.addEventListener('click', () => {
            this.loadRoutingHistory();
        });
        
        document.getElementById('routingExportBtn')?.addEventListener('click', () => {
            this.exportRoutingHistory();
        });

        // Sanitization preview
        document.getElementById('aiSanitizePreviewBtn')?.addEventListener('click', () => {
            this.previewSanitization();
        });
        
        // AI enabled toggle
        document.getElementById('aiEnabled').addEventListener('change', () => {
            this.updateProviderSectionVisibility();
        });
        
        // Provider toggle buttons
        document.getElementById('btnGemini').addEventListener('click', () => {
            this.switchProvider('gemini');
        });
        document.getElementById('btnOpenRouter').addEventListener('click', () => {
            this.switchProvider('openrouter');
        });
        
        // Toggle password visibility - Gemini
        document.getElementById('aiToggleGeminiKey').addEventListener('click', () => {
            const input = document.getElementById('aiGeminiKey');
            const isPassword = input.type === 'password';
            input.type = isPassword ? 'text' : 'password';
        });
        
        // Toggle password visibility - OpenRouter
        document.getElementById('aiToggleKey').addEventListener('click', () => {
            const input = document.getElementById('aiApiKey');
            const isPassword = input.type === 'password';
            input.type = isPassword ? 'text' : 'password';
        });

        // Toggle password visibility - Tavily
        document.getElementById('aiToggleTavilyKey').addEventListener('click', () => {
            const input = document.getElementById('aiTavilyKey');
            const isPassword = input.type === 'password';
            input.type = isPassword ? 'text' : 'password';
        });
        
        // Model selection change
        document.getElementById('aiDefaultModel').addEventListener('change', (e) => {
            // Clear custom model when dropdown is changed
            const customInput = document.getElementById('aiCustomModel');
            if (customInput) customInput.value = '';
            this.updateModelInfo(e.target.value);
        });
        
        // Custom model input change (OpenRouter only)
        const customModelInput = document.getElementById('aiCustomModel');
        if (customModelInput) {
            customModelInput.addEventListener('input', (e) => {
                this.updateModelInfo(document.getElementById('aiDefaultModel').value);
            });
        }
        
        // Test connection
        document.getElementById('aiTestConnection').addEventListener('click', () => {
            this.testConnection();
        });
        
        // Save
        document.getElementById('aiSaveBtn').addEventListener('click', () => {
            this.save();
        });
    }
    
    switchProvider(provider) {
        this.selectedProvider = provider;
        
        // Update button states
        document.getElementById('btnGemini').classList.toggle('active', provider === 'gemini');
        document.getElementById('btnOpenRouter').classList.toggle('active', provider === 'openrouter');
        
        // Show/hide relevant sections
        document.getElementById('geminiSection').style.display = provider === 'gemini' ? 'block' : 'none';
        document.getElementById('openrouterSection').style.display = provider === 'openrouter' ? 'block' : 'none';
        document.getElementById('customModelSection').style.display = provider === 'openrouter' ? 'block' : 'none';
        
        // Reload models for the selected provider
        this.loadModels();
        
        // Update status display
        this.updateStatusDisplay();
    }
    
    async loadConfig() {
        try {
            const response = await fetch('/api/llm/config');
            if (response.ok) {
                this.currentConfig = await response.json();
                // Set provider from config
                if (this.currentConfig.provider) {
                    this.selectedProvider = this.currentConfig.provider;
                    this.switchProvider(this.selectedProvider);
                }
                this.updateStatusDisplay();
            }
        } catch (error) {
            console.error('Failed to load AI config:', error);
        }
    }
    
    async loadModels() {
        try {
            const response = await fetch(`/api/llm/models?provider=${this.selectedProvider}&recommended_only=true`);
            if (response.ok) {
                const data = await response.json();
                this.models = data.models;
                this.populateModelSelect();
            }
        } catch (error) {
            console.error('Failed to load models:', error);
        }
    }
    
    populateModelSelect() {
        const select = document.getElementById('aiDefaultModel');
        const customInput = document.getElementById('aiCustomModel');
        
        // Group models by free/paid
        const freeModels = this.models.filter(m => m.prompt_price === 0);
        const paidModels = this.models.filter(m => m.prompt_price > 0);
        
        let optionsHtml = '';
        
        if (freeModels.length > 0) {
            optionsHtml += '<optgroup label="🆓 Free Models">';
            optionsHtml += freeModels.map(model => 
                `<option value="${model.id}">${model.name}</option>`
            ).join('');
            optionsHtml += '</optgroup>';
        }
        
        if (paidModels.length > 0) {
            optionsHtml += '<optgroup label="💰 Paid Models">';
            optionsHtml += paidModels.map(model => 
                `<option value="${model.id}">${model.name}</option>`
            ).join('');
            optionsHtml += '</optgroup>';
        }
        
        select.innerHTML = optionsHtml || this.models.map(model => 
            `<option value="${model.id}">${model.name}</option>`
        ).join('');
        
        // Set current default if configured
        if (this.currentConfig && this.currentConfig.default_model) {
            const isKnownModel = this.models.some(m => m.id === this.currentConfig.default_model);
            if (isKnownModel) {
                select.value = this.currentConfig.default_model;
                if (customInput) customInput.value = '';
            } else {
                // It's a custom model - show it in the custom input field
                if (customInput) {
                    customInput.value = this.currentConfig.default_model;
                }
            }
        }
        
        // Update model info display
        this.updateModelInfo(select.value);
    }
    
    updateModelInfo(modelId) {
        const model = this.models.find(m => m.id === modelId);
        const infoDiv = document.getElementById('aiModelInfo');
        const customInput = document.getElementById('aiCustomModel');
        const customModel = customInput ? customInput.value.trim() : '';
        
        // If there's a custom model entered, show info for that instead
        if (customModel) {
            infoDiv.innerHTML = `
                <div class="model-description">Custom model: <code>${customModel}</code></div>
                <div class="model-pricing">
                    <span style="color: #f59e0b;">Pricing depends on the model - check OpenRouter</span>
                </div>
            `;
            return;
        }
        
        if (model) {
            const isFree = model.prompt_price === 0 && model.completion_price === 0;
            const pricingHtml = isFree 
                ? '<span style="color: #22c55e; font-weight: 600;">✓ FREE - No cost per token</span>'
                : `<span>Input: $${model.prompt_price.toFixed(2)}/M tokens</span>
                   <span>Output: $${model.completion_price.toFixed(2)}/M tokens</span>`;
            
            infoDiv.innerHTML = `
                <div class="model-description">${model.description || 'No description available'}</div>
                <div class="model-pricing">
                    ${pricingHtml}
                </div>
            `;
        }
    }
    
    updateStatusDisplay() {
        const statusDiv = document.getElementById('aiConfigStatus');
        const geminiInput = document.getElementById('aiGeminiKey');
        const openrouterInput = document.getElementById('aiApiKey');
        const tavilyInput = document.getElementById('aiTavilyKey');
        
        if (!this.currentConfig) {
            statusDiv.className = 'ai-config-status not-configured';
            statusDiv.innerHTML = `
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M12 8v4M12 16h.01"/>
                </svg>
                <span>No API keys configured</span>
            `;
            return;
        }
        
        const geminiConfigured = this.currentConfig.gemini_configured;
        const openrouterConfigured = this.currentConfig.openrouter_configured;
        const activeProvider = this.currentConfig.provider || 'gemini';
        
        // Update placeholders with key previews
        if (this.currentConfig.gemini_api_key_preview) {
            geminiInput.placeholder = this.currentConfig.gemini_api_key_preview;
        }
        if (this.currentConfig.openrouter_api_key_preview) {
            openrouterInput.placeholder = this.currentConfig.openrouter_api_key_preview;
        }
        if (this.currentConfig.tavily_api_key_preview && tavilyInput) {
            tavilyInput.placeholder = this.currentConfig.tavily_api_key_preview;
        }
        
        // Check if the active provider is configured
        const activeConfigured = (activeProvider === 'gemini' && geminiConfigured) || 
                                 (activeProvider === 'openrouter' && openrouterConfigured);
        
        if (activeConfigured) {
            const providerName = activeProvider === 'gemini' ? 'Gemini' : 'OpenRouter';
            const keyPreview = activeProvider === 'gemini' 
                ? this.currentConfig.gemini_api_key_preview 
                : this.currentConfig.openrouter_api_key_preview;
            
            statusDiv.className = 'ai-config-status configured';
            
            // Build status text showing both providers
            let statusParts = [];
            if (geminiConfigured) statusParts.push(`✨ Gemini: ${this.currentConfig.gemini_api_key_preview || '✓'}`);
            if (openrouterConfigured) statusParts.push(`🔀 OpenRouter: ${this.currentConfig.openrouter_api_key_preview || '✓'}`);
            if (this.currentConfig.tavily_configured) statusParts.push(`🌐 Tavily: ${this.currentConfig.tavily_api_key_preview || '✓'}`);
            
            statusDiv.innerHTML = `
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                    <polyline points="22 4 12 14.01 9 11.01"/>
                </svg>
                <span>${statusParts.join(' • ') || 'Configured'}</span>
            `;
        } else {
            // Active provider not configured but maybe the other one is
            const providerName = activeProvider === 'gemini' ? 'Gemini' : 'OpenRouter';
            statusDiv.className = 'ai-config-status not-configured';
            
            let message = `${providerName} API key not configured`;
            if (geminiConfigured || openrouterConfigured) {
                const otherProvider = activeProvider === 'gemini' ? 'OpenRouter' : 'Gemini';
                message += ` (${otherProvider} is configured)`;
            }
            
            statusDiv.innerHTML = `
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M12 8v4M12 16h.01"/>
                </svg>
                <span>${message}</span>
            `;
        }
    }
    
    async testConnection() {
        const resultDiv = document.getElementById('aiTestResult');
        
        // Get API key based on selected provider
        const apiKey = this.selectedProvider === 'gemini' 
            ? document.getElementById('aiGeminiKey').value
            : document.getElementById('aiApiKey').value;
        
        // Show loading
        resultDiv.style.display = 'flex';
        resultDiv.className = 'ai-test-result loading';
        resultDiv.innerHTML = '<div class="ai-spinner"></div> Testing connection...';
        
        try {
            // Save the key first if entered
            if (apiKey) {
                const savePayload = {
                    provider: this.selectedProvider,
                    default_model: document.getElementById('aiDefaultModel').value
                };
                
                if (this.selectedProvider === 'gemini') {
                    savePayload.gemini_api_key = apiKey;
                } else {
                    savePayload.openrouter_api_key = apiKey;
                }
                
                await fetch('/api/llm/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(savePayload)
                });
            }
            
            const response = await fetch(`/api/llm/config/test?provider=${this.selectedProvider}`, { method: 'POST' });
            const result = await response.json();
            
            if (result.success) {
                resultDiv.className = 'ai-test-result success';
                resultDiv.innerHTML = `
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                        <polyline points="22 4 12 14.01 9 11.01"/>
                    </svg>
                    ${result.message}${result.model_count ? ` (${result.model_count} models available)` : ''}
                `;
            } else {
                resultDiv.className = 'ai-test-result error';
                resultDiv.innerHTML = `
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <path d="M15 9l-6 6M9 9l6 6"/>
                    </svg>
                    ${result.message}
                `;
            }
        } catch (error) {
            resultDiv.className = 'ai-test-result error';
            resultDiv.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M15 9l-6 6M9 9l6 6"/>
                </svg>
                Connection failed: ${error.message}
            `;
        }
    }
    
    async save() {
        const geminiKey = document.getElementById('aiGeminiKey').value.trim();
        const openrouterKey = document.getElementById('aiApiKey').value.trim();
        const tavilyKey = document.getElementById('aiTavilyKey').value.trim();
        const defaultModel = document.getElementById('aiDefaultModel').value;
        const customModelInput = document.getElementById('aiCustomModel');
        const customModel = customModelInput ? customModelInput.value.trim() : '';
        const webSearchEnabled = document.getElementById('aiWebSearchEnabled')?.checked || false;
        const aiEnabled = document.getElementById('aiEnabled')?.checked ?? true;
        const autoGenerate = document.getElementById('aiAutoGenerate')?.checked ?? true;
        
        // Use custom model if provided (OpenRouter only), otherwise use dropdown selection
        const modelToUse = (this.selectedProvider === 'openrouter' && customModel) ? customModel : defaultModel;
        
        // Validate that selected provider has a key
        const isGemini = this.selectedProvider === 'gemini';
        const isConfigured = isGemini ? 
            (geminiKey || this.currentConfig?.gemini_configured) :
            (openrouterKey || this.currentConfig?.openrouter_configured);
        
        if (!isConfigured) {
            window.showModal('API Key Required', `<p>Please enter a ${isGemini ? 'Gemini' : 'OpenRouter'} API key to continue.</p>`, null);
            return;
        }
        
        const saveBtn = document.getElementById('aiSaveBtn');
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<div class="ai-spinner"></div> Saving...';
        
        try {
            const payload = {
                provider: this.selectedProvider,
                default_model: modelToUse,
                web_search_enabled: webSearchEnabled,
                ai_enabled: aiEnabled,
                auto_generate: autoGenerate
            };
            if (tavilyKey) {
                payload.tavily_api_key = tavilyKey;
            }
            
            // Add API keys if provided
            if (geminiKey) {
                payload.gemini_api_key = geminiKey;
            }
            if (openrouterKey) {
                payload.openrouter_api_key = openrouterKey;
            }
            
            const response = await fetch('/api/llm/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            if (response.ok) {
                this.currentConfig = await response.json();
                this.updateStatusDisplay();
                
                // Call callback if set
                if (this.onConfigSaved) {
                    this.onConfigSaved(this.currentConfig);
                }
                
                this.close();
            } else {
                const error = await response.json();
                window.showModal('Save Failed', `<p style="color: #ef4444;">Failed to save: ${error.detail || 'Unknown error'}</p>`, null);
            }
        } catch (error) {
            window.showModal('Save Failed', `<p style="color: #ef4444;">Failed to save configuration: ${error.message}</p>`, null);
        } finally {
            saveBtn.disabled = false;
            saveBtn.innerHTML = `
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                    <polyline points="17 21 17 13 7 13 7 21"/>
                    <polyline points="7 3 7 8 15 8"/>
                </svg>
                Save
            `;
        }
    }
    
    open() {
        this.loadConfig();
        this.loadModels();
        this.overlay.classList.add('active');
        this.isOpen = true;
        
        // Clear previous test results
        document.getElementById('aiTestResult').style.display = 'none';
        document.getElementById('aiApiKey').value = '';
        document.getElementById('aiGeminiKey').value = '';
        document.getElementById('aiCustomModel').value = '';
        document.getElementById('aiTavilyKey').value = '';
        
        // If current model is not in our predefined list, show it in custom field
        if (this.currentConfig && this.currentConfig.default_model) {
            const isKnownModel = this.models.some(m => m.id === this.currentConfig.default_model);
            if (!isKnownModel) {
                document.getElementById('aiCustomModel').value = this.currentConfig.default_model;
            }
        }
        
        // Set web search checkbox
        const webSearchCheckbox = document.getElementById('aiWebSearchEnabled');
        if (webSearchCheckbox && this.currentConfig) {
            webSearchCheckbox.checked = this.currentConfig.web_search_enabled || false;
        }
        
        // Set AI enabled toggle
        const aiEnabledCheckbox = document.getElementById('aiEnabled');
        if (aiEnabledCheckbox && this.currentConfig) {
            aiEnabledCheckbox.checked = this.currentConfig.ai_enabled !== false; // Default to true
            this.updateProviderSectionVisibility();
        }
        
        // Set auto-generate toggle
        const autoGenerateCheckbox = document.getElementById('aiAutoGenerate');
        if (autoGenerateCheckbox && this.currentConfig) {
            autoGenerateCheckbox.checked = this.currentConfig.auto_generate !== false; // Default to true
        }
    }
    
    updateProviderSectionVisibility() {
        const aiEnabled = document.getElementById('aiEnabled')?.checked ?? true;
        const providerSection = document.getElementById('providerSection');
        const geminiSection = document.getElementById('geminiSection');
        const openrouterSection = document.getElementById('openrouterSection');
        const customModelSection = document.getElementById('customModelSection');
        
        if (providerSection) {
            providerSection.style.opacity = aiEnabled ? '1' : '0.5';
            providerSection.style.pointerEvents = aiEnabled ? 'auto' : 'none';
        }
        if (geminiSection) {
            geminiSection.style.opacity = aiEnabled ? '1' : '0.5';
            geminiSection.style.pointerEvents = aiEnabled ? 'auto' : 'none';
        }
        if (openrouterSection) {
            openrouterSection.style.opacity = aiEnabled ? '1' : '0.5';
            openrouterSection.style.pointerEvents = aiEnabled ? 'auto' : 'none';
        }
        if (customModelSection) {
            customModelSection.style.opacity = aiEnabled ? '1' : '0.5';
            customModelSection.style.pointerEvents = aiEnabled ? 'auto' : 'none';
        }
    }
    
    switchTab(tabName) {
        // Update tab buttons
        this.overlay.querySelectorAll('.ai-modal-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.tab === tabName);
        });
        
        // Update tab content
        this.overlay.querySelectorAll('.ai-tab-content').forEach(content => {
            content.classList.toggle('active', content.dataset.tabContent === tabName);
        });
        
        // Load routing history when switching to that tab
        if (tabName === 'routing') {
            this.loadRoutingHistory();
        }
    }
    
    async loadRoutingHistory() {
        const mismatchOnly = document.getElementById('routingMismatchOnly')?.checked || false;
        const tbody = document.getElementById('routingHistoryBody');
        
        if (!tbody) return;
        
        // Show loading
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="ai-routing-history-loading">
                    Loading...
                </td>
            </tr>
        `;
        
        try {
            const url = `/api/llm/routing/feedback?mismatch_only=${mismatchOnly}&limit=50`;
            const response = await fetch(url);
            
            if (!response.ok) {
                throw new Error('Failed to load routing history');
            }
            
            const data = await response.json();
            
            if (data.items.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="ai-routing-history-empty">
                            ${mismatchOnly 
                                ? 'No mismatches found. All routing decisions match user feedback!' 
                                : 'No routing feedback yet. Rate answers in Smart Search to build history.'}
                        </td>
                    </tr>
                `;
                this.updateRoutingStats(data);
                return;
            }
            
            // Build table rows
            tbody.innerHTML = data.items.map(item => {
                const suggested = [];
                if (item.should_use_local) suggested.push('⚡ Local');
                if (item.should_use_kb) suggested.push('📚 KB');
                if (item.should_use_report) suggested.push('📄 Report');
                
                const actualIcon = item.actual_source === 'local' ? '⚡' : 
                                   item.actual_source === 'kb' ? '📚' : '📄';
                
                const mismatchClass = item.mismatch ? 'mismatch' : '';
                const dateStr = new Date(item.created_at).toLocaleDateString();
                
                return `
                    <tr class="${mismatchClass}">
                        <td class="ai-routing-question" title="${this.escapeHtml(item.question)}">
                            ${this.escapeHtml(item.question.slice(0, 60))}${item.question.length > 60 ? '...' : ''}
                        </td>
                        <td class="ai-routing-actual">
                            ${actualIcon} ${item.actual_source}
                        </td>
                        <td class="ai-routing-suggested">
                            ${suggested.join(', ') || '-'}
                        </td>
                        <td class="ai-routing-comment" title="${this.escapeHtml(item.comment || '')}">
                            ${item.comment ? this.escapeHtml(item.comment.slice(0, 30)) + (item.comment.length > 30 ? '...' : '') : '-'}
                        </td>
                        <td class="ai-routing-date">${dateStr}</td>
                    </tr>
                `;
            }).join('');
            
            this.updateRoutingStats(data);
            
        } catch (error) {
            console.error('Failed to load routing history:', error);
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="ai-routing-history-error">
                        Failed to load routing history: ${error.message}
                    </td>
                </tr>
            `;
        }
    }
    
    updateRoutingStats(data) {
        const statsEl = document.getElementById('routingStats');
        if (!statsEl) return;
        
        const total = data.items.length;
        const mismatches = data.items.filter(i => i.mismatch).length;
        const matchRate = total > 0 ? Math.round(((total - mismatches) / total) * 100) : 0;
        
        statsEl.innerHTML = `
            <div class="ai-routing-stat">
                <span class="ai-routing-stat-value">${total}</span>
                <span class="ai-routing-stat-label">Total Feedback</span>
            </div>
            <div class="ai-routing-stat">
                <span class="ai-routing-stat-value">${mismatches}</span>
                <span class="ai-routing-stat-label">Mismatches</span>
            </div>
            <div class="ai-routing-stat">
                <span class="ai-routing-stat-value">${matchRate}%</span>
                <span class="ai-routing-stat-label">Match Rate</span>
            </div>
        `;
    }
    
    async exportRoutingHistory() {
        try {
            const response = await fetch('/api/llm/routing/feedback/export');
            if (!response.ok) {
                throw new Error('Export failed');
            }
            
            // Download the CSV file
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'routing_feedback.csv';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();
        } catch (error) {
            console.error('Failed to export routing history:', error);
            alert('Failed to export routing history');
        }
    }
    
    renderSanitizationEntities() {
        const container = document.getElementById('aiSanitizationEntities');
        if (!container) return;
        const layers = [
            { title: 'Layer 1: Presidio Core', items: ['IP address', 'Email', 'URL', 'Phone'] },
            { title: 'Layer 2: SpaCy NER', items: ['Person names', 'Groups/Nationalities'] },
            { title: 'Layer 3: Custom Recognizers', items: ['Hostnames', 'UNC paths', 'Connection strings', 'License info', 'File paths', 'Cloud resources', 'HTTPPath', 'Task server headers', 'Revision hashes'] },
            { title: 'Layer 4: Denylist Guards', items: ['ODBC/SQL codes', 'Replicate task terms', 'Schema.table patterns'] }
        ];
        const entities = [
            { label: 'IP Address', replacement: '[IP_ADDRESS]' },
            { label: 'Email Address', replacement: '[EMAIL]' },
            { label: 'URL', replacement: '[URL]' },
            { label: 'Phone Number', replacement: '[PHONE]' },
            { label: 'Person Name', replacement: '[PERSON]' },
            { label: 'Group/Nationality', replacement: '[GROUP]' },
            { label: 'Server/Hostname', replacement: '[HOSTNAME]' },
            { label: 'Network Path (UNC)', replacement: '[UNC_PATH]' },
            { label: 'Connection String', replacement: '[REDACTED]' },
            { label: 'License/Company Info', replacement: '[COMPANY]' },
            { label: 'File Path', replacement: '[PATH]' },
            { label: 'Cloud Resource ID', replacement: '[CLOUD_RESOURCE]' },
            { label: 'HTTP Path', replacement: '[REDACTED]' },
            { label: 'Task Server Info', replacement: '[SERVER_INFO]' },
            { label: 'Revision Hash', replacement: '[REVISION]' },
        ];
        container.innerHTML = `
            <div class="ai-sanitize-summary">
                <div class="ai-sanitize-card">
                    <div class="ai-sanitize-card-title">Sanitized</div>
                    <ul>
                        <li>Log summaries, errors, anomalies</li>
                        <li>File metadata (paths, filenames)</li>
                    </ul>
                </div>
                <div class="ai-sanitize-card">
                    <div class="ai-sanitize-card-title">Not sanitized</div>
                    <ul>
                        <li>KB articles (public docs)</li>
                        <li>System prompts</li>
                    </ul>
                </div>
                <div class="ai-sanitize-card">
                    <div class="ai-sanitize-card-title">Layers</div>
                    ${layers.map(layer => `
                        <div class="ai-sanitize-layer">
                            <div class="ai-sanitize-layer-title">${layer.title}</div>
                            <div class="ai-sanitize-layer-items">${layer.items.join(' · ')}</div>
                        </div>
                    `).join('')}
                </div>
            </div>
            <div class="ai-entity-list">
                ${entities.map(e => `
                    <div class="ai-entity-item">
                        <div class="ai-entity-row">
                            <span class="ai-entity-name">${e.label}</span>
                            <span class="ai-entity-arrow">→</span>
                            <span class="ai-entity-replacement">${e.replacement}</span>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    async previewSanitization() {
        const input = document.getElementById('aiSanitizeInput');
        const resultEl = document.getElementById('aiSanitizeResult');
        if (!input || !resultEl) return;
        const text = input.value.trim();
        if (!text) {
            resultEl.innerHTML = '<div class="ai-sanitize-empty">Enter text to preview redactions.</div>';
            return;
        }
        resultEl.innerHTML = '<div class="ai-sanitize-loading">Analyzing...</div>';
        try {
            const resp = await fetch('/api/llm/preview-redactions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });
            if (!resp.ok) {
                throw new Error('Preview failed');
            }
            const data = await resp.json();
            const redactions = data.redactions || [];
            resultEl.innerHTML = `
                <div class="ai-sanitize-section">
                    <div class="ai-sanitize-label">Sanitized</div>
                    <pre class="ai-sanitize-block">${this.escapeHtml(data.sanitized || '')}</pre>
                </div>
                <div class="ai-sanitize-section">
                    <div class="ai-sanitize-label">Detections (${redactions.length})</div>
                    ${redactions.length === 0 ? '<div class="ai-sanitize-none">No sensitive info detected.</div>' : `
                        <ul class="ai-sanitize-list">
                            ${redactions.map(r => `
                                <li>
                                    <span class="ai-sanitize-type">${this.escapeHtml(r.type_description || r.type)}</span>
                                    <code>${this.escapeHtml(r.original_value)}</code>
                                    <span class="ai-sanitize-arrow">→</span>
                                    <code>${this.escapeHtml(r.replacement)}</code>
                                </li>
                            `).join('')}
                        </ul>
                    `}
                </div>
            `;
        } catch (error) {
            console.error('Sanitization preview failed', error);
            resultEl.innerHTML = '<div class="ai-sanitize-error">Preview failed. Try again.</div>';
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    close() {
        this.overlay.classList.remove('active');
        this.isOpen = false;
    }
    
    isConfigured() {
        return this.currentConfig && this.currentConfig.is_configured;
    }
}

// Create singleton instance
window.aiConfigModal = new AIConfigModal();

