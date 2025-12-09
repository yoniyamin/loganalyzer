/**
 * AI Assistant Module
 * 
 * Provides KB-powered AI assistance for log analysis:
 * - Magic wand button for quick questions
 * - KB article integration for relevant suggestions
 * - Thread history with thumbs up/down feedback
 * - Per-file Q&A persistence
 */

class AIAssistant {
    constructor() {
        this.isEnabled = false;
        this.currentFileId = null;
        this.threads = [];  // Q&A threads for current file
        this.currentThreadIndex = 0;  // Index of currently displayed thread
        this.isLoading = false;
        this.questionBoxVisible = false;
        this.pendingLogSnippet = null;  // Log snippet to include in question
        
        // DOM references (set after init)
        this.magicWandBtn = null;
        this.questionContainer = null;
        this.questionInput = null;
        this.aiPanel = null;
        this.aiTab = null;
        this.contextMenu = null;
        
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
        this.createElements();
        this.bindEvents();
        this.loadConfig();
    }
    
    createElements() {
        // Create magic wand button (floating in log preview)
        const logPreviewWrapper = document.querySelector('.log-preview-wrapper');
        if (logPreviewWrapper) {
            this.magicWandBtn = document.createElement('button');
            this.magicWandBtn.className = 'ai-magic-wand-btn';
            this.magicWandBtn.title = 'Ask AI about this log';
            this.magicWandBtn.innerHTML = `
                <svg viewBox="0 0 512 512" fill="currentColor">
                    <path d="M327.5 85.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 128l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 128l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 64 426.8 7.5C425.1 3 420.8 0 416 0s-9.1 3-10.8 7.5L384 64 327.5 85.2zM9.3 240C3.6 242.6 0 248.3 0 254.6s3.6 11.9 9.3 14.5L26.3 277l8.1 3.7 .6 .3 88.3 40.8L164.1 410l.3 .6 3.7 8.1 7.9 17.1c2.6 5.7 8.3 9.3 14.5 9.3s11.9-3.6 14.5-9.3l7.9-17.1 3.7-8.1 .3-.6 40.8-88.3L346 281l.6-.3 8.1-3.7 17.1-7.9c5.7-2.6 9.3-8.3 9.3-14.5s-3.6-11.9-9.3-14.5l-17.1-7.9-8.1-3.7-.6-.3-88.3-40.8L217 99.1l-.3-.6L213 90.3l-7.9-17.1c-2.6-5.7-8.3-9.3-14.5-9.3s-11.9 3.6-14.5 9.3l-7.9 17.1-3.7 8.1-.3 .6-40.8 88.3L35.1 228.1l-.6 .3-8.1 3.7L9.3 240z"/>
                </svg>
            `;
            logPreviewWrapper.style.position = 'relative';
            logPreviewWrapper.appendChild(this.magicWandBtn);
            
            // Create question input container
            this.questionContainer = document.createElement('div');
            this.questionContainer.className = 'ai-question-container';
            this.questionContainer.innerHTML = `
                <div class="ai-question-box">
                    <div class="ai-snippet-preview" style="display: none;">
                        <div class="ai-snippet-header">
                            <span class="ai-snippet-label">📎 Log snippet attached:</span>
                            <button class="ai-snippet-remove" title="Remove snippet">×</button>
                        </div>
                        <pre class="ai-snippet-content"></pre>
                        <div class="ai-snippet-redaction-hint"></div>
                    </div>
                    <textarea 
                        class="ai-question-input" 
                        placeholder="Ask about errors, performance issues, or troubleshooting..."
                        rows="3"
                    ></textarea>
                    <div class="ai-redaction-preview" style="display: none;">
                        <div class="ai-redaction-preview-header">
                            <span>🔒 Redaction Preview</span>
                            <button class="ai-redaction-preview-close" title="Close preview">×</button>
                        </div>
                        <div class="ai-redaction-preview-content"></div>
                    </div>
                    <div class="ai-question-actions">
                        <span class="ai-question-hint">Press Enter to submit, Shift+Enter for new line</span>
                        <button class="ai-question-preview" type="button" title="Preview what will be redacted">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                                <circle cx="12" cy="12" r="3"/>
                            </svg>
                            Preview
                        </button>
                        <button class="ai-question-submit" type="button">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
                            </svg>
                            Ask
                        </button>
                    </div>
                </div>
            `;
            logPreviewWrapper.appendChild(this.questionContainer);
            this.questionInput = this.questionContainer.querySelector('.ai-question-input');
            
            // Snippet remove button
            const snippetRemoveBtn = this.questionContainer.querySelector('.ai-snippet-remove');
            if (snippetRemoveBtn) {
                snippetRemoveBtn.addEventListener('click', () => this.clearSnippet());
            }
            
            // Preview button
            const previewBtn = this.questionContainer.querySelector('.ai-question-preview');
            if (previewBtn) {
                previewBtn.addEventListener('click', () => this.showRedactionPreview());
            }
            
            // Preview close button
            const previewCloseBtn = this.questionContainer.querySelector('.ai-redaction-preview-close');
            if (previewCloseBtn) {
                previewCloseBtn.addEventListener('click', () => this.hideRedactionPreview());
            }
        }
        
        // Create context menu for log lines
        this.contextMenu = document.createElement('div');
        this.contextMenu.className = 'ai-context-menu';
        this.contextMenu.innerHTML = `
            <button class="ai-context-menu-item" data-action="ask-ai">
                <svg viewBox="0 0 512 512" fill="currentColor" width="14" height="14">
                    <path d="M327.5 85.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 128l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 128l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 64 426.8 7.5C425.1 3 420.8 0 416 0s-9.1 3-10.8 7.5L384 64 327.5 85.2z"/>
                </svg>
                Ask AI about this
            </button>
        `;
        this.contextMenu.style.display = 'none';
        document.body.appendChild(this.contextMenu);
        
        // Get AI panel reference (will be added to HTML)
        this.aiPanel = document.getElementById('ai-panel');
        this.aiTab = document.querySelector('.left-panel-tab[data-panel="ai-panel"]');
    }
    
    bindEvents() {
        // Magic wand click
        if (this.magicWandBtn) {
            this.magicWandBtn.addEventListener('click', () => this.toggleQuestionBox());
        }
        
        // Question input events
        if (this.questionInput) {
            this.questionInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.submitQuestion();
                }
            });
            
            // Submit button
            const submitBtn = this.questionContainer.querySelector('.ai-question-submit');
            if (submitBtn) {
                submitBtn.addEventListener('click', () => this.submitQuestion());
            }
        }
        
        // Close question box when clicking outside
        document.addEventListener('click', (e) => {
            if (this.questionBoxVisible && 
                !this.questionContainer.contains(e.target) && 
                !this.magicWandBtn.contains(e.target)) {
                this.hideQuestionBox();
            }
            // Hide context menu when clicking outside
            if (this.contextMenu && !this.contextMenu.contains(e.target)) {
                this.contextMenu.style.display = 'none';
            }
        });
        
        // Escape key to close
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                if (this.questionBoxVisible) {
                    this.hideQuestionBox();
                }
                if (this.contextMenu) {
                    this.contextMenu.style.display = 'none';
                }
            }
            
            // Ctrl+Shift+A to open AI assistant
            if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'a') {
                e.preventDefault();
                if (!this.isEnabled) return;
                
                // Switch to AI tab
                this.switchToAITab();
                
                // Toggle question box
                if (!this.questionBoxVisible) {
                    this.showQuestionBox();
                }
                
                // Focus on input
                if (this.questionInput) {
                    this.questionInput.focus();
                }
            }
        });
        
        // Context menu for log preview
        const logPreview = document.getElementById('log-preview');
        if (logPreview) {
            logPreview.addEventListener('contextmenu', (e) => this.handleLogContextMenu(e));
        }
        
        // Context menu item click
        if (this.contextMenu) {
            this.contextMenu.addEventListener('click', (e) => {
                const action = e.target.closest('[data-action]')?.dataset.action;
                if (action === 'ask-ai') {
                    this.addSelectedTextAsSnippet();
                }
                this.contextMenu.style.display = 'none';
            });
        }
    }
    
    handleLogContextMenu(e) {
        // Only show context menu if AI is enabled and text is selected
        const selection = window.getSelection();
        const selectedText = selection.toString().trim();
        
        if (!this.isEnabled || !selectedText || !this.currentFileId) {
            return;
        }
        
        e.preventDefault();
        
        // Position and show context menu
        this.contextMenu.style.left = `${e.pageX}px`;
        this.contextMenu.style.top = `${e.pageY}px`;
        this.contextMenu.style.display = 'block';
    }
    
    async addSelectedTextAsSnippet() {
        const selection = window.getSelection();
        const selectedText = selection.toString().trim();
        
        if (!selectedText) return;
        
        this.pendingLogSnippet = selectedText;
        
        // Show snippet preview in question box
        const snippetPreview = this.questionContainer.querySelector('.ai-snippet-preview');
        const snippetContent = this.questionContainer.querySelector('.ai-snippet-content');
        const redactionHint = this.questionContainer.querySelector('.ai-snippet-redaction-hint');
        
        if (snippetPreview && snippetContent) {
            // Show truncated snippet
            const displayText = selectedText.length > 300 
                ? selectedText.substring(0, 300) + '...' 
                : selectedText;
            snippetContent.textContent = displayText;
            snippetPreview.style.display = 'block';
            
            // Get redaction preview
            try {
                const response = await fetch('/api/llm/preview-redactions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: selectedText })
                });
                
                if (response.ok) {
                    const result = await response.json();
                    if (result.redactions && result.redactions.length > 0) {
                        redactionHint.innerHTML = `
                            <span class="redaction-info">
                                🔒 <strong>${result.summary}</strong> will be masked before sending to AI
                            </span>
                        `;
                        redactionHint.style.display = 'block';
                    } else {
                        redactionHint.innerHTML = `
                            <span class="redaction-info safe">
                                ✓ No sensitive information detected
                            </span>
                        `;
                        redactionHint.style.display = 'block';
                    }
                }
            } catch (error) {
                console.error('Failed to preview redactions:', error);
                redactionHint.style.display = 'none';
            }
        }
        
        // Show question box
        this.showQuestionBox();
    }
    
    clearSnippet() {
        this.pendingLogSnippet = null;
        const snippetPreview = this.questionContainer.querySelector('.ai-snippet-preview');
        const redactionHint = this.questionContainer.querySelector('.ai-snippet-redaction-hint');
        if (snippetPreview) {
            snippetPreview.style.display = 'none';
        }
        if (redactionHint) {
            redactionHint.style.display = 'none';
        }
    }
    
    async showRedactionPreview() {
        // Build the full question that would be sent
        let question = this.questionInput.value.trim();
        if (this.pendingLogSnippet) {
            question += '\n\nLog snippet:\n```\n' + this.pendingLogSnippet + '\n```';
        }
        
        if (!question || !this.currentFileId) {
            return;
        }
        
        const previewContainer = this.questionContainer.querySelector('.ai-redaction-preview');
        const previewContent = this.questionContainer.querySelector('.ai-redaction-preview-content');
        
        if (!previewContainer || !previewContent) return;
        
        // Show loading state
        previewContent.innerHTML = '<div class="ai-redaction-loading">Analyzing prompt and context...</div>';
        previewContainer.style.display = 'block';
        
        try {
            const response = await fetch('/api/llm/prompt-preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    file_id: this.currentFileId,
                    question: question 
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                let html = '';
                
                // Summary section
                html += `<div class="ai-preview-summary">${this.escapeHtml(result.summary)}</div>`;
                
                // Processing flow visualization
                if (result.processing_flow && result.processing_flow.length > 0) {
                    html += '<div class="ai-processing-flow">';
                    html += '<div class="ai-preview-section-title">Processing Pipeline:</div>';
                    html += '<div class="ai-flow-steps">';
                    result.processing_flow.forEach((step, i) => {
                        const statusClass = step.status === 'completed' ? 'success' : 
                                           step.status === 'warning' ? 'warning' : 'skipped';
                        const statusIcon = step.status === 'completed' ? '✓' :
                                          step.status === 'warning' ? '⚠' : '○';
                        html += `
                            <div class="ai-flow-step ${statusClass}">
                                <span class="ai-flow-icon">${statusIcon}</span>
                                <span class="ai-flow-name">${step.step}</span>
                                <span class="ai-flow-detail">${step.detail}</span>
                            </div>
                            ${i < result.processing_flow.length - 1 ? '<div class="ai-flow-arrow">↓</div>' : ''}
                        `;
                    });
                    html += '</div></div>';
                }
                
                // Context breakdown
                html += '<div class="ai-preview-context">';
                html += '<div class="ai-preview-section-title">What will be sent to AI:</div>';
                
                // KB Articles section
                if (result.kb_articles && result.kb_articles.length > 0) {
                    html += `<div class="ai-preview-section">
                        <div class="ai-preview-label">
                            <svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12">
                                <path d="M1 2.828c.885-.37 2.154-.769 3.388-.893 1.33-.134 2.458.063 3.112.752v9.746c-.935-.53-2.12-.603-3.213-.493-1.18.12-2.37.461-3.287.811V2.828zm7.5-.141c.654-.689 1.782-.886 3.112-.752 1.234.124 2.503.523 3.388.893v9.923c-.918-.35-2.107-.692-3.287-.81-1.094-.111-2.278-.039-3.213.492V2.687z"/>
                            </svg>
                            KB Articles (${result.kb_articles.length})
                            <span class="ai-preview-tag safe">Not sanitized</span>
                        </div>
                        <div class="ai-preview-items">`;
                    result.kb_articles.forEach(kb => {
                        html += `<div class="ai-preview-item kb">
                            <span class="ai-preview-item-title">${this.escapeHtml(kb.title)}</span>
                            <span class="ai-preview-item-score">${Math.round(kb.similarity * 100)}%</span>
                        </div>`;
                    });
                    html += '</div></div>';
                } else {
                    html += `<div class="ai-preview-section empty">
                        <div class="ai-preview-label">
                            <svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12">
                                <path d="M1 2.828c.885-.37 2.154-.769 3.388-.893 1.33-.134 2.458.063 3.112.752v9.746c-.935-.53-2.12-.603-3.213-.493-1.18.12-2.37.461-3.287.811V2.828z"/>
                            </svg>
                            No relevant KB articles found
                        </div>
                    </div>`;
                }
                
                // Log Errors section
                if (result.log_errors && result.log_errors.length > 0) {
                    html += `<div class="ai-preview-section">
                        <div class="ai-preview-label">
                            <svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12">
                                <path d="M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5c.535 0 .954.462.9.995l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 5.995A.905.905 0 0 1 8 5zm.002 6a1 1 0 1 1 0 2 1 1 0 0 1 0-2z"/>
                            </svg>
                            Log Errors (${result.log_errors.length})
                            <span class="ai-preview-tag warning">Will be sanitized</span>
                        </div>
                        <div class="ai-preview-items">`;
                    result.log_errors.forEach((err, i) => {
                        const truncated = err.length > 100 ? err.substring(0, 100) + '...' : err;
                        html += `<div class="ai-preview-item error">
                            <code>${this.escapeHtml(truncated)}</code>
                        </div>`;
                    });
                    html += '</div></div>';
                } else {
                    html += `<div class="ai-preview-section empty">
                        <div class="ai-preview-label">
                            <svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12">
                                <path d="M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566z"/>
                            </svg>
                            No log errors in context
                        </div>
                    </div>`;
                }
                
                // Anomalies section
                if (result.log_anomalies && result.log_anomalies.length > 0) {
                    html += `<div class="ai-preview-section">
                        <div class="ai-preview-label">
                            <svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12">
                                <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/>
                                <path d="M7.002 11a1 1 0 1 1 2 0 1 1 0 0 1-2 0zM7.1 4.995a.905.905 0 1 1 1.8 0l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 4.995z"/>
                            </svg>
                            Anomalies (${result.log_anomalies.length})
                            <span class="ai-preview-tag warning">Will be sanitized</span>
                        </div>
                        <div class="ai-preview-items">`;
                    result.log_anomalies.forEach((anomaly, i) => {
                        const truncated = anomaly.length > 100 ? anomaly.substring(0, 100) + '...' : anomaly;
                        html += `<div class="ai-preview-item anomaly">
                            <code>${this.escapeHtml(truncated)}</code>
                        </div>`;
                    });
                    html += '</div></div>';
                }
                
                html += '</div>';
                
                // Redactions section
                if (result.redactions && result.redactions.length > 0) {
                    html += '<div class="ai-preview-redactions">';
                    html += '<div class="ai-preview-section-title">PII that will be redacted:</div>';
                    html += '<div class="ai-redaction-list">';
                    
                    result.redactions.forEach(r => {
                        const truncatedValue = r.original_value.length > 40 
                            ? r.original_value.substring(0, 40) + '...' 
                            : r.original_value;
                        html += `
                            <div class="ai-redaction-item">
                                <span class="ai-redaction-type">${r.type_description}</span>
                                <code class="ai-redaction-original">${this.escapeHtml(truncatedValue)}</code>
                                <span class="ai-redaction-arrow">→</span>
                                <code class="ai-redaction-replacement">${r.replacement}</code>
                            </div>
                        `;
                    });
                    
                    html += '</div></div>';
                }
                
                // Full prompt toggle
                html += `
                    <div class="ai-preview-prompt-toggle">
                        <button class="ai-preview-expand-btn" onclick="this.parentElement.nextElementSibling.classList.toggle('expanded'); this.textContent = this.textContent === 'Show Full Prompt' ? 'Hide Prompt' : 'Show Full Prompt';">
                            Show Full Prompt
                        </button>
                    </div>
                    <div class="ai-preview-full-prompt">
                        <pre>${this.escapeHtml(result.sanitized_prompt)}</pre>
                    </div>
                `;
                
                // Safe indicator
                html += '<div class="ai-redaction-note">✓ Your prompt is ready to send. Log data will be sanitized, KB articles preserved.</div>';
                
                previewContent.innerHTML = html;
            } else {
                const error = await response.json();
                previewContent.innerHTML = `<div class="ai-redaction-error">Failed to analyze: ${error.detail || 'Unknown error'}</div>`;
            }
        } catch (error) {
            console.error('Failed to preview prompt:', error);
            previewContent.innerHTML = '<div class="ai-redaction-error">Failed to analyze. Try again.</div>';
        }
    }
    
    hideRedactionPreview() {
        const previewContainer = this.questionContainer.querySelector('.ai-redaction-preview');
        if (previewContainer) {
            previewContainer.style.display = 'none';
        }
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
        // Show/hide magic wand based on AI enabled state and file loaded
        if (this.magicWandBtn) {
            const hasFile = this.currentFileId !== null;
            this.magicWandBtn.classList.toggle('visible', this.isEnabled && hasFile);
        }
        
        // Show/hide AI tab in left panel
        if (this.aiTab) {
            this.aiTab.style.display = this.isEnabled ? '' : 'none';
        }
    }
    
    setFileId(fileId) {
        this.currentFileId = fileId;
        this.updateVisibility();
        this.loadThreads();
    }
    
    toggleQuestionBox() {
        if (this.questionBoxVisible) {
            this.hideQuestionBox();
        } else {
            this.showQuestionBox();
        }
    }
    
    showQuestionBox() {
        this.questionBoxVisible = true;
        this.questionContainer.classList.add('active');
        this.questionInput.focus();
    }
    
    hideQuestionBox() {
        this.questionBoxVisible = false;
        this.questionContainer.classList.remove('active');
        this.questionInput.value = '';
        this.clearSnippet();
        this.hideRedactionPreview();
    }
    
    async submitQuestion(allowAI = false) {
        let question = this.questionInput ? this.questionInput.value.trim() : '';
        
        // If retrying with AI, use the pending question
        if (allowAI && this.pendingAIQuestion) {
            question = this.pendingAIQuestion;
        }
        
        if (!question || this.isLoading || !this.currentFileId) return;
        
        // Include snippet in question if present
        if (this.pendingLogSnippet && !allowAI) {
            question = `${question}\n\nLog snippet:\n\`\`\`\n${this.pendingLogSnippet}\n\`\`\``;
        }
        
        this.isLoading = true;
        this.magicWandBtn.classList.add('loading');
        this.hideQuestionBox();
        
        // Switch to AI tab
        this.switchToAITab();
        
        // Show loading state in panel
        this.renderLoading();
        
        try {
            const response = await fetch('/api/llm/ask', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_id: this.currentFileId,
                    question: question,
                    allow_ai: allowAI
                })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to get response');
            }
            
            const result = await response.json();
            
            // Check if AI confirmation is needed
            if (result.source === 'needs_confirmation') {
                this.pendingAIQuestion = question;
                this.renderAIConfirmation(result.answer, question);
                return;
            }
            
            // Clear pending question
            this.pendingAIQuestion = null;
            
            // Add to threads with source information
            const thread = {
                id: result.thread_id,
                question: question,
                answer: result.answer,
                kb_articles: result.kb_articles || [],
                created_at: new Date().toISOString(),
                thumbs_up: false,
                source: result.source || 'ai',  // "local", "kb", or "ai"
                model_used: result.model_used || 'unknown',
                routing_mode: result.routing_mode || 'AI_REQUIRED',
                prompt_tokens: result.prompt_tokens || 0,
                completion_tokens: result.completion_tokens || 0
            };
            
            this.threads.unshift(thread);
            this.currentThreadIndex = 0;  // Show the newest thread
            this.renderThreads();
            
        } catch (error) {
            console.error('AI question error:', error);
            this.renderError(error.message);
        } finally {
            this.isLoading = false;
            this.magicWandBtn.classList.remove('loading');
        }
    }
    
    renderAIConfirmation(message, question) {
        if (!this.aiPanel) return;
        
        this.aiPanel.innerHTML = `
            <div class="ai-panel-header">
                <h3>
                    <svg viewBox="0 0 512 512" fill="currentColor">
                        <path d="M327.5 85.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 128l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 128l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 64 426.8 7.5C425.1 3 420.8 0 416 0s-9.1 3-10.8 7.5L384 64 327.5 85.2z"/>
                    </svg>
                    AI Assistant
                </h3>
            </div>
            <div class="ai-confirmation-prompt">
                <div class="ai-confirmation-icon">🤖</div>
                <div class="ai-confirmation-question">
                    <strong>Question:</strong> ${this.escapeHtml(question)}
                </div>
                <div class="ai-confirmation-message">
                    ${this.formatAnswer(message)}
                </div>
                <div class="ai-confirmation-note">
                    <strong>Note:</strong> Using AI will send sanitized log data to the configured AI provider.
                </div>
                <div class="ai-confirmation-actions">
                    <button class="ai-confirm-btn cancel" id="aiConfirmCancel">Cancel</button>
                    <button class="ai-confirm-btn proceed" id="aiConfirmProceed">
                        <span>🤖</span> Use AI Model
                    </button>
                </div>
            </div>
        `;
        
        // Bind confirmation buttons
        document.getElementById('aiConfirmCancel')?.addEventListener('click', () => {
            this.pendingAIQuestion = null;
            this.renderThreads();
        });
        
        document.getElementById('aiConfirmProceed')?.addEventListener('click', () => {
            this.submitQuestion(true);  // Retry with AI allowed
        });
    }
    
    async loadThreads() {
        if (!this.currentFileId) {
            this.threads = [];
            this.currentThreadIndex = 0;
            this.renderThreads();
            return;
        }
        
        try {
            const response = await fetch(`/api/llm/threads/${this.currentFileId}`);
            if (response.ok) {
                const data = await response.json();
                this.threads = data.threads || [];
            } else {
                this.threads = [];
            }
        } catch (error) {
            console.error('Failed to load threads:', error);
            this.threads = [];
        }
        
        this.currentThreadIndex = 0;  // Reset to newest thread
        this.renderThreads();
    }
    
    switchToAITab() {
        // Switch left panel to AI tab
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
    
    renderLoading() {
        if (!this.aiPanel) return;
        
        this.aiPanel.innerHTML = `
            <h3>
                <svg viewBox="0 0 512 512" fill="currentColor">
                    <path d="M327.5 85.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 128l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 128l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 64 426.8 7.5C425.1 3 420.8 0 416 0s-9.1 3-10.8 7.5L384 64 327.5 85.2z"/>
                </svg>
                AI Assistant
            </h3>
            <div class="ai-loading">
                <div class="ai-loading-spinner"></div>
                <span class="ai-loading-text">Analyzing with KB knowledge...</span>
            </div>
        `;
    }
    
    renderError(message) {
        if (!this.aiPanel) return;
        
        // Keep header, add error
        const existingThreads = this.aiPanel.querySelector('.ai-threads-container');
        const errorHtml = `
            <div class="ai-error">
                <div class="ai-error-title">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <path d="M15 9l-6 6M9 9l6 6"/>
                    </svg>
                    Error
                </div>
                <p class="ai-error-message">${this.escapeHtml(message)}</p>
            </div>
        `;
        
        if (existingThreads) {
            existingThreads.insertAdjacentHTML('afterbegin', errorHtml);
        } else {
            this.renderThreads();
            const container = this.aiPanel.querySelector('.ai-threads-container');
            if (container) {
                container.insertAdjacentHTML('afterbegin', errorHtml);
            }
        }
    }
    
    renderThreads() {
        if (!this.aiPanel) return;
        
        // Ensure currentThreadIndex is valid
        if (this.currentThreadIndex >= this.threads.length) {
            this.currentThreadIndex = Math.max(0, this.threads.length - 1);
        }
        if (this.currentThreadIndex < 0) {
            this.currentThreadIndex = 0;
        }
        
        const hasThreads = this.threads.length > 0;
        const canGoPrev = this.currentThreadIndex > 0;
        const canGoNext = this.currentThreadIndex < this.threads.length - 1;
        
        let html = `
            <div class="ai-panel-header">
                <h3>
                    <svg viewBox="0 0 512 512" fill="currentColor">
                        <path d="M327.5 85.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 128l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 128l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 64 426.8 7.5C425.1 3 420.8 0 416 0s-9.1 3-10.8 7.5L384 64 327.5 85.2z"/>
                    </svg>
                    AI Assistant
                </h3>
                ${hasThreads ? `
                <div class="ai-thread-navigation">
                    <button class="ai-nav-btn" id="aiNavPrev" ${canGoPrev ? '' : 'disabled'} title="Previous answer">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="15 18 9 12 15 6"/>
                        </svg>
                    </button>
                    <span class="ai-nav-indicator">${this.currentThreadIndex + 1} / ${this.threads.length}</span>
                    <button class="ai-nav-btn" id="aiNavNext" ${canGoNext ? '' : 'disabled'} title="Next answer">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="9 18 15 12 9 6"/>
                        </svg>
                    </button>
                </div>
                ` : ''}
            </div>
        `;
        
        if (!hasThreads) {
            html += `
                <div class="ai-panel-empty">
                    <svg viewBox="0 0 512 512" fill="currentColor">
                        <path d="M327.5 85.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 128l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 128l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 64 426.8 7.5C425.1 3 420.8 0 416 0s-9.1 3-10.8 7.5L384 64 327.5 85.2zM9.3 240C3.6 242.6 0 248.3 0 254.6s3.6 11.9 9.3 14.5L26.3 277l8.1 3.7 .6 .3 88.3 40.8L164.1 410l.3 .6 3.7 8.1 7.9 17.1c2.6 5.7 8.3 9.3 14.5 9.3s11.9-3.6 14.5-9.3l7.9-17.1 3.7-8.1 .3-.6 40.8-88.3L346 281l.6-.3 8.1-3.7 17.1-7.9c5.7-2.6 9.3-8.3 9.3-14.5s-3.6-11.9-9.3-14.5l-17.1-7.9-8.1-3.7-.6-.3-88.3-40.8L217 99.1l-.3-.6L213 90.3l-7.9-17.1c-2.6-5.7-8.3-9.3-14.5-9.3s-11.9 3.6-14.5 9.3l-7.9 17.1-3.7 8.1-.3 .6-40.8 88.3L35.1 228.1l-.6 .3-8.1 3.7L9.3 240z"/>
                    </svg>
                    <p>Click the magic wand button or press <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>A</kbd> to ask a question.</p>
                    <p class="hint">AI will search KB articles and analyze your log context to provide helpful answers.</p>
                </div>
            `;
        } else {
            // Only render the current thread
            const currentThread = this.threads[this.currentThreadIndex];
            html += '<div class="ai-threads-container">';
            html += this.renderThread(currentThread, true);
            html += '</div>';
        }
        
        this.aiPanel.innerHTML = html;
        
        // Bind thread action events
        this.bindThreadEvents();
        
        // Bind navigation events
        this.bindNavigationEvents();
    }
    
    bindNavigationEvents() {
        const prevBtn = document.getElementById('aiNavPrev');
        const nextBtn = document.getElementById('aiNavNext');
        
        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                if (this.currentThreadIndex > 0) {
                    this.currentThreadIndex--;
                    this.renderThreads();
                }
            });
        }
        
        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                if (this.currentThreadIndex < this.threads.length - 1) {
                    this.currentThreadIndex++;
                    this.renderThreads();
                }
            });
        }
    }
    
    renderThread(thread, isCurrent = false) {
        const timeAgo = this.formatTimeAgo(thread.created_at);
        const answerHtml = this.formatAnswer(thread.answer);
        const source = thread.source || 'ai';
        
        // Build source badge based on answer source
        const sourceInfo = this.getSourceInfo(source, thread);
        
        // Filter out KB articles with 0% or very low similarity
        const relevantKbArticles = (thread.kb_articles || []).filter(
            article => (article.similarity || 0) > 0.01
        );
        
        let kbArticlesHtml = '';
        if (relevantKbArticles.length > 0) {
            kbArticlesHtml = `
                <div class="ai-kb-articles">
                    <div class="ai-kb-articles-title">
                        <svg viewBox="0 0 16 16" fill="currentColor">
                            <path d="M1 2.828c.885-.37 2.154-.769 3.388-.893 1.33-.134 2.458.063 3.112.752v9.746c-.935-.53-2.12-.603-3.213-.493-1.18.12-2.37.461-3.287.811V2.828zm7.5-.141c.654-.689 1.782-.886 3.112-.752 1.234.124 2.503.523 3.388.893v9.923c-.918-.35-2.107-.692-3.287-.81-1.094-.111-2.278-.039-3.213.492V2.687zM8 1.783C7.015.936 5.587.81 4.287.94c-1.514.153-3.042.672-3.994 1.105A.5.5 0 000 2.5v11a.5.5 0 00.707.455c.882-.4 2.303-.881 3.68-1.02 1.409-.142 2.59.087 3.223.877a.5.5 0 00.78 0c.633-.79 1.814-1.019 3.222-.877 1.378.139 2.8.62 3.681 1.02A.5.5 0 0016 13.5v-11a.5.5 0 00-.293-.455c-.952-.433-2.48-.952-3.994-1.105C10.413.809 8.985.936 8 1.783z"/>
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
        
        // Add special class for AI-used threads (multicolored border)
        const threadClass = source === 'ai' ? 'ai-thread ai-source-ai' : `ai-thread ai-source-${source}`;
        
        return `
            <div class="${threadClass} ${isCurrent ? 'current' : ''}" data-thread-id="${thread.id}" data-source="${source}">
                <div class="ai-thread-header">
                    <div class="ai-thread-header-top">
                        <p class="ai-thread-question">${this.escapeHtml(thread.question)}</p>
                        <div class="ai-thread-source-badge ${sourceInfo.class}">
                            ${sourceInfo.icon} ${sourceInfo.label}
                            ${sourceInfo.tokens ? `<span class="ai-source-tokens">${sourceInfo.tokens}</span>` : ''}
                        </div>
                    </div>
                    <div class="ai-thread-actions">
                        <button class="ai-thread-action-btn save-to-findings" 
                                data-action="save-to-findings" 
                                title="Save to Findings">
                            <svg viewBox="0 0 16 16" fill="currentColor">
                                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" transform="scale(0.67)"/>
                                <path d="M6 9h4M6 12h4M6 15h2" stroke="currentColor" stroke-width="1" fill="none" transform="scale(0.9) translate(1,1)"/>
                            </svg>
                        </button>
                        <button class="ai-thread-action-btn thumbs-up ${thread.thumbs_up ? 'active' : ''}" 
                                data-action="thumbs-up" 
                                title="Mark as helpful">
                            <svg viewBox="0 0 16 16" fill="currentColor">
                                <path d="M8.864.046C7.908-.193 7.02.53 6.956 1.466c-.072 1.051-.23 2.016-.428 2.59-.125.36-.479 1.013-1.04 1.639-.557.623-1.282 1.178-2.131 1.41C2.685 7.288 2 7.87 2 8.72v4.001c0 .845.682 1.464 1.448 1.545 1.07.114 1.564.415 2.068.723l.048.03c.272.165.578.348.97.484.397.136.861.217 1.466.217h3.5c.937 0 1.599-.477 1.934-1.064a1.86 1.86 0 00.254-.912c0-.152-.023-.312-.077-.464.201-.263.38-.578.488-.901.11-.33.172-.762.004-1.149.069-.13.12-.269.159-.403.077-.27.113-.568.113-.857 0-.288-.036-.585-.113-.856a2.144 2.144 0 00-.138-.362 1.9 1.9 0 00.234-1.734c-.206-.592-.682-1.1-1.2-1.272-.847-.282-1.803-.276-2.516-.211a9.84 9.84 0 00-.443.05 9.365 9.365 0 00-.062-4.509A1.38 1.38 0 008.864.046z"/>
                            </svg>
                        </button>
                        <button class="ai-thread-action-btn thumbs-down" 
                                data-action="thumbs-down" 
                                title="Remove this answer">
                            <svg viewBox="0 0 16 16" fill="currentColor">
                                <path d="M8.864 15.674c-.956.24-1.843-.484-1.908-1.42-.072-1.05-.23-2.015-.428-2.59-.125-.36-.479-1.012-1.04-1.638-.557-.624-1.282-1.179-2.131-1.41C2.685 8.432 2 7.85 2 7V3c0-.845.682-1.464 1.448-1.546 1.07-.113 1.564-.415 2.068-.723l.048-.029c.272-.166.578-.349.97-.484C6.931.08 7.395 0 8 0h3.5c.937 0 1.599.478 1.934 1.064.164.287.254.607.254.913 0 .152-.023.312-.077.464.201.262.38.577.488.9.11.33.172.762.004 1.15.069.13.12.268.159.403.077.27.113.567.113.856 0 .289-.036.586-.113.856-.035.12-.076.237-.138.362.133.358.197.714.197 1.03 0 .292-.059.633-.234.995-.063.132-.13.254-.201.368.131.115.219.328.215.59-.004.312-.074.628-.236.895-.155.258-.393.458-.693.56-.307.105-.634.135-.983.135H8.5c-.123 0-.25-.004-.383-.012a8.89 8.89 0 00-.089 1.986c.002.36-.027.757-.14 1.138A1.38 1.38 0 018.864 15.674z"/>
                            </svg>
                        </button>
                    </div>
                </div>
                <div class="ai-thread-body">
                    <div class="ai-thread-answer">${answerHtml}</div>
                    ${kbArticlesHtml}
                    
                    <!-- Routing Feedback Section -->
                    <div class="ai-routing-feedback" data-thread-id="${thread.id}">
                        <div class="ai-routing-feedback-header">
                            <span class="ai-routing-feedback-title">📊 Rate this routing</span>
                            <span class="ai-routing-feedback-hint">What sources should have been used?</span>
                        </div>
                        <div class="ai-routing-feedback-options">
                            <label class="ai-routing-option">
                                <input type="checkbox" class="ai-routing-checkbox" data-source="local">
                                <span class="ai-routing-option-icon">⚡</span>
                                <span class="ai-routing-option-label">Local Data</span>
                            </label>
                            <label class="ai-routing-option">
                                <input type="checkbox" class="ai-routing-checkbox" data-source="kb">
                                <span class="ai-routing-option-icon">📚</span>
                                <span class="ai-routing-option-label">KB Articles</span>
                            </label>
                            <label class="ai-routing-option">
                                <input type="checkbox" class="ai-routing-checkbox" data-source="ai">
                                <span class="ai-routing-option-icon">🤖</span>
                                <span class="ai-routing-option-label">AI Model</span>
                            </label>
                        </div>
                        <div class="ai-routing-feedback-comment">
                            <input type="text" class="ai-routing-comment-input" placeholder="Why? (optional)">
                        </div>
                        <div class="ai-routing-feedback-actions">
                            <button class="ai-routing-submit-btn" data-thread-id="${thread.id}">Submit Feedback</button>
                        </div>
                    </div>
                    
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
    
    bindThreadEvents() {
        // Save to findings buttons - use event delegation for better reliability
        this.aiPanel.querySelectorAll('.ai-thread-action-btn.save-to-findings').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                e.stopPropagation();
                const threadEl = e.currentTarget.closest('.ai-thread');
                if (threadEl) {
                    const threadId = threadEl.dataset.threadId;
                    console.log('Save to findings clicked, threadId:', threadId);
                    await this.handleSaveToFindings(threadId);
                }
            });
        });
        
        // Thumbs up buttons
        this.aiPanel.querySelectorAll('.ai-thread-action-btn.thumbs-up').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                e.stopPropagation();
                const threadEl = e.currentTarget.closest('.ai-thread');
                if (threadEl) {
                    const threadId = threadEl.dataset.threadId;
                    await this.handleThumbsUp(threadId);
                }
            });
        });
        
        // Thumbs down buttons
        this.aiPanel.querySelectorAll('.ai-thread-action-btn.thumbs-down').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                e.stopPropagation();
                const threadEl = e.currentTarget.closest('.ai-thread');
                if (threadEl) {
                    const threadId = threadEl.dataset.threadId;
                    await this.handleThumbsDown(threadId);
                }
            });
        });
        
        // Routing feedback submit buttons
        this.aiPanel.querySelectorAll('.ai-routing-submit-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                e.stopPropagation();
                const threadId = e.currentTarget.dataset.threadId;
                await this.handleRoutingFeedback(threadId);
            });
        });
    }
    
    async handleRoutingFeedback(threadId) {
        const feedbackEl = this.aiPanel.querySelector(`.ai-routing-feedback[data-thread-id="${threadId}"]`);
        if (!feedbackEl) return;
        
        // Get checkbox values
        const shouldUseLocal = feedbackEl.querySelector('.ai-routing-checkbox[data-source="local"]').checked;
        const shouldUseKb = feedbackEl.querySelector('.ai-routing-checkbox[data-source="kb"]').checked;
        const shouldUseAi = feedbackEl.querySelector('.ai-routing-checkbox[data-source="ai"]').checked;
        const comment = feedbackEl.querySelector('.ai-routing-comment-input').value.trim();
        
        // Validate at least one is selected
        if (!shouldUseLocal && !shouldUseKb && !shouldUseAi) {
            this.showToast('Please select at least one source', 'warning');
            return;
        }
        
        const submitBtn = feedbackEl.querySelector('.ai-routing-submit-btn');
        submitBtn.disabled = true;
        submitBtn.textContent = 'Submitting...';
        
        try {
            const response = await fetch('/api/llm/routing/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    thread_id: parseInt(threadId),
                    should_use_local: shouldUseLocal,
                    should_use_kb: shouldUseKb,
                    should_use_ai: shouldUseAi,
                    comment: comment || null
                })
            });
            
            if (response.ok) {
                // Replace feedback form with thank you message
                feedbackEl.innerHTML = `
                    <div class="ai-routing-feedback-submitted">
                        <span class="ai-routing-feedback-checkmark">✓</span>
                        <span>Feedback submitted! This helps improve routing.</span>
                    </div>
                `;
                this.showToast('Routing feedback submitted!', 'success');
            } else {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to submit feedback');
            }
        } catch (error) {
            console.error('Failed to submit routing feedback:', error);
            this.showToast('Failed to submit feedback', 'error');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Submit Feedback';
        }
    }
    
    async handleSaveToFindings(threadId) {
        try {
            const response = await fetch(`/api/llm/findings/from-thread/${threadId}`, {
                method: 'POST'
            });
            
            if (response.ok) {
                const result = await response.json();
                // Show success feedback on button
                const btn = this.aiPanel.querySelector(`.ai-thread[data-thread-id="${threadId}"] .save-to-findings`);
                if (btn) {
                    btn.classList.add('saved');
                    btn.title = 'Saved to Findings!';
                }
                // Show toast notification
                this.showToast('Saved to Findings!', 'success');
                console.log('Saved to findings:', result);
                
                // Dispatch event to refresh findings list
                document.dispatchEvent(new CustomEvent('findingSaved', { detail: result }));
            } else {
                const error = await response.json();
                this.showToast(`Failed to save: ${error.detail || 'Unknown error'}`, 'error');
            }
        } catch (error) {
            console.error('Failed to save to findings:', error);
            this.showToast('Failed to save to findings', 'error');
        }
    }
    
    showToast(message, type = 'info') {
        // Remove any existing toasts
        document.querySelectorAll('.toast-notification').forEach(t => t.remove());
        
        const toast = document.createElement('div');
        toast.className = `toast-notification ${type}`;
        toast.innerHTML = `
            ${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}
            <span>${message}</span>
        `;
        document.body.appendChild(toast);
        
        // Auto-remove after 3 seconds
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
    
    async handleThumbsUp(threadId) {
        try {
            const response = await fetch(`/api/llm/threads/${threadId}/thumbs-up`, {
                method: 'POST'
            });
            
            if (response.ok) {
                // Update local state
                const thread = this.threads.find(t => t.id == threadId);
                if (thread) {
                    thread.thumbs_up = true;
                }
                this.renderThreads();
            }
        } catch (error) {
            console.error('Failed to save thumbs up:', error);
        }
    }
    
    async handleThumbsDown(threadId) {
        // Confirm deletion using modal
        window.showModal(
            'Delete Q&A',
            `<p>Delete this Q&A?</p>
             <p style="font-size: 0.85em; color: #9ca3af; margin-top: 8px;">It will be removed from history and not saved.</p>`,
            async () => {
                try {
                    const response = await fetch(`/api/llm/threads/${threadId}`, {
                        method: 'DELETE'
                    });
                    
                    if (response.ok) {
                        // Remove from local state
                        this.threads = this.threads.filter(t => t.id != threadId);
                        this.renderThreads();
                    }
                } catch (error) {
                    console.error('Failed to delete thread:', error);
                    window.showModal('Error', `<p style="color: #ef4444;">Failed to delete: ${error.message}</p>`, null);
                }
            },
            { confirmText: 'Delete', danger: true }
        );
    }
    
    formatAnswer(answer) {
        if (!answer) return '';
        
        // Process line by line for better markdown handling
        const lines = answer.split('\n');
        let html = '';
        let inList = false;
        let inCodeBlock = false;
        
        for (let i = 0; i < lines.length; i++) {
            let line = lines[i];
            
            // Code blocks
            if (line.trim().startsWith('```')) {
                if (inCodeBlock) {
                    html += '</code></pre>';
                    inCodeBlock = false;
                } else {
                    if (inList) { html += '</ul>'; inList = false; }
                    html += '<pre class="ai-code-block"><code>';
                    inCodeBlock = true;
                }
                continue;
            }
            
            if (inCodeBlock) {
                html += this.escapeHtml(line) + '\n';
                continue;
            }
            
            // Headers (### Header, ## Header, # Header)
            if (line.match(/^#{1,4}\s/)) {
                if (inList) { html += '</ul>'; inList = false; }
                const level = line.match(/^(#+)/)[1].length;
                const text = line.replace(/^#+\s*/, '');
                html += `<h${level + 2} class="ai-heading">${this.escapeHtml(text)}</h${level + 2}>`;
                continue;
            }
            
            // Numbered lists (1. Item, 2. Item)
            if (line.match(/^\d+\.\s/)) {
                const text = line.replace(/^\d+\.\s*/, '');
                const formatted = this.formatInline(text);
                html += `<div class="ai-list-item numbered">${formatted}</div>`;
                continue;
            }
            
            // Bullet lists (- Item, * Item, • Item)
            if (line.match(/^[-*•]\s/)) {
                if (!inList) { html += '<ul class="ai-list">'; inList = true; }
                const text = line.replace(/^[-*•]\s*/, '');
                html += `<li>${this.formatInline(text)}</li>`;
                continue;
            } else if (inList && line.trim() === '') {
                html += '</ul>';
                inList = false;
            }
            
            // Empty line = paragraph break
            if (line.trim() === '') {
                html += '<br>';
                continue;
            }
            
            // Regular paragraph
            html += `<p>${this.formatInline(line)}</p>`;
        }
        
        if (inList) html += '</ul>';
        if (inCodeBlock) html += '</code></pre>';
        
        return html;
    }
    
    formatInline(text) {
        // Escape HTML first
        let html = this.escapeHtml(text);
        
        // Bold **text**
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        
        // Italic *text*
        html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
        
        // Inline code `code`
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
    
    getSourceInfo(source, thread) {
        // Return source badge info based on answer source
        switch (source) {
            case 'local':
                return {
                    label: 'Local',
                    icon: '⚡',
                    class: 'source-local',
                    tokens: '0 tokens'
                };
            case 'kb':
                return {
                    label: 'KB Fusion',
                    icon: '📚',
                    class: 'source-kb',
                    tokens: '0 tokens'
                };
            case 'ai':
            default:
                const totalTokens = (thread.prompt_tokens || 0) + (thread.completion_tokens || 0);
                return {
                    label: thread.model_used || 'AI',
                    icon: '🤖',
                    class: 'source-ai',
                    tokens: totalTokens > 0 ? `${totalTokens.toLocaleString()} tokens` : null
                };
        }
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // Called when AI config changes
    onConfigChanged(config) {
        this.isEnabled = config.is_configured && config.ai_enabled !== false;
        this.updateVisibility();
    }
}

// Create singleton instance
window.aiAssistant = new AIAssistant();
