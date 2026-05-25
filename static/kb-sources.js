/**
 * KB Sources Manager
 * 
 * Manages the Sources tab in the Findings area:
 * - Lists all KB articles and markdown sources with pagination
 * - Allows adding custom markdown sources with file upload
 * - Shows source statistics
 * - Supports search filtering
 */

class KBSourcesManager {
    constructor() {
        this.sources = [];
        this.stats = {};
        this.isLoading = false;
        
        // Pagination state
        this.currentPage = 1;
        this.pageSize = this.loadPageSize();  // Load from localStorage
        this.totalPages = 1;
        this.totalCount = 0;
        this.searchQuery = '';
        this.searchTimeout = null;
        
        this.init();
    }
    
    loadPageSize() {
        const saved = localStorage.getItem('kbSourcesPageSize');
        return saved ? parseInt(saved, 10) : 10;  // Default to 10
    }
    
    savePageSize(size) {
        localStorage.setItem('kbSourcesPageSize', size);
        this.pageSize = size;
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
        // Load sources when the Sources tab is first shown
        this.loadSources();
    }
    
    bindEvents() {
        // Search input
        const searchInput = document.getElementById('sourcesSearch');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => this.handleSearch(e.target.value));
        }
        
        // Add markdown source button
        const addBtn = document.getElementById('addMarkdownSource');
        if (addBtn) {
            addBtn.addEventListener('click', () => this.showAddModal());
        }
        
        // Refresh button
        const refreshBtn = document.getElementById('refreshSources');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.loadSources(true));
        }
        
        // Modal close buttons
        const closeBtn = document.getElementById('closeMarkdownModal');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.hideAddModal());
        }
        
        const cancelBtn = document.getElementById('cancelMarkdownModal');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => this.hideAddModal());
        }
        
        // Submit button
        const submitBtn = document.getElementById('submitMarkdownSource');
        if (submitBtn) {
            submitBtn.addEventListener('click', () => this.submitMarkdown());
        }
        
        // File upload button
        const browseBtn = document.getElementById('markdownBrowseBtn');
        const fileInput = document.getElementById('markdownFileInput');
        if (browseBtn && fileInput) {
            browseBtn.addEventListener('click', () => fileInput.click());
            fileInput.addEventListener('change', (e) => this.handleFileUpload(e));
        }
        
        // Close modal when clicking outside
        const modal = document.getElementById('addMarkdownModal');
        if (modal) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    this.hideAddModal();
                }
            });
        }
        
        // Listen for tab changes to refresh when Sources tab is shown
        document.addEventListener('click', (e) => {
            const subtab = e.target.closest('.findings-sub-tab');
            if (subtab && subtab.dataset.subtab === 'sources-subtab') {
                this.loadSources();
            }
        });
    }
    
    async handleFileUpload(event) {
        const file = event.target.files[0];
        if (!file) return;
        
        // Check file extension
        const validExtensions = ['.md', '.markdown', '.txt'];
        const ext = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));
        if (!validExtensions.includes(ext)) {
            alert('Please select a Markdown (.md, .markdown) or text (.txt) file');
            return;
        }
        
        try {
            const content = await file.text();
            
            // Set title from filename if empty
            const titleInput = document.getElementById('markdownTitle');
            if (titleInput && !titleInput.value) {
                titleInput.value = file.name.replace(/\.(md|markdown|txt)$/i, '');
            }
            
            // Set content
            const contentInput = document.getElementById('markdownContent');
            if (contentInput) {
                contentInput.value = content;
            }
            
            // Show file name
            const fileNameEl = document.getElementById('markdownFileName');
            if (fileNameEl) {
                fileNameEl.textContent = `Loaded: ${file.name}`;
            }
        } catch (error) {
            console.error('Failed to read file:', error);
            alert('Failed to read file: ' + error.message);
        }
        
        // Clear file input for re-selection
        event.target.value = '';
    }
    
    async loadSources(resetPage = false) {
        if (this.isLoading) return;
        
        if (resetPage) {
            this.currentPage = 1;
        }
        
        this.isLoading = true;
        const listEl = document.getElementById('sourcesList');
        const statsEl = document.getElementById('sourcesStats');
        
        if (listEl) {
            listEl.innerHTML = '<p class="placeholder-text">Loading sources...</p>';
        }
        
        try {
            const params = new URLSearchParams({
                page: this.currentPage,
                page_size: this.pageSize
            });
            
            if (this.searchQuery) {
                params.append('search', this.searchQuery);
            }
            
            const response = await fetch(`/api/llm/kb/sources?${params}`);
            if (!response.ok) throw new Error('Failed to load sources');
            
            const data = await response.json();
            this.sources = data.sources || [];
            this.stats = data.stats || {};
            this.totalCount = data.total_count || 0;
            this.totalPages = data.total_pages || 1;
            this.currentPage = data.page || 1;
            
            this.renderStats(statsEl);
            this.renderSources(listEl);
            this.renderPagination();
            this.updateBadge();
            
        } catch (error) {
            console.error('Failed to load KB sources:', error);
            if (listEl) {
                listEl.innerHTML = `<p class="placeholder-text error">Failed to load sources: ${error.message}</p>`;
            }
        } finally {
            this.isLoading = false;
        }
    }
    
    renderPagination() {
        const container = document.getElementById('sourcesPagination');
        if (!container) return;
        
        // Always show pagination controls for page size selector
        container.innerHTML = `
            <div class="pagination-controls">
                <div class="pagination-left">
                    <label class="pagination-size-label">
                        Per page:
                        <select class="pagination-size-select" id="pageSizeSelect">
                            <option value="10" ${this.pageSize === 10 ? 'selected' : ''}>10</option>
                            <option value="20" ${this.pageSize === 20 ? 'selected' : ''}>20</option>
                            <option value="50" ${this.pageSize === 50 ? 'selected' : ''}>50</option>
                            <option value="100" ${this.pageSize === 100 ? 'selected' : ''}>100</option>
                        </select>
                    </label>
                </div>
                ${this.totalPages > 1 ? `
                    <div class="pagination-center">
                        <button class="pagination-btn" ${this.currentPage <= 1 ? 'disabled' : ''} data-page="${this.currentPage - 1}">
                            ← Prev
                        </button>
                        <span class="pagination-info">
                            Page ${this.currentPage} of ${this.totalPages} (${this.totalCount} total)
                        </span>
                        <button class="pagination-btn" ${this.currentPage >= this.totalPages ? 'disabled' : ''} data-page="${this.currentPage + 1}">
                            Next →
                        </button>
                    </div>
                ` : `
                    <span class="pagination-info">${this.totalCount} total</span>
                `}
            </div>
        `;
        
        // Bind pagination events
        container.querySelectorAll('.pagination-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const page = parseInt(btn.dataset.page);
                if (page >= 1 && page <= this.totalPages) {
                    this.currentPage = page;
                    this.loadSources();
                }
            });
        });
        
        // Bind page size change
        const pageSizeSelect = document.getElementById('pageSizeSelect');
        if (pageSizeSelect) {
            pageSizeSelect.addEventListener('change', (e) => {
                const newSize = parseInt(e.target.value);
                this.savePageSize(newSize);
                this.loadSources(true);  // Reset to page 1
            });
        }
    }
    
    handleSearch(query) {
        this.searchQuery = query;
        
        // Debounce search
        if (this.searchTimeout) {
            clearTimeout(this.searchTimeout);
        }
        
        this.searchTimeout = setTimeout(() => {
            this.loadSources(true);  // Reset to page 1
        }, 300);
    }
    
    renderStats(container) {
        if (!container) return;
        
        const { total = 0, kb_articles = 0, markdown = 0, indexed = 0, release_notes = 0 } = this.stats;
        
        container.innerHTML = `
            <div class="stats-grid">
                <div class="stat-item">
                    <span class="stat-value">${total}</span>
                    <span class="stat-label">Total Sources</span>
                </div>
                <div class="stat-item">
                    <span class="stat-value">${kb_articles}</span>
                    <span class="stat-label">KB Articles</span>
                </div>
                <div class="stat-item">
                    <span class="stat-value">${markdown}</span>
                    <span class="stat-label">Custom Docs</span>
                </div>
                <div class="stat-item">
                    <span class="stat-value">${release_notes}</span>
                    <span class="stat-label">Release Notes</span>
                </div>
            </div>
            <div id="releaseNotesIndex" class="release-notes-index-wrap"></div>
        `;
        
        this.loadReleaseNotesIndex();
    }
    
    async loadReleaseNotesIndex() {
        const container = document.getElementById('releaseNotesIndex');
        if (!container) return;
        
        try {
            const resp = await fetch('/api/llm/kb/release-notes-index');
            if (!resp.ok) return;
            const data = await resp.json();
            
            if (!data.versions || data.versions.length === 0) {
                container.innerHTML = '';
                return;
            }
            
            let html = '<details class="rn-index-details">';
            html += '<summary class="rn-index-summary">'
                  + '<span class="rn-index-icon">📋</span> Release Notes Index '
                  + '<span class="rn-index-count">(' + data.total_entries + ' fixes, ' + data.total_eol + ' EOL across ' + data.versions.length + ' versions)</span>'
                  + '</summary>';
            html += '<div class="rn-index-body">';
            
            html += '<div class="rn-index-url-row">'
                  + '<input type="text" id="rnUrlInput" placeholder="Paste a community.qlik.com release notes URL..." class="rn-index-input">'
                  + '<button id="rnUrlAddBtn" class="rn-index-add-btn">+ Add URL</button>'
                  + '</div>';
            
            for (const v of data.versions) {
                const compList = v.components.length > 5
                    ? v.components.slice(0, 5).join(', ') + ' +' + (v.components.length - 5) + ' more'
                    : v.components.join(', ');
                html += '<div class="rn-index-row">';
                html += '<span class="rn-index-version">' + this.escapeHtml(v.version) + '</span>';
                html += '<span class="rn-index-fixes">' + v.entry_count + ' fixes</span>';
                if (v.url) {
                    html += '<a href="' + v.url + '" target="_blank" class="rn-index-link">'
                          + '<svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor"><path d="M8.636 3.5a.5.5 0 0 0-.5-.5H1.5A1.5 1.5 0 0 0 0 4.5v10A1.5 1.5 0 0 0 1.5 16h10a1.5 1.5 0 0 0 1.5-1.5V7.864a.5.5 0 0 0-1 0V14.5a.5.5 0 0 1-.5.5h-10a.5.5 0 0 1-.5-.5v-10a.5.5 0 0 1 .5-.5h6.636a.5.5 0 0 0 .5-.5z"/><path d="M16 .5a.5.5 0 0 0-.5-.5h-5a.5.5 0 0 0 0 1h3.793L6.146 9.146a.5.5 0 1 0 .708.708L15 1.707V5.5a.5.5 0 0 0 1 0v-5z"/></svg>'
                          + 'Open</a>';
                }
                html += '<span class="rn-index-components">' + this.escapeHtml(compList) + '</span>';
                html += '</div>';
            }
            
            html += '</div></details>';
            container.innerHTML = html;
            
            // Bind Add URL button
            const addBtn = document.getElementById('rnUrlAddBtn');
            const urlInput = document.getElementById('rnUrlInput');
            if (addBtn && urlInput) {
                addBtn.addEventListener('click', () => this.addReleaseNotesUrl(urlInput, addBtn));
                urlInput.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') this.addReleaseNotesUrl(urlInput, addBtn);
                });
            }
        } catch (err) {
            console.error('Failed to load release notes index:', err);
        }
    }
    
    async addReleaseNotesUrl(input, btn) {
        const url = input.value.trim();
        if (!url) return;
        
        btn.disabled = true;
        btn.textContent = 'Fetching...';
        
        try {
            const resp = await fetch('/api/llm/kb/release-notes-url', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });
            
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Failed to add URL');
            }
            
            const data = await resp.json();
            input.value = '';
            
            // Refresh the index
            this.loadReleaseNotesIndex();
            this.loadSources();
            
            alert(`Added "${data.version}" release notes: ${data.entries_added} new fixes, ${data.eol_added} EOL entries`);
        } catch (err) {
            alert('Error: ' + err.message);
        } finally {
            btn.disabled = false;
            btn.textContent = '+ Add URL';
        }
    }
    
    renderSources(container) {
        if (!container) return;
        
        if (this.sources.length === 0) {
            container.innerHTML = `
                <p class="placeholder-text">
                    No KB sources found. 
                    <br><br>
                    Add custom documentation using the "+ Add Custom" button, 
                    or run the KB scraper to index Qlik Community articles.
                </p>
            `;
            return;
        }
        
        // Group by source type
        const kbArticles = this.sources.filter(s => s.source === 'kb_article');
        const markdownDocs = this.sources.filter(s => s.source === 'markdown');
        
        let html = '';
        
        // Markdown docs first (custom)
        if (markdownDocs.length > 0) {
            html += `
                <div class="sources-section">
                    <h4 class="sources-section-title">Custom Documents (${markdownDocs.length})</h4>
                    <div class="sources-items">
                        ${markdownDocs.map(s => this.renderSourceItem(s, true)).join('')}
                    </div>
                </div>
            `;
        }
        
        // KB articles
        if (kbArticles.length > 0) {
            html += `
                <div class="sources-section">
                    <h4 class="sources-section-title">KB Articles (${kbArticles.length})</h4>
                    <div class="sources-items">
                        ${kbArticles.map(s => this.renderSourceItem(s, false)).join('')}
                    </div>
                </div>
            `;
        }
        
        container.innerHTML = html;
        
        // Bind delete buttons
        container.querySelectorAll('.source-delete-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const sourceId = btn.dataset.sourceId;
                if (sourceId && confirm('Delete this source? This will remove it from the knowledge base.')) {
                    this.deleteSource(sourceId);
                }
            });
        });
    }
    
    renderSourceItem(source, showDelete = false) {
        const isUrl = source.url && source.url.startsWith('http');
        const dateStr = source.indexed_at 
            ? new Date(source.indexed_at).toLocaleDateString() 
            : 'Unknown';
        
        return `
            <div class="source-item ${source.source}">
                <div class="source-icon">
                    ${source.source === 'markdown' ? '📄' : '📰'}
                </div>
                <div class="source-info">
                    <div class="source-title">
                        ${isUrl 
                            ? `<a href="${source.url}" target="_blank" rel="noopener">${this.escapeHtml(source.title)}</a>`
                            : this.escapeHtml(source.title)
                        }
                    </div>
                    <div class="source-meta">
                        <span class="source-type">${source.source === 'markdown' ? 'Custom' : 'KB Article'}</span>
                        <span class="source-chunks">${source.chunks_count} chunks</span>
                        <span class="source-date">${dateStr}</span>
                        <span class="source-status ${source.status}">${source.status}</span>
                    </div>
                </div>
                ${showDelete ? `
                    <button class="source-delete-btn" data-source-id="${source.id}" title="Delete this source">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"/>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        </svg>
                    </button>
                ` : ''}
            </div>
        `;
    }
    
    updateBadge() {
        const badge = document.getElementById('sourcesCountBadge');
        if (badge) {
            // Show total count from stats, not current page count
            const total = this.stats.total || this.totalCount || 0;
            badge.textContent = total > 0 ? total : '';
        }
    }
    
    showAddModal() {
        const modal = document.getElementById('addMarkdownModal');
        if (modal) {
            modal.style.display = 'flex';
            // Clear form
            document.getElementById('markdownTitle').value = '';
            document.getElementById('markdownCategory').value = '';
            document.getElementById('markdownTags').value = '';
            document.getElementById('markdownContent').value = '';
            const fileNameEl = document.getElementById('markdownFileName');
            if (fileNameEl) fileNameEl.textContent = 'No file selected';
            // Focus title input
            document.getElementById('markdownTitle').focus();
        }
    }
    
    hideAddModal() {
        const modal = document.getElementById('addMarkdownModal');
        if (modal) {
            modal.style.display = 'none';
        }
    }
    
    async submitMarkdown() {
        const title = document.getElementById('markdownTitle').value.trim();
        const category = document.getElementById('markdownCategory').value;
        const tagsInput = document.getElementById('markdownTags').value.trim();
        const content = document.getElementById('markdownContent').value.trim();
        
        if (!title) {
            alert('Please enter a title');
            return;
        }
        
        if (!content) {
            alert('Please enter content');
            return;
        }
        
        // Combine category and tags
        let tags = tagsInput ? tagsInput.split(',').map(t => t.trim()).filter(t => t) : [];
        if (category && !tags.includes(category)) {
            tags.unshift(category);  // Add category as first tag
        }
        
        const submitBtn = document.getElementById('submitMarkdownSource');
        submitBtn.disabled = true;
        submitBtn.textContent = 'Adding...';
        
        try {
            const response = await fetch('/api/llm/kb/markdown', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title, content, tags })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to add source');
            }
            
            const result = await response.json();
            
            this.hideAddModal();
            this.loadSources();
            
            // Show success message
            alert(`Successfully added "${title}" with ${result.chunks_count} chunks`);
            
        } catch (error) {
            console.error('Failed to add markdown source:', error);
            alert(`Failed to add source: ${error.message}`);
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Add to KB';
        }
    }
    
    async deleteSource(sourceId) {
        try {
            const response = await fetch(`/api/llm/kb/sources/${sourceId}`, {
                method: 'DELETE'
            });
            
            if (!response.ok) {
                throw new Error('Failed to delete source');
            }
            
            // Reload sources
            this.loadSources();
            
        } catch (error) {
            console.error('Failed to delete source:', error);
            alert(`Failed to delete source: ${error.message}`);
        }
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize when DOM is ready
const kbSourcesManager = new KBSourcesManager();

