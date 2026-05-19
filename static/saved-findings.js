/**
 * Saved Findings Manager
 * 
 * Manages the display of saved findings in the Findings tab:
 * - Load and display findings from the API
 * - Drag-and-drop reordering
 * - Delete findings with centered modal confirmation
 * - Export findings as Markdown or AI-compiled email (export options modal)
 * - Source-aware formatting
 * - Optional rich HTML (log summary sections, bulk table rows) stored in metadata
 */

/**
 * Strip unsafe tags/attributes from HTML stored with findings before innerHTML display.
 */
function sanitizeFindingHtml(html) {
    if (!html || typeof html !== 'string') return '';
    try {
        const doc = new DOMParser().parseFromString(`<div id="__sf_root">${html}</div>`, 'text/html');
        const root = doc.getElementById('__sf_root');
        if (!root) return '';
        const walk = (node) => {
            if (!node) return;
            if (node.nodeType === 1) {
                const tag = node.tagName.toLowerCase();
                if (['script', 'iframe', 'object', 'embed', 'form', 'style'].includes(tag)) {
                    node.remove();
                    return;
                }
                [...node.attributes].forEach(attr => {
                    const n = attr.name.toLowerCase();
                    if (n.startsWith('on') || n === 'srcdoc') node.removeAttribute(attr.name);
                    if (n === 'href' && /^\s*javascript:/i.test(attr.value)) node.removeAttribute(attr.name);
                });
            }
            [...node.childNodes].forEach(walk);
        };
        walk(root);
        return root.innerHTML;
    } catch {
        return '';
    }
}

class SavedFindingsManager {
    constructor() {
        this.findings = [];
        this.currentFileId = null;
        this._loadedFileId = null;
        this.isLoading = false;
        this._orderKey = null;     // localStorage key for custom order
        this._dragSrcEl = null;
        /** Pending compiled email (after async LLM); opened from toast or Findings banner */
        this._compiledEmailPending = null;
        /** Per log file: last successful compiled email (survives switching files and closing preview) */
        this._compiledEmailsByFileId = {};
        /** fileId for in-flight compile (detect stale completion after file switch) */
        this._compileEmailFileId = null;
        this._compileEmailTimer = null;
        this._compileEmailAbort = null;

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
        this.bindEvents();
        
        document.addEventListener('fileLoaded', (e) => {
            const newFileId = e.detail?.fileId ?? null;
            const prevFileId = this.currentFileId;
            if (prevFileId != null && newFileId !== prevFileId) {
                this._clearCompiledEmailTransientState();
            }
            this.currentFileId = newFileId;
            this._orderKey = `findings_order_${this.currentFileId}`;
            this._syncCompiledEmailUiForCurrentFile();
            this.loadFindings();
        });

        document.addEventListener('fileClosed', () => {
            this.currentFileId = null;
            this._loadedFileId = null;
            this._orderKey = null;
            this.findings = [];
            this._clearCompiledEmailTransientState();
            this._updateReopenCompiledEmailButton();
            const container = document.getElementById('findingsList');
            if (container) {
                container.innerHTML = '<p class="placeholder-text">Open a log file to view and save findings.</p>';
            }
            this.updateBadge();
        });
        
        document.addEventListener('findingSaved', () => {
            this.loadFindings();
        });
    }
    
    bindEvents() {
        const exportBtn = document.getElementById('exportFindings');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => this.exportFindings());
        }

        const openCompiled = document.getElementById('compiledEmailOpenBtn');
        if (openCompiled) {
            openCompiled.addEventListener('click', () => this._openCompiledEmailPreviewFromPending());
        }
        const dismissBanner = document.getElementById('compiledEmailBannerDismiss');
        if (dismissBanner) {
            dismissBanner.addEventListener('click', () => this._dismissCompiledEmailBanner());
        }

        const reopenCompiled = document.getElementById('reopenCompiledEmailBtn');
        if (reopenCompiled) {
            reopenCompiled.addEventListener('click', () => this._openCompiledEmailPreviewFromPending());
        }

        const clearBtn = document.getElementById('clearFindings');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => this.clearAllFindings());
        }
        
        document.addEventListener('click', (e) => {
            const mainTab = e.target.closest('.tab-btn');
            if (mainTab && mainTab.dataset.tab === 'findings-tab') {
                this.loadFindings();
            }
        });
    }
    
    // ── Data ────────────────────────────────────────────────
    
    async loadFindings() {
        if (!this.currentFileId || this.isLoading) return;
        
        this.isLoading = true;
        const container = document.getElementById('findingsList');
        const hasExistingForFile = this.findings.length > 0
            && this._loadedFileId === this.currentFileId;
        
        if (container && !hasExistingForFile) {
            container.innerHTML = '<p class="placeholder-text">Loading findings...</p>';
        }
        
        try {
            const response = await fetch(`/api/llm/findings/${this.currentFileId}`);
            if (!response.ok) throw new Error('Failed to load findings');
            
            const data = await response.json();
            this.findings = data.findings || [];
            this._loadedFileId = this.currentFileId;
            this._orderKey = `findings_order_${this.currentFileId}`;
            
            this.renderFindings(container);
            this.updateBadge();
            
        } catch (error) {
            console.error('Failed to load findings:', error);
            if (container && !hasExistingForFile) {
                container.innerHTML = `<p class="placeholder-text">No findings yet. Use the AI assistant save button or right-click log lines.</p>`;
            }
        } finally {
            this.isLoading = false;
            this._updateReopenCompiledEmailButton();
        }
    }
    
    _getVisibleFindings() {
        return (this.findings || []).filter(f => !(f.metadata && f.metadata.auto_saved));
    }
    
    _getOrderedFindings() {
        const visible = this._getVisibleFindings();
        const saved = this._loadOrder();
        
        // Default: sort by created_at ascending (oldest first, new items at end)
        const byDate = [...visible].sort(
            (a, b) => new Date(a.created_at) - new Date(b.created_at)
        );
        
        if (!saved || saved.length === 0) return byDate;
        
        // Apply saved drag order, then append any new items at the end (by date)
        const map = {};
        byDate.forEach(f => { map[f.id] = f; });
        
        const ordered = [];
        saved.forEach(id => { if (map[id]) { ordered.push(map[id]); delete map[id]; } });
        // New items not in saved order — append at end sorted by date
        Object.values(map).forEach(f => ordered.push(f));
        return ordered;
    }
    
    _loadOrder() {
        if (!this._orderKey) return null;
        try { return JSON.parse(localStorage.getItem(this._orderKey)); } catch { return null; }
    }
    
    _saveOrder(ids) {
        if (!this._orderKey) return;
        localStorage.setItem(this._orderKey, JSON.stringify(ids));
    }
    
    // ── Rendering ──────────────────────────────────────────
    
    renderFindings(container) {
        if (!container) return;
        
        const ordered = this._getOrderedFindings();
        
        if (ordered.length === 0) {
            container.innerHTML = `
                <p class="placeholder-text">
                    No findings yet. 
                    <br><br>
                    • Use the save button in AI Assistant answers
                    <br>
                    • Right-click on log lines to add them
                    <br>
                    • Right-click on report rows/sections to add them
                </p>
            `;
            return;
        }
        
        let html = '';
        
        ordered.forEach(finding => {
            const dateStr = new Date(finding.created_at).toLocaleString();
            const typeIcon = this.getTypeIcon(finding);
            const typeLabel = this.getTypeLabel(finding);
            const sourceTag = this._renderSourceTag(finding);
            const borderColor = this._getBorderColor(finding);
            
            html += `
                <div class="finding-item" data-finding-id="${finding.id}" draggable="true"
                     style="border-left-color:${borderColor}">
                    <div class="finding-drag-handle" title="Drag to reorder">⠿</div>
                    <div class="finding-body">
                        <div class="finding-header">
                            <span class="finding-type ${finding.finding_type}">
                                ${typeIcon} ${typeLabel}
                            </span>
                            ${sourceTag}
                            <span class="finding-date">${dateStr}</span>
                            <button class="finding-delete-btn" data-finding-id="${finding.id}" title="Delete finding">
                                ×
                            </button>
                        </div>
                        ${finding.title ? `<div class="finding-title">${this.escapeHtml(finding.title)}</div>` : ''}
                        ${this._renderFindingBody(finding)}
                        ${this._renderMeta(finding)}
                    </div>
                </div>
            `;
        });
        
        container.innerHTML = html;
        
        // Bind delete buttons
        container.querySelectorAll('.finding-delete-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const findingId = btn.dataset.findingId;
                this._showConfirmModal('Delete this finding?', async () => {
                    await this.deleteFinding(findingId);
                });
            });
        });
        
        // Bind drag-and-drop
        this._initDragAndDrop(container);
    }
    
    // ── Source tags & indicators ─────────────────────────────
    
    _renderSourceTag(finding) {
        const meta = finding.metadata || {};
        const src = meta.source;
        if (!src) return '';
        
        const labels = {
            'context_menu': 'Log View',
            'log_summary_section': 'Log Summary',
            'log_summary_detail': 'Log Summary',
            'issues_view': 'Issues',
            'release_notes': 'Release Notes',
            'performance_cockpit': 'Performance',
            'latency_profile': 'Latency Profile',
            'analysis_report': 'Analysis',
            'analysis_insight': 'Analysis',
            'log_stats': 'Log Stats',
            'bulk_map': 'Bulk Map',
            'bulkMapMainView': 'Bulk Map',
            'bulkActivityMainView': 'Bulk Activity',
            'fileOperationsMainView': 'File Operations',
            'performanceCockpitMainView': 'Performance',
            'logSummaryMainView': 'Log Summary',
        };
        const label = labels[src] || src.replace(/_/g, ' ').replace(/MainView$/, '');
        return `<span class="finding-source-tag">${this.escapeHtml(label)}</span>`;
    }
    
    _getBorderColor(finding) {
        const meta = finding.metadata || {};
        const src = meta.source || '';
        if (src.includes('log_summary') || finding.finding_type === 'custom') return '#8b5cf6';
        if (src.includes('issues') || meta.severity === 'error') return '#ef4444';
        if (src.includes('performance') || src.includes('latency')) return '#3b82f6';
        if (src.includes('release_notes')) return '#10b981';
        if (src.includes('bulk') || src.includes('Bulk')) return '#f59e0b';
        if (finding.finding_type === 'log_line') return '#6b7280';
        if (finding.finding_type === 'qa_thread') return '#ec4899';
        return '#3b82f6';
    }
    
    _getContentClass(finding) {
        const meta = finding.metadata || {};
        const src = meta.source || '';
        if (src.includes('log_summary')) return 'finding-content-summary';
        if (src.includes('performance') || src.includes('latency')) return 'finding-content-perf';
        if (src.includes('bulk') || src.includes('Bulk')) return 'finding-content-bulk';
        if (src === 'context_menu' || finding.finding_type === 'log_line') return 'finding-content-logline';
        return '';
    }
    
    _renderFindingBody(finding) {
        const meta = finding.metadata || {};
        if (meta.content_format === 'html' && meta.content_html) {
            const safe = sanitizeFindingHtml(meta.content_html);
            if (safe) {
                const bulk = meta.source && (meta.source.includes('bulk') || meta.source.includes('Bulk'));
                const htmlMod = bulk ? ' finding-content-html-bulk' : ' finding-content-html-rich';
                return `<div class="finding-content ${this._getContentClass(finding)} finding-content-html${htmlMod}">${safe}</div>`;
            }
        }
        return `<div class="finding-content ${this._getContentClass(finding)}">${this.formatContent(finding.content, finding)}</div>`;
    }
    
    _renderMeta(finding) {
        const parts = [];
        if (finding.line_number) parts.push(`Line ${finding.line_number}`);
        const meta = finding.metadata || {};
        if (meta.severity) parts.push(meta.severity.toUpperCase());
        if (meta.component) parts.push(meta.component);
        if (parts.length === 0) return '';
        return `<div class="finding-meta">${parts.map(p => `<span>${this.escapeHtml(p)}</span>`).join('<span class="finding-meta-sep">·</span>')}</div>`;
    }
    
    // ── Type icons & labels ─────────────────────────────────
    
    getTypeIcon(finding) {
        const meta = finding.metadata || {};
        const src = meta.source || '';
        if (src.includes('log_summary')) return '<svg width="12" height="12" viewBox="0 0 512 512" fill="currentColor"><path d="M327.5 85.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 128l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 128l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 64 426.8 7.5C425.1 3 420.8 0 416 0s-9.1 3-10.8 7.5L384 64 327.5 85.2z"/></svg>';
        if (src.includes('performance') || src.includes('latency')) return '<svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0a8 8 0 100 16A8 8 0 008 0zM7 3.5a.5.5 0 011 0v4.793l2.354 2.353a.5.5 0 01-.708.708l-2.5-2.5A.5.5 0 017 8.5v-5z"/></svg>';
        if (src.includes('issues')) return '<svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor"><path d="M8.982 1.566a1.13 1.13 0 00-1.96 0L.305 13.75a1.123 1.123 0 00.98 1.69h13.43c.886 0 1.457-.917.98-1.69L8.982 1.566z"/></svg>';
        switch (finding.finding_type) {
            case 'qa_thread': return '💬';
            case 'log_line': return '📋';
            case 'custom': return '📝';
            default: return '📌';
        }
    }
    
    getTypeLabel(finding) {
        if (typeof finding === 'string') {
            switch (finding) {
                case 'qa_thread': return 'Q&A';
                case 'log_line': return 'Log Line';
                case 'custom': return 'Note';
                default: return 'Finding';
            }
        }
        const meta = finding.metadata || {};
        const src = meta.source || '';
        if (src.includes('log_summary')) return 'Summary';
        if (src.includes('performance') || src.includes('latency')) return 'Performance';
        if (src.includes('issues')) return 'Issue';
        if (src.includes('release_notes')) return 'Release Note';
        if (src.includes('bulk') || src.includes('Bulk')) return 'Bulk Report';
        if (src.includes('fileOps') || src.includes('FileOp')) return 'File Ops';
        switch (finding.finding_type) {
            case 'qa_thread': return 'Q&A';
            case 'log_line': return 'Log Line';
            case 'custom': return 'Note';
            default: return 'Finding';
        }
    }
    
    // ── Content formatting ──────────────────────────────────
    
    formatContent(content, finding) {
        if (!content) return '';
        
        let formatted = this.escapeHtml(content);
        
        // Bold text
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Code blocks
        formatted = formatted.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
        
        // Inline code
        formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');
        
        // URLs
        formatted = formatted.replace(
            /(https?:\/\/[^\s<>"']+)/g, 
            '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
        );
        
        // Markdown links
        formatted = formatted.replace(
            /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
            '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
        );
        
        // Line breaks
        formatted = formatted.replace(/\n/g, '<br>');
        
        return formatted;
    }
    
    // ── Badge ───────────────────────────────────────────────
    
    updateBadge() {
        const badge = document.getElementById('findingsCountBadge');
        const visibleCount = this._getVisibleFindings().length;
        if (badge) {
            badge.textContent = visibleCount > 0 ? visibleCount : '';
        }
    }
    
    // ── Delete ──────────────────────────────────────────────
    
    async deleteFinding(findingId) {
        try {
            const response = await fetch(`/api/llm/findings/${findingId}`, {
                method: 'DELETE'
            });
            
            if (!response.ok) throw new Error('Failed to delete');
            this.loadFindings();
            
        } catch (error) {
            console.error('Failed to delete finding:', error);
            if (window.showToast) window.showToast('Failed to delete finding', 'error');
        }
    }
    
    async clearAllFindings() {
        this._showConfirmModal('Delete all findings for this file?', async () => {
            try {
                for (const finding of this.findings) {
                    await fetch(`/api/llm/findings/${finding.id}`, {
                        method: 'DELETE'
                    });
                }
                
                this.findings = [];
                if (this._orderKey) localStorage.removeItem(this._orderKey);
                this.renderFindings(document.getElementById('findingsList'));
                this.updateBadge();
                
            } catch (error) {
                console.error('Failed to clear findings:', error);
            }
        });
    }
    
    // ── Centered confirm modal ──────────────────────────────
    
    _showConfirmModal(message, onConfirm) {
        const existing = document.getElementById('findingsConfirmOverlay');
        if (existing) existing.remove();
        
        const overlay = document.createElement('div');
        overlay.id = 'findingsConfirmOverlay';
        overlay.className = 'findings-confirm-overlay';
        overlay.innerHTML = `
            <div class="findings-confirm-dialog">
                <p>${this.escapeHtml(message)}</p>
                <div class="findings-confirm-actions">
                    <button class="findings-confirm-cancel">Cancel</button>
                    <button class="findings-confirm-ok">Confirm</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        
        overlay.querySelector('.findings-confirm-cancel').addEventListener('click', () => overlay.remove());
        overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
        overlay.querySelector('.findings-confirm-ok').addEventListener('click', () => {
            overlay.remove();
            onConfirm();
        });
    }
    
    // ── Compiled email (async LLM): toast progress + Findings banner ──

    _getCompiledEmailForFile(fileId) {
        if (fileId == null) return null;
        if (this._compiledEmailPending?.fileId === fileId) {
            return this._compiledEmailPending;
        }
        return this._compiledEmailsByFileId[fileId] || null;
    }

    _getCompiledEmailForCurrentFile() {
        return this._getCompiledEmailForFile(this.currentFileId);
    }

    _storeCompiledEmail(fileId, bundle) {
        if (fileId == null || !bundle) return;
        const entry = { ...bundle, fileId };
        this._compiledEmailsByFileId[fileId] = entry;
        if (this.currentFileId === fileId) {
            this._compiledEmailPending = entry;
            this._updateReopenCompiledEmailButton();
        }
    }

    _clearCompiledEmailTransientState() {
        const fileId = this._compileEmailFileId;
        this._compiledEmailPending = null;
        this._dismissCompiledEmailBanner();
        if (fileId != null) {
            this.cancelCompileEmail(fileId, { silent: true });
            return;
        }
        if (this._compileEmailAbort) {
            try { this._compileEmailAbort.abort(); } catch (_) { /* ignore */ }
        }
        this._compileEmailAbort = null;
        this._removeCompileEmailToast();
    }

    cancelCompileEmail(fileId, { silent = false } = {}) {
        if (fileId == null) return;
        fetch(`/api/llm/findings/${fileId}/export/cancel`, { method: 'POST' }).catch(() => {});
        const activeForFile = this._compileEmailFileId === fileId;
        if (!activeForFile) return;
        if (this._compileEmailAbort) {
            try { this._compileEmailAbort.abort(); } catch (_) { /* ignore */ }
        }
        this._compileEmailAbort = null;
        this._compileEmailFileId = null;
        this._removeCompileEmailToast();
        this._dismissCompiledEmailBanner();
        if (!silent && window.showToast) window.showToast('Compile email cancelled', 'info');
    }

    _syncCompiledEmailUiForCurrentFile() {
        const bundle = this._getCompiledEmailForCurrentFile();
        if (this._compiledEmailPending?.fileId !== this.currentFileId) {
            this._compiledEmailPending = bundle;
        }
        const banner = document.getElementById('compiledEmailReadyBanner');
        if (banner) {
            banner.style.display = bundle ? 'flex' : 'none';
        }
        this._updateReopenCompiledEmailButton();
    }

    _updateReopenCompiledEmailButton() {
        const btn = document.getElementById('reopenCompiledEmailBtn');
        if (!btn) return;
        const show = Boolean(this._getCompiledEmailForCurrentFile());
        btn.style.display = show ? '' : 'none';
        btn.disabled = !show;
    }

    _dismissCompiledEmailBanner() {
        const b = document.getElementById('compiledEmailReadyBanner');
        if (b) b.style.display = 'none';
    }

    _showCompiledEmailBanner() {
        const b = document.getElementById('compiledEmailReadyBanner');
        if (b) b.style.display = 'flex';
    }

    _goToFindingsTab() {
        const btn = document.querySelector('.tab-btn[data-tab="findings-tab"]');
        if (btn) btn.click();
    }

    _openCompiledEmailPreviewFromPending() {
        const bundle = this._getCompiledEmailForCurrentFile();
        if (!bundle) {
            if (window.showToast) window.showToast('No compiled email to show for this log file.', 'error');
            return;
        }
        const { filename, content, previewOpts } = bundle;
        this._goToFindingsTab();
        this._showExportPreview(filename, content, previewOpts);
        if (this._compiledEmailPending?.fileId === this.currentFileId) {
            this._compiledEmailPending = null;
        }
        this._dismissCompiledEmailBanner();
        this._removeCompileEmailToast();
    }

    _removeCompileEmailToast() {
        const t = document.getElementById('compileEmailToast');
        if (t) {
            t.classList.remove('visible');
            setTimeout(() => { if (t.parentNode) t.remove(); }, 300);
        }
        if (this._compileEmailTimer) {
            clearInterval(this._compileEmailTimer);
            this._compileEmailTimer = null;
        }
    }

    async _fetchProviderLabel() {
        let hint = 'the configured model';
        try {
            const cr = await fetch('/api/llm/config');
            if (cr.ok) {
                const c = await cr.json();
                const p = String(c.provider || '').toLowerCase();
                if (p === 'lmstudio') hint = 'local model (LM Studio)';
                else if (p === 'gemini') hint = 'Google Gemini';
                else if (p === 'openrouter') hint = 'OpenRouter';
            }
        } catch (_) { /* ignore */ }
        return hint;
    }

    _ensureCompileEmailToast() {
        let toast = document.getElementById('compileEmailToast');
        if (toast) return toast;
        toast = document.createElement('div');
        toast.id = 'compileEmailToast';
        toast.className = 'app-toast app-toast-warning compile-email-toast';
        toast.setAttribute('role', 'status');
        toast.innerHTML = `
            <div class="compile-email-toast-spinner" aria-hidden="true"></div>
            <div class="compile-email-toast-body">
                <div class="compile-email-toast-title">Compiling email…</div>
                <div class="compile-email-toast-meta"></div>
                <div class="compile-email-toast-status"></div>
            </div>
            <button type="button" class="compile-email-toast-dismiss" title="Cancel">×</button>
        `;
        document.body.appendChild(toast);
        requestAnimationFrame(() => toast.classList.add('visible'));
        return toast;
    }

    _bindCompileToastDismissRunning(toast) {
        const dismiss = toast.querySelector('.compile-email-toast-dismiss');
        if (!dismiss) return;
        dismiss.style.display = 'block';
        dismiss.onclick = (e) => {
            e.stopPropagation();
            const fileId = this._compileEmailFileId ?? this.currentFileId;
            this.cancelCompileEmail(fileId);
        };
    }

    _setCompileToastRunning(elapsedSec, providerHint) {
        const toast = this._ensureCompileEmailToast();
        toast.classList.remove('compile-email-toast--clickable', 'app-toast-success', 'app-toast-error', 'app-toast-info');
        toast.classList.add('app-toast-warning');
        toast.onclick = null;
        const spinner = toast.querySelector('.compile-email-toast-spinner');
        if (spinner) spinner.style.display = 'block';
        toast.querySelector('.compile-email-toast-title').textContent = 'Compiling email…';
        toast.querySelector('.compile-email-toast-meta').textContent =
            `${elapsedSec}s elapsed · ${providerHint}`;
        toast.querySelector('.compile-email-toast-status').textContent =
            'Generating message with the model. You can keep working — open the preview from here or the Findings tab when finished.';
        this._bindCompileToastDismissRunning(toast);
    }

    _setCompileToastSuccess(metaLine) {
        const toast = document.getElementById('compileEmailToast');
        if (!toast) return;
        toast.classList.remove('app-toast-warning', 'app-toast-error');
        toast.classList.add('app-toast-success', 'compile-email-toast--clickable');
        const spinner = toast.querySelector('.compile-email-toast-spinner');
        if (spinner) spinner.style.display = 'none';
        toast.querySelector('.compile-email-toast-title').textContent = 'Compiled email ready';
        toast.querySelector('.compile-email-toast-meta').textContent = metaLine || '';
        toast.querySelector('.compile-email-toast-status').textContent =
            'Click this notification to open the preview (Findings tab).';
        const dismiss = toast.querySelector('.compile-email-toast-dismiss');
        dismiss.style.display = 'block';
        dismiss.onclick = (e) => {
            e.stopPropagation();
            this._removeCompileEmailToast();
        };
        toast.onclick = () => this._openCompiledEmailPreviewFromPending();
    }

    _setCompileToastError(message) {
        let toast = document.getElementById('compileEmailToast');
        if (!toast) toast = this._ensureCompileEmailToast();
        toast.classList.remove('app-toast-warning', 'app-toast-success', 'compile-email-toast--clickable');
        toast.classList.add('app-toast-error');
        toast.onclick = null;
        const spinner = toast.querySelector('.compile-email-toast-spinner');
        if (spinner) spinner.style.display = 'none';
        toast.querySelector('.compile-email-toast-title').textContent = 'Compile failed';
        toast.querySelector('.compile-email-toast-meta').textContent = '';
        toast.querySelector('.compile-email-toast-status').textContent = message || 'Unknown error';
        const dismiss = toast.querySelector('.compile-email-toast-dismiss');
        dismiss.style.display = 'block';
        dismiss.onclick = (e) => {
            e.stopPropagation();
            this._removeCompileEmailToast();
        };
        setTimeout(() => {
            const t = document.getElementById('compileEmailToast');
            if (t && t.classList.contains('app-toast-error')) this._removeCompileEmailToast();
        }, 8000);
    }

    async _runCompiledEmailExport(payload) {
        if (!this.currentFileId) return;

        if (this._compileEmailAbort) {
            try { this._compileEmailAbort.abort(); } catch (_) { /* ignore */ }
        }
        const ac = new AbortController();
        this._compileEmailAbort = ac;
        const compileForFileId = this.currentFileId;
        this._compileEmailFileId = compileForFileId;

        const providerHint = await this._fetchProviderLabel();
        this._removeCompileEmailToast();
        this._setCompileToastRunning(0, providerHint);

        const start = Date.now();
        this._compileEmailTimer = setInterval(() => {
            const sec = Math.floor((Date.now() - start) / 1000);
            this._setCompileToastRunning(sec, providerHint);
        }, 1000);

        try {
            const resp = await fetch(`/api/llm/findings/${this.currentFileId}/export`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                signal: ac.signal
            });
            const errText = await resp.text();
            let data;
            try {
                data = JSON.parse(errText);
            } catch {
                throw new Error(errText || 'Export failed');
            }
            if (!resp.ok) {
                if (resp.status === 499) {
                    return;
                }
                const detail = data.detail;
                const msg = typeof detail === 'string' ? detail : (Array.isArray(detail) ? detail.map(d => d.msg || d).join(' ') : (data.message || errText));
                throw new Error(msg || 'Export failed');
            }

            if (data.format !== 'compiled_email') {
                throw new Error('Unexpected response from server');
            }

            const previewOpts = {
                format: 'compiled_email',
                rawMarkdown: data.raw_markdown || '',
                modelUsed: data.model_used,
                audience: payload.audience
            };
            const bundle = {
                filename: data.filename,
                content: data.content,
                previewOpts
            };
            this._storeCompiledEmail(compileForFileId, bundle);

            if (this._compileEmailTimer) {
                clearInterval(this._compileEmailTimer);
                this._compileEmailTimer = null;
            }
            this._compileEmailAbort = null;
            this._compileEmailFileId = null;

            if (this.currentFileId !== compileForFileId) {
                this._removeCompileEmailToast();
                return;
            }

            const elapsed = Math.floor((Date.now() - start) / 1000);
            const modelBit = data.model_used ? String(data.model_used) : providerHint;
            this._setCompileToastSuccess(`Done in ${elapsed}s · ${modelBit}`);
            this._showCompiledEmailBanner();
        } catch (e) {
            if (this._compileEmailTimer) {
                clearInterval(this._compileEmailTimer);
                this._compileEmailTimer = null;
            }
            this._compileEmailAbort = null;
            this._compileEmailFileId = null;
            if (e.name === 'AbortError') {
                return;
            }
            console.error('Compile email failed:', e);
            this._setCompileToastError(e.message || 'Export failed');
        }
    }

    // ── Export ───────────────────────────────────────────────
    
    exportFindings() {
        const ordered = this._getOrderedFindings();
        if (ordered.length === 0) {
            if (window.showToast) window.showToast('No findings to export', 'error');
            return;
        }
        if (!this.currentFileId) return;
        this._showExportOptionsModal();
    }
    
    _showExportOptionsModal() {
        const existing = document.getElementById('exportOptionsOverlay');
        if (existing) existing.remove();
        
        const overlay = document.createElement('div');
        overlay.id = 'exportOptionsOverlay';
        overlay.className = 'export-options-overlay';
        overlay.innerHTML = `
            <div class="export-options-dialog">
                <h3 class="export-options-title">Export findings</h3>
                <p class="export-options-hint">Choose how to share your findings. Audience and notes are used when compiling an email-style summary. <strong>Compile email</strong> runs in the background with a live timer — you can switch tabs; when it finishes, open the preview from the notification or the banner on Findings.</p>
                <label class="export-options-label" for="exportAudience">Audience</label>
                <select id="exportAudience" class="export-options-select">
                    <option value="technical">Technical — detail, codes, line refs</option>
                    <option value="business">Business — impact, risk, actions</option>
                    <option value="mixed">Mixed — summary + technical detail</option>
                    <option value="executive">Executive — brief bullets, decisions</option>
                </select>
                <label class="export-options-label" for="exportObservations">Additional observations <span class="export-options-optional">(optional)</span></label>
                <textarea id="exportObservations" class="export-options-textarea" rows="4" placeholder="Context for recipients, caveats, next steps…"></textarea>
                <div class="export-options-actions">
                    <button type="button" class="export-options-cancel">Cancel</button>
                    <button type="button" class="export-options-md">Export Markdown</button>
                    <button type="button" class="export-options-email">Compile email…</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        
        const close = () => overlay.remove();
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
        overlay.querySelector('.export-options-cancel').addEventListener('click', close);
        
        const getPayload = () => ({
            finding_ids: this._getOrderedFindings().map(f => f.id),
            audience: overlay.querySelector('#exportAudience').value,
            additional_observations: overlay.querySelector('#exportObservations').value.trim()
        });
        
        overlay.querySelector('.export-options-md').addEventListener('click', async () => {
            const payload = { ...getPayload(), compile: false };
            close();
            await this._runExport(payload);
        });
        
        overlay.querySelector('.export-options-email').addEventListener('click', async () => {
            const payload = { ...getPayload(), compile: true };
            close();
            await this._runExport(payload);
        });
    }
    
    async _runExport(payload) {
        if (!this.currentFileId) return;

        if (payload.compile) {
            await this._runCompiledEmailExport(payload);
            return;
        }

        const loadingId = 'exportLoadingOverlay';
        let loading = document.getElementById(loadingId);
        if (!loading) {
            loading = document.createElement('div');
            loading.id = loadingId;
            loading.className = 'export-loading-overlay';
            loading.innerHTML = '<div class="export-loading-box">Exporting…</div>';
            document.body.appendChild(loading);
        }
        loading.style.display = 'none';

        try {
            const resp = await fetch(`/api/llm/findings/${this.currentFileId}/export`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const errText = await resp.text();
            let data;
            try {
                data = JSON.parse(errText);
            } catch {
                throw new Error(errText || 'Export failed');
            }
            if (!resp.ok) {
                const detail = data.detail;
                const msg = typeof detail === 'string' ? detail : (Array.isArray(detail) ? detail.map(d => d.msg || d).join(' ') : (data.message || errText));
                throw new Error(msg || 'Export failed');
            }

            this._showExportPreview(data.filename, data.content, { format: 'markdown' });
        } catch (e) {
            console.error('Export failed:', e);
            if (window.showToast) window.showToast(e.message || 'Export failed', 'error');
        }
    }
    
    _showExportPreview(filename, primaryText, options = {}) {
        const existing = document.getElementById('exportPreviewOverlay');
        if (existing) existing.remove();
        
        const format = options.format || 'markdown';
        const rawMd = options.rawMarkdown != null ? options.rawMarkdown : primaryText;
        const isEmail = format === 'compiled_email';
        
        const overlay = document.createElement('div');
        overlay.id = 'exportPreviewOverlay';
        overlay.className = 'export-preview-overlay';
        
        const title = isEmail ? 'Compiled email' : 'Export preview';
        const sub = isEmail && options.modelUsed
            ? `${this.escapeHtml(filename)} · ${this.escapeHtml(options.modelUsed)}`
            : this.escapeHtml(filename);
        
        const renderedPrimary = isEmail
            ? `<div class="export-email-body">${this._renderMarkdownPlain(primaryText)}</div>`
            : this._renderMarkdown(primaryText);
        
        const tabsHtml = isEmail
            ? `<button class="export-preview-tab active" data-view="primary">Email body</button>
               <button class="export-preview-tab" data-view="raw">Source (Markdown)</button>`
            : `<button class="export-preview-tab active" data-view="primary">Preview</button>
               <button class="export-preview-tab" data-view="raw">Markdown</button>`;
        
        const audienceRow = isEmail && options.audience
            ? `<div class="export-preview-sentiment">Requested audience: <span>${this.escapeHtml(this._audienceLabel(options.audience))}</span></div>`
            : '';
        
        overlay.innerHTML = `
            <div class="export-preview-dialog">
                <div class="export-preview-header">
                    <h3>${this.escapeHtml(title)}</h3>
                    <span class="export-preview-filename">${sub}</span>
                    <button class="export-preview-close" title="Close">×</button>
                </div>
                ${audienceRow}
                <div class="export-preview-tabs">
                    ${tabsHtml}
                </div>
                <div class="export-preview-body">
                    <div class="export-preview-rendered active" data-view="primary">${renderedPrimary}</div>
                    <div class="export-preview-raw" data-view="raw"><pre>${this.escapeHtml(rawMd)}</pre></div>
                </div>
                <div class="export-preview-actions">
                    <button class="export-action-btn export-copy-btn">Copy to Clipboard</button>
                    <button class="export-action-btn export-save-btn">Save File</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        
        const getActiveText = () => {
            const rawEl = overlay.querySelector('.export-preview-raw');
            const rawActive = rawEl && rawEl.classList.contains('active');
            return rawActive ? rawMd : primaryText;
        };
        
        overlay.querySelector('.export-preview-close').addEventListener('click', () => overlay.remove());
        overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
        
        overlay.querySelectorAll('.export-preview-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                overlay.querySelectorAll('.export-preview-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const view = tab.dataset.view;
                overlay.querySelector('.export-preview-rendered').classList.toggle('active', view === 'primary');
                overlay.querySelector('.export-preview-raw').classList.toggle('active', view === 'raw');
            });
        });
        
        overlay.querySelector('.export-copy-btn').addEventListener('click', async () => {
            const text = getActiveText();
            try {
                await navigator.clipboard.writeText(text);
                if (window.showToast) window.showToast('Copied to clipboard');
            } catch {
                const ta = document.createElement('textarea');
                ta.value = text;
                ta.style.cssText = 'position:fixed;left:-9999px';
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
                if (window.showToast) window.showToast('Copied to clipboard');
            }
        });
        
        overlay.querySelector('.export-save-btn').addEventListener('click', async () => {
            const text = getActiveText();
            const saveName = filename;
            if (window.pywebview && window.pywebview.api && window.pywebview.api.save_file) {
                const saved = await window.pywebview.api.save_file(saveName, text);
                if (saved) {
                    if (window.showToast) window.showToast('File saved');
                    overlay.remove();
                }
            } else {
                const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = saveName;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                if (window.showToast) window.showToast('Download started');
                overlay.remove();
            }
        });
    }
    
    _audienceLabel(value) {
        const map = {
            technical: 'Technical — detail, codes, line refs',
            business: 'Business — impact, risk, actions',
            mixed: 'Mixed — summary + technical detail',
            executive: 'Executive — brief bullets, decisions'
        };
        if (!value) return '';
        return map[value] || String(value);
    }
    
    _renderMarkdownPlain(text) {
        if (!text) return '';
        let html = this.escapeHtml(text);
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\n/g, '<br>');
        return html;
    }
    
    _renderMarkdown(md) {
        let html = this.escapeHtml(md);
        
        // Headings
        html = html.replace(/^## (\d+\..*)$/gm, '<h3 class="ep-h2">$1</h3>');
        html = html.replace(/^# (.*)$/gm, '<h2 class="ep-h1">$1</h2>');
        
        // Bold
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Horizontal rules
        html = html.replace(/^---$/gm, '<hr>');
        
        // Code blocks
        html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
        
        // Inline code
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
        
        // Line breaks (two trailing spaces = <br>)
        html = html.replace(/  \n/g, '<br>');
        
        // Paragraphs (blank lines)
        html = html.replace(/\n\n/g, '</p><p>');
        html = '<p>' + html + '</p>';
        html = html.replace(/<p><\/p>/g, '');
        
        // Clean up headings/hr inside <p>
        html = html.replace(/<p>(<h[23]|<hr)/g, '$1');
        html = html.replace(/(<\/h[23]>|<hr>)<\/p>/g, '$1');
        
        return html;
    }
    
    // ── Drag-and-drop reordering ────────────────────────────
    
    _initDragAndDrop(container) {
        const items = container.querySelectorAll('.finding-item');
        
        items.forEach(item => {
            item.addEventListener('dragstart', (e) => this._onDragStart(e, item));
            item.addEventListener('dragover', (e) => this._onDragOver(e, item));
            item.addEventListener('dragenter', (e) => this._onDragEnter(e, item));
            item.addEventListener('dragleave', (e) => this._onDragLeave(e, item));
            item.addEventListener('drop', (e) => this._onDrop(e, item, container));
            item.addEventListener('dragend', () => this._onDragEnd(container));
        });
    }
    
    _onDragStart(e, item) {
        this._dragSrcEl = item;
        item.classList.add('finding-dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', item.dataset.findingId);
    }
    
    _onDragOver(e, item) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        
        const rect = item.getBoundingClientRect();
        const midY = rect.top + rect.height / 2;
        item.classList.remove('finding-drop-above', 'finding-drop-below');
        if (e.clientY < midY) {
            item.classList.add('finding-drop-above');
        } else {
            item.classList.add('finding-drop-below');
        }
    }
    
    _onDragEnter(e, item) {
        e.preventDefault();
        if (item !== this._dragSrcEl) {
            item.classList.add('finding-drop-target');
        }
    }
    
    _onDragLeave(e, item) {
        item.classList.remove('finding-drop-target', 'finding-drop-above', 'finding-drop-below');
    }
    
    _onDrop(e, item, container) {
        e.preventDefault();
        e.stopPropagation();
        
        item.classList.remove('finding-drop-target', 'finding-drop-above', 'finding-drop-below');
        
        if (this._dragSrcEl && this._dragSrcEl !== item) {
            const rect = item.getBoundingClientRect();
            const midY = rect.top + rect.height / 2;
            
            if (e.clientY < midY) {
                container.insertBefore(this._dragSrcEl, item);
            } else {
                container.insertBefore(this._dragSrcEl, item.nextSibling);
            }
            
            // Persist new order
            const ids = Array.from(container.querySelectorAll('.finding-item'))
                .map(el => parseInt(el.dataset.findingId));
            this._saveOrder(ids);
        }
    }
    
    _onDragEnd(container) {
        if (this._dragSrcEl) {
            this._dragSrcEl.classList.remove('finding-dragging');
        }
        container.querySelectorAll('.finding-item').forEach(el => {
            el.classList.remove('finding-drop-target', 'finding-drop-above', 'finding-drop-below');
        });
        this._dragSrcEl = null;
    }
    
    // ── Helpers ──────────────────────────────────────────────
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    setFileId(fileId) {
        this.currentFileId = fileId;
        this._orderKey = `findings_order_${fileId}`;
        this.loadFindings();
    }
}

// Initialize
const savedFindingsManager = new SavedFindingsManager();
window.savedFindingsManager = savedFindingsManager;
window.sanitizeFindingHtml = sanitizeFindingHtml;
