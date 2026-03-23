/**
 * Log Colors Module
 * Handles syntax highlighting for log lines with customizable color schemes.
 */

(function() {
    'use strict';

    // Default color schemes
    const DEFAULT_SCHEMES = {
        'qlik': {
            name: 'Qlik Default',
            colors: {
                thread: '#60a5fa',
                timestamp: '#6b7280',
                component: '#a855f7',
                quoted: '#fbbf24',
                sourceRef: '#4b5563',
                levelInfo: '#10b981',
                levelWarning: '#f59e0b',
                levelError: '#ef4444',
                levelTrace: '#8b5cf6',
                levelVerbose: '#6b7280',
                number: '#f472b6',
                keyword: '#22d3ee',
                path: '#a3e635'
            }
        },
        'dark-contrast': {
            name: 'High Contrast Dark',
            colors: {
                thread: '#38bdf8',
                timestamp: '#94a3b8',
                component: '#c084fc',
                quoted: '#fde047',
                sourceRef: '#64748b',
                levelInfo: '#4ade80',
                levelWarning: '#fb923c',
                levelError: '#f87171',
                levelTrace: '#a78bfa',
                levelVerbose: '#94a3b8',
                number: '#f9a8d4',
                keyword: '#67e8f9',
                path: '#bef264'
            }
        },
        'solarized': {
            name: 'Solarized Dark',
            colors: {
                thread: '#268bd2',
                timestamp: '#839496',
                component: '#6c71c4',
                quoted: '#b58900',
                sourceRef: '#586e75',
                levelInfo: '#859900',
                levelWarning: '#cb4b16',
                levelError: '#dc322f',
                levelTrace: '#2aa198',
                levelVerbose: '#839496',
                number: '#d33682',
                keyword: '#2aa198',
                path: '#859900'
            }
        },
        'monokai': {
            name: 'Monokai',
            colors: {
                thread: '#66d9ef',
                timestamp: '#75715e',
                component: '#ae81ff',
                quoted: '#e6db74',
                sourceRef: '#75715e',
                levelInfo: '#a6e22e',
                levelWarning: '#fd971f',
                levelError: '#f92672',
                levelTrace: '#ae81ff',
                levelVerbose: '#75715e',
                number: '#ae81ff',
                keyword: '#66d9ef',
                path: '#a6e22e'
            }
        },
        'dracula': {
            name: 'Dracula',
            colors: {
                thread: '#8be9fd',
                timestamp: '#6272a4',
                component: '#bd93f9',
                quoted: '#f1fa8c',
                sourceRef: '#6272a4',
                levelInfo: '#50fa7b',
                levelWarning: '#ffb86c',
                levelError: '#ff5555',
                levelTrace: '#bd93f9',
                levelVerbose: '#6272a4',
                number: '#ff79c6',
                keyword: '#8be9fd',
                path: '#50fa7b'
            }
        },
        'minimal': {
            name: 'Minimal',
            colors: {
                thread: '#9ca3af',
                timestamp: '#6b7280',
                component: '#d1d5db',
                quoted: '#e5e7eb',
                sourceRef: '#4b5563',
                levelInfo: '#6b7280',
                levelWarning: '#f59e0b',
                levelError: '#ef4444',
                levelTrace: '#6b7280',
                levelVerbose: '#4b5563',
                number: '#9ca3af',
                keyword: '#9ca3af',
                path: '#9ca3af'
            }
        }
    };

    // Current color settings
    let currentColors = { ...DEFAULT_SCHEMES['qlik'].colors };
    let syntaxHighlightingEnabled = true;
    let customThemes = {};

    // Storage keys
    const STORAGE_KEY_COLORS = 'logAnalyzer_colorScheme';
    const STORAGE_KEY_CUSTOM_THEMES = 'logAnalyzer_customThemes';
    const STORAGE_KEY_ENABLED = 'logAnalyzer_syntaxEnabled';

    // Track if settings have been loaded
    let settingsLoaded = false;

    // Initialize from backend API (with localStorage fallback)
    function loadSettings() {
        // First try to load from backend
        fetch('/api/settings/color_scheme')
            .then(res => res.json())
            .then(data => {
                if (data.value && data.value.colors) {
                    // Merge with defaults to ensure all color keys exist
                    currentColors = { ...DEFAULT_SCHEMES['qlik'].colors, ...data.value.colors };
                    if (data.value.customThemes) {
                        customThemes = data.value.customThemes;
                    }
                    if (data.value.syntaxEnabled !== undefined) {
                        syntaxHighlightingEnabled = data.value.syntaxEnabled;
                    }
                    applyColorsToCSS();
                    onSettingsLoaded();
                } else {
                    // Fallback to localStorage
                    loadFromLocalStorage();
                }
            })
            .catch(() => {
                // Fallback to localStorage on error
                loadFromLocalStorage();
            });
    }
    
    function loadFromLocalStorage() {
        try {
            const savedColors = localStorage.getItem(STORAGE_KEY_COLORS);
            if (savedColors) {
                // Merge with defaults to ensure all color keys exist
                currentColors = { ...DEFAULT_SCHEMES['qlik'].colors, ...JSON.parse(savedColors) };
            }

            const savedThemes = localStorage.getItem(STORAGE_KEY_CUSTOM_THEMES);
            if (savedThemes) {
                customThemes = JSON.parse(savedThemes);
            }

            const savedEnabled = localStorage.getItem(STORAGE_KEY_ENABLED);
            if (savedEnabled !== null) {
                syntaxHighlightingEnabled = JSON.parse(savedEnabled);
            }
        } catch (e) {
            console.error('Failed to load color settings from localStorage:', e);
        }

        applyColorsToCSS();
        onSettingsLoaded();
    }
    
    // Called after settings are loaded - refresh any displayed log lines
    function onSettingsLoaded() {
        settingsLoaded = true;
        // Refresh log display if there are already lines loaded
        if (window.refreshLogDisplay) {
            window.refreshLogDisplay();
        }
    }

    // Save settings to backend API (and localStorage as backup)
    function saveSettings() {
        const settingsData = {
            colors: currentColors,
            customThemes: customThemes,
            syntaxEnabled: syntaxHighlightingEnabled
        };
        
        // Save to backend
        fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                key: 'color_scheme',
                value: settingsData
            })
        }).catch(err => {
            console.error('Failed to save settings to backend:', err);
        });
        
        // Also save to localStorage as backup
        try {
            localStorage.setItem(STORAGE_KEY_COLORS, JSON.stringify(currentColors));
            localStorage.setItem(STORAGE_KEY_CUSTOM_THEMES, JSON.stringify(customThemes));
            localStorage.setItem(STORAGE_KEY_ENABLED, JSON.stringify(syntaxHighlightingEnabled));
        } catch (e) {
            console.error('Failed to save color settings to localStorage:', e);
        }
    }

    // Apply colors to CSS variables
    function applyColorsToCSS() {
        const root = document.documentElement;
        root.style.setProperty('--log-thread-color', currentColors.thread);
        root.style.setProperty('--log-timestamp-color', currentColors.timestamp);
        root.style.setProperty('--log-component-color', currentColors.component);
        root.style.setProperty('--log-quoted-color', currentColors.quoted);
        root.style.setProperty('--log-source-ref-color', currentColors.sourceRef);
        root.style.setProperty('--log-level-info-color', currentColors.levelInfo);
        root.style.setProperty('--log-level-warning-color', currentColors.levelWarning);
        root.style.setProperty('--log-level-error-color', currentColors.levelError);
        root.style.setProperty('--log-level-trace-color', currentColors.levelTrace);
        root.style.setProperty('--log-level-verbose-color', currentColors.levelVerbose || currentColors.timestamp);
        root.style.setProperty('--log-number-color', currentColors.number);
        root.style.setProperty('--log-keyword-color', currentColors.keyword);
        root.style.setProperty('--log-path-color', currentColors.path);

        // Warning/Error backgrounds with transparency
        root.style.setProperty('--log-level-warning-bg', hexToRgba(currentColors.levelWarning, 0.1));
        root.style.setProperty('--log-level-error-bg', hexToRgba(currentColors.levelError, 0.15));
    }

    // Convert hex to rgba
    function hexToRgba(hex, alpha) {
        const r = parseInt(hex.slice(1, 3), 16);
        const g = parseInt(hex.slice(3, 5), 16);
        const b = parseInt(hex.slice(5, 7), 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    // Highlight a log line with syntax colors
    function highlightLogLine(text) {
        if (!syntaxHighlightingEnabled) {
            return escapeHtml(text);
        }

        // Trim trailing whitespace that might break matching
        const trimmedText = text.trimEnd();

        // Log line pattern: THREAD: TIMESTAMP [COMPONENT    ]LEVEL:  MESSAGE
        // Example: 00012300: 2025-11-19T17:19:53 [AT_GLOBAL       ]I:  Task Server Log...  (at_logger.c:2770)
        // Timestamp can have optional microseconds: 2025-12-03T10:42:49:879024
        // Made regex more flexible - handles both hex and decimal thread IDs
        const logLineRegex = /^(\d{8}):\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?::\d+)?)\s+\[([^\]]+)\]([IEWTV]):\s*(.*)/;
        const match = trimmedText.match(logLineRegex);

        if (match) {
            const [, thread, timestamp, component, level, message] = match;

            // Build highlighted line using current colors
            const parts = [];
            parts.push(`<span style="color:${currentColors.thread};font-weight:500">${escapeHtml(thread)}:</span>`);
            parts.push(` <span style="color:${currentColors.timestamp}">${escapeHtml(timestamp)}</span>`);
            parts.push(` <span style="color:${currentColors.timestamp}">[</span><span style="color:${currentColors.component};font-weight:600">${escapeHtml(component)}</span><span style="color:${currentColors.timestamp}">]</span>`);
            
            // Level with color based on type
            const levelColors = { 
                i: currentColors.levelInfo, 
                w: currentColors.levelWarning, 
                e: currentColors.levelError, 
                t: currentColors.levelTrace,
                v: currentColors.levelVerbose || currentColors.timestamp
            };
            const levelColor = levelColors[level.toLowerCase()] || currentColors.timestamp;
            parts.push(`<span style="color:${levelColor};font-weight:bold">${level}:</span>`);
            parts.push('  ');

            // Process message content
            if (message) {
                parts.push(highlightMessageContent(message));
            }

            return parts.join('');
        } else {
            // Fallback: try to highlight parts that we recognize
            return highlightPartialLine(text);
        }
    }

    // Highlight message content (quoted strings, source references, etc.)
    function highlightMessageContent(message) {
        let result = escapeHtml(message);

        // Highlight quoted strings: 'value' - do this FIRST before adding any HTML
        result = result.replace(/'([^']+)'/g,
            `<span style="color:${currentColors.quoted}">'$1'</span>`);

        // Highlight source file references at the end: (filename.c:1234)
        result = result.replace(/\(([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z]+:\d+)\)\s*$/,
            `<span style="color:${currentColors.sourceRef};font-style:italic">($1)</span>`);

        return result;
    }

    // Highlight partial/non-standard lines
    function highlightPartialLine(text) {
        let result = escapeHtml(text);

        // Try to highlight timestamps (with optional microseconds like :879024)
        result = result.replace(/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?::\d+)?)/g,
            `<span style="color:${currentColors.timestamp}">$1</span>`);

        // Highlight thread IDs (can be decimal or hex)
        result = result.replace(/^(\d{8}):/,
            `<span style="color:${currentColors.thread};font-weight:500">$1:</span>`);

        // Highlight quoted strings
        result = result.replace(/'([^']+)'/g,
            `<span style="color:${currentColors.quoted}">'$1'</span>`);

        // Highlight source references
        result = result.replace(/\(([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z]+:\d+)\)/g,
            `<span style="color:${currentColors.sourceRef};font-style:italic">($1)</span>`);

        return result;
    }

    // Escape HTML characters
    function escapeHtml(text) {
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // Create the color schema modal HTML
    function createColorSchemaModal() {
        const modalHtml = `
            <div id="colorSchemaOverlay" class="modal-overlay" style="display: none;">
                <div class="modal-content color-schema-modal">
                    <h3>
                        <svg width="20" height="20" viewBox="0 0 16 16" fill="#a855f7">
                            <path d="M8 5a1.5 1.5 0 100-3 1.5 1.5 0 000 3zm4 3a1.5 1.5 0 100-3 1.5 1.5 0 000 3zM5.5 7a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zm.5 6a1.5 1.5 0 100-3 1.5 1.5 0 000 3z"/>
                            <path d="M16 8c0 3.15-1.866 2.585-3.567 2.07C11.42 9.763 10.465 9.473 10 10c-.603.683-.475 1.819-.351 2.92C9.826 14.495 9.996 16 8 16a8 8 0 118-8zm-8 7c.611 0 .654-.171.655-.176.078-.146.124-.464.07-1.119-.014-.168-.037-.37-.061-.591-.052-.464-.112-1.005-.118-1.462-.01-.707.083-1.61.704-2.314.369-.417.845-.578 1.272-.618.404-.038.812.026 1.16.104.343.077.702.186 1.025.284l.028.008c.346.105.658.199.953.266.653.148.904.083.991.024C14.717 9.38 15 9.161 15 8a7 7 0 10-7 7z"/>
                        </svg>
                        Log Color Schema
                    </h3>

                    <div class="preset-themes-section">
                        <h4>Preset Themes</h4>
                        <div class="preset-themes-grid" id="presetThemesGrid"></div>
                    </div>

                    <div class="color-preview-section">
                        <div class="preview-title">Preview</div>
                        <div id="colorPreview" class="preview-log-line"></div>
                    </div>

                    <div class="color-schema-grid">
                        <div class="color-schema-section">
                            <h4>Log Structure</h4>
                            <div class="color-item">
                                <span class="color-item-label">
                                    <span class="color-item-preview" id="previewThread"></span>
                                    Thread ID
                                </span>
                                <input type="color" id="colorThread" data-key="thread">
                            </div>
                            <div class="color-item">
                                <span class="color-item-label">
                                    <span class="color-item-preview" id="previewTimestamp"></span>
                                    Timestamp
                                </span>
                                <input type="color" id="colorTimestamp" data-key="timestamp">
                            </div>
                            <div class="color-item">
                                <span class="color-item-label">
                                    <span class="color-item-preview" id="previewComponent"></span>
                                    Component
                                </span>
                                <input type="color" id="colorComponent" data-key="component">
                            </div>
                            <div class="color-item">
                                <span class="color-item-label">
                                    <span class="color-item-preview" id="previewQuoted"></span>
                                    Quoted Text
                                </span>
                                <input type="color" id="colorQuoted" data-key="quoted">
                            </div>
                            <div class="color-item">
                                <span class="color-item-label">
                                    <span class="color-item-preview" id="previewSourceRef"></span>
                                    Source Reference
                                </span>
                                <input type="color" id="colorSourceRef" data-key="sourceRef">
                            </div>
                        </div>

                        <div class="color-schema-section">
                            <h4>Log Levels</h4>
                            <div class="color-item">
                                <span class="color-item-label">
                                    <span class="color-item-preview" id="previewLevelInfo"></span>
                                    Info (I:)
                                </span>
                                <input type="color" id="colorLevelInfo" data-key="levelInfo">
                            </div>
                            <div class="color-item">
                                <span class="color-item-label">
                                    <span class="color-item-preview" id="previewLevelWarning"></span>
                                    Warning (W:)
                                </span>
                                <input type="color" id="colorLevelWarning" data-key="levelWarning">
                            </div>
                            <div class="color-item">
                                <span class="color-item-label">
                                    <span class="color-item-preview" id="previewLevelError"></span>
                                    Error (E:)
                                </span>
                                <input type="color" id="colorLevelError" data-key="levelError">
                            </div>
                            <div class="color-item">
                                <span class="color-item-label">
                                    <span class="color-item-preview" id="previewLevelTrace"></span>
                                    Trace (T:)
                                </span>
                                <input type="color" id="colorLevelTrace" data-key="levelTrace">
                            </div>
                            <div class="color-item">
                                <span class="color-item-label">
                                    <span class="color-item-preview" id="previewLevelVerbose"></span>
                                    Verbose (V:)
                                </span>
                                <input type="color" id="colorLevelVerbose" data-key="levelVerbose">
                            </div>
                        </div>
                    </div>

                    <div class="preset-themes-section">
                        <h4>Custom Themes</h4>
                        <div id="customThemesList" class="preset-themes-grid"></div>
                        <div class="save-theme-row">
                            <input type="text" id="newThemeName" placeholder="Enter theme name...">
                            <button class="save-theme-btn" id="saveThemeBtn">Save Current</button>
                        </div>
                    </div>

                    <div class="color-schema-actions">
                        <div class="color-schema-actions-left">
                            <button class="reset-colors-btn" id="resetColorsBtn">Reset to Default</button>
                            <label class="syntax-toggle">
                                <input type="checkbox" id="syntaxHighlightToggle" checked>
                                <span>Enable Syntax Highlighting</span>
                            </label>
                        </div>
                        <div class="modal-buttons">
                            <button id="colorSchemaCancel" class="modal-btn cancel-btn">Cancel</button>
                            <button id="colorSchemaApply" class="modal-btn save-btn">Apply</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Insert modal into the document
        document.body.insertAdjacentHTML('beforeend', modalHtml);

        // Setup event listeners
        setupModalEventListeners();
    }

    // Setup modal event listeners
    function setupModalEventListeners() {
        const overlay = document.getElementById('colorSchemaOverlay');
        const cancelBtn = document.getElementById('colorSchemaCancel');
        const applyBtn = document.getElementById('colorSchemaApply');
        const resetBtn = document.getElementById('resetColorsBtn');
        const saveThemeBtn = document.getElementById('saveThemeBtn');
        const syntaxToggle = document.getElementById('syntaxHighlightToggle');

        // Color inputs
        const colorInputs = overlay.querySelectorAll('input[type="color"]');
        colorInputs.forEach(input => {
            input.addEventListener('input', (e) => {
                const key = e.target.dataset.key;
                currentColors[key] = e.target.value;
                updatePreviewColors();
                updateColorPreview();
            });
        });

        // Cancel button
        cancelBtn.addEventListener('click', closeColorSchemaModal);

        // Apply button
        applyBtn.addEventListener('click', () => {
            // Apply colors to CSS and save
            applyColorsToCSS();
            saveSettings();
            
            // Show visual feedback
            const originalText = applyBtn.textContent;
            applyBtn.textContent = 'Saving...';
            applyBtn.disabled = true;
            
            // Brief delay for visual feedback, then close and refresh
            setTimeout(() => {
                closeColorSchemaModal();
                applyBtn.textContent = originalText;
                applyBtn.disabled = false;
                
                // Re-render log lines with new colors
                if (window.refreshLogDisplay) {
                    window.refreshLogDisplay();
                }
            }, 300);
        });

        // Reset button
        resetBtn.addEventListener('click', () => {
            currentColors = { ...DEFAULT_SCHEMES['qlik'].colors };
            populateColorInputs();
            updatePreviewColors();
            updateColorPreview();
        });

        // Save theme button
        saveThemeBtn.addEventListener('click', () => {
            const nameInput = document.getElementById('newThemeName');
            const name = nameInput.value.trim();
            if (name) {
                customThemes[name] = { ...currentColors };
                saveSettings();
                renderCustomThemes();
                nameInput.value = '';
            }
        });

        // Syntax toggle
        syntaxToggle.addEventListener('change', (e) => {
            syntaxHighlightingEnabled = e.target.checked;
        });

        // Close on overlay click
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                closeColorSchemaModal();
            }
        });

        // Escape key to close
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && overlay.style.display !== 'none') {
                closeColorSchemaModal();
            }
        });
    }

    // Open the modal
    function openColorSchemaModal() {
        const overlay = document.getElementById('colorSchemaOverlay');
        if (!overlay) {
            createColorSchemaModal();
        }

        // Populate preset themes
        renderPresetThemes();
        renderCustomThemes();

        // Populate current colors
        populateColorInputs();
        updatePreviewColors();
        updateColorPreview();

        // Set syntax toggle state
        document.getElementById('syntaxHighlightToggle').checked = syntaxHighlightingEnabled;

        document.getElementById('colorSchemaOverlay').style.display = 'flex';
    }

    // Close the modal
    function closeColorSchemaModal() {
        document.getElementById('colorSchemaOverlay').style.display = 'none';
    }

    // Populate color inputs with current values
    function populateColorInputs() {
        document.getElementById('colorThread').value = currentColors.thread;
        document.getElementById('colorTimestamp').value = currentColors.timestamp;
        document.getElementById('colorComponent').value = currentColors.component;
        document.getElementById('colorQuoted').value = currentColors.quoted;
        document.getElementById('colorSourceRef').value = currentColors.sourceRef;
        document.getElementById('colorLevelInfo').value = currentColors.levelInfo;
        document.getElementById('colorLevelWarning').value = currentColors.levelWarning;
        document.getElementById('colorLevelError').value = currentColors.levelError;
        document.getElementById('colorLevelTrace').value = currentColors.levelTrace;
        document.getElementById('colorLevelVerbose').value = currentColors.levelVerbose || currentColors.timestamp;
    }

    // Update preview color indicators
    function updatePreviewColors() {
        document.getElementById('previewThread').style.background = currentColors.thread;
        document.getElementById('previewTimestamp').style.background = currentColors.timestamp;
        document.getElementById('previewComponent').style.background = currentColors.component;
        document.getElementById('previewQuoted').style.background = currentColors.quoted;
        document.getElementById('previewSourceRef').style.background = currentColors.sourceRef;
        document.getElementById('previewLevelInfo').style.background = currentColors.levelInfo;
        document.getElementById('previewLevelWarning').style.background = currentColors.levelWarning;
        document.getElementById('previewLevelError').style.background = currentColors.levelError;
        document.getElementById('previewLevelTrace').style.background = currentColors.levelTrace;
        document.getElementById('previewLevelVerbose').style.background = currentColors.levelVerbose || currentColors.timestamp;
    }

    // Update the preview log line
    function updateColorPreview() {
        const preview = document.getElementById('colorPreview');
        const sampleLine = "00012300: 2025-11-19T17:19:53 [TARGET_APPLY    ]I:  Connected to server 'db-server.example.com' successfully.  (cloud_imp.c:5028)";

        // Apply temp colors for preview
        const tempRoot = document.createElement('div');
        tempRoot.style.cssText = `
            --log-thread-color: ${currentColors.thread};
            --log-timestamp-color: ${currentColors.timestamp};
            --log-component-color: ${currentColors.component};
            --log-quoted-color: ${currentColors.quoted};
            --log-source-ref-color: ${currentColors.sourceRef};
            --log-level-info-color: ${currentColors.levelInfo};
        `;

        preview.innerHTML = `
            <span style="color: ${currentColors.thread}; font-weight: 500;">00012300:</span>
            <span style="color: ${currentColors.timestamp};"> 2025-11-19T17:19:53</span>
            <span> [</span><span style="color: ${currentColors.component}; font-weight: 600;">TARGET_APPLY    </span><span>]</span>
            <span style="color: ${currentColors.levelInfo}; font-weight: bold;">I:</span>
            <span>  Connected to server </span>
            <span style="color: ${currentColors.quoted};">'db-server.example.com'</span>
            <span> successfully.  </span>
            <span style="color: ${currentColors.sourceRef}; font-style: italic;">(cloud_imp.c:5028)</span>
        `;
    }

    // Render preset themes
    function renderPresetThemes() {
        const grid = document.getElementById('presetThemesGrid');
        grid.innerHTML = '';

        Object.entries(DEFAULT_SCHEMES).forEach(([key, scheme]) => {
            const btn = document.createElement('button');
            btn.className = 'preset-theme-btn';
            btn.innerHTML = `
                <span class="theme-colors">
                    <span class="theme-color-dot" style="background: ${scheme.colors.thread}"></span>
                    <span class="theme-color-dot" style="background: ${scheme.colors.component}"></span>
                    <span class="theme-color-dot" style="background: ${scheme.colors.quoted}"></span>
                    <span class="theme-color-dot" style="background: ${scheme.colors.levelError}"></span>
                </span>
                ${scheme.name}
            `;

            btn.addEventListener('click', () => {
                // Merge with defaults to ensure all color keys exist
                currentColors = { ...DEFAULT_SCHEMES['qlik'].colors, ...scheme.colors };
                populateColorInputs();
                updatePreviewColors();
                updateColorPreview();
            });

            grid.appendChild(btn);
        });
    }

    // Render custom themes list (same style as preset themes with delete button)
    function renderCustomThemes() {
        const grid = document.getElementById('customThemesList');
        grid.innerHTML = '';

        if (Object.keys(customThemes).length === 0) {
            grid.innerHTML = '<p style="font-size: 0.75rem; color: #6b7280; font-style: italic; grid-column: 1/-1;">No custom themes saved yet</p>';
            return;
        }

        Object.entries(customThemes).forEach(([name, colors]) => {
            const btn = document.createElement('button');
            btn.className = 'preset-theme-btn custom-theme-btn';
            btn.innerHTML = `
                <span class="theme-colors">
                    <span class="theme-color-dot" style="background: ${colors.thread}"></span>
                    <span class="theme-color-dot" style="background: ${colors.component}"></span>
                    <span class="theme-color-dot" style="background: ${colors.quoted}"></span>
                    <span class="theme-color-dot" style="background: ${colors.levelError}"></span>
                </span>
                <span class="theme-name">${escapeHtml(name)}</span>
                <span class="custom-theme-delete" title="Delete theme">×</span>
            `;

            // Load theme on click (but not when clicking delete)
            btn.addEventListener('click', (e) => {
                if (e.target.classList.contains('custom-theme-delete')) {
                    e.stopPropagation();
                    delete customThemes[name];
                    saveSettings();
                    renderCustomThemes();
                } else {
                    // Merge with defaults to ensure all color keys exist
                    currentColors = { ...DEFAULT_SCHEMES['qlik'].colors, ...colors };
                    populateColorInputs();
                    updatePreviewColors();
                    updateColorPreview();
                }
            });

            grid.appendChild(btn);
        });
    }

    // Add button to log controls
    function addColorSchemaButton() {
        const logControls = document.querySelector('.log-controls > div:last-child');
        if (!logControls) return;

        // Check if button already exists
        if (document.getElementById('colorSchemaBtn')) return;

        const btn = document.createElement('button');
        btn.id = 'colorSchemaBtn';
        btn.className = 'color-schema-btn';
        btn.title = 'Customize log colors';
        btn.innerHTML = `
            <svg viewBox="0 0 16 16" fill="currentColor">
                <path d="M8 5a1.5 1.5 0 100-3 1.5 1.5 0 000 3zm4 3a1.5 1.5 0 100-3 1.5 1.5 0 000 3zM5.5 7a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zm.5 6a1.5 1.5 0 100-3 1.5 1.5 0 000 3z"/>
                <path d="M16 8c0 3.15-1.866 2.585-3.567 2.07C11.42 9.763 10.465 9.473 10 10c-.603.683-.475 1.819-.351 2.92C9.826 14.495 9.996 16 8 16a8 8 0 118-8zm-8 7c.611 0 .654-.171.655-.176.078-.146.124-.464.07-1.119-.014-.168-.037-.37-.061-.591-.052-.464-.112-1.005-.118-1.462-.01-.707.083-1.61.704-2.314.369-.417.845-.578 1.272-.618.404-.038.812.026 1.16.104.343.077.702.186 1.025.284l.028.008c.346.105.658.199.953.266.653.148.904.083.991.024C14.717 9.38 15 9.161 15 8a7 7 0 10-7 7z"/>
            </svg>
            Colors
        `;

        btn.addEventListener('click', openColorSchemaModal);

        // Insert before the file status
        const fileStatus = document.getElementById('fileStatus');
        if (fileStatus) {
            fileStatus.parentNode.insertBefore(btn, fileStatus);
        } else {
            logControls.appendChild(btn);
        }
    }

    // Public API
    window.LogColors = {
        init: function() {
            loadSettings();
            // Wait for DOM to be ready
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', () => {
                    addColorSchemaButton();
                    createColorSchemaModal();
                });
            } else {
                addColorSchemaButton();
                createColorSchemaModal();
            }
        },
        highlightLine: highlightLogLine,
        isEnabled: function() {
            return syntaxHighlightingEnabled;
        },
        isReady: function() {
            return settingsLoaded;
        },
        getColors: function() {
            return { ...currentColors };
        },
        openModal: openColorSchemaModal,
        refresh: function() {
            if (window.refreshLogDisplay) {
                window.refreshLogDisplay();
            }
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            window.LogColors.init();
        });
    } else {
        window.LogColors.init();
    }
})();

