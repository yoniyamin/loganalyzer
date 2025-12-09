/**
 * Saved Findings Manager
 * 
 * Manages the display of saved findings in the Findings tab:
 * - Load and display findings from the API
 * - Delete findings
 * - Export findings
 */

class SavedFindingsManager {
    constructor() {
        this.findings = [];
        this.currentFileId = null;
        this.isLoading = false;
        
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
        
        // Listen for file changes
        document.addEventListener('fileLoaded', (e) => {
            this.currentFileId = e.detail?.fileId;
            this.loadFindings();
        });
        
        // Listen for new findings saved
        document.addEventListener('findingSaved', () => {
            this.loadFindings();
        });
    }
    
    bindEvents() {
        // Export button
        const exportBtn = document.getElementById('exportFindings');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => this.exportFindings());
        }
        
        // Clear all button
        const clearBtn = document.getElementById('clearFindings');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => this.clearAllFindings());
        }
        
        // Listen for tab changes to refresh when Findings tab is shown
        document.addEventListener('click', (e) => {
            const subtab = e.target.closest('.findings-sub-tab');
            if (subtab && subtab.dataset.subtab === 'findings-subtab') {
                this.loadFindings();
            }
        });
    }
    
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
    
    renderFindings(container) {
        if (!container) return;
        
        if (this.findings.length === 0) {
            container.innerHTML = `
                <p class="placeholder-text">
                    No findings yet. 
                    <br><br>
                    • Use the save button in AI Assistant answers
                    <br>
                    • Right-click on log lines to add them
                </p>
            `;
            return;
        }
        
        let html = '';
        
        this.findings.forEach(finding => {
            const dateStr = new Date(finding.created_at).toLocaleString();
            const typeIcon = this.getTypeIcon(finding.finding_type);
            const typeLabel = this.getTypeLabel(finding.finding_type);
            
            html += `
                <div class="finding-item" data-finding-id="${finding.id}">
                    <div class="finding-header">
                        <span class="finding-type ${finding.finding_type}">
                            ${typeIcon} ${typeLabel}
                        </span>
                        <span class="finding-date">${dateStr}</span>
                        <button class="finding-delete-btn" data-finding-id="${finding.id}" title="Delete finding">
                            ×
                        </button>
                    </div>
                    ${finding.title ? `<div class="finding-title">${this.escapeHtml(finding.title)}</div>` : ''}
                    <div class="finding-content">${this.formatContent(finding.content, finding.finding_type)}</div>
                    ${finding.line_number ? `<div class="finding-meta">Line ${finding.line_number}</div>` : ''}
                </div>
            `;
        });
        
        container.innerHTML = html;
        
        // Bind delete buttons
        container.querySelectorAll('.finding-delete-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const findingId = btn.dataset.findingId;
                if (confirm('Delete this finding?')) {
                    await this.deleteFinding(findingId);
                }
            });
        });
    }
    
    getTypeIcon(type) {
        switch (type) {
            case 'qa_thread': return '💬';
            case 'log_line': return '📋';
            case 'custom': return '📝';
            default: return '📌';
        }
    }
    
    getTypeLabel(type) {
        switch (type) {
            case 'qa_thread': return 'Q&A';
            case 'log_line': return 'Log Line';
            case 'custom': return 'Note';
            default: return 'Finding';
        }
    }
    
    formatContent(content, type) {
        if (!content) return '';
        
        // Simple markdown-like formatting
        let formatted = this.escapeHtml(content);
        
        // Bold text
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Code blocks
        formatted = formatted.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
        
        // Inline code
        formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');
        
        // Line breaks
        formatted = formatted.replace(/\n/g, '<br>');
        
        return formatted;
    }
    
    updateBadge() {
        const badge = document.getElementById('findingsCountBadge');
        if (badge) {
            badge.textContent = this.findings.length > 0 ? this.findings.length : '';
        }
    }
    
    async deleteFinding(findingId) {
        try {
            const response = await fetch(`/api/llm/findings/${findingId}`, {
                method: 'DELETE'
            });
            
            if (!response.ok) throw new Error('Failed to delete');
            
            // Reload findings
            this.loadFindings();
            
        } catch (error) {
            console.error('Failed to delete finding:', error);
            alert('Failed to delete finding');
        }
    }
    
    async clearAllFindings() {
        if (!confirm('Delete all findings for this file?')) return;
        
        try {
            // Delete each finding
            for (const finding of this.findings) {
                await fetch(`/api/llm/findings/${finding.id}`, {
                    method: 'DELETE'
                });
            }
            
            this.findings = [];
            this.renderFindings(document.getElementById('findingsList'));
            this.updateBadge();
            
        } catch (error) {
            console.error('Failed to clear findings:', error);
        }
    }
    
    exportFindings() {
        if (this.findings.length === 0) {
            alert('No findings to export');
            return;
        }
        
        let markdown = '# Saved Findings\n\n';
        markdown += `Exported: ${new Date().toLocaleString()}\n\n`;
        
        this.findings.forEach((finding, i) => {
            markdown += `## ${i + 1}. ${finding.title || this.getTypeLabel(finding.finding_type)}\n\n`;
            markdown += `**Type:** ${this.getTypeLabel(finding.finding_type)}\n`;
            markdown += `**Date:** ${new Date(finding.created_at).toLocaleString()}\n\n`;
            markdown += finding.content + '\n\n';
            markdown += '---\n\n';
        });
        
        // Download as file
        const blob = new Blob([markdown], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `findings-${Date.now()}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // Public method to set file ID (called from main app)
    setFileId(fileId) {
        this.currentFileId = fileId;
        this.loadFindings();
    }
}

// Initialize
const savedFindingsManager = new SavedFindingsManager();

// Expose for external access
window.savedFindingsManager = savedFindingsManager;
