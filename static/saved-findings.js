/**
 * Saved Findings Manager
 * 
 * Manages the display of saved findings in the Findings tab:
 * - Load and display findings from the API
 * - Drag-and-drop reordering
 * - Delete findings with centered modal confirmation
 * - Export findings as Markdown
 * - Source-aware formatting
 */

class SavedFindingsManager {
    constructor() {
        this.findings = [];
        this.currentFileId = null;
        this.isLoading = false;
        this._orderKey = null;     // localStorage key for custom order
        this._dragSrcEl = null;
        
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
            this.currentFileId = e.detail?.fileId;
            this._orderKey = `findings_order_${this.currentFileId}`;
            this.loadFindings();
        });

        document.addEventListener('fileClosed', () => {
            this.currentFileId = null;
            this._orderKey = null;
            this.findings = [];
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
        
        if (container) {
            container.innerHTML = '<p class="placeholder-text">Loading findings...</p>';
        }
        
        try {
            const response = await fetch(`/api/llm/findings/${this.currentFileId}`);
            if (!response.ok) throw new Error('Failed to load findings');
            
            const data = await response.json();
            this.findings = data.findings || [];
            this._orderKey = `findings_order_${this.currentFileId}`;
            
            this.renderFindings(container);
            this.updateBadge();
            
        } catch (error) {
            console.error('Failed to load findings:', error);
            if (container) {
                container.innerHTML = `<p class="placeholder-text">No findings yet. Use the AI assistant save button or right-click log lines.</p>`;
            }
        } finally {
            this.isLoading = false;
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
                        <div class="finding-content ${this._getContentClass(finding)}">${this.formatContent(finding.content, finding)}</div>
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
        if (src === 'context_menu' || finding.finding_type === 'log_line') return 'finding-content-logline';
        return '';
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
    
    // ── Export ───────────────────────────────────────────────
    
    async exportFindings() {
        const ordered = this._getOrderedFindings();
        if (ordered.length === 0) {
            if (window.showToast) window.showToast('No findings to export', 'error');
            return;
        }
        
        if (!this.currentFileId) return;
        
        try {
            const resp = await fetch(`/api/llm/findings/${this.currentFileId}/export`, {
                method: 'POST'
            });
            if (!resp.ok) throw new Error('Export failed');
            const data = await resp.json();
            
            this._showExportPreview(data.filename, data.content);
        } catch (e) {
            console.error('Export failed:', e);
            if (window.showToast) window.showToast('Export failed', 'error');
        }
    }
    
    _showExportPreview(filename, markdown) {
        const existing = document.getElementById('exportPreviewOverlay');
        if (existing) existing.remove();
        
        const overlay = document.createElement('div');
        overlay.id = 'exportPreviewOverlay';
        overlay.className = 'export-preview-overlay';
        
        const rendered = this._renderMarkdown(markdown);
        
        overlay.innerHTML = `
            <div class="export-preview-dialog">
                <div class="export-preview-header">
                    <h3>Export Preview</h3>
                    <span class="export-preview-filename">${this.escapeHtml(filename)}</span>
                    <button class="export-preview-close" title="Close">×</button>
                </div>
                <div class="export-preview-tabs">
                    <button class="export-preview-tab active" data-view="rendered">Preview</button>
                    <button class="export-preview-tab" data-view="raw">Markdown</button>
                </div>
                <div class="export-preview-body">
                    <div class="export-preview-rendered active" data-view="rendered">${rendered}</div>
                    <div class="export-preview-raw" data-view="raw"><pre>${this.escapeHtml(markdown)}</pre></div>
                </div>
                <div class="export-preview-actions">
                    <button class="export-action-btn export-copy-btn">Copy to Clipboard</button>
                    <button class="export-action-btn export-save-btn">Save File</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        
        // Close
        overlay.querySelector('.export-preview-close').addEventListener('click', () => overlay.remove());
        overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
        
        // Tab switching
        overlay.querySelectorAll('.export-preview-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                overlay.querySelectorAll('.export-preview-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const view = tab.dataset.view;
                overlay.querySelector('.export-preview-rendered').classList.toggle('active', view === 'rendered');
                overlay.querySelector('.export-preview-raw').classList.toggle('active', view === 'raw');
            });
        });
        
        // Copy
        overlay.querySelector('.export-copy-btn').addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(markdown);
                if (window.showToast) window.showToast('Copied to clipboard');
            } catch {
                // Fallback
                const ta = document.createElement('textarea');
                ta.value = markdown;
                ta.style.cssText = 'position:fixed;left:-9999px';
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
                if (window.showToast) window.showToast('Copied to clipboard');
            }
        });
        
        // Save
        overlay.querySelector('.export-save-btn').addEventListener('click', async () => {
            if (window.pywebview && window.pywebview.api && window.pywebview.api.save_file) {
                const saved = await window.pywebview.api.save_file(filename, markdown);
                if (saved) {
                    if (window.showToast) window.showToast('File saved');
                    overlay.remove();
                }
            } else {
                if (window.showToast) window.showToast('Save dialog not available in browser mode', 'error');
            }
        });
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
