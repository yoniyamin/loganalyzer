/**
 * Quick Patterns — modal CRUD, regex toolbox, SQLite persistence via API.
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'logAnalyzer_quickPatterns';
  const API_BASE = '/api/quick-patterns';

  const REGEX_TOOLS = [
    { token: '.', desc: 'Any character', example: 'Err.r → matches Error, Err0r' },
    { token: '\\d', desc: 'Digit (0–9)', example: 'latency \\d+\\.\\d+ sec → latency 1.25 sec' },
    { token: '\\w', desc: 'Word character', example: '\\w+_ERR → SQL_ERR, Task_ERR' },
    { token: '\\s', desc: 'Whitespace', example: 'Task\\s+Server\\s+Log → Task Server Log' },
    { token: '[]', desc: 'Character class', example: '[EW]: → ]W: warning or ]E: error', cursorOffset: -1 },
    { token: '*', desc: 'Zero or more', example: 'bulk.*apply → bulk_map apply, bulk apply' },
    { token: '+', desc: 'One or more', example: 'from seq \\d+ to → from seq 42 to' },
    { token: '?', desc: 'Optional', example: 'colo?ur → color, colour' },
    { token: '^', desc: 'Start of line', example: '^\\d{8}: → 20240315: at line start' },
    { token: '$', desc: 'End of line', example: 'finished\\.c:\\d+\\)$ → ...finished.c:2770)' },
    { token: '|', desc: 'Or / alternation', example: ']E:|]W:|]T: → error, warn, or trace' },
    { token: '()', desc: 'Capture group', example: "(table '[^']+)' → table 'dbo.orders'", cursorOffset: -1 },
    { token: '\\[', desc: 'Literal [', example: '\\[\\w+\\.c:\\d+\\] → [logger.c:2770]' },
  ];

  let presets = [];
  let editingId = null;
  let onPatternClick = null;
  let getCurrentFileId = null;
  let searchPatternInLog = null;
  let cachedFileId = null;

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function insertAtCursor(textarea, text, cursorOffset = 0) {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const value = textarea.value;
    textarea.value = value.slice(0, start) + text + value.slice(end);
    const pos = Math.max(0, start + text.length + cursorOffset);
    textarea.setSelectionRange(pos, pos);
    textarea.focus();
  }

  function setTestResult(html, className) {
    const resultEl = document.getElementById('presetTestResult');
    if (!resultEl) return;
    resultEl.innerHTML = html;
    resultEl.className = `preset-test-result${className ? ' ' + className : ''}`;
  }

  function clearTestResult() {
    setTestResult('', '');
  }

  function resolveFileId() {
    if (getCurrentFileId) {
      const id = getCurrentFileId();
      if (id != null && id !== '') return id;
    }
    return cachedFileId;
  }

  function extractMatches(data) {
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.matches)) return data.matches;
    if (data && Array.isArray(data.results)) return data.results;
    return [];
  }

  function normalizeMatch(raw) {
    if (!raw || typeof raw !== 'object') return null;
    const line = raw.line ?? raw.line_number ?? raw.lineNumber;
    const text = raw.text ?? raw.content ?? raw.line_text;
    if (text == null || String(text) === '') return null;
    return { line: line != null ? Number(line) : 0, text: String(text) };
  }

  function truncateLine(text, maxLen = 220) {
    if (text.length <= maxLen) return text;
    return text.slice(0, maxLen) + '…';
  }

  function showMatchPreview(match, pattern) {
    const lineNum = match.line + 1;
    const previewText = truncateLine(match.text);
    const highlighted = highlightMatch(previewText, pattern);
    setTestResult(`
      <div class="preset-test-summary">Match found in current log</div>
      <div class="preset-test-preview">
        <span class="preset-test-line-num">Line ${lineNum}:</span>
        <span class="preset-test-line-text">${highlighted}</span>
      </div>
    `, 'success');
  }

  function highlightMatch(text, pattern) {
    try {
      const regex = new RegExp(pattern, 'i');
      const match = regex.exec(text);
      if (!match) return escapeHtml(text);
      const before = text.slice(0, match.index);
      const matched = match[0];
      const after = text.slice(match.index + matched.length);
      return (
        escapeHtml(before) +
        '<mark class="preset-match-highlight">' + escapeHtml(matched) + '</mark>' +
        escapeHtml(after)
      );
    } catch (_) {
      return escapeHtml(text);
    }
  }

  async function fetchPresets() {
    const res = await fetch(API_BASE);
    if (!res.ok) throw new Error('Failed to load patterns');
    return res.json();
  }

  async function migrateFromLocalStorage() {
    try {
      const legacy = localStorage.getItem(STORAGE_KEY);
      if (!legacy) return;
      const parsed = JSON.parse(legacy);
      if (!Array.isArray(parsed)) return;

      const existingPatterns = new Set(presets.map(p => p.pattern));
      for (const item of parsed) {
        if (!item.pattern || !item.label || item.builtin) continue;
        if (existingPatterns.has(item.pattern)) continue;
        await fetch(API_BASE, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            label: item.label,
            pattern: item.pattern,
            description: item.description || null,
          }),
        });
      }
      localStorage.removeItem(STORAGE_KEY);
    } catch (_) { /* ignore migration errors */ }
  }

  async function loadPresets() {
    presets = await fetchPresets();
    await migrateFromLocalStorage();
    presets = await fetchPresets();
  }

  function renderPresetTags() {
    const container = document.getElementById('presetTags');
    if (!container) return;

    container.querySelectorAll('.preset-tag:not(.add-preset-btn)').forEach(el => el.remove());

    presets.forEach(preset => {
      const tag = document.createElement('span');
      tag.className = 'preset-tag';
      tag.dataset.pattern = preset.pattern;
      tag.dataset.label = preset.label;
      tag.dataset.id = String(preset.id);
      tag.textContent = preset.label;
      tag.title = preset.description || preset.pattern;
      tag.addEventListener('click', () => {
        if (onPatternClick) onPatternClick(preset.pattern, preset.label);
      });
      container.appendChild(tag);
    });
  }

  function renderToolbox() {
    const toolbox = document.getElementById('regexToolbox');
    const patternInput = document.getElementById('presetPatternInput');
    if (!toolbox || !patternInput) return;

    toolbox.innerHTML = '';
    REGEX_TOOLS.forEach(tool => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'regex-tool-btn';
      btn.title = tool.example ? `${tool.desc} — ${tool.example}` : tool.desc;
      btn.innerHTML = `
        <span class="regex-tool-token">${escapeHtml(tool.token)}</span>
        <span class="regex-tool-desc">
          <span class="regex-tool-desc-label">${escapeHtml(tool.desc)}</span>
          ${tool.example ? `<span class="regex-tool-example">${escapeHtml(tool.example)}</span>` : ''}
        </span>
      `;
      btn.addEventListener('click', () => {
        insertAtCursor(patternInput, tool.token, tool.cursorOffset || 0);
      });
      toolbox.appendChild(btn);
    });
  }

  function renderManageTable() {
    const tbody = document.getElementById('presetTableBody');
    if (!tbody) return;

    if (presets.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" style="color:#6b7280;text-align:center;padding:20px;">No patterns yet.</td></tr>';
      return;
    }

    tbody.innerHTML = presets.map(p => `
      <tr data-id="${p.id}">
        <td class="preset-table-label">${escapeHtml(p.label)}</td>
        <td class="preset-table-pattern" title="${escapeHtml(p.pattern)}">${escapeHtml(p.pattern)}</td>
        <td>
          <div class="preset-table-actions">
            <button type="button" class="preset-action-btn" data-action="edit" data-id="${p.id}">Edit</button>
            <button type="button" class="preset-action-btn" data-action="duplicate" data-id="${p.id}">Duplicate</button>
            <button type="button" class="preset-action-btn danger" data-action="delete" data-id="${p.id}">Delete</button>
          </div>
        </td>
      </tr>
    `).join('');
  }

  function switchTab(tabName) {
    document.querySelectorAll('.preset-modal-tab').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.presetTab === tabName);
    });
    document.getElementById('presetEditPanel').classList.toggle('active', tabName === 'edit');
    document.getElementById('presetManagePanel').classList.toggle('active', tabName === 'manage');
    document.getElementById('savePresetBtn').style.display = tabName === 'edit' ? '' : 'none';

    if (tabName === 'manage') renderManageTable();
  }

  function clearEditForm() {
    editingId = null;
    document.getElementById('presetLabelInput').value = '';
    document.getElementById('presetPatternInput').value = '';
    clearTestResult();
    document.getElementById('savePresetBtn').textContent = 'Save Pattern';
  }

  function openModal(tab = 'edit', editId = null) {
    const modal = document.getElementById('presetPatternsModal');
    if (!modal) return;

    clearEditForm();
    switchTab(tab);

    if (editId != null) {
      const preset = presets.find(p => p.id === Number(editId));
      if (preset) {
        editingId = preset.id;
        document.getElementById('presetLabelInput').value = preset.label;
        document.getElementById('presetPatternInput').value = preset.pattern;
        document.getElementById('savePresetBtn').textContent = 'Update Pattern';
        switchTab('edit');
      }
    }

    modal.style.display = 'flex';
  }

  function openModalWithPattern(pattern, suggestedLabel = '') {
    openModal('edit');
    document.getElementById('presetPatternInput').value = pattern || '';
    document.getElementById('presetLabelInput').value = suggestedLabel || '';
    document.getElementById('savePresetBtn').textContent = 'Save Pattern';
    editingId = null;
  }

  function closeModal() {
    const modal = document.getElementById('presetPatternsModal');
    if (modal) modal.style.display = 'none';
    clearEditForm();
  }

  function apiErrorMessage(errBody, fallback) {
    if (!errBody || !errBody.detail) return fallback;
    if (typeof errBody.detail === 'string') return errBody.detail;
    return Array.isArray(errBody.detail)
      ? errBody.detail.map(d => d.msg || String(d)).join(', ')
      : fallback;
  }

  function validatePatternSyntax(pattern) {
    try {
      new RegExp(pattern);
      return { valid: true };
    } catch (err) {
      return { valid: false, error: err.message };
    }
  }

  async function testPattern() {
    const pattern = document.getElementById('presetPatternInput').value.trim();

    if (!pattern) {
      setTestResult('Enter a pattern to test.', 'error');
      return;
    }

    const syntax = validatePatternSyntax(pattern);
    if (!syntax.valid) {
      setTestResult(`Invalid regex: ${escapeHtml(syntax.error)}`, 'error');
      return;
    }

    const fileId = resolveFileId();
    if (!fileId) {
      setTestResult(
        'Pattern syntax is valid. Open a log file to test against log content.',
        'success'
      );
      return;
    }

    setTestResult('Testing against log…', '');

    try {
      let rawMatch = null;

      if (searchPatternInLog) {
        rawMatch = await searchPatternInLog(pattern);
      } else {
        const res = await fetch(
          `/api/files/${fileId}/search?q=${encodeURIComponent(pattern)}&limit=1`
        );
        if (!res.ok) {
          const errBody = await res.json().catch(() => ({}));
          throw new Error(apiErrorMessage(errBody, 'Search request failed'));
        }
        const matches = extractMatches(await res.json());
        rawMatch = matches[0] || null;
      }

      const match = normalizeMatch(rawMatch);
      if (!match) {
        setTestResult('Valid regex — no matches in current log.', 'success');
        return;
      }

      showMatchPreview(match, pattern);
    } catch (err) {
      setTestResult(`Search failed: ${escapeHtml(err.message)}`, 'error');
    }
  }

  async function savePattern() {
    const label = document.getElementById('presetLabelInput').value.trim();
    const pattern = document.getElementById('presetPatternInput').value.trim();

    if (!label) {
      setTestResult('Label is required.', 'error');
      return;
    }
    if (!pattern) {
      setTestResult('Pattern is required.', 'error');
      return;
    }

    const syntax = validatePatternSyntax(pattern);
    if (!syntax.valid) {
      setTestResult(`Invalid regex: ${escapeHtml(syntax.error)}`, 'error');
      return;
    }

    try {
      if (editingId != null) {
        const res = await fetch(`${API_BASE}/${editingId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ label, pattern }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(apiErrorMessage(err, 'Update failed'));
        }
      } else {
        const res = await fetch(API_BASE, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ label, pattern }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(apiErrorMessage(err, 'Save failed'));
        }
      }

      await loadPresets();
      renderPresetTags();
      closeModal();
    } catch (err) {
      setTestResult(escapeHtml(err.message), 'error');
    }
  }

  async function duplicatePattern(id) {
    const source = presets.find(p => p.id === Number(id));
    if (!source) return;

    let copyLabel = `${source.label} (copy)`;
    let suffix = 2;
    while (presets.some(p => p.label === copyLabel)) {
      copyLabel = `${source.label} (copy ${suffix++})`;
    }

    try {
      const res = await fetch(API_BASE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          label: copyLabel,
          pattern: source.pattern,
          description: source.description,
        }),
      });
      if (!res.ok) throw new Error('Duplicate failed');
      await loadPresets();
      renderPresetTags();
      renderManageTable();
    } catch (err) {
      if (window.showAlert) window.showAlert('Error', err.message);
    }
  }

  function deletePattern(id) {
    const preset = presets.find(p => p.id === Number(id));
    if (!preset) return;

    const doDelete = async () => {
      try {
        const res = await fetch(`${API_BASE}/${preset.id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Delete failed');
        await loadPresets();
        renderPresetTags();
        renderManageTable();
      } catch (err) {
        if (window.showAlert) window.showAlert('Error', err.message);
      }
    };

    if (window.showModal) {
      window.showModal(
        'Delete Pattern',
        `<p>Remove pattern "<strong>${escapeHtml(preset.label)}</strong>"?</p>`,
        doDelete,
        { confirmText: 'Delete', danger: true }
      );
    } else if (window.confirm(`Remove pattern "${preset.label}"?`)) {
      doDelete();
    }
  }

  function bindEvents() {
    document.getElementById('addPresetBtn')?.addEventListener('click', () => openModal('edit'));
    document.getElementById('managePresetsBtn')?.addEventListener('click', () => openModal('manage'));
    document.getElementById('closePresetModal')?.addEventListener('click', closeModal);
    document.getElementById('cancelPresetModal')?.addEventListener('click', closeModal);
    document.getElementById('savePresetBtn')?.addEventListener('click', savePattern);
    document.getElementById('presetTestBtn')?.addEventListener('click', testPattern);

    document.querySelectorAll('.preset-modal-tab').forEach(btn => {
      btn.addEventListener('click', () => switchTab(btn.dataset.presetTab));
    });

    document.getElementById('presetTableBody')?.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-action]');
      if (!btn) return;
      const { action, id } = btn.dataset;
      if (action === 'edit') openModal('edit', id);
      else if (action === 'duplicate') duplicatePattern(id);
      else if (action === 'delete') deletePattern(id);
    });

    document.getElementById('presetPatternsModal')?.addEventListener('click', (e) => {
      if (e.target.id === 'presetPatternsModal') closeModal();
    });
  }

  function bindFileEvents() {
    document.addEventListener('fileLoaded', (e) => {
      cachedFileId = e.detail?.fileId ?? null;
    });
    document.addEventListener('fileClosed', () => {
      cachedFileId = null;
    });
  }

  window.PresetPatterns = {
    async init(options = {}) {
      onPatternClick = options.onPatternClick || null;
      getCurrentFileId = options.getCurrentFileId || null;
      searchPatternInLog = options.searchPatternInLog || null;
      bindFileEvents();
      if (getCurrentFileId) {
        cachedFileId = getCurrentFileId();
      }
      renderToolbox();
      bindEvents();
      try {
        await loadPresets();
        renderPresetTags();
      } catch (err) {
        console.error('Failed to load quick patterns:', err);
        if (window.showAlert) {
          window.showAlert('Quick Patterns', 'Could not load saved patterns from the server.');
        }
      }
    },

    getLabelForPattern(pattern) {
      const preset = presets.find(p => p.pattern === pattern);
      return preset ? preset.label : null;
    },

    openModalWithPattern,

    async reload() {
      await loadPresets();
      renderPresetTags();
      renderManageTable();
    },
  };
})();
