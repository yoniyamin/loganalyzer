/**
 * Prompt Lab — inspect report prompts, compare models, package outputs for analysis.
 */
class PromptLabModal {
    constructor() {
        this.overlay = null;
        this.isOpen = false;
        this.compareEnabled = false;
        this.variantCounter = 0;
        this.reportHistory = [];
        /** @type {Map<string, object>} keys: saved-{id} | compare-baseline | compare-variant-N */
        this.packagePool = new Map();
        this.packageSelection = [];
        this.lastCompareData = null;
        this.lastPreviewMeta = null;
        this.init();
    }

    init() {
        this.createModal();
        this.bindEvents();
        this.loadStatus();
    }

    createModal() {
        const html = `
            <div class="pl-overlay" id="promptLabOverlay">
                <div class="pl-modal" role="dialog" aria-labelledby="promptLabTitle">
                    <div class="pl-header">
                        <h2 id="promptLabTitle">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18"/>
                            </svg>
                            Prompt Lab
                        </h2>
                        <button type="button" class="pl-close" id="promptLabClose" aria-label="Close">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M18 6L6 18M6 6l12 12"/>
                            </svg>
                        </button>
                    </div>
                    <div class="pl-tabs-bar">
                        <div class="pl-tabs">
                            <button type="button" class="pl-tab active" data-pl-tab="preview">Prompt Preview</button>
                            <button type="button" class="pl-tab" data-pl-tab="compare">Model Compare</button>
                        </div>
                        <div class="pl-file-badge" id="plFileBadge">No log file loaded</div>
                    </div>
                    <div class="pl-body">
                        <div class="pl-reports-section" id="plReportsSection" style="display: none;">
                            <h4>Saved reports for this file</h4>
                            <div class="pl-reports-list" id="plReportsList"></div>
                        </div>
                        <div class="pl-package-bar" id="plPackageBar">
                            <span class="pl-package-hint" id="plPackageHint">Select exactly 2 outputs (saved reports or compare runs), then export a JSON package with the prompt.</span>
                            <button type="button" class="ai-btn ai-btn-secondary ai-btn-sm" id="plExportPackageBtn" disabled>Export analysis package</button>
                        </div>
                        <div class="pl-tab-panel active" data-pl-panel="preview">
                            <div class="pl-options-grid">
                                <div class="pl-option-group">
                                    <label for="plFocusMode">Focus mode</label>
                                    <select id="plFocusMode" class="ai-select">
                                        <option value="">Auto (default)</option>
                                        <option value="general_review">General review</option>
                                        <option value="performance">Performance</option>
                                        <option value="errors">Errors</option>
                                        <option value="configuration">Configuration</option>
                                    </select>
                                </div>
                                <div class="pl-option-group">
                                    <label for="plPayloadFormat">Payload format (A/B)</label>
                                    <select id="plPayloadFormat" class="ai-select">
                                        <option value="markdown">A — Markdown (default)</option>
                                        <option value="json_markdown">B — JSON facts + Markdown</option>
                                        <option value="xml">C — XML-heavy</option>
                                    </select>
                                </div>
                            </div>
                            <div class="pl-check-row">
                                <label><input type="checkbox" id="plQuick"> Quick summary prompt</label>
                                <label><input type="checkbox" id="plWebSearch"> Web search context</label>
                                <label><input type="checkbox" id="plIncludeChart"> Include chart image</label>
                                <label><input type="checkbox" id="plFetchExternal"> Fetch external KB / release notes</label>
                                <label><input type="checkbox" id="plIncludeGraph" checked> Include graph context (gated)</label>
                            </div>
                            <div class="pl-actions">
                                <button type="button" class="ai-btn ai-btn-primary" id="plPreviewBtn">Preview Prompt</button>
                                <button type="button" class="ai-btn ai-btn-secondary" id="plCopyPromptBtn" disabled>Copy Prompt</button>
                            </div>
                            <div id="plPreviewMeta"></div>
                            <div id="plPreviewOutput">
                                <div class="pl-empty-hint">Load a log file, then preview the exact report prompt that would be sent to the model.</div>
                            </div>
                        </div>
                        <div class="pl-tab-panel" data-pl-panel="compare">
                            <div id="plCompareDisabled" class="pl-compare-disabled" style="display: none;">
                                Model compare is disabled on this server. Set <code>LOG_ANALYZER_PROMPT_LAB=1</code> before starting the app (enabled automatically in <code>desktop.py</code>).
                            </div>
                            <div id="plComparePanel">
                                <div class="pl-check-row">
                                    <label><input type="checkbox" id="plCompareQuick"> Quick mode (alert prompt)</label>
                                    <label><input type="checkbox" id="plCompareWebSearch"> Web search</label>
                                    <label><input type="checkbox" id="plCompareIncludeChart"> Include chart</label>
                                    <label><input type="checkbox" id="plCompareFetchExternal"> Fetch KB / release notes</label>
                                    <label><input type="checkbox" id="plCompareIncludeGraph" checked> Include graph context</label>
                                </div>
                                <div class="pl-options-grid">
                                    <div class="pl-option-group">
                                        <label for="plComparePayloadFormat">Payload format (A/B)</label>
                                        <select id="plComparePayloadFormat" class="ai-select">
                                            <option value="markdown">A — Markdown</option>
                                            <option value="json_markdown">B — JSON + Markdown</option>
                                            <option value="xml">C — XML-heavy</option>
                                        </select>
                                    </div>
                                </div>
                                <div class="pl-baseline-block">
                                    <h4>Baseline</h4>
                                    <div class="pl-config-row baseline">
                                        <div class="pl-config-field">
                                            <label for="plBaselineProvider">Provider</label>
                                            <select id="plBaselineProvider" class="ai-select">
                                                <option value="gemini">Gemini</option>
                                                <option value="openrouter">OpenRouter</option>
                                                <option value="lmstudio">LM Studio</option>
                                                <option value="openai_api">OpenAI API (FLM)</option>
                                            </select>
                                        </div>
                                        <div class="pl-config-field">
                                            <label for="plBaselineModel">Model</label>
                                            <input type="text" id="plBaselineModel" class="ai-input" placeholder="default from config">
                                        </div>
                                        <div class="pl-config-field">
                                            <label for="plBaselineTemp">Temp</label>
                                            <input type="number" id="plBaselineTemp" class="ai-input pl-temp-input" value="0.3" min="0" max="2" step="0.05">
                                        </div>
                                    </div>
                                </div>
                                <div class="pl-actions">
                                    <button type="button" class="ai-btn ai-btn-secondary ai-btn-sm" id="plAddVariantBtn">+ Add variant</button>
                                </div>
                                <div class="pl-variant-list" id="plVariantList"></div>
                                <div class="pl-actions">
                                    <button type="button" class="ai-btn ai-btn-primary" id="plCompareBtn">Run Compare</button>
                                </div>
                                <div id="plCompareOutput"></div>
                            </div>
                        </div>
                    </div>
                    <div class="pl-footer">
                        <button type="button" class="ai-btn ai-btn-secondary" id="plCloseFooterBtn">Close</button>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', html);
        this.overlay = document.getElementById('promptLabOverlay');
    }

    bindEvents() {
        const close = () => this.close();
        document.getElementById('promptLabClose').addEventListener('click', close);
        document.getElementById('plCloseFooterBtn').addEventListener('click', close);
        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay) close();
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isOpen) close();
        });

        this.overlay.querySelectorAll('.pl-tab').forEach((tab) => {
            tab.addEventListener('click', () => this.switchTab(tab.dataset.plTab));
        });

        document.getElementById('plPreviewBtn').addEventListener('click', () => this.runPreview());
        document.getElementById('plCopyPromptBtn').addEventListener('click', () => this.copyPrompt());
        document.getElementById('plCompareBtn').addEventListener('click', () => this.runCompare());
        document.getElementById('plAddVariantBtn').addEventListener('click', () => this.addVariantRow());
        document.getElementById('plExportPackageBtn').addEventListener('click', () => this.exportAnalysisPackage());
    }

    async loadStatus() {
        try {
            const resp = await fetch('/api/llm/prompt-lab/status');
            if (resp.ok) {
                const data = await resp.json();
                this.compareEnabled = !!data.compare_enabled;
            }
        } catch (_) {
            this.compareEnabled = false;
        }
        this.updateCompareAvailability();
    }

    updateCompareAvailability() {
        const disabled = document.getElementById('plCompareDisabled');
        const panel = document.getElementById('plComparePanel');
        const compareBtn = document.getElementById('plCompareBtn');
        const addBtn = document.getElementById('plAddVariantBtn');
        if (!disabled || !panel) return;
        disabled.style.display = this.compareEnabled ? 'none' : 'block';
        panel.style.opacity = this.compareEnabled ? '1' : '0.45';
        panel.style.pointerEvents = this.compareEnabled ? 'auto' : 'none';
        if (compareBtn) compareBtn.disabled = !this.compareEnabled;
        if (addBtn) addBtn.disabled = !this.compareEnabled;
    }

    getFileId() {
        return window.aiReportManager?.currentFileId ?? window.currentFileId ?? null;
    }

    refreshFileBadge() {
        const badge = document.getElementById('plFileBadge');
        const fileId = this.getFileId();
        if (!badge) return;
        if (!fileId) {
            badge.textContent = 'No log file loaded';
            badge.classList.add('no-file');
            return;
        }
        badge.classList.remove('no-file');
        badge.textContent = `File #${fileId}`;
    }

    async loadReportHistory() {
        const section = document.getElementById('plReportsSection');
        const list = document.getElementById('plReportsList');
        const fileId = this.getFileId();
        this.reportHistory = [];
        if (!section || !list) return;

        if (!fileId) {
            section.style.display = 'none';
            list.innerHTML = '';
            return;
        }

        try {
            const resp = await fetch(`/api/llm/report/${fileId}/history`);
            if (!resp.ok) throw new Error('Failed to load report history');
            const data = await resp.json();
            this.reportHistory = data.reports || [];
        } catch (_) {
            this.reportHistory = [];
        }

        if (this.reportHistory.length === 0) {
            section.style.display = 'none';
            list.innerHTML = '';
            return;
        }

        section.style.display = 'block';
        list.innerHTML = this.reportHistory.map((r) => this.renderReportHistoryItem(r)).join('');
        list.querySelectorAll('.pl-report-pack-cb').forEach((cb) => {
            cb.addEventListener('change', (e) => this.togglePackageSelection(e.target));
        });
        list.querySelectorAll('.pl-report-view-btn').forEach((btn) => {
            btn.addEventListener('click', () => this.viewSavedReport(btn.dataset.reportId));
        });
    }

    renderReportHistoryItem(report) {
        const when = report.generated_at ? new Date(report.generated_at).toLocaleString() : 'Unknown date';
        const dur = report.llm_duration_seconds != null ? `${report.llm_duration_seconds}s` : '—';
        const focus = report.focus_mode ? ` · ${report.focus_mode}` : '';
        const key = `saved-${report.report_id}`;
        const checked = this.packageSelection.includes(key) ? 'checked' : '';
        return `
            <div class="pl-report-item${checked ? ' selected' : ''}" data-pack-key="${key}">
                <label class="pl-report-pack-label">
                    <input type="checkbox" class="pl-report-pack-cb" data-pack-key="${key}" ${checked}>
                </label>
                <div class="pl-report-meta">
                    <div>${this.escapeHtml(report.model_used || 'unknown model')}</div>
                    <div class="pl-report-meta-sub">${this.escapeHtml(when)} · ${report.prompt_tokens || 0}+${report.completion_tokens || 0} tok · ${dur}${this.escapeHtml(focus)}</div>
                </div>
                <button type="button" class="ai-btn ai-btn-secondary ai-btn-sm pl-report-view-btn" data-report-id="${report.report_id}">View</button>
            </div>
        `;
    }

    async viewSavedReport(reportId) {
        const out = document.getElementById('plPreviewOutput');
        if (!out) return;
        out.innerHTML = '<div class="pl-loading">Loading report…</div>';
        this.switchTab('preview');
        try {
            const resp = await fetch(`/api/llm/report/by-id/${reportId}`);
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(data.detail || 'Failed to load report');
            out.innerHTML = `<pre class="pl-prompt-viewer">${this.escapeHtml(data.report_content || '')}</pre>`;
            const meta = document.getElementById('plPreviewMeta');
            if (meta) {
                meta.innerHTML = `
                    <div class="pl-meta-bar">
                        <span class="pl-meta-chip">Saved report #${reportId}</span>
                        <span class="pl-meta-chip">${this.escapeHtml(data.model_used || '')}</span>
                        <span class="pl-meta-chip">${data.prompt_tokens || 0} in / ${data.completion_tokens || 0} out</span>
                    </div>
                `;
            }
        } catch (e) {
            out.innerHTML = `<div class="pl-error">${this.escapeHtml(e.message)}</div>`;
        }
    }

    syncBaselineFromConfig() {
        const cfgModal = window.aiConfigModal;
        const provider = cfgModal?.selectedProvider || cfgModal?.currentConfig?.provider || 'gemini';
        const providerEl = document.getElementById('plBaselineProvider');
        if (providerEl) providerEl.value = provider;

        const reportModel = document.getElementById('aiReportModel')?.value
            || cfgModal?.currentConfig?.default_model
            || '';
        const modelEl = document.getElementById('plBaselineModel');
        if (modelEl && reportModel) modelEl.value = reportModel;

        const temp = this._temperatureForProvider(provider, cfgModal?.currentConfig);
        const tempEl = document.getElementById('plBaselineTemp');
        if (tempEl && temp != null) tempEl.value = temp;
    }

    _temperatureForProvider(provider, config) {
        if (!config) return 0.3;
        if (provider === 'lmstudio') return config.lmstudio_temperature ?? 0.3;
        if (provider === 'openai_api') return config.openai_api_temperature ?? 0.3;
        return 0.3;
    }

    open() {
        this.refreshFileBadge();
        this.syncBaselineFromConfig();
        this.loadStatus();
        this.loadReportHistory();
        this.updatePackageUi();
        this.overlay.classList.add('active');
        this.isOpen = true;
    }

    close() {
        this.overlay.classList.remove('active');
        this.isOpen = false;
    }

    switchTab(tabName) {
        this.overlay.querySelectorAll('.pl-tab').forEach((t) => {
            t.classList.toggle('active', t.dataset.plTab === tabName);
        });
        this.overlay.querySelectorAll('.pl-tab-panel').forEach((p) => {
            p.classList.toggle('active', p.dataset.plPanel === tabName);
        });
    }

    _requireFileId() {
        const fileId = this.getFileId();
        if (!fileId) {
            throw new Error('Load a log file first — Prompt Lab needs an indexed file.');
        }
        return fileId;
    }

    _focusModeValue() {
        const v = document.getElementById('plFocusMode')?.value;
        return v || null;
    }

    _payloadFormatValue(prefix = 'pl') {
        const el = document.getElementById(`${prefix}PayloadFormat`);
        return el?.value || 'markdown';
    }

    async runPreview() {
        const out = document.getElementById('plPreviewOutput');
        const meta = document.getElementById('plPreviewMeta');
        const copyBtn = document.getElementById('plCopyPromptBtn');
        let fileId;
        try {
            fileId = this._requireFileId();
        } catch (e) {
            out.innerHTML = `<div class="pl-error">${this.escapeHtml(e.message)}</div>`;
            return;
        }

        out.innerHTML = '<div class="pl-loading">Building prompt…</div>';
        meta.innerHTML = '';
        if (copyBtn) copyBtn.disabled = true;
        this._lastPromptText = '';

        const body = {
            quick: document.getElementById('plQuick')?.checked || false,
            web_search: document.getElementById('plWebSearch')?.checked || false,
            focus_mode: this._focusModeValue(),
            include_chart: document.getElementById('plIncludeChart')?.checked || false,
            fetch_external: document.getElementById('plFetchExternal')?.checked || false,
            payload_format: this._payloadFormatValue('pl'),
            include_graph: document.getElementById('plIncludeGraph')?.checked ?? true,
        };

        try {
            const resp = await fetch(`/api/llm/report/${fileId}/prompt-preview`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) {
                throw new Error(data.detail || `Preview failed (${resp.status})`);
            }

            this._lastPromptText = data.prompt_text || '';
            this.lastPreviewMeta = { ...body, ...data, file_id: fileId };
            const stats = data.context_stats || {};
            meta.innerHTML = `
                <div class="pl-meta-bar">
                    <span class="pl-meta-chip">~${Number(data.est_tokens || 0).toLocaleString()} tokens</span>
                    <span class="pl-meta-chip">${this.escapeHtml(data.provider || '')}</span>
                    <span class="pl-meta-chip">${data.compact ? 'compact' : 'full'} prompt</span>
                    <span class="pl-meta-chip">format: ${this.escapeHtml(data.payload_format || 'markdown')}</span>
                    <span class="pl-meta-chip">${data.message_count || 0} messages</span>
                    <span class="pl-meta-chip">errors: ${stats.errors ?? 0}</span>
                    <span class="pl-meta-chip">anomalies: ${stats.anomalies ?? 0}</span>
                    <span class="pl-meta-chip">kb: ${stats.kb ?? 0}</span>
                    <span class="pl-meta-chip">release notes: ${stats.release_notes ?? 0}</span>
                    <span class="pl-meta-chip">graph: ${stats.graph_injected ? 'injected' : 'skipped'}</span>
                </div>
            `;
            out.innerHTML = `<pre class="pl-prompt-viewer">${this.escapeHtml(this._lastPromptText)}</pre>`;
            if (copyBtn) copyBtn.disabled = !this._lastPromptText;
        } catch (e) {
            out.innerHTML = `<div class="pl-error">${this.escapeHtml(e.message)}</div>`;
        }
    }

    async copyPrompt() {
        if (!this._lastPromptText) return;
        try {
            await navigator.clipboard.writeText(this._lastPromptText);
        } catch (_) {
            /* clipboard may be restricted in some hosts */
        }
    }

    addVariantRow(initial = {}) {
        const list = document.getElementById('plVariantList');
        if (!list) return;
        const rows = list.querySelectorAll('.pl-config-row.variant');
        if (rows.length >= 5) {
            alert('Maximum 5 variants allowed.');
            return;
        }

        this.variantCounter += 1;
        const row = document.createElement('div');
        row.className = 'pl-config-row variant';
        row.innerHTML = `
            <div class="pl-config-field">
                <label>Provider</label>
                <select class="ai-select pl-variant-provider">
                    <option value="gemini">Gemini</option>
                    <option value="openrouter">OpenRouter</option>
                    <option value="lmstudio">LM Studio</option>
                    <option value="openai_api">OpenAI API (FLM)</option>
                </select>
            </div>
            <div class="pl-config-field">
                <label>Model</label>
                <input type="text" class="ai-input pl-variant-model" placeholder="model id" value="${this.escapeHtml(initial.model || '')}">
            </div>
            <div class="pl-config-field">
                <label>Temp</label>
                <input type="number" class="ai-input pl-temp-input pl-variant-temp" value="${initial.temperature ?? 0.3}" min="0" max="2" step="0.05">
            </div>
            <div class="pl-config-field pl-config-actions">
                <label>&nbsp;</label>
                <button type="button" class="ai-btn ai-btn-secondary ai-btn-sm pl-remove-variant">Remove</button>
            </div>
        `;
        const prov = row.querySelector('.pl-variant-provider');
        if (prov && initial.provider) prov.value = initial.provider;
        row.querySelector('.pl-remove-variant').addEventListener('click', () => row.remove());
        list.appendChild(row);
    }

    _readVariant(el) {
        return {
            provider: el.querySelector('.pl-variant-provider')?.value || 'gemini',
            model: (el.querySelector('.pl-variant-model')?.value || '').trim() || null,
            temperature: parseFloat(el.querySelector('.pl-variant-temp')?.value || '0.3'),
        };
    }

    async runCompare() {
        if (!this.compareEnabled) return;
        const out = document.getElementById('plCompareOutput');
        let fileId;
        try {
            fileId = this._requireFileId();
        } catch (e) {
            out.innerHTML = `<div class="pl-error">${this.escapeHtml(e.message)}</div>`;
            return;
        }

        const baseline = {
            provider: document.getElementById('plBaselineProvider')?.value || 'gemini',
            model: (document.getElementById('plBaselineModel')?.value || '').trim() || null,
            temperature: parseFloat(document.getElementById('plBaselineTemp')?.value || '0.3'),
        };

        const variants = [];
        document.querySelectorAll('#plVariantList .pl-config-row.variant').forEach((row) => {
            variants.push(this._readVariant(row));
        });

        out.innerHTML = '<div class="pl-loading">Running compare — this may take several minutes…</div>';
        document.getElementById('plCompareBtn').disabled = true;

        const body = {
            baseline,
            variants,
            quick: document.getElementById('plCompareQuick')?.checked ?? false,
            web_search: document.getElementById('plCompareWebSearch')?.checked || false,
            include_chart: document.getElementById('plCompareIncludeChart')?.checked || false,
            fetch_external: document.getElementById('plCompareFetchExternal')?.checked || false,
            payload_format: this._payloadFormatValue('plCompare'),
            include_graph: document.getElementById('plCompareIncludeGraph')?.checked ?? true,
            focus_mode: this._focusModeValue(),
            save_sample: false,
        };

        try {
            const resp = await fetch(`/api/llm/report/${fileId}/compare`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) {
                throw new Error(data.detail || `Compare failed (${resp.status})`);
            }
            this.lastCompareData = data;
            this.registerCompareResults(data);
            out.innerHTML = this.renderCompareResults(data);
            this.bindComparePackageCheckboxes(out);
        } catch (e) {
            out.innerHTML = `<div class="pl-error">${this.escapeHtml(e.message)}</div>`;
        } finally {
            document.getElementById('plCompareBtn').disabled = !this.compareEnabled;
        }
    }

    registerCompareResults(data) {
        if (!data?.baseline) return;
        this.packagePool.set('compare-baseline', {
            source: 'compare',
            label: 'Baseline',
            ...data.baseline,
            content: data.baseline.content || data.baseline.content_excerpt || '',
        });
        (data.variants || []).forEach((v, i) => {
            this.packagePool.set(`compare-variant-${i}`, {
                source: 'compare',
                label: `Variant ${i + 1}`,
                ...v,
                content: v.content || v.content_excerpt || '',
            });
        });
    }

    bindComparePackageCheckboxes(container) {
        container.querySelectorAll('.pl-compare-pack-cb').forEach((cb) => {
            cb.addEventListener('change', (e) => this.togglePackageSelection(e.target));
        });
    }

    togglePackageSelection(checkbox) {
        const key = checkbox.dataset.packKey;
        if (!key) return;

        if (checkbox.checked) {
            if (this.packageSelection.length >= 2) {
                const removed = this.packageSelection.shift();
                const prev = document.querySelector(`[data-pack-key="${removed}"] .pl-report-pack-cb, .pl-compare-pack-cb[data-pack-key="${removed}"]`);
                if (prev) prev.checked = false;
                document.querySelector(`.pl-report-item[data-pack-key="${removed}"]`)?.classList.remove('selected');
                document.querySelector(`.pl-result-card[data-pack-key="${removed}"]`)?.classList.remove('pack-selected');
            }
            if (!this.packageSelection.includes(key)) {
                this.packageSelection.push(key);
            }
        } else {
            this.packageSelection = this.packageSelection.filter((k) => k !== key);
        }

        document.querySelector(`.pl-report-item[data-pack-key="${key}"]`)?.classList.toggle('selected', checkbox.checked);
        document.querySelector(`.pl-result-card[data-pack-key="${key}"]`)?.classList.toggle('pack-selected', checkbox.checked);
        this.updatePackageUi();
    }

    updatePackageUi() {
        const btn = document.getElementById('plExportPackageBtn');
        const hint = document.getElementById('plPackageHint');
        const count = this.packageSelection.length;
        if (btn) btn.disabled = count !== 2;
        if (hint) {
            hint.textContent = count === 2
                ? 'Ready — export JSON with prompt + both selected outputs.'
                : `Select exactly 2 outputs (${count}/2 selected).`;
        }
    }

    async _resolvePackageEntry(key) {
        if (key.startsWith('saved-')) {
            const reportId = parseInt(key.replace('saved-', ''), 10);
            const summary = this.reportHistory.find((r) => r.report_id === reportId);
            const resp = await fetch(`/api/llm/report/by-id/${reportId}`);
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(data.detail || `Failed to load report ${reportId}`);
            return {
                source: 'saved_report',
                label: summary ? `Saved #${reportId}` : `Report #${reportId}`,
                report_id: reportId,
                model: data.model_used,
                provider: null,
                temperature: null,
                llm_duration_seconds: data.llm_duration_seconds,
                prompt_tokens: data.prompt_tokens,
                completion_tokens: data.completion_tokens,
                cost_usd: data.cost_usd,
                focus_mode: data.focus_mode,
                generated_at: data.generated_at,
                content: data.report_content || '',
            };
        }
        const pooled = this.packagePool.get(key);
        if (pooled) return { ...pooled };
        throw new Error(`Unknown selection: ${key}`);
    }

    async _resolvePromptForPackage(fileId) {
        if (this.lastCompareData?.prompt_text) {
            return {
                prompt_text: this.lastCompareData.prompt_text,
                est_tokens: this.lastCompareData.prompt_est_tokens,
                context_stats: this.lastCompareData.context_stats,
                compare_options: this.lastCompareData.compare_options,
                note: 'Prompt from the most recent compare run.',
            };
        }
        if (this._lastPromptText) {
            return {
                prompt_text: this._lastPromptText,
                est_tokens: this.lastPreviewMeta?.est_tokens,
                context_stats: this.lastPreviewMeta?.context_stats,
                preview_options: {
                    quick: this.lastPreviewMeta?.quick,
                    web_search: this.lastPreviewMeta?.web_search,
                    focus_mode: this.lastPreviewMeta?.focus_mode,
                },
                note: 'Prompt from the most recent preview in this session.',
            };
        }
        const resp = await fetch(`/api/llm/report/${fileId}/prompt-preview`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                quick: document.getElementById('plCompareQuick')?.checked ?? false,
                web_search: document.getElementById('plCompareWebSearch')?.checked || false,
                focus_mode: this._focusModeValue(),
                include_chart: false,
                fetch_external: false,
            }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(data.detail || 'Could not build prompt for package');
        return {
            prompt_text: data.prompt_text,
            est_tokens: data.est_tokens,
            context_stats: data.context_stats,
            note: 'Prompt reconstructed at export time — may differ from original generation.',
        };
    }

    async exportAnalysisPackage() {
        if (this.packageSelection.length !== 2) return;
        const fileId = this.getFileId();
        if (!fileId) {
            alert('No file loaded.');
            return;
        }

        try {
            const [aKey, bKey] = this.packageSelection;
            const [outputA, outputB] = await Promise.all([
                this._resolvePackageEntry(aKey),
                this._resolvePackageEntry(bKey),
            ]);
            const prompt = await this._resolvePromptForPackage(fileId);

            const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
            const pkg = {
                exported_at: new Date().toISOString(),
                file_id: fileId,
                package_type: 'prompt_lab_analysis',
                prompt,
                output_a: outputA,
                output_b: outputB,
                selection_keys: [aKey, bKey],
            };

            const json = JSON.stringify(pkg, null, 2);
            const filename = `prompt-lab-${fileId}-${stamp}.json`;

            if (window.pywebview?.api?.save_file) {
                const ok = await window.pywebview.api.save_file(filename, json);
                if (ok) return;
            }

            const blob = new Blob([json], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            a.click();
            URL.revokeObjectURL(url);
        } catch (e) {
            alert(`Export failed: ${e.message}`);
        }
    }

    renderCompareResults(data) {
        const cards = [];
        cards.push(this.renderResultCard('Baseline', data.baseline, true, 'compare-baseline'));
        (data.variants || []).forEach((v, i) => {
            cards.push(this.renderResultCard(`Variant ${i + 1}`, v, false, `compare-variant-${i}`));
        });
        return `
            <div class="pl-meta-bar" style="margin-top:12px;">
                <span class="pl-meta-chip">Prompt ~${Number(data.prompt_est_tokens || 0).toLocaleString()} tokens</span>
            </div>
            <div class="pl-results">${cards.join('')}</div>
        `;
    }

    renderResultCard(label, result, isBaseline, packKey) {
        if (!result) return '';
        const checked = this.packageSelection.includes(packKey) ? 'checked' : '';
        const selectedClass = checked ? ' pack-selected' : '';
        if (result.error) {
            return `
                <div class="pl-result-card${isBaseline ? ' baseline' : ''}${selectedClass}" data-pack-key="${packKey}">
                    <div class="pl-result-head">${this.escapeHtml(label)} — ${this.escapeHtml(result.provider || '')}</div>
                    <div class="pl-error">${this.escapeHtml(result.error)}</div>
                </div>
            `;
        }
        const excerpt = result.content || result.content_excerpt || '';
        return `
            <div class="pl-result-card${isBaseline ? ' baseline' : ''}${selectedClass}" data-pack-key="${packKey}">
                <div class="pl-result-head">
                    ${this.escapeHtml(label)} — ${this.escapeHtml(result.provider || '')}
                    ${result.model ? `<span class="pl-meta-chip">${this.escapeHtml(result.model)}</span>` : ''}
                    <span class="pl-meta-chip">T=${result.temperature ?? '?'}</span>
                    <label class="pl-result-pack-label">
                        <input type="checkbox" class="pl-compare-pack-cb" data-pack-key="${packKey}" ${checked}>
                        Include in package
                    </label>
                </div>
                <div class="pl-result-stats">
                    <span>${result.llm_duration_seconds != null ? `${result.llm_duration_seconds}s` : '—'}</span>
                    <span>${result.prompt_tokens || 0} in / ${result.completion_tokens || 0} out</span>
                    <span>$${Number(result.cost_usd || 0).toFixed(4)}</span>
                    ${result.grade ? `<span class="pl-meta-chip${result.grade.passed ? '' : ' pl-grade-fail'}">Grade ${Math.round((result.grade.normalized_score || 0) * 100)}%</span>` : ''}
                </div>
                <div class="pl-result-excerpt">${this.escapeHtml(excerpt)}</div>
            </div>
        `;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }
}

window.promptLabModal = new PromptLabModal();
