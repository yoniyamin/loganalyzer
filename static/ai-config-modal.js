/**
 * AI Configuration Modal
 * 
 * Provides a modal dialog for configuring AI API settings:
 * - Provider selection (LM Studio default in UI; persisted via Save)
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
        this.selectedProvider = 'lmstudio';
        this.onConfigSaved = null; // Callback when config is saved
        
        this.init();
    }
    
    init() {
        // Create modal HTML
        this.createModal();
        
        // Load initial config (also loads models when config resolves)
        this.loadConfig();

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
                    
                    <!-- Tab row + compact status -->
                    <div class="ai-modal-tabs-bar">
                        <div class="ai-modal-tabs">
                            <button type="button" class="ai-modal-tab active" data-tab="config">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                                    <circle cx="12" cy="12" r="3"/>
                                    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
                                </svg>
                                Configuration
                            </button>
                            <button type="button" class="ai-modal-tab" data-tab="sanitization">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                                    <path d="M12 1l3 5 5 3-5 3-3 5-3-5-5-3 5-3z"/>
                                </svg>
                                Sanitization
                            </button>
                        </div>
                        <div class="ai-status-compact" id="aiStatusCompact" role="status" aria-live="polite"></div>
                    </div>
                    
                    <div class="ai-modal-body">
                        <!-- Config Tab Content -->
                        <div class="ai-tab-content active" data-tab-content="config">
                            
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
                        <div class="ai-form-group ai-provider-section ai-provider-select-wrap" id="providerSection">
                            <label for="aiProviderSelect">AI Provider</label>
                            <select id="aiProviderSelect" class="ai-select">
                                <option value="lmstudio">LM Studio (local)</option>
                                <option value="gemini">Google Gemini</option>
                                <option value="openrouter">OpenRouter</option>
                            </select>
                            <p class="ai-help-text">Saved when you click Save. Your last choice is restored on the next visit.</p>
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
                        
                        <!-- LM Studio Section -->
                        <div class="ai-form-group ai-lmstudio-section" id="lmstudioSection" style="display: none;">
                            <label for="aiLMStudioUrl">LM Studio Server URL</label>
                            <div class="ai-input-wrapper">
                                <input type="text" id="aiLMStudioUrl" class="ai-input"
                                       value="http://localhost:1234" placeholder="http://localhost:1234" autocomplete="off">
                            </div>
                            <p class="ai-help-text">
                                In LM Studio: Developer tab → Start Server (default port 1234).
                                <br><span style="color: #22c55e;">✓ No API key needed — runs fully locally.</span>
                            </p>

                            <!-- Model generation parameters -->
                            <div class="ai-lmstudio-params">
                                <div class="ai-param-row">
                                    <div class="ai-param-group">
                                        <label for="aiLMStudioTemp">Temperature</label>
                                        <input type="number" id="aiLMStudioTemp" class="ai-input ai-param-input"
                                               value="0.3" min="0" max="2" step="0.05" placeholder="0.3">
                                        <p class="ai-help-text">Lower = more focused. 0.1–0.4 recommended for reports.</p>
                                    </div>
                                    <div class="ai-param-group">
                                        <label for="aiLMStudioMaxTokens">Max Output Tokens</label>
                                        <input type="number" id="aiLMStudioMaxTokens" class="ai-input ai-param-input"
                                               value="1500" min="256" max="4096" step="128" placeholder="1500">
                                        <p class="ai-help-text">Response length cap. Higher = more detail, slower.</p>
                                    </div>
                                </div>
                            </div>
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
                        
                        <!-- Cloud-only: web search, cloud sanitization notice, Tavily -->
                        <div id="aiCloudExtras" class="ai-cloud-extras">

                        <!-- Mandatory log sanitization (cloud only — LM Studio hides this block) -->
                        <div class="ai-sanitize-mandatory-notice" id="aiCloudSanitizeNotice">
                            <strong>Log sanitization is required</strong> for Google Gemini and OpenRouter. Identifiers are redacted before any log-derived content is sent to the cloud. This is always on for these providers and cannot be turned off.
                            <br><span style="color: var(--text-muted, #585b70);">LM Studio runs locally and does not use this cloud sanitization path.</span>
                        </div>

                        <!-- Web Search Option -->
                        <div class="ai-form-group">
                            <label class="ai-checkbox-label">
                                <input type="checkbox" id="aiWebSearchEnabled">
                                <span>Enable Web Search</span>
                            </label>
                            <p class="ai-help-text ai-cloud-extras-note">
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
                            <p class="ai-help-text ai-cloud-extras-note">
                                Used for manual error resolution searches (Tavily advanced answer).
                            </p>
                        </div>

                        </div><!-- aiCloudExtras -->
                        </div><!-- End Config Tab -->
                        
                        <!-- Sanitization Tab Content -->
                        <div class="ai-tab-content" data-tab-content="sanitization">
                            <div class="ai-sanitization-header">
                                <h3>Sanitization Rules</h3>
                                <p class="ai-sanitization-desc">
                                    For <strong>Google Gemini</strong> and <strong>OpenRouter</strong>, log-derived content is always sanitized before it is sent to the model (required; cannot be disabled).
                                    <strong>LM Studio</strong> runs locally and does not use this cloud sanitization path for prompts.
                                    KB articles are never modified.
                                    Embeddings in the vector index are still sanitized to protect stored chunks.
                                    Use this tab to preview rules and test samples.
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
        
        // Sanitization preview
        document.getElementById('aiSanitizePreviewBtn')?.addEventListener('click', () => {
            this.previewSanitization();
        });
        
        // AI enabled toggle
        document.getElementById('aiEnabled').addEventListener('change', () => {
            this.updateProviderSectionVisibility();
        });
        
        // Provider dropdown
        document.getElementById('aiProviderSelect').addEventListener('change', (e) => {
            this.switchProvider(e.target.value);
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

        const sel = document.getElementById('aiProviderSelect');
        if (sel && sel.value !== provider) {
            sel.value = provider;
        }

        this._applyProviderUi();
        // Reload models for the selected provider
        this.loadModels();
        
        // Update status display
        this.updateStatusDisplay();
    }

    _applyProviderUi() {
        const provider = this.selectedProvider;
        document.getElementById('geminiSection').style.display = provider === 'gemini' ? 'block' : 'none';
        document.getElementById('openrouterSection').style.display = provider === 'openrouter' ? 'block' : 'none';
        document.getElementById('lmstudioSection').style.display = provider === 'lmstudio' ? 'block' : 'none';
        document.getElementById('customModelSection').style.display = provider === 'openrouter' ? 'block' : 'none';
        const cloudExtras = document.getElementById('aiCloudExtras');
        if (cloudExtras) {
            cloudExtras.style.display = provider === 'lmstudio' ? 'none' : 'block';
        }
    }
    
    async loadConfig() {
        try {
            const response = await fetch('/api/llm/config');
            if (response.ok) {
                this.currentConfig = await response.json();
                // Set provider from config
                if (this.currentConfig.provider) {
                    this.selectedProvider = String(this.currentConfig.provider).toLowerCase();
                }
                const provSelect = document.getElementById('aiProviderSelect');
                if (provSelect) {
                    provSelect.value = this.selectedProvider;
                }
                this._applyProviderUi();
                // Populate LM Studio fields
                if (this.currentConfig.lmstudio_base_url) {
                    const urlInput = document.getElementById('aiLMStudioUrl');
                    if (urlInput) urlInput.value = this.currentConfig.lmstudio_base_url;
                }
                if (this.currentConfig.lmstudio_temperature != null) {
                    const tempInput = document.getElementById('aiLMStudioTemp');
                    if (tempInput) tempInput.value = this.currentConfig.lmstudio_temperature;
                }
                if (this.currentConfig.lmstudio_max_tokens != null) {
                    const maxTokInput = document.getElementById('aiLMStudioMaxTokens');
                    if (maxTokInput) maxTokInput.value = this.currentConfig.lmstudio_max_tokens;
                }
                this.updateStatusDisplay();
                await this.loadModels();
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
        if (!select) return;

        const cfg = this.currentConfig;
        const savedProv = cfg?.provider ? String(cfg.provider).toLowerCase() : null;
        const applySavedModel = savedProv === this.selectedProvider;
        const savedDefault =
            applySavedModel && cfg?.default_model ? cfg.default_model : null;

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

        if (customInput) {
            customInput.value = '';
        }

        if (savedDefault) {
            const isKnownModel = this.models.some(m => m.id === savedDefault);
            if (isKnownModel) {
                select.value = savedDefault;
            } else if (this.selectedProvider === 'openrouter') {
                if (customInput) customInput.value = savedDefault;
                if (this.models[0]) select.value = this.models[0].id;
            } else {
                if (this.models[0]) select.value = this.models[0].id;
            }
        } else if (this.models[0]) {
            select.value = this.models[0].id;
        }
        
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
                <div class="model-description">Custom model: <code>${this.escapeHtml(customModel)}</code></div>
                <div class="model-pricing">
                    <span style="color: #f59e0b;">Pricing depends on the model - check OpenRouter</span>
                </div>
            `;
            return;
        }
        
        if (model) {
            const isFree = model.prompt_price === 0 && model.completion_price === 0;
            const pricingHtml = isFree 
                ? '<span style="color: #22c55e; font-weight: 600;">Free — no cost per token</span>'
                : `<span>Input: $${model.prompt_price.toFixed(2)}/M tokens</span>
                   <span>Output: $${model.completion_price.toFixed(2)}/M tokens</span>`;

            let lmLoadHint = '';
            if (this.selectedProvider === 'lmstudio') {
                const desc = model.description || '';
                const loaded =
                    /\bLoaded\b/i.test(desc) ||
                    (typeof model.name === 'string' && model.name.includes('(loaded)'));
                lmLoadHint = loaded
                    ? '<div class="model-lm-load-hint" style="margin-top:8px;font-size:0.78rem;color:#22c55e;font-weight:500;">Status: loaded in LM Studio — ready to generate.</div>'
                    : '<div class="model-lm-load-hint" style="margin-top:8px;font-size:0.78rem;color:#f59e0b;">Status: not loaded — load this model in LM Studio before generating reports.</div>';
            }
            
            infoDiv.innerHTML = `
                <div class="model-description">${this.escapeHtml(model.description || 'No description available')}</div>
                ${lmLoadHint}
                <div class="model-pricing">
                    ${pricingHtml}
                </div>
            `;
        } else {
            infoDiv.innerHTML = `
                <div class="model-description">Select a model to see details</div>
                <div class="model-pricing">
                    <span>Input: $--/M tokens</span>
                    <span>Output: $--/M tokens</span>
                </div>
            `;
        }
    }
    
    updateStatusDisplay() {
        const host = document.getElementById('aiStatusCompact');
        if (!host) return;

        if (!this.currentConfig) {
            host.innerHTML = this._renderStatusPills([
                { icon: '✨', ok: false, title: 'Gemini API key not saved', mark: '−' },
                { icon: '🔀', ok: false, title: 'OpenRouter API key not saved', mark: '−' },
                { icon: '🖥️', ok: true, title: 'LM Studio — local inference (no cloud API key)', mark: '✓' },
                { icon: '🌐', ok: false, title: 'Tavily not configured (optional)', mark: '−' },
            ]);
            return;
        }

        this._applyKeyPlaceholders();

        const c = this.currentConfig;
        const geminiOk = !!c.gemini_configured;
        const orOk = !!c.openrouter_configured;
        const tavOk = !!c.tavily_configured;

        host.innerHTML = this._renderStatusPills([
            {
                icon: '✨',
                ok: geminiOk,
                title: geminiOk
                    ? `Gemini key: ${c.gemini_api_key_preview || 'saved'}`
                    : 'Gemini API key not saved',
                mark: geminiOk ? '✓' : '−',
            },
            {
                icon: '🔀',
                ok: orOk,
                title: orOk
                    ? `OpenRouter key: ${c.openrouter_api_key_preview || 'saved'}`
                    : 'OpenRouter API key not saved',
                mark: orOk ? '✓' : '−',
            },
            {
                icon: '🖥️',
                ok: true,
                title: `LM Studio base URL: ${c.lmstudio_base_url || 'http://localhost:1234'}`,
                mark: '✓',
            },
            {
                icon: '🌐',
                ok: tavOk,
                title: tavOk
                    ? `Tavily key: ${c.tavily_api_key_preview || 'saved'}`
                    : 'Tavily not configured (optional)',
                mark: tavOk ? '✓' : '−',
            },
        ]);
    }

    _applyKeyPlaceholders() {
        const c = this.currentConfig;
        const geminiInput = document.getElementById('aiGeminiKey');
        const openrouterInput = document.getElementById('aiApiKey');
        const tavilyInput = document.getElementById('aiTavilyKey');
        if (!c) return;
        if (c.gemini_api_key_preview && geminiInput) {
            geminiInput.placeholder = c.gemini_api_key_preview;
        }
        if (c.openrouter_api_key_preview && openrouterInput) {
            openrouterInput.placeholder = c.openrouter_api_key_preview;
        }
        if (c.tavily_api_key_preview && tavilyInput) {
            tavilyInput.placeholder = c.tavily_api_key_preview;
        }
    }

    _renderStatusPills(items) {
        return items.map(p => {
            const tip = this.escapeAttr(p.title);
            const ok = p.ok ? 'true' : 'false';
            return `<span class="ai-status-pill" data-ok="${ok}" title="${tip}"><span class="ai-status-ico">${p.icon}</span><span class="ai-status-mark">${p.mark}</span></span>`;
        }).join('');
    }

    escapeAttr(s) {
        if (s == null) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;');
    }
    
    async testConnection() {
        const resultDiv = document.getElementById('aiTestResult');
        
        // Get API key based on selected provider (not applicable for LM Studio)
        const isLMStudio = this.selectedProvider === 'lmstudio';
        const apiKey = isLMStudio ? null
            : this.selectedProvider === 'gemini'
                ? document.getElementById('aiGeminiKey').value
                : document.getElementById('aiApiKey').value;
        
        // Show loading
        resultDiv.style.display = 'flex';
        resultDiv.className = 'ai-test-result loading';
        resultDiv.innerHTML = '<div class="ai-spinner"></div> Testing connection...';
        
        try {
            // For cloud providers: save the key first if entered.
            // For LM Studio: save the URL so the backend uses the latest value.
            if (isLMStudio) {
                const lmUrl = document.getElementById('aiLMStudioUrl')?.value.trim() || 'http://localhost:1234';
                const testPayload = { provider: 'lmstudio', lmstudio_base_url: lmUrl };
                const rawTemp = parseFloat(document.getElementById('aiLMStudioTemp')?.value);
                if (!isNaN(rawTemp)) testPayload.lmstudio_temperature = rawTemp;
                const rawMaxTok = parseInt(document.getElementById('aiLMStudioMaxTokens')?.value, 10);
                if (!isNaN(rawMaxTok)) testPayload.lmstudio_max_tokens = rawMaxTok;
                await fetch('/api/llm/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(testPayload)
                });
            } else if (apiKey) {
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
        
        // Validate that selected provider has a key (LM Studio never needs one)
        const isGemini = this.selectedProvider === 'gemini';
        const isLMStudio = this.selectedProvider === 'lmstudio';
        const isConfigured = isLMStudio ? true
            : isGemini
                ? (geminiKey || this.currentConfig?.gemini_configured)
                : (openrouterKey || this.currentConfig?.openrouter_configured);
        
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
            if (!isLMStudio) {
                payload.sanitize_log_for_cloud_llm = true;
            }
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
            // LM Studio: include base URL and generation parameters
            if (isLMStudio) {
                payload.lmstudio_base_url = document.getElementById('aiLMStudioUrl')?.value.trim() || 'http://localhost:1234';
                const rawTemp = parseFloat(document.getElementById('aiLMStudioTemp')?.value);
                if (!isNaN(rawTemp)) payload.lmstudio_temperature = rawTemp;
                const rawMaxTok = parseInt(document.getElementById('aiLMStudioMaxTokens')?.value, 10);
                if (!isNaN(rawMaxTok)) payload.lmstudio_max_tokens = rawMaxTok;
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
        this.overlay.classList.add('active');
        this.isOpen = true;
        
        // Clear previous test results
        document.getElementById('aiTestResult').style.display = 'none';
        document.getElementById('aiApiKey').value = '';
        document.getElementById('aiGeminiKey').value = '';
        document.getElementById('aiCustomModel').value = '';
        document.getElementById('aiTavilyKey').value = '';
        
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
        const sections = [
            'providerSection', 'geminiSection', 'openrouterSection',
            'lmstudioSection', 'customModelSection'
        ];
        for (const id of sections) {
            const el = document.getElementById(id);
            if (el) {
                el.style.opacity = aiEnabled ? '1' : '0.5';
                el.style.pointerEvents = aiEnabled ? 'auto' : 'none';
            }
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
                        <li>Log summaries, errors, anomalies (cloud LLMs: mandatory redaction)</li>
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

