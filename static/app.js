document.addEventListener("DOMContentLoaded", () => {
  // State variables
  let currentFileId = null;
  let currentFileName = ''; // Track current log filename for exports
  let currentLogStart = 0;
  let totalLogLines = 0;
  let isFetchingLog = false;
  let findings = [];
  let contextMenu = null;
  let currentHighlightColor = 'yellow'; // Default highlight color
  let currentView = 'all'; // 'all' or 'search' - tracks which view is active
  let lastSearchMatches = []; // Store last search matches for highlighting in All Lines view
  
  // Track loaded line range for bidirectional scrolling
  let loadedLinesStart = 0;
  let loadedLinesEnd = 0;
  
  // Store highlighted lines by line index (persists across reloads)
  let highlightedLines = {}; // { lineIndex: colorName }
  
  // Multiple search tabs state
  let searchTabs = []; // Array of { id, query, matches }
  let searchTabIdCounter = 0;
  let visibleSearchTabIndex = 0;
  const MAX_VISIBLE_SEARCH_TABS = 3;
  
  // Recent files state
  const RECENT_FILES_KEY = 'logAnalyzer_recentFiles';
  const MAX_RECENT_FILES = 20;

  // DOM Elements
  const fileList = document.getElementById("fileList");
  const logPreview = document.getElementById("logPreview");
  const loadedCountSpan = document.getElementById("loadedCount");
  const statsPanel = document.getElementById("statsPanel");
  const findingsList = document.getElementById("findingsList");
  const clearFindingsBtn = document.getElementById("clearFindings");
  const exportFindingsBtn = document.getElementById("exportFindings");
  
  const localPathInput = document.getElementById("localPathInput");
  const loadPathBtn = document.getElementById("loadPathBtn");
  const uploadForm = document.getElementById("uploadForm");
  const logFileInput = document.getElementById("logFileInput");
  
  const webControls = document.getElementById("webControls");
  const nativeOpenBtn = document.getElementById("nativeOpenBtn");
  
  const searchInput = document.getElementById("searchInput");
  const searchBtn = document.getElementById("searchBtn");
  const searchResults = document.getElementById("searchResults");
  const fileStatusDiv = document.getElementById("fileStatus");
  const tabBtns = document.querySelectorAll(".tab-btn");
  const tabContents = document.querySelectorAll(".tab-content");
  const threadListDiv = document.getElementById("threadList");
  const threadLogView = document.getElementById("threadLogView");
  const componentInfo = document.getElementById("componentInfo");
  
  // Placeholder handling for log area (welcome screen until a file loads)
  function showLogPlaceholder() {
    if (logPreview) {
      logPreview.classList.add('log-placeholder');
      logPreview.innerHTML = `
        <div class="log-welcome">
          <p class="log-welcome-kicker">Welcome to</p>
          <div class="log-welcome-image-wrap">
            <img src="/static/new_welcome_screen.png" alt="">
          </div>
          <div class="log-welcome-section">
            <h2 class="log-welcome-heading">Getting Started</h2>
            <div class="log-welcome-cta-row">
              <button type="button" id="welcomeOpenLogBtn" class="btn log-welcome-open-btn">Open log file</button>
            </div>
            <p class="log-welcome-getting-started">To start you need to open a log file. Once it loads here, you can search, filter by thread, and inspect errors and performance.</p>
            <p class="log-welcome-hint">If the AI API key has not been configured yet, click the <span class="log-welcome-inline-ai-wrap"><button type="button" id="welcomeAiSettingsBtn" class="ai-settings-btn" title="AI Settings" aria-label="AI Settings"><svg width="18" height="18" viewBox="0 0 512 512" fill="currentColor"><path d="M327.5 85.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 128l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 128l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 64 426.8 7.5C425.1 3 420.8 0 416 0s-9.1 3-10.8 7.5L384 64 327.5 85.2zM9.3 240C3.6 242.6 0 248.3 0 254.6s3.6 11.9 9.3 14.5L26.3 277l8.1 3.7 .6 .3 88.3 40.8L164.1 410l.3 .6 3.7 8.1 7.9 17.1c2.6 5.7 8.3 9.3 14.5 9.3s11.9-3.6 14.5-9.3l7.9-17.1 3.7-8.1 .3-.6 40.8-88.3L346 281l.6-.3 8.1-3.7 17.1-7.9c5.7-2.6 9.3-8.3 9.3-14.5s-3.6-11.9-9.3-14.5l-17.1-7.9-8.1-3.7-.6-.3-88.3-40.8L217 99.1l-.3-.6L213 90.3l-7.9-17.1c-2.6-5.7-8.3-9.3-14.5-9.3s-11.9 3.6-14.5 9.3l-7.9 17.1-3.7 8.1-.3 .6-40.8 88.3L35.1 228.1l-.6 .3-8.1 3.7L9.3 240zM384 384l-56.5 21.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 448l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 448l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 384l-21.2-56.5c-1.7-4.5-6-7.5-10.8-7.5s-9.1 3-10.8 7.5L384 384z"/></svg><span class="ai-settings-indicator"></span></button></span> in the top-right corner of the header.</p>
          </div>
        </div>`;
      const welcomeOpenBtn = logPreview.querySelector('#welcomeOpenLogBtn');
      if (welcomeOpenBtn) {
        welcomeOpenBtn.addEventListener('click', () => {
          if (window.pywebview && window.pywebview.api && nativeOpenBtn) {
            nativeOpenBtn.click();
          } else if (logFileInput) {
            logFileInput.click();
          }
        });
      }
      const welcomeAiBtn = logPreview.querySelector('#welcomeAiSettingsBtn');
      const mainAiBtn = document.getElementById('aiSettingsBtn');
      if (welcomeAiBtn && mainAiBtn) {
        welcomeAiBtn.addEventListener('click', () => mainAiBtn.click());
      }
      updateAISettingsIndicator();
    }
  }

  function hideLogPlaceholder() {
    if (logPreview) {
      logPreview.classList.remove('log-placeholder');
    }
  }

  // Default to placeholder state before any log is loaded
  showLogPlaceholder();

  // Log View Threads Panel elements
  const logViewThreadList = document.getElementById("logViewThreadList");
  const logViewComponentInfo = document.getElementById("logViewComponentInfo");
  const logViewComponentInfoContent = document.getElementById("logViewComponentInfoContent");
  const logViewComponentSearch = document.getElementById("logViewComponentSearch");
  const componentThreadSearch = document.getElementById("componentThreadSearch");
  const activityQuickSearch = document.getElementById("activityQuickSearch");
  const activitySearchPrev = document.getElementById("activitySearchPrev");
  const activitySearchNext = document.getElementById("activitySearchNext");
  const activitySearchCount = document.getElementById("activitySearchCount");
  const showTimeGapsAnalysis = document.getElementById("showTimeGapsAnalysis");
  const backToBulkMapNotification = document.getElementById("backToBulkMapNotification");
  const backToBulkMapBtn = document.getElementById("backToBulkMapBtn");
  const closeBulkMapNotification = document.getElementById("closeBulkMapNotification");
  const logQuickSearch = document.getElementById("logQuickSearch");
  const logSearchPrev = document.getElementById("logSearchPrev");
  const logSearchNext = document.getElementById("logSearchNext");
  const logSearchCount = document.getElementById("logSearchCount");
  
  // Activity search state
  let activityMatches = [];
  let currentActivityMatchIndex = -1;
  
  // Log search state
  let logMatches = [];
  let currentLogMatchIndex = -1;
  let logSearchTimeout = null;
  let activitySearchTimeout = null;
  
  // Component descriptions from Qlik Replicate documentation
  const componentDescriptions = {
    'ADDONS': {
      short: 'User-defined transformations / add-ons',
      desc: 'Only relevant when working with a Replicate add-on such as user-defined transformations.',
      lookFor: 'Errors in custom transformation logic; add-on initialization failures.'
    },
    'ASSERTION': {
      short: 'Data anomaly detection',
      desc: 'Detects anomalies with the data that might result in replication issues. These warnings are not exposed in the console and do not trigger notifications.',
      lookFor: 'ASSERTION WARNING entries — they signal data inconsistencies that can cause downstream problems even if the task keeps running.'
    },
    'COMMON': {
      short: 'Low-level network & utility messages',
      desc: 'Writes low-level messages such as network activity. Setting to Trace produces enormous output.',
      lookFor: 'Network timeouts, DNS resolution failures, TLS/SSL handshake errors.'
    },
    'COMMUNICATION': {
      short: 'Source/target transport layer (HTTP, CURL)',
      desc: 'Communication between Replicate and source/target components. For cloud targets (Hadoop, Databricks) this includes CURL debug messages and file uploads.',
      lookFor: 'HTTP errors (4xx/5xx), CURL failures, slow uploads, authentication/token refresh issues.'
    },
    'DATA_RECORD': {
      short: 'Per-change event capture details',
      desc: 'Writes information about each captured change event. Content varies by endpoint — Oracle logs header fields; some endpoints include changed data.',
      lookFor: 'Events captured out of scope, unexpected data types, event ordering issues.'
    },
    'DATA_STRUCTURE': {
      short: 'Internal data layout in memory',
      desc: 'Internal Replicate data structures — how the code organizes and stores data in memory. Only enable Trace when requested by Qlik Support.',
      lookFor: 'Memory corruption indicators, unexpected structure sizes.'
    },
    'FILE_FACTORY': {
      short: 'File staging for cloud targets',
      desc: 'Responsible for moving files from Replicate to file-based targets (Hadoop HDFS, Redshift, Azure Synapse, Databricks). Handles the HDFS/S3/ADLS staging step.',
      lookFor: 'File write failures, staging directory issues, permission errors, slow file creation.'
    },
    'FILE_TRANSFER': {
      short: 'File push to external storage (CIFTA)',
      desc: 'Handles the File Transfer / CIFTA component that pushes files to specific locations (S3, ADLS, GCS).',
      lookFor: 'Upload failures, compression errors, throughput bottlenecks, credential issues.'
    },
    'INFRASTRUCTURE': {
      short: 'ODBC, threading, task state persistence',
      desc: 'Infrastructure layers: ODBC connections, logger setup, thread lifecycle, task state persistence, and internal protocol buffers.',
      lookFor: 'ODBC driver load failures, thread creation/termination issues, state save errors, ODBC connection pool exhaustion.'
    },
    'IO': {
      short: 'File system operations',
      desc: 'Logs all file I/O operations — directory scanning, file creation/deletion, disk space checks.',
      lookFor: 'Disk full errors, permission denied, directory not found, excessive directory scanning times.'
    },
    'METADATA_CHANGES': {
      short: 'DDL change propagation',
      desc: 'Shows actual DDL changes (ALTER TABLE, etc.) captured within the task scope. Availability depends on endpoint.',
      lookFor: 'DDL changes that cause table reloads, unsupported DDL types, metadata sync failures between source and target.'
    },
    'METADATA_MANAGER': {
      short: 'Table metadata read/write/store',
      desc: 'Manages reading metadata from source/target, storing it, and handling dynamic metadata changes.',
      lookFor: 'Metadata read timeouts, column type mismatches, metadata store corruption, slow metadata fetches.'
    },
    'PERFORMANCE': {
      short: 'Latency tracking (source/target, every 30s)',
      desc: 'Logs latency values for source and target endpoints every 30 seconds. This is the primary source for latency graphs and performance monitoring.',
      lookFor: 'Sudden latency spikes, sustained high latency plateaus, imbalance between source and target latency (indicates bottleneck location).'
    },
    'REST_SERVER': {
      short: 'API & UI request handling',
      desc: 'Handles REST API requests from the console UI and Qlik Enterprise Manager.',
      lookFor: 'API timeouts, authentication failures, Enterprise Manager communication issues.'
    },
    'SERVER': {
      short: 'Task ↔ Server service communication',
      desc: 'The server thread that communicates with the Replicate Server service for task start/stop. Contains init functions and task definition.',
      lookFor: 'Task start failures, licensing issues, server communication timeouts.'
    },
    'SORTER': {
      short: 'CDC transaction routing & ordering (critical)',
      desc: 'The central CDC component that routes changes from source to target. Synchronizes Full Load and CDC, decides cached-change apply order, and stores transactions until commit.',
      lookFor: 'Missing events, transaction ordering issues, high memory usage, "cached changes" buildup, slow commit processing. Enable Verbose when investigating CDC latency or missing data.'
    },
    'SORTER_STORAGE': {
      short: 'Transaction memory & swap management',
      desc: 'Storage backend for the Sorter — keeps transactions in memory and offloads to disk when they become too large or long-running.',
      lookFor: 'Swap file creation (large transactions), disk I/O spikes from offloading, corrupt swap files, out-of-memory conditions.'
    },
    'SOURCE_CAPTURE': {
      short: 'CDC source-side log reading (critical)',
      desc: 'The main CDC component on the source side. Reads database transaction logs (redo logs, WAL, etc.) and captures changes. Some target-side LOB lookups also use this logger.',
      lookFor: 'Log read delays (redo/WAL), reconnection events, supplemental logging gaps, archive log access issues, high source latency. Enable Trace for source I/O performance analysis.'
    },
    'SOURCE_LOG_DUMP': {
      short: 'Raw change dump files (Log Reader)',
      desc: 'When using Replicate Log Reader, creates separate dump files of captured changes. Data is stored in a file, not in the main log.',
      lookFor: 'Dump file creation failures, missing change records in dumps.'
    },
    'SOURCE_UNLOAD': {
      short: 'Full Load SELECT execution on source',
      desc: 'Records source-side Full Load activity including the SELECT statements executed against source tables.',
      lookFor: 'Slow SELECT queries, timeout errors, table lock contention during Full Load, query plan issues.'
    },
    'STREAM': {
      short: 'In-memory data & control buffers',
      desc: 'The memory buffer where data and control commands flow between components. Data streams carry row changes; Control streams carry start/stop signals.',
      lookFor: 'Buffer overflows, stream backpressure (target too slow), control command delays (table load stuck). Enable Trace only for specific stream issues.'
    },
    'STREAM_COMPONENT': {
      short: 'Component ↔ Stream interaction',
      desc: 'Used by Source, Sorter, and Target to interact with the Stream buffer. Includes mode switches (e.g., transactional apply mode).',
      lookFor: 'Apply mode switches, stream communication failures, component synchronization issues.'
    },
    'TABLES_MANAGER': {
      short: 'Table status & partition tracking',
      desc: 'Manages table status (loaded, loading, error), event counts, partitioning, and table-level state.',
      lookFor: 'Tables stuck in "loading" state, unexpected table error status, partition issues, table count mismatches.'
    },
    'TARGET_APPLY': {
      short: 'CDC apply to target (batch & transactional)',
      desc: 'Applies CDC changes to the target. Covers both Batch Optimized Apply and Transactional Apply. Logs bulk operations, one-by-one fallbacks, apply errors, and batch closure reasons.',
      lookFor: 'Batch closure reasons (PK conflicts, timeouts, memory), one-by-one mode switches, SQL errors during apply, slow apply times, "Failed to execute" messages.'
    },
    'TARGET_LOAD': {
      short: 'Full Load on target side',
      desc: 'Full Load operations on the target — table creation, data loading, metadata operations. May print target table metadata.',
      lookFor: 'Table creation failures, data type mapping errors, bulk load errors, slow load times.'
    },
    'TASK_MANAGER': {
      short: 'Task orchestration & lifecycle',
      desc: 'The parent component that manages all other components. Issues start/stop commands, creates threads, manages table load lifecycle.',
      lookFor: 'Components not starting or stopping properly, tables stuck in loading, task initialization failures, thread creation errors.'
    },
    'TRANSFORMATION': {
      short: 'Column/expression transformations',
      desc: 'Logs transformation activity — column mappings, expression evaluation, filter logic. Trace level shows actual transformation expressions.',
      lookFor: 'Transformation expression errors, unexpected NULL handling, filter logic dropping records, expression evaluation performance.'
    },
    'UTILITIES': {
      short: 'Notifications & misc utilities',
      desc: 'Utility functions, primarily notification-related (email, SNMP, etc.).',
      lookFor: 'Notification delivery failures, SMTP errors.'
    },
    'AT_GLOBAL': {
      short: 'Global task info & licensing',
      desc: 'Global task information, licensing details, and server-wide configuration.',
      lookFor: 'License expiry warnings, global configuration issues.'
    },
    'METADATA_MANAGE': {
      short: 'Metadata operations (alias)',
      desc: 'Alternative name for METADATA_MANAGER — manages metadata read/write operations.',
      lookFor: 'Same as METADATA_MANAGER.'
    }
  };

  function getComponentDescription(name) {
    const info = componentDescriptions[name];
    if (!info) return 'No description available for this component.';
    return typeof info === 'string' ? info : info.desc;
  }
  function getComponentShort(name) {
    const info = componentDescriptions[name];
    if (!info) return '';
    return typeof info === 'string' ? '' : (info.short || '');
  }
  function getComponentLookFor(name) {
    const info = componentDescriptions[name];
    if (!info) return '';
    return typeof info === 'string' ? '' : (info.lookFor || '');
  }
  
  // Modal elements
  const modalOverlay = document.getElementById("modalOverlay");
  const modalTitle = document.getElementById("modalTitle");
  const modalBody = document.getElementById("modalBody");
  let modalCancel = document.getElementById("modalCancel");
  let modalConfirm = document.getElementById("modalConfirm");

  // --- Initialization ---
  
  // Check for PyWebView
  // PyWebView injects window.pywebview, but sometimes it takes a moment after DOMContentLoaded
  window.addEventListener('pywebviewready', function() {
      console.log("PyWebView ready!");
      enableNativeMode();
  });
  
  // Fallback check
  setTimeout(() => {
     if (window.pywebview) enableNativeMode(); 
  }, 500);

  function enableNativeMode() {
      // Hide web controls and show native open button
      if (webControls) {
          webControls.style.display = "none";
      }
      if (nativeOpenBtn) {
          nativeOpenBtn.style.display = "flex";
      }
  }

  fetchFileList();

  // --- Event Listeners ---
  
  // Native Open
  if (nativeOpenBtn) {
      nativeOpenBtn.addEventListener("click", () => {
         if (window.pywebview && window.pywebview.api) {
             window.pywebview.api.pick_file().then(path => {
                 if (path) {
                     registerLocalFile(path);
                 }
             });
         } 
      });
  }
  
  // Local Path Load (Web Mode)
  if (loadPathBtn && localPathInput) {
      loadPathBtn.addEventListener("click", () => {
          const path = localPathInput.value.trim();
          if (path) registerLocalFile(path);
      });
      localPathInput.addEventListener("keypress", (e) => {
          if (e.key === "Enter") {
              const path = localPathInput.value.trim();
              if (path) registerLocalFile(path);
          }
      });
  }

  // File Upload (Web Mode)
  if (logFileInput) {
    logFileInput.addEventListener("change", (e) => {
      if (e.target.files.length > 0) {
        uploadFile(e.target.files[0]);
      }
    });
  }

  const closeLogFileBtn = document.getElementById('closeLogFileBtn');
  if (closeLogFileBtn) {
    closeLogFileBtn.addEventListener('click', () => closeLogFile());
  }

  // Tabs
  window.analysisTabFirstClick = true;
  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      tabBtns.forEach(b => b.classList.remove("active"));
      tabContents.forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(btn.dataset.tab).classList.add("active");
      
      // Auto-load Log Summary on first click of Analysis tab
      if (btn.dataset.tab === 'analysis-tab' && window.analysisTabFirstClick && currentFileId) {
        window.analysisTabFirstClick = false;
        setTimeout(() => {
          if (window.logSummaryData) {
            showLogSummaryInMain();
          }
        }, 100);
      }
    });
  });

  // Latency graph collapse/expand toggle
  const graphHeaderToggle = document.getElementById('graphHeaderToggle');
  if (graphHeaderToggle) {
    graphHeaderToggle.addEventListener('click', () => {
      const section = document.getElementById('graphSection');
      if (section) {
        section.classList.toggle('collapsed');
        // Resize Plotly chart when expanding
        if (!section.classList.contains('collapsed')) {
          const graphDiv = document.getElementById('latencyGraph');
          if (graphDiv && graphDiv.data) {
            setTimeout(() => Plotly.Plots.resize(graphDiv), 50);
          }
        }
      }
    });
  }

  // Left Panel Tabs (Files/Search)
  const leftPanelTabs = document.querySelectorAll('.left-panel-tab');
  const leftPanelContents = document.querySelectorAll('.left-panel-content');
  
  leftPanelTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const panelId = tab.dataset.panel;
      
      // Update tab active states
      leftPanelTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      
      // Update panel visibility
      leftPanelContents.forEach(content => {
        content.classList.remove('active');
        if (content.id === panelId) {
          content.classList.add('active');
        }
      });
    });
  });
  
  // Function to switch to search panel
  function switchToSearchPanel() {
    const searchTab = document.querySelector('.left-panel-tab[data-panel="search-panel"]');
    if (searchTab) {
      searchTab.click();
    }
  }

  // Search
  if (searchBtn) searchBtn.addEventListener("click", performSearch);
  if (searchInput) {
    searchInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") performSearch();
    });
  }

  // Track last fetch to prevent duplicate requests (declared at module scope for access in jumpToLineAndHighlight)
  let lastFetchStart = -1;
  let lastFetchDirection = null;
  
  // Infinite Scroll - bidirectional, only active when viewing "All Lines"
  // Throttled via requestAnimationFrame to avoid excessive DOM reads
  let scrollRafPending = false;
  if (logPreview) {
    logPreview.addEventListener("scroll", () => {
      if (scrollRafPending) return;
      scrollRafPending = true;
      requestAnimationFrame(() => {
        scrollRafPending = false;
        if (currentView !== 'all') return;
        if (isFetchingLog) return;

        const { scrollTop, clientHeight, scrollHeight } = logPreview;

        if (scrollTop + clientHeight >= scrollHeight - 50) {
          if (loadedLinesEnd < totalLogLines) {
            if (lastFetchStart !== loadedLinesEnd || lastFetchDirection !== 'down') {
              lastFetchStart = loadedLinesEnd;
              lastFetchDirection = 'down';
              fetchLogLines(loadedLinesEnd, 100, true, 'down');
            }
          }
        }

        if (scrollTop <= 50) {
          if (loadedLinesStart > 0) {
            const newStart = Math.max(0, loadedLinesStart - 100);
            const count = loadedLinesStart - newStart;
            if (count > 0 && (lastFetchStart !== newStart || lastFetchDirection !== 'up')) {
              lastFetchStart = newStart;
              lastFetchDirection = 'up';
              fetchLogLines(newStart, count, true, 'up');
            }
          }
        }
      });
    });

    // Delegated contextmenu for all log lines inside logPreview
    logPreview.addEventListener("contextmenu", (e) => {
      const logLine = e.target.closest('.log-line');
      if (logLine && logLine.dataset.originalText) {
        showContextMenu(e, logLine.dataset.originalText, logLine);
      }
    });
  }

  // Findings
  if (clearFindingsBtn) {
    clearFindingsBtn.addEventListener("click", () => {
      findings = [];
      renderFindings();
    });
  }
  
  if (exportFindingsBtn) {
    exportFindingsBtn.addEventListener("click", exportFindings);
  }
  
  // Preset Tags
  const presetTags = document.querySelectorAll('.preset-tag[data-pattern]');
  presetTags.forEach(tag => {
    tag.addEventListener('click', () => {
      const pattern = tag.getAttribute('data-pattern');
      searchInput.value = pattern;
      performSearch();
    });
  });
  
  // Highlight Filter Dropdown
  const highlightFilterBtn = document.getElementById('highlightFilterBtn');
  const highlightFilterDropdown = document.getElementById('highlightFilterDropdown');
  const showTimeGapsCheckbox = document.getElementById('showTimeGaps');
  
  if (highlightFilterBtn && highlightFilterDropdown) {
    highlightFilterBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isVisible = highlightFilterDropdown.style.display === 'block';
      highlightFilterDropdown.style.display = isVisible ? 'none' : 'block';
    });
    
    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
      if (!highlightFilterDropdown.contains(e.target) && e.target !== highlightFilterBtn) {
        highlightFilterDropdown.style.display = 'none';
      }
    });
    
    // Handle checkbox changes
    const filterCheckboxes = highlightFilterDropdown.querySelectorAll('input[type="checkbox"]');
    filterCheckboxes.forEach(checkbox => {
      checkbox.addEventListener('change', applyHighlightFilter);
    });
    
    // Handle clear color buttons
    const clearColorBtns = highlightFilterDropdown.querySelectorAll('.clear-color-btn');
    clearColorBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const color = btn.getAttribute('data-color');
        clearHighlightsByColor(color);
      });
    });
  }
  
  // Clear all highlights of a specific color
  function clearHighlightsByColor(color) {
    [logPreview, threadLogView].forEach(container => {
      if (!container) return;
      const logLines = container.querySelectorAll('.log-line');
      logLines.forEach(line => {
        if (color === 'search') {
          line.classList.remove('search-highlight-line');
        } else {
          line.classList.remove(`highlight-${color}`);
        }
      });
    });
  }
  
  // Time Gaps Checkbox
  if (showTimeGapsCheckbox) {
    showTimeGapsCheckbox.addEventListener('change', () => {
      applyTimeGapsDisplay();
    });
  }
  
  // Time Gaps Checkbox for Analysis Tab
  if (showTimeGapsAnalysis) {
    showTimeGapsAnalysis.addEventListener('change', () => {
      applyTimeGapsDisplay();
    });
  }

  // Hide Noise Checkbox
  const hideNoiseCheckbox = document.getElementById('hideNoise');
  if (hideNoiseCheckbox) {
    hideNoiseCheckbox.addEventListener('change', () => {
      applyHideNoise();
    });
  }
  
  // Colors button for Analysis Tab
  const analysisColorsBtn = document.getElementById('analysisColorsBtn');
  if (analysisColorsBtn) {
    analysisColorsBtn.addEventListener('click', () => {
      if (window.LogColors && window.LogColors.openModal) {
        window.LogColors.openModal();
      }
    });
  }
  
  // Component/Thread Search
  if (componentThreadSearch) {
    componentThreadSearch.addEventListener('input', () => {
      filterComponentThreadList();
    });
  }
  
  // Activity Quick Search with debounce
  if (activityQuickSearch) {
    activityQuickSearch.addEventListener('input', () => {
      // Clear existing timeout
      if (activitySearchTimeout) {
        clearTimeout(activitySearchTimeout);
      }
      // Set new timeout (500ms delay)
      activitySearchTimeout = setTimeout(() => {
        performActivityQuickSearch();
      }, 500);
    });
  }
  
  if (activitySearchNext) {
    activitySearchNext.addEventListener('click', () => {
      navigateActivityMatch(1);
    });
  }
  
  if (activitySearchPrev) {
    activitySearchPrev.addEventListener('click', () => {
      navigateActivityMatch(-1);
    });
  }
  
  // Log Quick Search with debounce
  if (logQuickSearch) {
    logQuickSearch.addEventListener('input', () => {
      // Clear existing timeout
      if (logSearchTimeout) {
        clearTimeout(logSearchTimeout);
      }
      // Set new timeout (500ms delay)
      logSearchTimeout = setTimeout(() => {
        performLogQuickSearch();
      }, 500);
    });
  }
  
  if (logSearchNext) {
    logSearchNext.addEventListener('click', () => {
      navigateLogMatch(1);
    });
  }
  
  if (logSearchPrev) {
    logSearchPrev.addEventListener('click', () => {
      navigateLogMatch(-1);
    });
  }
  
  // Jump to top/end buttons
  const jumpToTopBtn = document.getElementById('jumpToTopBtn');
  const jumpToEndBtn = document.getElementById('jumpToEndBtn');
  
  if (jumpToTopBtn) {
    jumpToTopBtn.addEventListener('click', () => {
      if (currentFileId) {
        jumpToLineAndHighlight(0, '');  // 0-indexed
      }
    });
  }
  
  if (jumpToEndBtn) {
    jumpToEndBtn.addEventListener('click', () => {
      if (currentFileId && totalLogLines > 0) {
        jumpToLineAndHighlight(totalLogLines - 1, '');  // 0-indexed, so last line is totalLogLines - 1
      }
    });
  }
  
  // Keyboard shortcuts for jump to top/end (Ctrl+Home / Ctrl+End)
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 'Home') {
      e.preventDefault();
      if (currentFileId) {
        jumpToLineAndHighlight(0, '');  // 0-indexed
      }
    } else if (e.ctrlKey && e.key === 'End') {
      e.preventDefault();
      if (currentFileId && totalLogLines > 0) {
        jumpToLineAndHighlight(totalLogLines - 1, '');  // 0-indexed
      }
    }
  });
  
  // Back to Bulk Map notification handlers
  let _bulkMapNotifTimer = null;
  
  function dismissBulkMapNotification() {
    if (backToBulkMapNotification) backToBulkMapNotification.style.display = 'none';
    if (_bulkMapNotifTimer) { clearTimeout(_bulkMapNotifTimer); _bulkMapNotifTimer = null; }
  }
  
  function showBulkMapNotification() {
    if (!backToBulkMapNotification) return;
    backToBulkMapNotification.style.display = 'block';
    if (_bulkMapNotifTimer) clearTimeout(_bulkMapNotifTimer);
    _bulkMapNotifTimer = setTimeout(dismissBulkMapNotification, 10000);
  }
  
  if (backToBulkMapBtn) {
    backToBulkMapBtn.addEventListener('click', () => {
      const analysisTab = document.querySelector('.tab-btn[data-tab="analysis-tab"]');
      if (analysisTab) analysisTab.click();
      setTimeout(() => {
        showBulkMapInMain();
        dismissBulkMapNotification();
      }, 100);
    });
  }
  
  if (closeBulkMapNotification) {
    closeBulkMapNotification.addEventListener('click', dismissBulkMapNotification);
  }
  
  // Dismiss notification on any tab navigation
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', dismissBulkMapNotification);
  });
  
  function applyHighlightFilter() {
    const checkboxes = document.querySelectorAll('#highlightFilterDropdown input[type="checkbox"]');
    const visibleColors = Array.from(checkboxes)
      .filter(cb => cb.checked)
      .map(cb => cb.value);
    
    console.log('Applying highlight filter:', visibleColors);
    
    const logLines = logPreview.querySelectorAll('.log-line');
    logLines.forEach(line => {
      // Check if line has any highlight
      const hasYellow = line.classList.contains('highlight-yellow');
      const hasGreen = line.classList.contains('highlight-green');
      const hasBlue = line.classList.contains('highlight-blue');
      const hasRed = line.classList.contains('highlight-red');
      const hasPurple = line.classList.contains('highlight-purple');
      const hasOrange = line.classList.contains('highlight-orange');
      const hasSearch = line.classList.contains('search-match-line');
      
      let shouldShow = true;
      
      // If line has any highlight, check if that highlight is enabled in filter
      if (hasYellow && !visibleColors.includes('yellow')) shouldShow = false;
      if (hasGreen && !visibleColors.includes('green')) shouldShow = false;
      if (hasBlue && !visibleColors.includes('blue')) shouldShow = false;
      if (hasRed && !visibleColors.includes('red')) shouldShow = false;
      if (hasPurple && !visibleColors.includes('purple')) shouldShow = false;
      if (hasOrange && !visibleColors.includes('orange')) shouldShow = false;
      if (hasSearch && !visibleColors.includes('search')) shouldShow = false;
      
      // If line has no highlights, always show it
      if (!hasYellow && !hasGreen && !hasBlue && !hasRed && !hasPurple && !hasOrange && !hasSearch) {
        shouldShow = true;
      }
      
      line.style.display = shouldShow ? '' : 'none';
    });
  }
  
  // Fast timestamp parser - avoids new Date() overhead for fixed-format timestamps
  function parseTimestampFast(ts) {
    // Format: "2025-10-20T18:34:12"
    const y = ts.charCodeAt(0) * 1000 + ts.charCodeAt(1) * 100 + ts.charCodeAt(2) * 10 + ts.charCodeAt(3) - 53328;
    const mo = (ts.charCodeAt(5) - 48) * 10 + ts.charCodeAt(6) - 48;
    const d = (ts.charCodeAt(8) - 48) * 10 + ts.charCodeAt(9) - 48;
    const h = (ts.charCodeAt(11) - 48) * 10 + ts.charCodeAt(12) - 48;
    const mi = (ts.charCodeAt(14) - 48) * 10 + ts.charCodeAt(15) - 48;
    const s = (ts.charCodeAt(17) - 48) * 10 + ts.charCodeAt(18) - 48;
    return new Date(y, mo - 1, d, h, mi, s);
  }

  // Apply time-gap classes/indicators only to lines that have gap data in a container
  function applyTimeGapsToLines(container, showGaps) {
    const logLines = container.querySelectorAll('.log-line[data-time-gap]');
    logLines.forEach(line => {
      line.classList.remove('time-gap', 'time-gap-small', 'time-gap-medium', 'time-gap-large');
      if (showGaps) {
        const gapSize = line.dataset.gapSize;
        const timeGap = parseFloat(line.dataset.timeGap);
        line.classList.add('time-gap');
        if (!line.querySelector('.time-gap-indicator')) {
          const indicator = document.createElement('span');
          indicator.className = 'time-gap-indicator';
          indicator.textContent = `⏱ +${timeGap.toFixed(2)}s`;
          const lineNumSpan = line.querySelector('.line-number');
          if (lineNumSpan && lineNumSpan.nextSibling) {
            line.insertBefore(indicator, lineNumSpan.nextSibling);
          } else {
            line.insertBefore(indicator, line.firstChild);
          }
        }
        line.classList.add(gapSize === 'small' ? 'time-gap-small' : gapSize === 'medium' ? 'time-gap-medium' : 'time-gap-large');
      } else {
        const indicator = line.querySelector('.time-gap-indicator');
        if (indicator) indicator.remove();
      }
    });
  }

  // Optimized: only apply search highlights to lines not already highlighted
  function applySearchHighlightsToNewLines() {
    if (lastSearchMatches.length === 0) return;
    const matchLineNumbers = new Set(lastSearchMatches.map(m => m.line));
    const logLines = logPreview.querySelectorAll('.log-line:not(.search-highlight-line)');
    logLines.forEach(line => {
      const idx = parseInt(line.dataset.idx);
      if (matchLineNumbers.has(idx)) {
        line.classList.add('search-highlight-line');
      }
    });
  }

  function applyTimeGapsDisplay() {
    const showGapsMain = document.getElementById('showTimeGaps')?.checked || false;
    const showGapsAnalysis = document.getElementById('showTimeGapsAnalysis')?.checked || false;
    
    // Apply to main log view
    if (logPreview) {
      const logLines = logPreview.querySelectorAll('.log-line');
      logLines.forEach(line => {
        line.classList.remove('time-gap', 'time-gap-small', 'time-gap-medium', 'time-gap-large');
        
        if (showGapsMain && line.dataset.timeGap) {
          const gapSize = line.dataset.gapSize;
          const timeGap = parseFloat(line.dataset.timeGap);
          line.classList.add('time-gap');
          
          // Add time gap indicator with actual time
          if (!line.querySelector('.time-gap-indicator')) {
            const indicator = document.createElement('span');
            indicator.className = 'time-gap-indicator';
            indicator.textContent = `⏱ +${timeGap.toFixed(2)}s`;
            // Insert after line number span
            const lineNumSpan = line.querySelector('.line-number');
            if (lineNumSpan && lineNumSpan.nextSibling) {
              line.insertBefore(indicator, lineNumSpan.nextSibling);
            } else {
              line.insertBefore(indicator, line.firstChild);
            }
          }
          
          if (gapSize === 'small') {
            line.classList.add('time-gap-small');
          } else if (gapSize === 'medium') {
            line.classList.add('time-gap-medium');
          } else if (gapSize === 'large') {
            line.classList.add('time-gap-large');
          }
        } else {
          // Remove time gap indicator if present
          const indicator = line.querySelector('.time-gap-indicator');
          if (indicator) indicator.remove();
        }
      });
    }
    
    // Apply to thread log view (analysis tab)
    if (threadLogView) {
      const logLines = threadLogView.querySelectorAll('.log-line');
      logLines.forEach(line => {
        line.classList.remove('time-gap', 'time-gap-small', 'time-gap-medium', 'time-gap-large');
        
        if (showGapsAnalysis && line.dataset.timeGap) {
          const gapSize = line.dataset.gapSize;
          const timeGap = parseFloat(line.dataset.timeGap);
          line.classList.add('time-gap');
          
          // Add time gap indicator with actual time
          if (!line.querySelector('.time-gap-indicator')) {
            const indicator = document.createElement('span');
            indicator.className = 'time-gap-indicator';
            indicator.textContent = `⏱ +${timeGap.toFixed(2)}s`;
            line.insertBefore(indicator, line.firstChild);
          }
          
          if (gapSize === 'small') {
            line.classList.add('time-gap-small');
          } else if (gapSize === 'medium') {
            line.classList.add('time-gap-medium');
          } else if (gapSize === 'large') {
            line.classList.add('time-gap-large');
          }
        } else {
          // Remove time gap indicator if present
          const indicator = line.querySelector('.time-gap-indicator');
          if (indicator) indicator.remove();
        }
      });
    }
  }
  
  // Extract the "message body" from a log line, stripping thread ID, timestamp, and source ref
  // so that lines differing only in those fields are treated as identical.
  // Input: "00013552: 2025-10-20T18:34:12 [SORTER          ]I:  Task is running  (sorter.c:712)"
  // Output: "[SORTER          ]I:  Task is running"
  const noiseLineRegex = /^\d{8}:\s+\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?::\d+)?\s+(.+?)(?:\s+\([a-zA-Z_]\w*\.\w+:\d+\))?\s*$/;

  function getLineMessageKey(text) {
    const m = text.match(noiseLineRegex);
    return m ? m[1] : text;
  }

  // --- ASM virtual thread helpers ---
  // Virtual thread IDs from the indexer have the format: __asm:N:K
  // where N = ASM statement handle number, K = number of pooled OS threads
  function parseAsmThread(threadId) {
    if (!threadId || !threadId.startsWith('__asm:')) return null;
    const parts = threadId.split(':');
    return { stmtNum: parts[1], poolCount: parseInt(parts[2], 10) || 0 };
  }

  function isAsmThread(threadId) {
    return threadId && threadId.startsWith('__asm:');
  }

  function getAsmLabel(threadId) {
    const asm = parseAsmThread(threadId);
    if (!asm) return threadId;
    return `ASM Stmt ${asm.stmtNum}`;
  }

  function getAsmSublabel(threadId) {
    const asm = parseAsmThread(threadId);
    if (!asm) return '';
    return `${asm.poolCount} pooled OS threads`;
  }

  // Build a search query for an ASM virtual thread (matches by message content)
  function buildAsmSearchQuery(threadId, component) {
    const asm = parseAsmThread(threadId);
    if (!asm) return null;
    const escapedComponent = component.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return `\\[${escapedComponent}.*Preparing read from ASM statement \\(${asm.stmtNum}\\)`;
  }

  function applyHideNoise() {
    const hideNoise = document.getElementById('hideNoise')?.checked || false;

    [logPreview, threadLogView].forEach(container => {
      if (!container) return;
      const logLines = container.querySelectorAll('.log-line');
      if (logLines.length === 0) return;

      // First, remove all existing noise-hidden state and collapse indicators
      container.querySelectorAll('.noise-collapse-indicator').forEach(el => el.remove());
      logLines.forEach(line => {
        line.classList.remove('noise-hidden');
        line.style.display = '';
      });

      if (!hideNoise) return;

      // Identify runs of consecutive lines with the same message key
      let i = 0;
      const linesArr = Array.from(logLines);
      while (i < linesArr.length) {
        const currentKey = getLineMessageKey(linesArr[i].dataset.originalText || '');
        let runEnd = i + 1;
        while (runEnd < linesArr.length) {
          const nextKey = getLineMessageKey(linesArr[runEnd].dataset.originalText || '');
          if (nextKey !== currentKey) break;
          runEnd++;
        }

        const runLength = runEnd - i;
        if (runLength >= 3) {
          const runStart = i;
          const runStop = runEnd;
          const hiddenCount = runLength - 2;

          // Keep first and last, hide the middle ones
          for (let j = runStart + 1; j < runStop - 1; j++) {
            linesArr[j].classList.add('noise-hidden');
            linesArr[j].style.display = 'none';
          }

          const indicator = document.createElement('div');
          indicator.className = 'noise-collapse-indicator';
          indicator.textContent = `⤵ ${hiddenCount} identical line${hiddenCount > 1 ? 's' : ''} hidden`;
          indicator.title = `"${currentKey.substring(0, 80)}${currentKey.length > 80 ? '…' : ''}" repeated ${runLength} times`;
          indicator.style.cursor = 'pointer';
          indicator.addEventListener('click', () => {
            const isExpanded = indicator.dataset.expanded === 'true';
            for (let j = runStart + 1; j < runStop - 1; j++) {
              linesArr[j].style.display = isExpanded ? 'none' : '';
              if (isExpanded) {
                linesArr[j].classList.add('noise-hidden');
              } else {
                linesArr[j].classList.remove('noise-hidden');
              }
            }
            indicator.dataset.expanded = isExpanded ? 'false' : 'true';
            indicator.textContent = isExpanded
              ? `⤵ ${hiddenCount} identical line${hiddenCount > 1 ? 's' : ''} hidden`
              : `⤴ ${hiddenCount} identical line${hiddenCount > 1 ? 's' : ''} shown`;
          });
          linesArr[runStart].after(indicator);
        }

        i = runEnd;
      }
    });
  }

  function filterComponentThreadList() {
    const query = componentThreadSearch.value.toLowerCase().trim();
    const groups = threadListDiv.querySelectorAll('.component-group-container');
    
    groups.forEach(group => {
      const componentName = group.dataset.componentName.toLowerCase();
      const threads = group.querySelectorAll('.thread-item');
      let groupHasMatch = false;
      
      if (query === '') {
        // Show all
        group.style.display = '';
        threads.forEach(t => t.style.display = '');
        groupHasMatch = true;
      } else {
        // Check if component name matches
        const componentMatches = componentName.includes(query);
        
        // Check each thread
        threads.forEach(thread => {
          const threadId = thread.dataset.threadId;
          const threadMatches = threadId.includes(query);
          
          if (componentMatches || threadMatches) {
            thread.style.display = '';
            groupHasMatch = true;
          } else {
            thread.style.display = 'none';
          }
        });
        
        // Show/hide group based on matches
        group.style.display = groupHasMatch ? '' : 'none';
        
        // Expand group if it has matches
        if (groupHasMatch && query !== '') {
          const threadList = group.querySelector('.thread-list-inner');
          const icon = group.querySelector('.expand-icon');
          if (threadList && icon) {
            threadList.classList.remove('hidden');
            icon.textContent = '▼';
          }
        }
      }
    });
  }
  
  // Filter for Log View threads panel
  function filterLogViewThreadList() {
    if (!logViewComponentSearch || !logViewThreadList) return;
    
    const query = logViewComponentSearch.value.toLowerCase().trim();
    const groups = logViewThreadList.querySelectorAll('.component-group-container');
    
    groups.forEach(group => {
      const componentName = group.dataset.componentName.toLowerCase();
      const threads = group.querySelectorAll('.thread-item');
      let groupHasMatch = false;
      
      if (query === '') {
        group.style.display = '';
        threads.forEach(t => t.style.display = '');
        groupHasMatch = true;
      } else {
        const componentMatches = componentName.includes(query);
        
        threads.forEach(thread => {
          const threadId = thread.dataset.threadId;
          const threadMatches = threadId.includes(query);
          
          if (componentMatches || threadMatches) {
            thread.style.display = '';
            groupHasMatch = true;
          } else {
            thread.style.display = 'none';
          }
        });
        
        group.style.display = groupHasMatch ? '' : 'none';
        
        if (groupHasMatch && query !== '') {
          const threadList = group.querySelector('.thread-list-inner');
          const icon = group.querySelector('.expand-icon');
          if (threadList && icon) {
            threadList.classList.remove('hidden');
            icon.textContent = '▼';
          }
        }
      }
    });
  }
  
  // Add event listener for log view component search
  if (logViewComponentSearch) {
    logViewComponentSearch.addEventListener('input', filterLogViewThreadList);
  }
  
  // Render threads in Log View panel
  function renderLogViewThreads(data) {
    if (!logViewThreadList) return;
    
    logViewThreadList.innerHTML = "";
    
    if (!data.components || data.components.length === 0) {
      logViewThreadList.innerHTML = '<p class="placeholder-text-small">No components found</p>';
      return;
    }
    
    // First, classify threads by their dominant component
    const threadToComponentMap = {};
    const threadCounts = {};
    
    data.components.forEach(c => {
      if (!threadCounts[c.thread]) {
        threadCounts[c.thread] = {};
      }
      threadCounts[c.thread][c.name] = c.count;
    });
    
    // Assign each thread to its dominant component
    Object.keys(threadCounts).forEach(thread => {
      const components = threadCounts[thread];
      let maxCount = 0;
      let dominantComponent = null;
      
      Object.entries(components).forEach(([component, count]) => {
        if (count > maxCount) {
          maxCount = count;
          dominantComponent = component;
        }
      });
      
      threadToComponentMap[thread] = dominantComponent;
    });
    
    // Group by dominant component
    const componentMap = {};
    data.components.forEach(c => {
      const dominantComp = threadToComponentMap[c.thread];
      
      if (!componentMap[dominantComp]) {
        componentMap[dominantComp] = {
          name: dominantComp,
          totalCount: 0,
          threads: {}
        };
      }
      
      if (!componentMap[dominantComp].threads[c.thread]) {
        componentMap[dominantComp].threads[c.thread] = {
          thread: c.thread,
          count: 0,
          first_ts: c.first_ts,
          last_ts: c.last_ts
        };
      }
      
      componentMap[dominantComp].threads[c.thread].count += c.count;
      componentMap[dominantComp].totalCount += c.count;
    });
    
    // Sort components by message count (descending)
    const sortedComponents = Object.values(componentMap).sort((a, b) => b.totalCount - a.totalCount);
    
    // Render each component group
    sortedComponents.forEach(comp => {
      const groupDiv = document.createElement("div");
      groupDiv.className = "component-group-container";
      groupDiv.dataset.componentName = comp.name;
      
      const headerDiv = document.createElement("div");
      headerDiv.className = "group-header";

      // Separate real threads from ASM virtual groups for accurate counts
      const allThreadKeys = Object.keys(comp.threads);
      const asmThreads = allThreadKeys.filter(isAsmThread);
      const realThreads = allThreadKeys.filter(k => !isAsmThread(k));
      const totalPooled = asmThreads.reduce((sum, k) => sum + (parseAsmThread(k)?.poolCount || 0), 0);

      let headerStats = `${comp.totalCount} msgs, ${realThreads.length} thr`;
      if (asmThreads.length > 0) {
        headerStats += ` + ${totalPooled} pooled`;
      }
      const shortDesc = getComponentShort(comp.name);
      headerDiv.innerHTML = `<span class="expand-icon">▶</span> <strong>${comp.name}</strong> <span style="color:#9ca3af;">(${headerStats})</span>`
        + (shortDesc ? `<span class="component-short-desc">${shortDesc}</span>` : '');
      headerDiv.onclick = () => {
        const threadList = groupDiv.querySelector('.thread-list-inner');
        const icon = headerDiv.querySelector('.expand-icon');
        const isHidden = threadList.classList.toggle('hidden');
        icon.textContent = isHidden ? '▶' : '▼';
      };
      
      groupDiv.appendChild(headerDiv);
      
      const threadListInner = document.createElement("div");
      threadListInner.className = "thread-list-inner hidden";
      
      const sortedThreads = Object.values(comp.threads).sort((a, b) => b.count - a.count);

      // Render real threads first, then ASM groups with special styling
      const realEntries = sortedThreads.filter(t => !isAsmThread(t.thread));
      const asmEntries = sortedThreads.filter(t => isAsmThread(t.thread));

      realEntries.forEach(t => {
        const threadDiv = document.createElement("div");
        threadDiv.className = "thread-item";
        threadDiv.dataset.threadId = t.thread;
        threadDiv.innerHTML = `Thread ${t.thread}: ${t.count} msgs`;
        threadDiv.onclick = (e) => {
          e.stopPropagation();
          loadComponentActivityForLogView(comp.name, t.thread, t.count);
        };
        threadListInner.appendChild(threadDiv);
      });

      if (asmEntries.length > 0) {
        const asmHeader = document.createElement("div");
        asmHeader.className = "asm-group-header";
        asmHeader.innerHTML = `<span class="asm-icon">⛁</span> ASM Parallel Readers <span class="asm-pool-note">${totalPooled} short-lived OS threads grouped by ASM handle</span>`;
        threadListInner.appendChild(asmHeader);

        asmEntries.forEach(t => {
          const asm = parseAsmThread(t.thread);
          const threadDiv = document.createElement("div");
          threadDiv.className = "thread-item asm-thread-item";
          threadDiv.dataset.threadId = t.thread;
          threadDiv.innerHTML = `<span class="asm-label">${getAsmLabel(t.thread)}</span>: ${t.count} msgs <span class="asm-pool-badge">${getAsmSublabel(t.thread)}</span>`;
          threadDiv.onclick = (e) => {
            e.stopPropagation();
            loadComponentActivityForLogView(comp.name, t.thread, t.count);
          };
          threadListInner.appendChild(threadDiv);
        });
      }
      
      groupDiv.appendChild(threadListInner);
      logViewThreadList.appendChild(groupDiv);
    });
  }
  
  // Load component activity from log view (shows info in left panel)
  function loadComponentActivityForLogView(component, thread, messageCount) {
    // Update component info in log view panel
    updateLogViewComponentInfo(component, thread, messageCount);
    
    // Perform search and create a search tab with results (but don't switch left panel)
    if (!currentFileId) return;
    
    let searchQuery;
    if (isAsmThread(thread)) {
      searchQuery = buildAsmSearchQuery(thread, component);
    } else {
      const escapedComponent = component.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      searchQuery = `^${thread}:.*\\[${escapedComponent}`;
    }
    
    // Update the search input but DON'T switch to search panel - user stays on threads panel
    if (searchInput) {
      searchInput.value = searchQuery;
      // Trigger search without switching panel
      performSearch();
    }
  }
  
  // Reusable collapsible section builder
  function buildCollapsibleSection(title, bodyHtml, opts = {}) {
    const color = opts.color || '#818cf8';
    const icon = opts.icon || '';
    const startOpen = opts.startOpen || false;
    const cls = opts.cls || '';
    const hiddenCls = startOpen ? '' : ' hidden';
    const arrow = startOpen ? '▼' : '▶';
    return `
      <div class="info-collapsible ${cls}">
        <div class="info-collapsible-header" onclick="this.nextElementSibling.classList.toggle('hidden'); this.querySelector('.info-collapse-arrow').textContent = this.nextElementSibling.classList.contains('hidden') ? '▶' : '▼';">
          <span class="info-collapse-arrow" style="color:${color}">${arrow}</span>
          ${icon ? `<span class="info-collapse-icon">${icon}</span>` : ''}
          <span class="info-collapse-title" style="color:${color}">${title}</span>
        </div>
        <div class="info-collapsible-body${hiddenCls}">
          ${bodyHtml}
        </div>
      </div>`;
  }

  function updateLogViewComponentInfo(component, thread, messageCount) {
    if (!logViewComponentInfo || !logViewComponentInfoContent) return;
    
    const description = getComponentDescription(component);
    const lookFor = getComponentLookFor(component);
    const asm = parseAsmThread(thread);
    
    logViewComponentInfo.style.display = 'block';
    
    let threadInfo;
    if (asm) {
      threadInfo = `
        <p><strong>ASM Statement Handle:</strong> ${asm.stmtNum}</p>
        <p><strong>Pooled OS Threads:</strong> ${asm.poolCount}</p>`;
    } else {
      threadInfo = thread ? `<p><strong>Thread:</strong> ${thread}</p>` : '';
    }

    let html = `
      <div class="component-detail-card">
        <h5>${component}</h5>
        ${threadInfo}
        <p><strong>Messages:</strong> ${messageCount}</p>
      </div>`;

    if (asm) {
      let asmBody = `<p>Oracle ASM spawns short-lived OS threads for parallel disk I/O via <code>dbms_diskgroup.read</code>. 
        Each thread typically appears only a few times, logging its prepared SQL statement. These ${asm.poolCount} 
        ephemeral threads all used ASM handle ${asm.stmtNum} and have been grouped together.</p>`;
      html += buildCollapsibleSection('ASM Parallel Reader Pool', asmBody, { color: '#a78bfa', icon: '⛁', cls: 'asm-info-note' });
    }

    let aboutBody = `<p>${description}</p>`;
    if (lookFor) {
      aboutBody += `
        <div style="margin-top:8px;padding:6px 8px;background:rgba(59,130,246,0.08);border-left:2px solid #3b82f6;border-radius:0 4px 4px 0;">
          <strong style="font-size:0.7rem;color:#93c5fd;">What to look for</strong>
          <p style="margin:2px 0 0;font-size:0.72rem;color:#d1d5db;line-height:1.4;">${lookFor}</p>
        </div>`;
    }
    aboutBody += `
        <p style="margin-top: 8px; font-size: 0.7rem;">
          <a href="https://help.qlik.com/en-US/replicate/November2025/Content/Replicate/Main/Replicate%20Loggers/Loggers.htm" 
             target="_blank" style="color: #60a5fa; text-decoration: none;">
             Qlik Documentation ↗
          </a>
        </p>`;
    html += buildCollapsibleSection('About this Component', aboutBody, { color: '#818cf8', icon: 'ℹ' });

    logViewComponentInfoContent.innerHTML = html;
  }
  
  function performActivityQuickSearch() {
    const query = activityQuickSearch.value.trim();
    const logLines = threadLogView.querySelectorAll('.log-line');
    
    // Clear previous highlights
    logLines.forEach(line => {
      line.classList.remove('activity-search-match', 'activity-search-current');
      const text = line.dataset.originalText || line.textContent;
      line.textContent = text;
    });
    
    activityMatches = [];
    currentActivityMatchIndex = -1;
    
    if (query === '') {
      updateActivitySearchUI();
      return;
    }
    
    // Find matches (case-insensitive)
    const queryLower = query.toLowerCase();
    logLines.forEach((line, idx) => {
      const text = line.dataset.originalText || line.textContent;
      if (text.toLowerCase().includes(queryLower)) {
        activityMatches.push(idx);
        line.classList.add('activity-search-match');
        
        // Highlight the matching text
        highlightTextInLine(line, text, query);
      }
    });
    
    if (activityMatches.length > 0) {
      currentActivityMatchIndex = 0;
      scrollToActivityMatch(0);
    }
    
    updateActivitySearchUI();
  }
  
  function highlightTextInLine(lineElement, text, query) {
    const parts = text.split(new RegExp(`(${escapeRegex(query)})`, 'gi'));
    lineElement.textContent = '';
    
    parts.forEach(part => {
      if (part.toLowerCase() === query.toLowerCase()) {
        const span = document.createElement('span');
        span.className = 'activity-search-highlight';
        span.textContent = part;
        lineElement.appendChild(span);
      } else {
        lineElement.appendChild(document.createTextNode(part));
      }
    });
  }
  
  function escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }
  
  function navigateActivityMatch(direction) {
    if (activityMatches.length === 0) return;
    
    currentActivityMatchIndex += direction;
    
    if (currentActivityMatchIndex < 0) {
      currentActivityMatchIndex = activityMatches.length - 1;
    } else if (currentActivityMatchIndex >= activityMatches.length) {
      currentActivityMatchIndex = 0;
    }
    
    scrollToActivityMatch(currentActivityMatchIndex);
    updateActivitySearchUI();
  }
  
  function scrollToActivityMatch(index) {
    const logLines = Array.from(threadLogView.querySelectorAll('.log-line'));
    
    // Remove current highlight from all
    logLines.forEach(line => line.classList.remove('activity-search-current'));
    
    // Add current highlight to the target
    const lineIndex = activityMatches[index];
    const targetLine = logLines[lineIndex];
    
    if (targetLine) {
      targetLine.classList.add('activity-search-current');
      targetLine.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
  
  function updateActivitySearchUI() {
    if (activityMatches.length === 0) {
      activitySearchCount.textContent = '';
      activitySearchPrev.disabled = true;
      activitySearchNext.disabled = true;
    } else {
      activitySearchCount.textContent = `${currentActivityMatchIndex + 1} / ${activityMatches.length}`;
      activitySearchPrev.disabled = false;
      activitySearchNext.disabled = false;
    }
  }
  
  // Log Quick Search Functions
  function performLogQuickSearch() {
    const query = logQuickSearch.value.trim();
    const logLines = logPreview.querySelectorAll('.log-line');
    
    // Clear previous highlights
    logLines.forEach(line => {
      line.classList.remove('log-search-match', 'log-search-current');
      const text = line.dataset.originalText || line.textContent;
      // Check if this is a line with line number
      if (line.dataset.lineNumber) {
        line.innerHTML = `<span class="line-number">${line.dataset.lineNumber}</span>${text}`;
      } else {
        line.textContent = text;
      }
    });
    
    logMatches = [];
    currentLogMatchIndex = -1;
    
    if (query === '') {
      updateLogSearchUI();
      return;
    }
    
    // Find matches (case-insensitive)
    const queryLower = query.toLowerCase();
    logLines.forEach((line, idx) => {
      const text = line.dataset.originalText || line.textContent;
      if (text.toLowerCase().includes(queryLower)) {
        logMatches.push(idx);
        line.classList.add('log-search-match');
        
        // Highlight the matching text
        const lineNumber = line.dataset.lineNumber;
        const parts = text.split(new RegExp(`(${escapeRegex(query)})`, 'gi'));
        line.innerHTML = '';
        
        // Add line number if it exists
        if (lineNumber) {
          const lineNumSpan = document.createElement('span');
          lineNumSpan.className = 'line-number';
          lineNumSpan.textContent = lineNumber;
          line.appendChild(lineNumSpan);
        }
        
        // Add highlighted text
        parts.forEach(part => {
          if (part.toLowerCase() === query.toLowerCase()) {
            const span = document.createElement('span');
            span.className = 'log-search-highlight';
            span.textContent = part;
            line.appendChild(span);
          } else {
            line.appendChild(document.createTextNode(part));
          }
        });
      }
    });
    
    if (logMatches.length > 0) {
      currentLogMatchIndex = 0;
      scrollToLogMatch(0);
    }
    
    updateLogSearchUI();
  }
  
  function navigateLogMatch(direction) {
    if (logMatches.length === 0) return;
    
    currentLogMatchIndex += direction;
    
    if (currentLogMatchIndex < 0) {
      currentLogMatchIndex = logMatches.length - 1;
    } else if (currentLogMatchIndex >= logMatches.length) {
      currentLogMatchIndex = 0;
    }
    
    scrollToLogMatch(currentLogMatchIndex);
    updateLogSearchUI();
  }
  
  function scrollToLogMatch(index) {
    const logLines = Array.from(logPreview.querySelectorAll('.log-line'));
    
    // Remove current highlight from all
    logLines.forEach(line => line.classList.remove('log-search-current'));
    
    // Add current highlight to the target
    const lineIndex = logMatches[index];
    const targetLine = logLines[lineIndex];
    
    if (targetLine) {
      targetLine.classList.add('log-search-current');
      targetLine.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
  
  function updateLogSearchUI() {
    if (logMatches.length === 0) {
      logSearchCount.textContent = '';
      logSearchPrev.disabled = true;
      logSearchNext.disabled = true;
    } else {
      logSearchCount.textContent = `${currentLogMatchIndex + 1} / ${logMatches.length}`;
      logSearchPrev.disabled = false;
      logSearchNext.disabled = false;
    }
  }
  
  // Add Preset Button
  const addPresetBtn = document.getElementById('addPresetBtn');
  if (addPresetBtn) {
    addPresetBtn.addEventListener('click', () => {
      const pattern = prompt('Enter regex pattern:');
      if (pattern && pattern.trim()) {
        const label = prompt('Enter label for this pattern:');
        if (label && label.trim()) {
          addCustomPreset(pattern.trim(), label.trim());
        }
      }
    });
  }
  
  function addCustomPreset(pattern, label) {
    const presetTagsContainer = document.getElementById('presetTags');
    const newTag = document.createElement('span');
    newTag.className = 'preset-tag';
    newTag.setAttribute('data-pattern', pattern);
    newTag.textContent = label;
    newTag.title = pattern;
    newTag.addEventListener('click', () => {
      searchInput.value = pattern;
      performSearch();
    });
    
    // Add remove functionality on right-click
    newTag.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      showModal(
        'Remove Preset',
        `<p>Remove preset "<strong>${label}</strong>"?</p>`,
        () => newTag.remove(),
        { confirmText: 'Remove', danger: true }
      );
    });
    
    presetTagsContainer.appendChild(newTag);
  }

  // --- API Functions ---

  function fetchFileList() {
    fetch("/api/files")
      .then(res => res.json())
      .then(files => {
        // Merge with recent files from localStorage
        const recentFiles = getRecentFiles();
        
        // Create a map of files by id for quick lookup
        const fileMap = new Map();
        files.forEach(f => fileMap.set(f.id, f));
        
        // Sort: current file first, then by recent order
        const sortedFiles = [];
        
        // Add currently loaded file first if exists
        if (currentFileId && fileMap.has(currentFileId)) {
          sortedFiles.push(fileMap.get(currentFileId));
        }
        
        // Add recent files in order
        recentFiles.forEach(recentId => {
          if (recentId !== currentFileId && fileMap.has(recentId)) {
            sortedFiles.push(fileMap.get(recentId));
          }
        });
        
        // Add any remaining files not in recent list
        files.forEach(f => {
          if (!sortedFiles.find(sf => sf.id === f.id)) {
            sortedFiles.push(f);
          }
        });
        
        renderFileList(sortedFiles.slice(0, MAX_RECENT_FILES));
      });
  }
  
  // Track selected file (before loading)
  let selectedFileId = null;
  let filesCache = []; // Cache file list for metadata lookup
  
  function renderFileList(files) {
    filesCache = files; // Cache for metadata lookup
    fileList.innerHTML = "";
    if (files.length === 0) {
      fileList.innerHTML = '<li class="placeholder-text-small">No files loaded</li>';
      hideFileMetadataPanel();
      return;
    }
    
    files.forEach(f => {
      const li = document.createElement("li");
      // Active = currently loaded, Selected = clicked but not loaded
      let className = "recent-file-item";
      if (f.id === currentFileId) className += " active";
      if (f.id === selectedFileId && f.id !== currentFileId) className += " selected";
      li.className = className;
      li.dataset.fileId = f.id;
      
      // File icon SVG
      const iconSvg = document.createElement("span");
      iconSvg.innerHTML = `<svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" style="flex-shrink: 0; opacity: 0.5;">
        <path d="M14 4.5V14a2 2 0 01-2 2H4a2 2 0 01-2-2V2a2 2 0 012-2h5.5L14 4.5zm-3 0A1.5 1.5 0 019.5 3V1H4a1 1 0 00-1 1v12a1 1 0 001 1h8a1 1 0 001-1V4.5h-2z"/>
      </svg>`;
      
      const filenameSpan = document.createElement("span");
      filenameSpan.className = "recent-file-name";
      // Let CSS handle truncation with ellipsis - show full name, tooltip for very long names
      filenameSpan.textContent = f.filename;
      filenameSpan.title = f.filename;
      
      // Line count badge
      const linesSpan = document.createElement("span");
      linesSpan.className = "recent-file-lines";
      const lineCount = f.line_count || 0;
      linesSpan.textContent = lineCount > 1000 
        ? `${(lineCount / 1000).toFixed(1)}K` 
        : lineCount;
      linesSpan.title = `${lineCount.toLocaleString()} lines`;
      
      // Actions container
      const actionsDiv = document.createElement("div");
      actionsDiv.className = "recent-file-actions";
      actionsDiv.onclick = (e) => e.stopPropagation();
      
      // Reindex button
      const reindexBtn = document.createElement("button");
      reindexBtn.className = "recent-file-action-btn";
      reindexBtn.title = "Re-index this file";
      reindexBtn.innerHTML = `<svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor">
        <path fill-rule="evenodd" d="M8 3a5 5 0 104.546 2.914.5.5 0 01.908-.417A6 6 0 118 2v1z"/>
        <path d="M8 4.466V.534a.25.25 0 01.41-.192l2.36 1.966c.12.1.12.284 0 .384L8.41 4.658A.25.25 0 018 4.466z"/>
      </svg>`;
      reindexBtn.onclick = () => reindexFile(f.id, f.filename);
      
      // Remove button
      const removeBtn = document.createElement("button");
      removeBtn.className = "recent-file-action-btn recent-file-remove";
      removeBtn.title = "Remove from recent files";
      removeBtn.innerHTML = `<svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor">
        <path d="M4.646 4.646a.5.5 0 01.708 0L8 7.293l2.646-2.647a.5.5 0 01.708.708L8.707 8l2.647 2.646a.5.5 0 01-.708.708L8 8.707l-2.646 2.647a.5.5 0 01-.708-.708L7.293 8 4.646 5.354a.5.5 0 010-.708z"/>
      </svg>`;
      removeBtn.onclick = () => {
        removeFromRecentFiles(f.id);
        li.remove();
        if (selectedFileId === f.id) {
          selectedFileId = null;
          hideFileMetadataPanel();
        }
      };
      
      actionsDiv.appendChild(reindexBtn);
      actionsDiv.appendChild(removeBtn);
      
      // Single click to select, double-click or click selected to open
      li.onclick = () => {
        if (f.id === currentFileId) {
          // Already loaded, do nothing
          return;
        }
        if (f.id === selectedFileId) {
          // Already selected, load the file
          loadFile(f.id);
        } else {
          // Select this file
          selectFile(f.id);
        }
      };
      
      // Double-click to load directly
      li.ondblclick = () => {
        if (f.id !== currentFileId) {
          loadFile(f.id);
        }
      };
      
      li.appendChild(iconSvg);
      li.appendChild(filenameSpan);
      li.appendChild(linesSpan);
      li.appendChild(actionsDiv);
      fileList.appendChild(li);
    });
  }
  
  // Select a file (show metadata) without loading it
  function selectFile(fileId) {
    selectedFileId = fileId;
    
    // Update visual state
    document.querySelectorAll('.recent-file-item').forEach(item => {
      item.classList.remove('selected');
      if (item.dataset.fileId == fileId && fileId !== currentFileId) {
        item.classList.add('selected');
      }
    });
    
    // Find file in cache
    const file = filesCache.find(f => f.id === fileId);
    if (file) {
      showFileMetadataPanel(file);
    }
  }
  
  // Show file metadata panel
  function showFileMetadataPanel(file) {
    const panel = document.getElementById('fileMetadataPanel');
    if (!panel) return;
    
    panel.classList.remove('hidden');
    
    // Update metadata fields
    document.getElementById('metadataFileName').textContent = file.filename;
    document.getElementById('metadataFileName').title = file.filename;
    
    // Status
    const statusEl = document.getElementById('metadataStatus');
    statusEl.textContent = file.status || 'ready';
    statusEl.className = 'file-metadata-value';
    if (file.status === 'ready') statusEl.classList.add('status-ready');
    else if (file.status === 'indexing') statusEl.classList.add('status-indexing');
    else if (file.status === 'error') statusEl.classList.add('status-error');
    
    // Lines
    const lines = file.line_count || 0;
    document.getElementById('metadataLines').textContent = lines.toLocaleString();
    
    // Size
    const size = file.size_bytes || 0;
    let sizeText = '';
    if (size < 1024) sizeText = `${size} B`;
    else if (size < 1024 * 1024) sizeText = `${(size / 1024).toFixed(1)} KB`;
    else sizeText = `${(size / (1024 * 1024)).toFixed(1)} MB`;
    document.getElementById('metadataSize').textContent = sizeText;
    
    // Indexed date
    const indexed = file.indexed_at || file.created_at;
    document.getElementById('metadataIndexed').textContent = indexed 
      ? new Date(indexed).toLocaleDateString() 
      : '-';
    
    // Vectorized
    const vecEl = document.getElementById('metadataVectorized');
    vecEl.textContent = file.vectorized ? 'Yes' : 'No';
    vecEl.className = 'file-metadata-value' + (file.vectorized ? ' vectorized' : '');
    
    // Path
    const pathEl = document.getElementById('metadataPath');
    const path = file.file_path || file.local_path || '-';
    pathEl.textContent = path.length > 25 ? '...' + path.slice(-22) : path;
    pathEl.title = path;
    
    // Open button
    const openBtn = document.getElementById('metadataOpenBtn');
    openBtn.onclick = () => loadFile(file.id);
  }
  
  // Hide file metadata panel
  function hideFileMetadataPanel() {
    const panel = document.getElementById('fileMetadataPanel');
    if (panel) {
      panel.classList.add('hidden');
    }
  }
  
  // Recent files localStorage management
  function getRecentFiles() {
    try {
      const stored = localStorage.getItem(RECENT_FILES_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch (e) {
      return [];
    }
  }
  
  function addToRecentFiles(fileId) {
    let recent = getRecentFiles();
    // Remove if already exists
    recent = recent.filter(id => id !== fileId);
    // Add to front
    recent.unshift(fileId);
    // Keep only MAX_RECENT_FILES
    recent = recent.slice(0, MAX_RECENT_FILES);
    localStorage.setItem(RECENT_FILES_KEY, JSON.stringify(recent));
  }
  
  function removeFromRecentFiles(fileId) {
    let recent = getRecentFiles();
    recent = recent.filter(id => id !== fileId);
    localStorage.setItem(RECENT_FILES_KEY, JSON.stringify(recent));
  }
  
  function reindexFile(fileId, filename) {
    showModal(
      'Re-index File',
      `<p>Re-index "${filename}"?</p>
       <p style="margin-top: 10px; font-size: 0.85em; color: #9ca3af;">This will:</p>
       <ul style="font-size: 0.85em; color: #9ca3af; margin: 5px 0 0 20px;">
         <li>Clear existing indexes</li>
         <li>Re-parse the log file</li>
         <li>Update line numbers for plot navigation</li>
         <li>Take a moment to complete</li>
       </ul>
       <div style="margin-top: 15px; padding: 12px; background: rgba(139, 92, 246, 0.1); border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 6px;">
         <label style="display: flex; align-items: flex-start; gap: 10px; cursor: pointer;">
           <input type="checkbox" id="reembed-checkbox" style="margin-top: 3px; accent-color: #8b5cf6;">
           <div>
             <span style="color: #e2e8f0; font-weight: 500;">Re-embed for AI analysis</span>
             <p style="font-size: 0.8em; color: #9ca3af; margin-top: 4px;">
               Updates embeddings with improved PII sanitization. Recommended after sanitizer updates.
             </p>
           </div>
         </label>
       </div>`,
      () => {
        const reembed = document.getElementById('reembed-checkbox')?.checked || false;
        fileStatusDiv.textContent = `Re-indexing ${filename}...`;
        console.log('Re-indexing file:', fileId, 'reembed:', reembed);
    
    fetch(`/api/files/${fileId}/reindex`, {
      method: "POST",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reembed: reembed })
    })
    .then(res => {
      if (!res.ok) {
        return res.json().then(e => { throw new Error(e.detail) });
      }
      return res.json();
    })
    .then(data => {
      console.log('Re-indexing started:', data);
      fileStatusDiv.textContent = `Re-indexing ${filename}...`;
      fetchFileList();
      pollStatus(fileId);
    })
    .catch(err => {
      console.error('Re-index failed:', err);
      fileStatusDiv.textContent = `Re-index failed: ${err.message}`;
      showModal('Re-index Failed', `<p>Failed to re-index file:</p><p style="color: #ef4444; margin-top: 10px;">${err.message}</p>`, null);
    });
      }
    );
  }
  
  // Modal Dialog Functions
  function showModal(title, bodyHTML, onConfirm, options = {}) {
    modalTitle.textContent = title;
    modalBody.innerHTML = bodyHTML;
    modalOverlay.style.display = 'flex';
    
    // Options: confirmText, cancelText, danger (red confirm button)
    const { confirmText = 'Confirm', cancelText = 'Cancel', danger = false } = options;
    
    // If no confirm callback, it's just an info dialog
    if (!onConfirm) {
      modalConfirm.style.display = 'none';
      modalCancel.textContent = 'OK';
    } else {
      modalConfirm.style.display = 'block';
      modalCancel.textContent = cancelText;
      modalConfirm.textContent = confirmText;
      
      // Style danger buttons differently
      if (danger) {
        modalConfirm.style.background = 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)';
      } else {
        modalConfirm.style.background = 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)';
      }
    }
    
    // Remove old listeners by cloning and replacing
    const newConfirm = modalConfirm.cloneNode(true);
    const newCancel = modalCancel.cloneNode(true);
    modalConfirm.parentNode.replaceChild(newConfirm, modalConfirm);
    modalCancel.parentNode.replaceChild(newCancel, modalCancel);
    
    // Update references to the new elements
    modalConfirm = newConfirm;
    modalCancel = newCancel;
    
    // Add new listeners
    modalConfirm.addEventListener('click', () => {
      modalOverlay.style.display = 'none';
      if (onConfirm) onConfirm();
    });
    
    modalCancel.addEventListener('click', () => {
      modalOverlay.style.display = 'none';
    });
    
    // Close on overlay click
    modalOverlay.addEventListener('click', (e) => {
      if (e.target === modalOverlay) {
        modalOverlay.style.display = 'none';
      }
    });
  }
  
  // Make showModal globally accessible for other scripts
  window.showModal = showModal;
  
  // Global alert replacement
  window.showAlert = function(title, message) {
    showModal(title, `<p>${message}</p>`, null);
  };
  
  // Global confirm replacement (returns a Promise)
  window.showConfirm = function(title, message, options = {}) {
    return new Promise((resolve) => {
      showModal(title, `<p>${message}</p>`, () => resolve(true), options);
      // Handle cancel case - we need to detect modal close
      const checkClosed = setInterval(() => {
        if (modalOverlay.style.display === 'none') {
          clearInterval(checkClosed);
          // Only resolve false if not already resolved via confirm
        }
      }, 100);
    });
  };

  function registerLocalFile(path) {
      fileStatusDiv.textContent = "Registering file...";
      fetch("/api/files/local", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({path: path})
      })
      .then(res => {
          if (!res.ok) return res.json().then(e => { throw new Error(e.detail) });
          return res.json();
      })
      .then(data => {
          fetchFileList();
          pollStatus(data.id);
      })
      .catch(err => {
          console.error(err);
          fileStatusDiv.textContent = `Error: ${err.message}`;
          showModal('Error', `<p style="color: #ef4444;">${err.message}</p>`, null);
      });
  }

  function uploadFile(file) {
    const formData = new FormData();
    formData.append("file", file);

    fileStatusDiv.textContent = "Uploading...";
    
    fetch("/api/upload", {
      method: "POST",
      body: formData
    })
    .then(res => res.json())
    .then(data => {
      fetchFileList();
      pollStatus(data.id);
    })
    .catch(err => {
      console.error(err);
      fileStatusDiv.textContent = "Upload failed.";
    });
  }

  function pollStatus(id) {
    currentFileId = id;
    fileStatusDiv.textContent = "Indexing...";
    
    // Clear interval if exists
    if (window.pollInterval) clearInterval(window.pollInterval);
    
    window.pollInterval = setInterval(() => {
      fetch(`/api/files/${id}`)
        .then(res => res.json())
        .then(data => {
          // Show detailed status
          let statusText = `Status: ${data.status}`;
          if (data.line_count) {
            statusText += ` (${data.line_count.toLocaleString()} lines)`;
          }
          if (data.status === 'indexing') {
            statusText = `📊 Indexing... (${data.line_count ? data.line_count.toLocaleString() : '0'} lines)`;
          } else if (data.status === 'vectorizing') {
            statusText = `🔮 Creating embeddings... (${data.line_count ? data.line_count.toLocaleString() : '0'} lines)`;
          }
          fileStatusDiv.textContent = statusText;
          
          if (data.status === "ready") {
            clearInterval(window.pollInterval);
            loadFile(id);
          } else if (data.status === "error") {
            clearInterval(window.pollInterval);
            fileStatusDiv.textContent = `Error: ${data.error}`;
          }
        });
    }, 1000);
  }

  function loadFile(id) {
    // Clear all state from previous file
    clearAllFileData();
    
    currentFileId = id;
    selectedFileId = null; // Clear selection since file is now loaded
    hideFileMetadataPanel();
    
    // Show file-dependent tabs
    document.querySelectorAll('.file-dependent-tab').forEach(t => t.style.display = '');
    
    // Dispatch fileLoaded event for components that need to know
    document.dispatchEvent(new CustomEvent('fileLoaded', { 
      detail: { fileId: id } 
    }));
    
    // Update AI Assistant with new file
    if (window.aiAssistant) {
      window.aiAssistant.setFileId(id);
    }
    
    // Update Saved Findings Manager with new file
    if (window.savedFindingsManager) {
      window.savedFindingsManager.currentFileId = id;
      window.savedFindingsManager.loadFindings();
    }
    
    // Add to recent files
    addToRecentFiles(id);
    
    // Update file list to show active state
    fetchFileList();
    
    // 1. Get Summary (includes filename)
    fetch(`/api/files/${id}/summary`)
      .then(res => res.json())
      .then(data => {
        // Store the filename for exports
        if (data.filename) {
          currentFileName = data.filename.replace(/\.[^.]+$/, ''); // Remove extension
        }
        
        // Update file info bar
        updateFileInfoBar(data.filename, data.file_size, data.line_count);
        
        updateStats(data);
        renderAnalysis(data);
        
        // Auto-switch to search panel after file is loaded
        switchToSearchPanel();
      });

    // 2. Get Initial Lines
    fetchLogLines(0, 150, false);
  }
  
  // Update file info bar at top of app
  function updateFileInfoBar(filename, fileSize, lineCount) {
    const fileInfoBar = document.getElementById('fileInfoBar');
    const fileInfoName = document.getElementById('fileInfoName');
    const fileInfoSize = document.getElementById('fileInfoSize');
    const fileInfoLines = document.getElementById('fileInfoLines');
    
    if (fileInfoBar && fileInfoName) {
      fileInfoBar.style.display = 'flex';
      fileInfoName.textContent = filename || 'Unknown file';
      
      if (fileInfoSize && fileSize) {
        // Format file size
        let sizeText = '';
        if (fileSize < 1024) {
          sizeText = `${fileSize} B`;
        } else if (fileSize < 1024 * 1024) {
          sizeText = `${(fileSize / 1024).toFixed(1)} KB`;
        } else if (fileSize < 1024 * 1024 * 1024) {
          sizeText = `${(fileSize / (1024 * 1024)).toFixed(1)} MB`;
        } else {
          sizeText = `${(fileSize / (1024 * 1024 * 1024)).toFixed(2)} GB`;
        }
        fileInfoSize.textContent = sizeText;
      }
      
      if (fileInfoLines && lineCount) {
        fileInfoLines.textContent = `${lineCount.toLocaleString()} lines`;
      }
    }
  }
  
  // Clear all data when loading a new file (or closing the log when showWelcomeAfter is true)
  function clearAllFileData(options = {}) {
    const { showWelcomeAfter = false } = options;

    // Reset toggle checkboxes
    const showTimeGapsEl = document.getElementById('showTimeGaps');
    if (showTimeGapsEl) showTimeGapsEl.checked = false;
    const showTimeGapsAnalysisEl = document.getElementById('showTimeGapsAnalysis');
    if (showTimeGapsAnalysisEl) showTimeGapsAnalysisEl.checked = false;
    const hideNoiseEl = document.getElementById('hideNoise');
    if (hideNoiseEl) hideNoiseEl.checked = false;

    // Clear log preview
    if (logPreview) {
      if (showWelcomeAfter) {
        showLogPlaceholder();
      } else {
        hideLogPlaceholder();
        logPreview.innerHTML = '<div class="log-line">Loading...</div>';
      }
    }
    
    // Clear compact stats panel
    const statSamples = document.getElementById('statSamples');
    const statSource = document.getElementById('statSource');
    const statTarget = document.getElementById('statTarget');
    const statHandling = document.getElementById('statHandling');
    if (statSamples) statSamples.style.display = 'none';
    if (statSource) statSource.style.display = 'none';
    if (statTarget) statTarget.style.display = 'none';
    if (statHandling) statHandling.style.display = 'none';
    
    // Clear search results
    const searchResults = document.getElementById('searchResults');
    if (searchResults) {
      searchResults.innerHTML = '';
    }
    lastSearchMatches = [];
    
    // Clear all search tabs
    searchTabs = [];
    searchTabIdCounter = 0;
    visibleSearchTabIndex = 0;
    const logViewTabs = document.getElementById('logViewTabs');
    if (logViewTabs) {
      // Remove all search tabs, keep only "All Lines"
      const allSearchTabs = logViewTabs.querySelectorAll('.log-view-tab[data-view="search"]');
      allSearchTabs.forEach(tab => tab.remove());
    }
    updateSearchTabsOverflow();
    
    // Hide export button
    const exportBtn = document.getElementById('exportSearchBtn');
    if (exportBtn) {
      exportBtn.style.display = 'none';
    }
    
    // Clear thread log view
    if (threadLogView) {
      threadLogView.innerHTML = '<div class="placeholder-text">Select a thread to view its activity.</div>';
    }
    
    // Clear thread list
    if (threadListDiv) {
      threadListDiv.innerHTML = '';
    }
    
    // Clear component info
    if (componentInfo) {
      componentInfo.innerHTML = '';
    }
    
    // Clear findings (optional - you might want to keep these across files)
    // findings = [];
    // renderFindings();
    
    // Clear bulk map view
    const bulkMapMainView = document.getElementById('bulkMapMainView');
    if (bulkMapMainView) {
      bulkMapMainView.style.display = 'none';
      const content = document.getElementById('bulkMapMainContent');
      if (content) content.innerHTML = '<p class="placeholder-text-small">Loading bulk map...</p>';
    }
    
    // Clear bulk activity view
    const bulkActivityMainView = document.getElementById('bulkActivityMainView');
    if (bulkActivityMainView) {
      bulkActivityMainView.style.display = 'none';
      const content = document.getElementById('bulkActivityMainContent');
      if (content) content.innerHTML = '<p class="placeholder-text-small">Loading bulk activity...</p>';
    }
    
    // Clear file operations view
    const fileOperationsMainView = document.getElementById('fileOperationsMainView');
    if (fileOperationsMainView) {
      fileOperationsMainView.style.display = 'none';
      const content = document.getElementById('fileOperationsMainContent');
      if (content) content.innerHTML = '<p class="placeholder-text-small">Loading file operations...</p>';
    }
    
    // Clear latency graph
    const latencyGraph = document.getElementById('latencyGraph');
    if (latencyGraph) {
      latencyGraph.innerHTML = '<p class="placeholder-text">Loading latency data...</p>';
    }
    
    // Reset graph section to collapsed (will expand when data loads)
    const graphSection = document.querySelector('#log-tab .graph-section');
    if (graphSection) {
      graphSection.classList.add('collapsed');
    }
    
    // Hide time range notification if visible
    const timeRangeNotification = document.getElementById('timeRangeNotification');
    if (timeRangeNotification) {
      timeRangeNotification.style.display = 'none';
    }
    
    // Reset available reports
    const bulkMapLink = document.getElementById('bulkMapLink');
    const bulkActivityLink = document.getElementById('bulkActivityLink');
    const fileOperationsLink = document.getElementById('fileOperationsLink');
    const issuesLink = document.getElementById('issuesLink');
    const logSummaryLink = document.getElementById('logSummaryLink');
    if (bulkMapLink) bulkMapLink.style.display = 'none';
    if (bulkActivityLink) bulkActivityLink.style.display = 'none';
    if (fileOperationsLink) fileOperationsLink.style.display = 'none';
    if (issuesLink) issuesLink.style.display = 'none';
    if (logSummaryLink) logSummaryLink.style.display = 'none';
    const logSummaryNewBadge = document.getElementById('logSummaryNewBadge');
    if (logSummaryNewBadge) logSummaryNewBadge.style.display = 'none';
    const performanceCockpitLink = document.getElementById('performanceCockpitLink');
    if (performanceCockpitLink) performanceCockpitLink.style.display = 'none';
    
    // Reset performance cockpit data
    window.performanceCockpitData = null;
    
    // Clear issues view
    const issuesMainView = document.getElementById('issuesMainView');
    if (issuesMainView) {
      issuesMainView.style.display = 'none';
      const content = document.getElementById('issuesMainContent');
      if (content) content.innerHTML = '<p class="placeholder-text-small">Loading possible issues...</p>';
    }
    
    // Clear log summary view
    const logSummaryMainView = document.getElementById('logSummaryMainView');
    if (logSummaryMainView) {
      logSummaryMainView.style.display = 'none';
      const content = document.getElementById('logSummaryMainContent');
      if (content) content.innerHTML = '<p class="placeholder-text-small">Loading log summary...</p>';
    }
    
    // Hide floating export button
    const floatingExportBtn = document.getElementById('floatingExportBtn');
    if (floatingExportBtn) {
      floatingExportBtn.style.display = 'none';
    }
    
    // Reset view state
    currentView = 'all';
    currentLogStart = 0;
    totalLogLines = 0;
    loadedLinesStart = 0;
    loadedLinesEnd = 0;
    highlightedLines = {};
    lastFetchStart = -1;
    lastFetchDirection = null;
    
    // Clear global data stores
    window.bulkMapData = null;
    window.bulkMapStats = null;
    window.bulkMapInsights = null;
    window._tempPerTableStats = null;
    window._tempBulkMapByTable = null;
    window._tempFileOperations = null;
    window._tempFileOpsStats = null;
    window._tempFileOpsInsights = null;
    window.issuesData = null;
    window.logSummaryData = null;
    window.analysisTabFirstClick = true;
    
    // Clear active report link styling
    const reportLinks = document.querySelectorAll('.report-link');
    reportLinks.forEach(link => link.classList.remove('active'));

    if (showWelcomeAfter && loadedCountSpan) {
      loadedCountSpan.textContent = '0';
    }
  }

  function closeLogFile() {
    if (!currentFileId) return;
    if (window.pollInterval) {
      clearInterval(window.pollInterval);
      window.pollInterval = null;
    }
    isFetchingLog = false;
    currentFileId = null;
    currentFileName = '';
    selectedFileId = null;
    const fileInfoBar = document.getElementById('fileInfoBar');
    if (fileInfoBar) fileInfoBar.style.display = 'none';
    if (fileStatusDiv) fileStatusDiv.textContent = '';
    hideFileMetadataPanel();
    document.querySelectorAll('.file-dependent-tab').forEach((t) => {
      t.style.display = 'none';
    });
    if (window.aiAssistant) window.aiAssistant.setFileId(null);
    if (window.aiReportManager && typeof window.aiReportManager.setFileId === 'function') {
      window.aiReportManager.setFileId(null);
    }
    document.dispatchEvent(new CustomEvent('fileClosed'));
    clearAllFileData({ showWelcomeAfter: true });
    fetchFileList();
    const logTabBtn = document.querySelector('.tab-btn[data-tab="log-tab"]');
    if (logTabBtn) logTabBtn.click();
  }

  function fetchLogLines(start, limit, append, direction = 'down') {
    if (!currentFileId || isFetchingLog) return;
    isFetchingLog = true;

    console.log(`[fetchLogLines] start=${start}, limit=${limit}, append=${append}, direction=${direction}`);

    fetch(`/api/files/${currentFileId}/lines?start=${start}&limit=${limit}`)
      .then(res => res.json())
      .then(data => {
        console.log(`[fetchLogLines] Response: start=${data.start}, end=${data.end}, lines=${data.lines.length}, total=${data.total}`);
        
        currentLogStart = data.start;
        totalLogLines = data.total;
        loadedCountSpan.textContent = totalLogLines;
        
        if (!append) {
          // Fresh load - reset the loaded range
          loadedLinesStart = data.start;
          loadedLinesEnd = data.start + data.lines.length;
          renderLines(data.lines, false, data.start);
        } else if (direction === 'up') {
          // Prepend lines when scrolling up - only if we got lines
          if (data.lines.length > 0) {
            loadedLinesStart = data.start;
            prependLines(data.lines, data.start);
          }
        } else {
          // Append lines when scrolling down - only if we got new lines
          if (data.lines.length > 0) {
            loadedLinesEnd = data.start + data.lines.length;
            renderLines(data.lines, true, data.start);
          } else {
            // No more lines - mark as fully loaded
            loadedLinesEnd = totalLogLines;
          }
        }
        
        console.log(`[fetchLogLines] After: loadedLinesStart=${loadedLinesStart}, loadedLinesEnd=${loadedLinesEnd}, totalLogLines=${totalLogLines}`);
        isFetchingLog = false;
      })
      .catch(err => {
        console.error('[fetchLogLines] Error:', err);
        isFetchingLog = false;
      });
  }
  
  // Prepend lines to the log view (for upward scrolling)
  function prependLines(lines, startIdx) {
    if (lines.length === 0) return;
    
    // Save current scroll position
    const scrollHeightBefore = logPreview.scrollHeight;
    
    // Extract timestamps from first existing line if present
    let lastTimestamp = null;
    
    // Create a document fragment for better performance
    const fragment = document.createDocumentFragment();
    
    lines.forEach((line, idx) => {
      const div = document.createElement("div");
      div.className = "log-line";
      const lineNumber = startIdx + idx + 1;
      const lineIndex = startIdx + idx;
      div.dataset.idx = lineIndex;
      div.dataset.lineNumber = lineNumber;
      div.dataset.originalText = line;
      
      // Create line number span
      const lineNumSpan = document.createElement("span");
      lineNumSpan.className = "line-number";
      lineNumSpan.textContent = lineNumber;
      div.appendChild(lineNumSpan);
      
      // Check if this line has a stored highlight
      if (highlightedLines[lineIndex]) {
        div.classList.add(`highlight-${highlightedLines[lineIndex]}`);
        // Add highlight dot
        const dot = document.createElement("span");
        dot.className = `highlight-dot highlight-dot-${highlightedLines[lineIndex]}`;
        dot.title = `Click to remove ${highlightedLines[lineIndex]} highlight`;
        dot.onclick = (e) => {
          e.stopPropagation();
          removeHighlightFromLine(div, lineIndex);
        };
        div.insertBefore(dot, lineNumSpan);
      }
      
      // Apply syntax highlighting if available
      if (window.LogColors && window.LogColors.isEnabled()) {
        const contentSpan = document.createElement("span");
        contentSpan.innerHTML = window.LogColors.highlightLine(line);
        div.appendChild(contentSpan);
      } else {
        div.appendChild(document.createTextNode(line));
      }
      
      // Add warning/error class for background highlighting
      if (line.includes(']W:')) {
        div.classList.add('warning-line');
      } else if (line.includes(']E:')) {
        div.classList.add('error-line');
      }
      
      // Calculate time gap
      const tsMatch = line.match(/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})/);
      if (tsMatch) {
        const currentTimestamp = parseTimestampFast(tsMatch[1]);
        if (lastTimestamp) {
          const timeDiff = (currentTimestamp - lastTimestamp) / 1000;
          div.dataset.timeGap = timeDiff;
          div.dataset.gapSize = timeDiff < 1 ? 'small' : timeDiff < 10 ? 'medium' : 'large';
        }
        lastTimestamp = currentTimestamp;
      }

      fragment.appendChild(div);
    });

    logPreview.insertBefore(fragment, logPreview.firstChild);

    const scrollHeightAfter = logPreview.scrollHeight;
    logPreview.scrollTop += (scrollHeightAfter - scrollHeightBefore);

    if (document.getElementById('showTimeGaps')?.checked) {
      applyTimeGapsToLines(logPreview, true);
    }

    applySearchHighlightsToNewLines();

    if (document.getElementById('hideNoise')?.checked) {
      applyHideNoise();
    }
  }

  // Load log lines within a specific range (for latency graph time selection).
  // Optional timeRange: { start: Date, end: Date } for display in the notification.
  function loadLogLinesInRange(startLine, endLine, timeRange) {
    if (!currentFileId || isFetchingLog) return;
    isFetchingLog = true;
    
    const limit = endLine - startLine + 1;
    
    // Switch to All Lines tab and update view state
    const logViewTabs = document.getElementById('logViewTabs');
    const allLinesTab = logViewTabs.querySelector('.log-view-tab[data-view="all"]');
    if (allLinesTab) {
      logViewTabs.querySelectorAll('.log-view-tab').forEach(t => t.classList.remove('active'));
      allLinesTab.classList.add('active');
    }
    currentView = 'all';
    
    fetch(`/api/files/${currentFileId}/lines?start=${startLine}&limit=${limit}`)
      .then(res => res.json())
      .then(data => {
        currentLogStart = data.start;
        totalLogLines = data.total;
        loadedLinesStart = data.start;
        loadedLinesEnd = data.start + data.lines.length;
        
        // Update the count display to show the range
        loadedCountSpan.textContent = `${data.lines.length} of ${data.total}`;
        
        renderLines(data.lines, false, data.start);
        isFetchingLog = false;
        
        // Show notification about filtered view
        showTimeRangeNotification(startLine, endLine, data.lines.length, data.total, timeRange);
      })
      .catch(err => isFetchingLog = false);
  }
  
  // Show notification that log is filtered to a time range
  function showTimeRangeNotification(startLine, endLine, loaded, total, timeRange) {
    // Check if notification already exists
    let notification = document.getElementById('timeRangeNotification');
    if (!notification) {
      notification = document.createElement('div');
      notification.id = 'timeRangeNotification';
      notification.className = 'time-range-notification';
      logPreview.parentNode.insertBefore(notification, logPreview);
    }

    let label = `Showing lines ${startLine + 1} - ${endLine + 1} (${loaded} of ${total})`;
    if (timeRange && timeRange.start && timeRange.end) {
      const fmt = d => d.toISOString().replace('T', ' ').substring(0, 19);
      label += ` | ${fmt(timeRange.start)} → ${fmt(timeRange.end)}`;
    }
    
    notification.innerHTML = `
      <span>📊 ${label}</span>
      <button id="clearTimeRangeFilter" class="small-btn" style="margin-left: 10px;">Load All Lines</button>
    `;
    notification.style.display = 'flex';
    
    document.getElementById('clearTimeRangeFilter').addEventListener('click', () => {
      notification.style.display = 'none';
      fetchLogLines(0, 150, false);
    });
  }

  function performSearch() {
    if (!currentFileId) return;
    const q = searchInput.value;
    if (!q) return;

    const searchResultsDiv = document.getElementById('searchResults');
    const searchResultsHeader = document.getElementById('searchResultsHeader');
    const searchResultsCount = document.getElementById('searchResultsCount');
    
    searchResultsDiv.innerHTML = "Searching...";
    if (searchResultsHeader) searchResultsHeader.style.display = 'none';
    
    fetch(`/api/files/${currentFileId}/search?q=${encodeURIComponent(q)}&limit=50`)
      .then(res => res.json())
      .then(matches => {
        searchResultsDiv.innerHTML = "";
        if (matches.length === 0) {
          searchResultsDiv.innerHTML = '<p class="placeholder-text-small">No matches found.</p>';
          lastSearchMatches = [];
          document.getElementById('exportSearchBtn').style.display = 'none';
          if (searchResultsHeader) searchResultsHeader.style.display = 'none';
          return;
        }
        
        // Store matches globally for highlighting in All Lines view
        lastSearchMatches = matches;
        
        // Show search results header with count
        if (searchResultsHeader) {
          searchResultsHeader.style.display = 'flex';
          searchResultsCount.textContent = `${matches.length} match${matches.length === 1 ? '' : 'es'}`;
        }
        
        // Show export button
        document.getElementById('exportSearchBtn').style.display = 'flex';
        
        const ul = document.createElement("ul");
        ul.style.listStyle = "none";
        ul.style.padding = "0";
        ul.style.margin = "0";
        
        matches.forEach(m => {
          const li = document.createElement("li");
          li.className = "search-result-item";
          li.textContent = `Line ${m.line + 1}: ${m.text.substring(0, 100)}`;
          
          li.onclick = () => {
             // Jump to line and highlight it
             jumpToLineAndHighlight(m.line, m.text);
          };
          ul.appendChild(li);
        });
        searchResultsDiv.appendChild(ul);
        
        // Create a search results tab (now supports multiple)
        createSearchResultsTab(matches, q);
      })
      .catch(err => {
        console.error('Search error:', err);
        searchResultsDiv.innerHTML = '<p class="placeholder-text-small">Search failed.</p>';
        if (searchResultsHeader) searchResultsHeader.style.display = 'none';
      });
  }
  
  // Export search results to text file
  function exportSearchResults() {
    if (lastSearchMatches.length === 0) return;
    
    const searchQuery = searchInput.value || 'search';
    const content = lastSearchMatches.map(m => `Line ${m.line + 1}: ${m.text}`).join('\n');
    
    // Create filename: logfilename_searchterm.txt (sanitized)
    const sanitizedQuery = searchQuery.replace(/[^a-z0-9]/gi, '_').substring(0, 50);
    const baseFilename = currentFileName || 'log';
    const filename = `${baseFilename}_${sanitizedQuery}.txt`;
    
    // Check if running in PyWebView
    if (window.pywebview && window.pywebview.api && window.pywebview.api.save_file) {
      window.pywebview.api.save_file(filename, content).then(result => {
        if (result) {
          console.log('File saved successfully');
        }
      }).catch(err => {
        console.error('Failed to save file:', err);
      });
    } else {
      // Browser fallback
      const blob = new Blob([content], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  }
  
  // Initialize export button
  const exportSearchBtn = document.getElementById('exportSearchBtn');
  if (exportSearchBtn) {
    exportSearchBtn.addEventListener('click', exportSearchResults);
  }
  
  function jumpToLineAndHighlight(lineNum, text) {
    console.log(`[jumpToLineAndHighlight] lineNum=${lineNum}, totalLogLines=${totalLogLines}`);
    
    // Switch to "All Lines" tab first
    const logViewTabs = document.getElementById('logViewTabs');
    const allLinesTab = logViewTabs.querySelector('.log-view-tab[data-view="all"]');
    if (allLinesTab) {
      logViewTabs.querySelectorAll('.log-view-tab').forEach(t => t.classList.remove('active'));
      allLinesTab.classList.add('active');
    }
    currentView = 'all';
    
    // Use the centered read API for efficient jumping
    if (!currentFileId || isFetchingLog) return;
    isFetchingLog = true;
    
    // Reset last fetch tracker
    lastFetchStart = -1;
    lastFetchDirection = null;
    
    fetch(`/api/files/${currentFileId}/lines?center=${lineNum}&before=50&after=50`)
      .then(res => res.json())
      .then(data => {
        console.log(`[jumpToLineAndHighlight] Response: start=${data.start}, end=${data.end}, lines=${data.lines.length}, total=${data.total}`);
        
        currentLogStart = data.start;
        totalLogLines = data.total;
        loadedLinesStart = data.start;
        loadedLinesEnd = data.end || (data.start + data.lines.length);
        loadedCountSpan.textContent = totalLogLines;
        
        console.log(`[jumpToLineAndHighlight] After: loadedLinesStart=${loadedLinesStart}, loadedLinesEnd=${loadedLinesEnd}`);
        
        renderLines(data.lines, false, data.start);
        isFetchingLog = false;
        
        // Highlight the target line after rendering
        setTimeout(() => {
          const logLines = logPreview.querySelectorAll('.log-line');
          logLines.forEach(line => {
            line.classList.remove('selected-line');
            if (line.dataset.idx == lineNum) {
              line.classList.add('selected-line');
              line.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
          });
        }, 100);
      })
      .catch(err => {
        console.error('[jumpToLineAndHighlight] Failed:', err);
        isFetchingLog = false;
      });
  }
  
  function createSearchResultsTab(matches, query) {
    const logViewTabs = document.getElementById('logViewTabs');
    
    // Create unique tab ID
    const tabId = ++searchTabIdCounter;
    
    // Add to search tabs array
    searchTabs.push({
      id: tabId,
      query: query,
      matches: matches
    });
    
    // Create new search results tab
    const searchTab = document.createElement('button');
    searchTab.className = 'log-view-tab';
    searchTab.dataset.view = 'search';
    searchTab.dataset.tabId = tabId;
    
    // Truncate query for display
    const displayQuery = query.length > 15 ? query.substring(0, 15) + '...' : query;
    searchTab.innerHTML = `
      <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" style="opacity: 0.7;">
        <path d="M11.742 10.344a6.5 6.5 0 10-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 001.415-1.414l-3.85-3.85a1.007 1.007 0 00-.115-.1zM12 6.5a5.5 5.5 0 11-11 0 5.5 5.5 0 0111 0z"/>
      </svg>
      ${displayQuery} (${matches.length})
      <span class="close-tab-btn" title="Close this search tab">×</span>
    `;
    searchTab.title = `Search: ${query} (${matches.length} results)`;
    
    // Add click handler for tab
    searchTab.addEventListener('click', (e) => {
      if (e.target.classList.contains('close-tab-btn')) {
        removeSearchTab(tabId);
        return;
      }
      
      activateSearchTab(tabId);
    });
    
    // Add the tab
    logViewTabs.appendChild(searchTab);
    
    // Make "All Lines" tab clickable to return to full log view
    const allLinesTab = logViewTabs.querySelector('.log-view-tab[data-view="all"]');
    if (allLinesTab && !allLinesTab.hasAttribute('data-listener')) {
      allLinesTab.setAttribute('data-listener', 'true');
      allLinesTab.addEventListener('click', () => {
        currentView = 'all';
        logViewTabs.querySelectorAll('.log-view-tab').forEach(t => t.classList.remove('active'));
        allLinesTab.classList.add('active');
        
        // Hide floating export button when not in search view
        const floatingExportBtn = document.getElementById('floatingExportBtn');
        if (floatingExportBtn) {
          floatingExportBtn.style.display = 'none';
        }
        
        fetchLogLines(0, 150, false);
        // Apply search highlights after loading lines
        setTimeout(() => {
          applySearchHighlightsToAllLines();
        }, 300);
      });
    }
    
    // Update overflow indicator
    updateSearchTabsOverflow();
    
    // Automatically switch to the search results tab
    activateSearchTab(tabId);
  }
  
  function activateSearchTab(tabId) {
    const logViewTabs = document.getElementById('logViewTabs');
    const tabData = searchTabs.find(t => t.id === tabId);
    if (!tabData) return;
    
    // Switch to search results view
    currentView = 'search';
    logViewTabs.querySelectorAll('.log-view-tab').forEach(t => t.classList.remove('active'));
    
    const searchTab = logViewTabs.querySelector(`.log-view-tab[data-tab-id="${tabId}"]`);
    if (searchTab) {
      searchTab.classList.add('active');
    }
    
    // Show floating export button
    const floatingExportBtn = document.getElementById('floatingExportBtn');
    if (floatingExportBtn) {
      floatingExportBtn.style.display = 'flex';
    }
    
    // Store current matches for export
    lastSearchMatches = tabData.matches;
    
    // Display only search results - CLEAR FIRST!
    hideLogPlaceholder();
    logPreview.innerHTML = "";
    
    tabData.matches.forEach(m => {
      const div = document.createElement("div");
      div.className = "log-line search-result-line";
      div.dataset.idx = m.line;
      div.dataset.originalText = m.text;
      
      // Create line number span and text content (like All Lines view)
      const lineNumSpan = document.createElement("span");
      lineNumSpan.className = "line-number";
      lineNumSpan.textContent = m.line + 1; // Line numbers start from 1
      div.appendChild(lineNumSpan);
      div.appendChild(document.createTextNode(m.text));
      
      // Left-click: allow text selection, double-click navigates to line in All Lines
      div.addEventListener("dblclick", () => {
        // Switch back to all lines and jump to this line
        const allLinesTab = logViewTabs.querySelector('.log-view-tab[data-view="all"]');
        if (allLinesTab) allLinesTab.click();
        jumpToLineAndHighlight(m.line, m.text);
      });
      
      logPreview.appendChild(div);
    });
  }
  
  function removeSearchTab(tabId) {
    const logViewTabs = document.getElementById('logViewTabs');
    
    // Remove from array
    searchTabs = searchTabs.filter(t => t.id !== tabId);
    
    // Remove tab element
    const tabElement = logViewTabs.querySelector(`.log-view-tab[data-tab-id="${tabId}"]`);
    if (tabElement) {
      const wasActive = tabElement.classList.contains('active');
      tabElement.remove();
      
      // If this was the active tab, switch to All Lines or another search tab
      if (wasActive) {
        if (searchTabs.length > 0) {
          activateSearchTab(searchTabs[searchTabs.length - 1].id);
        } else {
          currentView = 'all';
          const allLinesTab = logViewTabs.querySelector('.log-view-tab[data-view="all"]');
          if (allLinesTab) {
            allLinesTab.click();
          }
        }
      }
    }
    
    updateSearchTabsOverflow();
  }
  
  function updateSearchTabsOverflow() {
    const overflowDiv = document.getElementById('searchTabsOverflow');
    const countSpan = document.getElementById('searchTabsCount');
    const prevBtn = document.getElementById('searchTabsPrev');
    const nextBtn = document.getElementById('searchTabsNext');
    
    if (!overflowDiv) return;
    
    if (searchTabs.length > MAX_VISIBLE_SEARCH_TABS) {
      overflowDiv.style.display = 'flex';
      countSpan.textContent = `${searchTabs.length} tabs`;
      
      // Update visibility of tabs
      const logViewTabs = document.getElementById('logViewTabs');
      const allSearchTabElements = logViewTabs.querySelectorAll('.log-view-tab[data-view="search"]');
      
      allSearchTabElements.forEach((tab, index) => {
        if (index >= visibleSearchTabIndex && index < visibleSearchTabIndex + MAX_VISIBLE_SEARCH_TABS) {
          tab.style.display = '';
        } else {
          tab.style.display = 'none';
        }
      });
      
      prevBtn.disabled = visibleSearchTabIndex === 0;
      nextBtn.disabled = visibleSearchTabIndex + MAX_VISIBLE_SEARCH_TABS >= searchTabs.length;
    } else {
      overflowDiv.style.display = 'none';
      // Show all tabs
      const logViewTabs = document.getElementById('logViewTabs');
      logViewTabs.querySelectorAll('.log-view-tab[data-view="search"]').forEach(tab => {
        tab.style.display = '';
      });
    }
  }
  
  // Search tabs navigation
  const searchTabsPrev = document.getElementById('searchTabsPrev');
  const searchTabsNext = document.getElementById('searchTabsNext');
  
  if (searchTabsPrev) {
    searchTabsPrev.addEventListener('click', () => {
      if (visibleSearchTabIndex > 0) {
        visibleSearchTabIndex--;
        updateSearchTabsOverflow();
      }
    });
  }
  
  if (searchTabsNext) {
    searchTabsNext.addEventListener('click', () => {
      if (visibleSearchTabIndex + MAX_VISIBLE_SEARCH_TABS < searchTabs.length) {
        visibleSearchTabIndex++;
        updateSearchTabsOverflow();
      }
    });
  }
  
  // Apply search highlights to currently loaded lines in All Lines view
  function applySearchHighlightsToAllLines() {
    if (lastSearchMatches.length === 0) return;
    
    const matchLineNumbers = new Set(lastSearchMatches.map(m => m.line));
    const logLines = logPreview.querySelectorAll('.log-line');
    
    logLines.forEach(line => {
      const idx = parseInt(line.dataset.idx);
      if (matchLineNumbers.has(idx)) {
        line.classList.add('search-highlight-line');
      }
    });
  }

  // --- Rendering Functions ---
  
  // Helper to remove highlight from a specific line
  function removeHighlightFromLine(lineElement, lineIndex) {
    lineElement.classList.remove('highlight-yellow', 'highlight-green', 'highlight-blue', 
                                 'highlight-red', 'highlight-purple', 'highlight-orange');
    // Remove the dot
    const dot = lineElement.querySelector('.highlight-dot');
    if (dot) dot.remove();
    // Remove from stored highlights
    delete highlightedLines[lineIndex];
  }
  
  // Helper to add highlight dot to a line
  function addHighlightDot(lineElement, lineIndex, color) {
    // Remove existing dot if any
    const existingDot = lineElement.querySelector('.highlight-dot');
    if (existingDot) existingDot.remove();
    
    const lineNumSpan = lineElement.querySelector('.line-number');
    const dot = document.createElement("span");
    dot.className = `highlight-dot highlight-dot-${color}`;
    dot.title = `Click to remove ${color} highlight`;
    dot.onclick = (e) => {
      e.stopPropagation();
      removeHighlightFromLine(lineElement, lineIndex);
    };
    lineElement.insertBefore(dot, lineNumSpan);
  }

  function renderLines(lines, append, startIdx) {
    hideLogPlaceholder();
    if (!append) logPreview.innerHTML = "";

    let lastTimestamp = null;
    if (append && logPreview.children.length > 0) {
      const lastLine = logPreview.children[logPreview.children.length - 1];
      const tsMatch = lastLine.textContent.match(/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})/);
      if (tsMatch) {
        lastTimestamp = parseTimestampFast(tsMatch[1]);
      }
    }

    const fragment = document.createDocumentFragment();

    lines.forEach((line, idx) => {
      const div = document.createElement("div");
      div.className = "log-line";
      const lineNumber = startIdx + idx + 1; // Line numbers start from 1
      const lineIndex = startIdx + idx;
      div.dataset.idx = lineIndex;
      div.dataset.lineNumber = lineNumber;
      div.dataset.originalText = line;
      
      // Create line number span
      const lineNumSpan = document.createElement("span");
      lineNumSpan.className = "line-number";
      lineNumSpan.textContent = lineNumber;
      div.appendChild(lineNumSpan);
      
      // Check if this line has a stored highlight and add dot
      if (highlightedLines[lineIndex]) {
        div.classList.add(`highlight-${highlightedLines[lineIndex]}`);
        addHighlightDot(div, lineIndex, highlightedLines[lineIndex]);
      }
      
      // Apply syntax highlighting if available
      if (window.LogColors && window.LogColors.isEnabled()) {
        const contentSpan = document.createElement("span");
        contentSpan.innerHTML = window.LogColors.highlightLine(line);
        div.appendChild(contentSpan);
      } else {
        div.appendChild(document.createTextNode(line));
      }
      
      // Add warning/error class for background highlighting
      if (line.includes(']W:')) {
        div.classList.add('warning-line');
      } else if (line.includes(']E:')) {
        div.classList.add('error-line');
      }
      
      // Calculate time gap
      const tsMatch = line.match(/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})/);
      if (tsMatch) {
        const currentTimestamp = parseTimestampFast(tsMatch[1]);
        if (lastTimestamp) {
          const timeDiff = (currentTimestamp - lastTimestamp) / 1000;
          div.dataset.timeGap = timeDiff;
          div.dataset.gapSize = timeDiff < 1 ? 'small' : timeDiff < 10 ? 'medium' : 'large';
        }
        lastTimestamp = currentTimestamp;
      }

      fragment.appendChild(div);
    });

    logPreview.appendChild(fragment);

    if (document.getElementById('showTimeGaps')?.checked) {
      applyTimeGapsToLines(logPreview, true);
    }

    applySearchHighlightsToNewLines();

    if (document.getElementById('hideNoise')?.checked) {
      applyHideNoise();
    }
  }
  
  // Function to refresh log display (called when colors change)
  window.refreshLogDisplay = function() {
    // Re-render the current log lines with new syntax highlighting (main log view)
    const logLines = logPreview.querySelectorAll('.log-line');
    logLines.forEach(div => {
      const originalText = div.dataset.originalText;
      if (originalText) {
        const lineNumSpan = div.querySelector('.line-number');
        div.innerHTML = '';
        if (lineNumSpan) {
          div.appendChild(lineNumSpan);
        }
        if (window.LogColors && window.LogColors.isEnabled()) {
          const contentSpan = document.createElement("span");
          contentSpan.innerHTML = window.LogColors.highlightLine(originalText);
          div.appendChild(contentSpan);
        } else {
          div.appendChild(document.createTextNode(originalText));
        }
      }
    });
    
    // Also refresh the thread activity view (analysis tab)
    if (threadLogView) {
      const activityLines = threadLogView.querySelectorAll('.log-line');
      activityLines.forEach(div => {
        const originalText = div.dataset.originalText;
        if (originalText) {
          div.innerHTML = '';
          if (window.LogColors && window.LogColors.isEnabled()) {
            const contentSpan = document.createElement("span");
            contentSpan.innerHTML = window.LogColors.highlightLine(originalText);
            div.appendChild(contentSpan);
          } else {
            div.textContent = originalText;
          }
        }
      });
    }
    
    // Also refresh the findings view
    const findingsList = document.getElementById('findingsList');
    if (findingsList) {
      const findingLines = findingsList.querySelectorAll('.finding-line');
      findingLines.forEach(div => {
        const originalText = div.dataset.originalText;
        if (originalText) {
          if (window.LogColors && window.LogColors.isEnabled()) {
            div.innerHTML = window.LogColors.highlightLine(originalText);
          } else {
            div.textContent = originalText;
          }
        }
      });
    }
  };

  function updateStats(data) {
    // Update compact stats panel in graph header
    const statSamples = document.getElementById('statSamples');
    const statSource = document.getElementById('statSource');
    const statTarget = document.getElementById('statTarget');
    const statHandling = document.getElementById('statHandling');
    
    if (data.performance && data.performance.count > 0) {
       const p = data.performance;
       
       if (statSamples) {
         statSamples.style.display = 'flex';
         document.getElementById('statSamplesValue').textContent = p.count;
       }
       if (statSource) {
         statSource.style.display = 'flex';
         document.getElementById('statSourceValue').textContent = `${p.source.avg.toFixed(3)}s`;
       }
       if (statTarget) {
         statTarget.style.display = 'flex';
         document.getElementById('statTargetValue').textContent = `${p.target.avg.toFixed(3)}s`;
       }
       if (statHandling) {
         statHandling.style.display = 'flex';
         document.getElementById('statHandlingValue').textContent = `${p.handling.avg.toFixed(3)}s`;
       }
    } else {
       // Hide stats if no performance data
       if (statSamples) statSamples.style.display = 'none';
       if (statSource) statSource.style.display = 'none';
       if (statTarget) statTarget.style.display = 'none';
       if (statHandling) statHandling.style.display = 'none';
    }
    
    // Render latency graph
    renderLatencyGraph(data);
  }

  function renderAnalysis(data) {
      // Fetch and display task properties
      fetchTaskProperties();
      
      // Fetch and display bulk map operations
      fetchBulkMap();
      
      // Fetch and display bulk activity analysis
      fetchBulkActivity();
      
      // Fetch and display issues
      fetchIssues();
      
      // Fetch and display log summary
      fetchLogSummary();
      
      // Fetch Performance Cockpit data to check if there's anything to show
      fetchPerformanceCockpitCheck();
      
      // Populate unavailable reports after all async fetches settle
      setTimeout(updateUnavailableReports, 4000);

      // Render threads in Log View panel
      renderLogViewThreads(data);
      
      // Group components by name and show threads (for Analysis tab - now removed, but keep for backward compatibility)
      if (!threadListDiv) return;
      threadListDiv.innerHTML = "";
      
      if (!data.components || data.components.length === 0) {
          threadListDiv.innerHTML = '<p class="placeholder-text-small">No components found</p>';
          return;
      }
      
      // First, classify threads by their dominant component
      const threadToComponentMap = {};
      const threadCounts = {};
      
      data.components.forEach(c => {
          if (!threadCounts[c.thread]) {
              threadCounts[c.thread] = {};
          }
          threadCounts[c.thread][c.name] = c.count;
      });
      
      // Assign each thread to its dominant component
      Object.keys(threadCounts).forEach(thread => {
          const components = threadCounts[thread];
          let maxCount = 0;
          let dominantComponent = null;
          
          Object.entries(components).forEach(([component, count]) => {
              if (count > maxCount) {
                  maxCount = count;
                  dominantComponent = component;
              }
          });
          
          threadToComponentMap[thread] = dominantComponent;
      });
      
      // Group by dominant component
      const componentMap = {};
      data.components.forEach(c => {
          const dominantComp = threadToComponentMap[c.thread];
          
          if (!componentMap[dominantComp]) {
              componentMap[dominantComp] = {
                  name: dominantComp,
                  totalCount: 0,
                  threads: {}
              };
          }
          
          if (!componentMap[dominantComp].threads[c.thread]) {
              componentMap[dominantComp].threads[c.thread] = {
                  thread: c.thread,
                  count: 0,
                  first_ts: c.first_ts,
                  last_ts: c.last_ts
              };
          }
          
          componentMap[dominantComp].threads[c.thread].count += c.count;
          componentMap[dominantComp].totalCount += c.count;
      });
      
      // Sort components by message count (descending)
      const sortedComponents = Object.values(componentMap).sort((a, b) => b.totalCount - a.totalCount);
      
      // Render each component group
      sortedComponents.forEach(comp => {
          const groupDiv = document.createElement("div");
          groupDiv.className = "component-group-container";
          groupDiv.dataset.componentName = comp.name;
          
          const headerDiv = document.createElement("div");
          headerDiv.className = "group-header";

          const allThreadKeys2 = Object.keys(comp.threads);
          const asmThreads2 = allThreadKeys2.filter(isAsmThread);
          const realThreads2 = allThreadKeys2.filter(k => !isAsmThread(k));
          const totalPooled2 = asmThreads2.reduce((sum, k) => sum + (parseAsmThread(k)?.poolCount || 0), 0);

          let headerStats2 = `${comp.totalCount} msgs, ${realThreads2.length} thr`;
          if (asmThreads2.length > 0) {
            headerStats2 += ` + ${totalPooled2} pooled`;
          }
          const shortDesc = getComponentShort(comp.name);
          headerDiv.innerHTML = `<span class="expand-icon">▶</span> <strong>${comp.name}</strong> <span style="color:#9ca3af;">(${headerStats2})</span>`
            + (shortDesc ? `<span class="component-short-desc">${shortDesc}</span>` : '');
          headerDiv.onclick = () => {
              const threadList = groupDiv.querySelector('.thread-list-inner');
              const icon = headerDiv.querySelector('.expand-icon');
              const isHidden = threadList.classList.toggle('hidden');
              icon.textContent = isHidden ? '▶' : '▼';
          };
          
          groupDiv.appendChild(headerDiv);
          
          const threadListInner = document.createElement("div");
          threadListInner.className = "thread-list-inner hidden";
          
          const sortedThreads = Object.values(comp.threads).sort((a, b) => b.count - a.count);

          const realEntries2 = sortedThreads.filter(t => !isAsmThread(t.thread));
          const asmEntries2 = sortedThreads.filter(t => isAsmThread(t.thread));

          realEntries2.forEach(t => {
              const threadDiv = document.createElement("div");
              threadDiv.className = "thread-item";
              threadDiv.dataset.threadId = t.thread;
              threadDiv.innerHTML = `Thread ${t.thread}: ${t.count} msgs`;
              threadDiv.onclick = (e) => {
                  e.stopPropagation();
                  loadComponentActivity(comp.name, t.thread);
              };
              threadListInner.appendChild(threadDiv);
          });

          if (asmEntries2.length > 0) {
            const asmHeader = document.createElement("div");
            asmHeader.className = "asm-group-header";
            asmHeader.innerHTML = `<span class="asm-icon">⛁</span> ASM Parallel Readers <span class="asm-pool-note">${totalPooled2} short-lived OS threads grouped by ASM handle</span>`;
            threadListInner.appendChild(asmHeader);

            asmEntries2.forEach(t => {
              const threadDiv = document.createElement("div");
              threadDiv.className = "thread-item asm-thread-item";
              threadDiv.dataset.threadId = t.thread;
              threadDiv.innerHTML = `<span class="asm-label">${getAsmLabel(t.thread)}</span>: ${t.count} msgs <span class="asm-pool-badge">${getAsmSublabel(t.thread)}</span>`;
              threadDiv.onclick = (e) => {
                  e.stopPropagation();
                  loadComponentActivity(comp.name, t.thread);
              };
              threadListInner.appendChild(threadDiv);
            });
          }
          
          groupDiv.appendChild(threadListInner);
          threadListDiv.appendChild(groupDiv);
      });
  }
  
  function loadComponentActivity(component, thread) {
      if (!currentFileId) {
          console.error('No file loaded');
          return;
      }
      
      console.log('loadComponentActivity called - Component:', component, 'Thread:', thread);
      
      // Hide ALL other views first
      document.querySelectorAll('.analysis-view').forEach(v => v.style.display = 'none');
      
      // Show thread log view
      document.getElementById('threadLogView').style.display = 'block';
      document.getElementById('threadActivityControls').style.display = 'flex';
      
      // Clear active report link since we're viewing thread activity
      setActiveReportLink(null);
      
      // Clear activity search
      if (activityQuickSearch) activityQuickSearch.value = '';
      activityMatches = [];
      currentActivityMatchIndex = -1;
      updateActivitySearchUI();
      
      threadLogView.innerHTML = '<div class="placeholder-text">Loading component activity...</div>';
      componentInfo.innerHTML = '<div class="placeholder-text-small">Loading...</div>';
      
      // Build search query
      let searchQuery;
      if (isAsmThread(thread)) {
        searchQuery = buildAsmSearchQuery(thread, component);
      } else {
        const escapedComponent = component.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        searchQuery = `^${thread}:.*\\[${escapedComponent}`;
      }
      
      console.log('Search query:', searchQuery);
      console.log('Fetching from:', `/api/files/${currentFileId}/search?q=${encodeURIComponent(searchQuery)}&limit=5000`);
      
      fetch(`/api/files/${currentFileId}/search?q=${encodeURIComponent(searchQuery)}&limit=5000`)
          .then(res => {
              console.log('Response status:', res.status);
              if (!res.ok) {
                  throw new Error(`HTTP ${res.status}: ${res.statusText}`);
              }
              return res.json();
          })
          .then(matches => {
              console.log('Received', matches.length, 'matches');
              threadLogView.innerHTML = "";
              
              if (matches.length === 0) {
                  threadLogView.innerHTML = `<div class="placeholder-text">No activity found for this component/thread<br><small style="color: #9ca3af; font-size: 0.7rem;">Thread: ${thread}, Component: ${component}</small></div>`;
                  componentInfo.innerHTML = '<div class="placeholder-text-small">No data</div>';
                  console.warn('No matches found for query:', searchQuery);
                  return;
              }
              
              // Parse for task start info
              let taskInfo = null;
              matches.forEach(m => {
                  if (m.text.includes('(replicationtask.c:1868)')) {
                      taskInfo = parseTaskStartLine(m.text);
                  }
              });
              
              // Display component info
              updateComponentInfo(component, thread, matches.length, taskInfo);
              
              // Calculate time gaps between messages
              const linesWithTimestamps = [];
              matches.forEach(m => {
                  const tsMatch = m.text.match(/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})/);
                  if (tsMatch) {
                      linesWithTimestamps.push({
                          ...m,
                          timestamp: new Date(tsMatch[1])
                      });
                  } else {
                      linesWithTimestamps.push({ ...m, timestamp: null });
                  }
              });
              
              matches.forEach((m, idx) => {
                  const div = document.createElement("div");
                  div.className = "log-line";
                  div.dataset.idx = m.line;
                  div.dataset.originalText = m.text; // Store for searching
                  div.style.cursor = "pointer";
                  
                  // Apply syntax highlighting if available
                  if (window.LogColors && window.LogColors.isEnabled()) {
                      const contentSpan = document.createElement("span");
                      contentSpan.innerHTML = window.LogColors.highlightLine(m.text);
                      div.appendChild(contentSpan);
                  } else {
                      div.textContent = m.text;
                  }
                  
                  // Calculate time gap from previous line
                  if (idx > 0 && linesWithTimestamps[idx].timestamp && linesWithTimestamps[idx-1].timestamp) {
                      const timeDiff = (linesWithTimestamps[idx].timestamp - linesWithTimestamps[idx-1].timestamp) / 1000; // in seconds
                      div.dataset.timeGap = timeDiff.toFixed(2);
                      
                      // Classify gap size - more aggressive thresholds for performance analysis
                      if (timeDiff < 0.5) {
                          div.dataset.gapSize = 'small';
                      } else if (timeDiff < 5) {
                          div.dataset.gapSize = 'medium';
                      } else {
                          div.dataset.gapSize = 'large';
                      }
                  }
                  
                  // Add context menu
                  div.addEventListener("contextmenu", (e) => showContextMenu(e, m.text));
                  
                  // Click to jump to line in main log
                  div.onclick = () => {
                      // Switch to Log View tab
                      const logViewTab = document.querySelector('.tab-btn[data-tab="log-tab"]');
                      if (logViewTab) logViewTab.click();
                      
                      // Jump to the line
                      setTimeout(() => {
                          jumpToLineAndHighlight(m.line, m.text);
                      }, 100);
                  };
                  
                  threadLogView.appendChild(div);
              });
              
              // Apply time gaps if checkbox is checked
              applyTimeGapsDisplay();
              
              console.log('Loaded', matches.length, 'lines for component:', component, 'thread:', thread);
          })
          .catch(err => {
              console.error('Failed to load component activity:', err);
              threadLogView.innerHTML = `<div class="placeholder-text">Error loading component activity<br><small style="color: #ef4444; font-size: 0.8rem;">${err.message}</small></div>`;
              componentInfo.innerHTML = `<div class="placeholder-text-small" style="color: #ef4444;">Error: ${err.message}</div>`;
          });
  }
  
  function parseTaskStartLine(line) {
      // Example: Task 'P1JRNC_DATABRICKS_1_B' running full load and CDC in resume mode  (replicationtask.c:1868)
      const taskMatch = line.match(/Task '([^']+)'/);
      const modeMatch = line.match(/running ([^in]+) in ([^(]+)/);
      
      if (taskMatch && modeMatch) {
          return {
              taskName: taskMatch[1],
              runningMode: modeMatch[1].trim(),
              startMode: modeMatch[2].trim().replace(' mode', '')
          };
      }
      return null;
  }
  
  function updateComponentInfo(component, thread, messageCount, taskInfo) {
      const description = getComponentDescription(component);
      const lookFor = getComponentLookFor(component);
      const shortDesc = getComponentShort(component);
      const asm = parseAsmThread(thread);

      let threadHtml;
      if (asm) {
        threadHtml = `
              <p style="margin: 5px 0; font-size: 0.85rem;"><strong>ASM Statement Handle:</strong> ${asm.stmtNum}</p>
              <p style="margin: 5px 0; font-size: 0.85rem;"><strong>Pooled OS Threads:</strong> ${asm.poolCount}</p>`;
      } else {
        threadHtml = thread ? `<p style="margin: 5px 0; font-size: 0.85rem;"><strong>Thread:</strong> ${thread}</p>` : '';
      }

      let html = `
          <div style="padding: 10px; background: #1f2937; border-radius: 6px; margin-bottom: 10px;">
              <h4 style="margin: 0 0 4px 0; color: #3b82f6;">${component}</h4>
              ${shortDesc ? `<p style="margin:0 0 8px;font-size:0.72rem;color:#9ca3af;">${shortDesc}</p>` : ''}
              ${threadHtml}
              <p style="margin: 5px 0; font-size: 0.85rem;"><strong>Messages:</strong> ${messageCount}</p>
          </div>`;

      if (asm) {
        let asmBody = `<p>Oracle ASM spawns short-lived OS threads for parallel disk I/O via <code>dbms_diskgroup.read</code>. 
            Each thread typically appears only a few times. These ${asm.poolCount} ephemeral threads all used 
            ASM handle ${asm.stmtNum} and have been grouped together.</p>`;
        html += buildCollapsibleSection('ASM Parallel Reader Pool', asmBody, { color: '#a78bfa', icon: '⛁', cls: 'asm-info-note' });
      }

      let aboutBody = `<p style="margin: 0; font-size: 0.8rem; color: #d1d5db; line-height: 1.5;">${description}</p>`;
      if (lookFor) {
          aboutBody += `
              <div style="margin-top:10px;padding:8px 10px;background:rgba(59,130,246,0.08);border-left:2px solid #3b82f6;border-radius:0 4px 4px 0;">
                  <strong style="font-size:0.75rem;color:#93c5fd;">What to look for</strong>
                  <p style="margin:3px 0 0;font-size:0.78rem;color:#d1d5db;line-height:1.45;">${lookFor}</p>
              </div>`;
      }
      aboutBody += `
              <p style="margin: 10px 0 0 0; font-size: 0.7rem; color: #9ca3af;">
                  <a href="https://help.qlik.com/en-US/replicate/November2025/Content/Replicate/Main/Replicate%20Loggers/Loggers.htm" 
                     target="_blank" style="color: #60a5fa; text-decoration: none;">
                     Qlik Documentation ↗
                  </a>
              </p>`;
      html += buildCollapsibleSection('About this Component', aboutBody, { color: '#818cf8', icon: 'ℹ' });
      
      if (taskInfo) {
          let taskBody = `
                  <p style="margin: 5px 0; font-size: 0.85rem;"><strong>Task Name:</strong><br>${taskInfo.taskName}</p>
                  <p style="margin: 5px 0; font-size: 0.85rem;"><strong>Running Mode:</strong><br>${taskInfo.runningMode}</p>
                  <p style="margin: 5px 0; font-size: 0.85rem;"><strong>Start Mode:</strong><br><span style="color: ${taskInfo.startMode.toLowerCase().includes('resume') ? '#f59e0b' : '#10b981'}">${taskInfo.startMode}</span></p>`;
          html += buildCollapsibleSection('Task Start Info', taskBody, { color: '#10b981', icon: '▸', startOpen: true });
      }
      
      componentInfo.innerHTML = html;
  }
  
  function renderLatencyGraph(data) {
    const graphSection = document.querySelector('#log-tab .graph-section');
    
    if (!data.performance || data.performance.count === 0) {
        document.getElementById('latencyGraph').innerHTML = '<p class="placeholder-text">No performance data available.</p>';
        if (graphSection) graphSection.classList.add('collapsed');
        return;
    }
    
    // Fetch the detailed performance data
    if (!currentFileId) return;
    
    fetch(`/api/files/${currentFileId}/performance`)
        .then(res => res.json())
        .then(perfData => {
            if (!perfData || perfData.length === 0) {
                document.getElementById('latencyGraph').innerHTML = '<p class="placeholder-text">No performance data points found.</p>';
                if (graphSection) graphSection.classList.add('collapsed');
                return;
            }
            
            // Has data - ensure section is expanded
            if (graphSection) graphSection.classList.remove('collapsed');
            
            const timestamps = perfData.map(p => p.timestamp);
            const sourceLatencies = perfData.map(p => p.source_latency);
            const targetLatencies = perfData.map(p => p.target_latency);
            const handlingLatencies = perfData.map(p => p.handling_latency);
            const customIndices = perfData.map((_, i) => i);
            
            const traces = [
                {
                    x: timestamps,
                    y: sourceLatencies,
                    customdata: customIndices,
                    mode: 'lines+markers',
                    name: 'Source Latency',
                    line: { color: '#f59e0b' },
                    marker: { size: 4 }
                },
                {
                    x: timestamps,
                    y: targetLatencies,
                    customdata: customIndices,
                    mode: 'lines+markers',
                    name: 'Target Latency',
                    line: { color: '#3b82f6' },
                    marker: { size: 4 }
                },
                {
                    x: timestamps,
                    y: handlingLatencies,
                    customdata: customIndices,
                    mode: 'lines+markers',
                    name: 'Handling Latency',
                    line: { color: '#10b981' },
                    marker: { size: 4 }
                }
            ];
            
            const layout = {
                xaxis: { 
                    title: 'Timestamp',
                    type: 'date'
                },
                yaxis: { 
                    title: 'Latency (seconds)'
                },
                margin: { t: 10, r: 20, b: 50, l: 60 },
                hovermode: 'closest',
                dragmode: 'select',
                autosize: true
            };
            
            const config = { 
                responsive: true,
                modeBarButtonsToAdd: ['select2d', 'lasso2d'],
                displayModeBar: true
            };
            
            Plotly.newPlot('latencyGraph', traces, layout, config);
            
            // Ensure chart fits after rendering
            setTimeout(() => {
                const gd = document.getElementById('latencyGraph');
                if (gd) Plotly.Plots.resize(gd);
            }, 100);
            
            const graphDiv = document.getElementById('latencyGraph');
            let lastPlotlyClickTime = 0;

            // Click on a data-point marker -> jump to its log line
            graphDiv.on('plotly_click', function(eventData) {
                if (eventData.points && eventData.points.length > 0) {
                    lastPlotlyClickTime = Date.now();
                    const perfIdx = eventData.points[0].customdata;
                    const lineNumber = perfData[perfIdx].line_number;
                    console.log('Graph clicked - perfIdx:', perfIdx, 'Line:', lineNumber);
                    if (lineNumber !== undefined && lineNumber !== null) {
                        jumpToLineAndHighlight(lineNumber, '');
                    }
                }
            });

            // Click anywhere on the plot area (including gaps) -> jump to nearest point
            graphDiv.addEventListener('click', function(evt) {
                if (Date.now() - lastPlotlyClickTime < 300) return;

                const fullLayout = graphDiv._fullLayout;
                if (!fullLayout || !fullLayout.xaxis) return;

                const xaxis = fullLayout.xaxis;
                const yaxis = fullLayout.yaxis;
                const rect = graphDiv.getBoundingClientRect();
                const xPx = evt.clientX - rect.left;
                const yPx = evt.clientY - rect.top;

                const plotLeft = xaxis._offset;
                const plotRight = plotLeft + xaxis._length;
                const plotTop = yaxis._offset;
                const plotBottom = plotTop + yaxis._length;
                if (xPx < plotLeft || xPx > plotRight || yPx < plotTop || yPx > plotBottom) return;

                const rangeMin = new Date(xaxis.range[0]).getTime();
                const rangeMax = new Date(xaxis.range[1]).getTime();
                const fraction = (xPx - plotLeft) / xaxis._length;
                const clickTimeMs = rangeMin + fraction * (rangeMax - rangeMin);

                let nearestIdx = 0;
                let nearestDist = Infinity;
                for (let i = 0; i < perfData.length; i++) {
                    const dist = Math.abs(new Date(perfData[i].timestamp).getTime() - clickTimeMs);
                    if (dist < nearestDist) { nearestDist = dist; nearestIdx = i; }
                }

                const lineNumber = perfData[nearestIdx].line_number;
                if (lineNumber !== undefined && lineNumber !== null) {
                    console.log('Graph background click - nearest perfIdx:', nearestIdx, 'Line:', lineNumber);
                    jumpToLineAndHighlight(lineNumber, '');
                }
            });
            
            // Selection handler: map the selection box's x-range to log line numbers
            // by interpolating between the nearest perf data points.
            graphDiv.on('plotly_selected', function(eventData) {
                if (!eventData) return;

                let xRange = (eventData.range && eventData.range.x)
                    || (eventData.lassoPoints && eventData.lassoPoints.x);
                if (!xRange || xRange.length < 2) return;

                const edgeTimes = xRange.map(t => new Date(t).getTime());
                const lo = Math.min(...edgeTimes);
                const hi = Math.max(...edgeTimes);

                function timeToLine(ms) {
                    const firstMs = new Date(perfData[0].timestamp).getTime();
                    const lastMs  = new Date(perfData[perfData.length - 1].timestamp).getTime();
                    if (ms <= firstMs) return perfData[0].line_number;
                    if (ms >= lastMs)  return perfData[perfData.length - 1].line_number;
                    for (let i = 1; i < perfData.length; i++) {
                        const t1 = new Date(perfData[i].timestamp).getTime();
                        if (t1 >= ms) {
                            const t0 = new Date(perfData[i - 1].timestamp).getTime();
                            const l0 = perfData[i - 1].line_number;
                            const l1 = perfData[i].line_number;
                            return Math.round(l0 + (l1 - l0) * (ms - t0) / (t1 - t0));
                        }
                    }
                    return perfData[perfData.length - 1].line_number;
                }

                const startLine = timeToLine(lo);
                const endLine   = timeToLine(hi);

                if (startLine <= endLine) {
                    console.log('Selected time range - Lines:', startLine, 'to', endLine,
                                '(', new Date(lo).toISOString(), '-', new Date(hi).toISOString(), ')');
                    loadLogLinesInRange(startLine, endLine, { start: new Date(lo), end: new Date(hi) });
                }
            });
        })
        .catch(err => {
            console.error('Failed to load performance data:', err);
            document.getElementById('latencyGraph').innerHTML = '<p class="placeholder-text">Error loading performance data.</p>';
            if (graphSection) graphSection.classList.add('collapsed');
        });
  }
  
  // --- Context Menu ---
  function createContextMenu() {
    const menu = document.createElement("div");
    menu.className = "context-menu";
    menu.style.display = "none";
    menu.style.position = "absolute";
    menu.innerHTML = `
      <div id="ctx-add-finding" class="context-menu-item">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
          <path d="M4.146.146A.5.5 0 014.5 0h7a.5.5 0 01.354.146l4 4A.5.5 0 0116 4.5v7a.5.5 0 01-.146.354l-4 4a.5.5 0 01-.354.146h-7a.5.5 0 01-.354-.146l-4-4A.5.5 0 010 11.5v-7a.5.5 0 01.146-.354l4-4zM8 10a1 1 0 100-2 1 1 0 000 2zm0-6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 018 4z"/>
        </svg>
        Add to Findings
      </div>
      <div id="ctx-highlight" class="context-menu-item">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
          <path d="M5.21 13.823l.078-.17a.5.5 0 01.664-.254l.028.013 4.01 2.006a.5.5 0 01.217.689l-.078.17a.5.5 0 01-.665.254l-.028-.013-4.01-2.006a.5.5 0 01-.217-.69zm5.505-10.89l2.121 2.121-7.071 7.071-2.121-2.12 7.07-7.072zM6.646 1.646a.5.5 0 01.708 0L9.5 3.793l-4.95 4.95L2.404 6.596a.5.5 0 010-.708l4.242-4.242z"/>
        </svg>
        Highlight
        <div class="color-picker" onclick="event.stopPropagation()">
          <span class="color-dot" data-color="yellow" style="background: #fbbf24" title="Highlight Yellow"></span>
          <span class="color-dot" data-color="green" style="background: #10b981" title="Highlight Green"></span>
          <span class="color-dot" data-color="blue" style="background: #3b82f6" title="Highlight Blue"></span>
          <span class="color-dot" data-color="red" style="background: #ef4444" title="Highlight Red"></span>
          <span class="color-dot" data-color="purple" style="background: #a855f7" title="Highlight Purple"></span>
          <span class="color-dot" data-color="orange" style="background: #f97316" title="Highlight Orange"></span>
        </div>
      </div>
      <div id="ctx-clear-line-highlight" class="context-menu-item">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
          <path d="M4.646 4.646a.5.5 0 01.708 0L8 7.293l2.646-2.647a.5.5 0 01.708.708L8.707 8l2.647 2.646a.5.5 0 01-.708.708L8 8.707l-2.646 2.647a.5.5 0 01-.708-.708L7.293 8 4.646 5.354a.5.5 0 010-.708z"/>
        </svg>
        Clear Line Highlight
      </div>
      <div id="ctx-clear-highlight" class="context-menu-item">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
          <path d="M5.5 5.5A.5.5 0 016 6v6a.5.5 0 01-1 0V6a.5.5 0 01.5-.5zm2.5 0a.5.5 0 01.5.5v6a.5.5 0 01-1 0V6a.5.5 0 01.5-.5zm3 .5a.5.5 0 00-1 0v6a.5.5 0 001 0V6z"/>
          <path fill-rule="evenodd" d="M14.5 3a1 1 0 01-1 1H13v9a2 2 0 01-2 2H5a2 2 0 01-2-2V4h-.5a1 1 0 01-1-1V2a1 1 0 011-1H6a1 1 0 011-1h2a1 1 0 011 1h3.5a1 1 0 011 1v1zM4.118 4L4 4.059V13a1 1 0 001 1h6a1 1 0 001-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
        </svg>
        Clear All Highlights
      </div>
      <div id="ctx-copy" class="context-menu-item">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
          <path d="M4 1.5H3a2 2 0 00-2 2V14a2 2 0 002 2h10a2 2 0 002-2V3.5a2 2 0 00-2-2h-1v1h1a1 1 0 011 1V14a1 1 0 01-1 1H3a1 1 0 01-1-1V3.5a1 1 0 011-1h1v-1z"/>
          <path d="M9.5 1a.5.5 0 01.5.5v1a.5.5 0 01-.5.5h-3a.5.5 0 01-.5-.5v-1a.5.5 0 01.5-.5h3zm-3-1A1.5 1.5 0 005 1.5v1A1.5 1.5 0 006.5 4h3A1.5 1.5 0 0011 2.5v-1A1.5 1.5 0 009.5 0h-3z"/>
        </svg>
        Copy
      </div>
      <div id="ctx-google" class="context-menu-item">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
          <path d="M11.742 10.344a6.5 6.5 0 10-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 001.415-1.414l-3.85-3.85a1.007 1.007 0 00-.115-.1zM12 6.5a5.5 5.5 0 11-11 0 5.5 5.5 0 0111 0z"/>
        </svg>
        Search on Google
      </div>
    `;
    document.body.appendChild(menu);
    return menu;
  }
  
  contextMenu = createContextMenu();
  
  document.addEventListener("click", () => contextMenu.style.display = "none");
  
  // Store reference to the element that was right-clicked for "Clear Line Highlight"
  let contextMenuTargetElement = null;
  
  function showContextMenu(e, text, targetElement = null) {
      e.preventDefault();
      contextMenu.style.left = e.pageX + "px";
      contextMenu.style.top = e.pageY + "px";
      contextMenu.style.display = "block";
      
      // Store the target element for line-specific operations
      contextMenuTargetElement = targetElement || e.target.closest('.log-line');
      
      // Add to Findings (save via API)
      const addFindingBtn = document.getElementById("ctx-add-finding");
      addFindingBtn.onclick = async () => {
          contextMenu.style.display = "none";
          await saveLogLineToFindings(text, contextMenuTargetElement);
      };
      
      // Highlight with color picker
      const colorDots = contextMenu.querySelectorAll('.color-dot');
      
      // Color dot click - highlight ONLY the clicked line (not all matching text)
      colorDots.forEach(dot => {
          dot.onclick = (e) => {
              e.stopPropagation();
              const color = dot.getAttribute('data-color');
              currentHighlightColor = color;
              
              // Only highlight the specific clicked line
              if (contextMenuTargetElement) {
                  const lineIndex = parseInt(contextMenuTargetElement.dataset.idx);
                  
                  // Remove old color classes
                  contextMenuTargetElement.classList.remove('highlight-yellow', 'highlight-green', 'highlight-blue', 
                                       'highlight-red', 'highlight-purple', 'highlight-orange');
                  // Add new color class
                  contextMenuTargetElement.classList.add(`highlight-${color}`);
                  
                  // Add highlight dot
                  addHighlightDot(contextMenuTargetElement, lineIndex, color);
                  
                  // Store in highlightedLines for persistence across scroll
                  if (!isNaN(lineIndex)) {
                      highlightedLines[lineIndex] = color;
                  }
              }
              contextMenu.style.display = "none";
          };
      });
      
      // Clear Line Highlight - only clears highlight from the specific clicked line
      const clearLineHighlightBtn = document.getElementById("ctx-clear-line-highlight");
      clearLineHighlightBtn.onclick = () => {
          if (contextMenuTargetElement) {
              const lineIndex = parseInt(contextMenuTargetElement.dataset.idx);
              removeHighlightFromLine(contextMenuTargetElement, lineIndex);
              contextMenuTargetElement.classList.remove('selected-line', 'search-highlight-line');
          }
          contextMenu.style.display = "none";
      };
      
      // Clear All Highlights
      const clearHighlightBtn = document.getElementById("ctx-clear-highlight");
      clearHighlightBtn.onclick = () => {
          // Clear stored highlights
          highlightedLines = {};
          
          // Clear from both main log view and analysis thread view
          [logPreview, threadLogView].forEach(container => {
              if (!container) return;
              const logLines = container.querySelectorAll('.log-line');
              logLines.forEach(line => {
                  line.classList.remove('selected-line', 'highlight-yellow', 'highlight-green', 
                                        'highlight-blue', 'highlight-red', 'highlight-purple', 'highlight-orange',
                                        'search-highlight-line');
                  // Remove dots
                  const dot = line.querySelector('.highlight-dot');
                  if (dot) dot.remove();
              });
          });
          contextMenu.style.display = "none";
      };
      
      // Copy
      const copyBtn = document.getElementById("ctx-copy");
      copyBtn.onclick = () => {
          navigator.clipboard.writeText(text).then(() => {
              console.log('Text copied to clipboard');
          }).catch(err => {
              console.error('Failed to copy:', err);
          });
          contextMenu.style.display = "none";
      };
      
      // Google Search
      const googleBtn = document.getElementById("ctx-google");
      googleBtn.onclick = () => {
          const searchQuery = encodeURIComponent(text.trim());
          window.open(`https://www.google.com/search?q=${searchQuery}`, '_blank');
          contextMenu.style.display = "none";
      };
  }

  // Save a log line or text to findings via API
  async function saveLogLineToFindings(text, targetElement) {
    if (!currentFileId) return;
    
    let lineNumber = null;
    if (targetElement) {
      const idx = parseInt(targetElement.dataset.idx);
      if (!isNaN(idx)) lineNumber = idx;
    }
    
    try {
      const resp = await fetch('/api/llm/findings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: currentFileId,
          finding_type: 'log_line',
          title: text.slice(0, 120),
          content: text,
          line_number: lineNumber,
          metadata: { source: 'context_menu' }
        })
      });
      
      if (resp.ok) {
        if (window.savedFindingsManager) {
          window.savedFindingsManager.loadFindings();
        }
        showToast('Added to Findings');
      }
    } catch (e) {
      console.error('Failed to save finding:', e);
    }
  }
  window.saveLogLineToFindings = saveLogLineToFindings;
  
  // Save an issue to findings
  window.saveIssueFinding = async function(issueIdx) {
    if (!currentFileId || !window.issuesData || !window.issuesData.issues) return;
    const issue = window.issuesData.issues[issueIdx];
    if (!issue) return;
    
    const lineNumber = issue.occurrences[0]?.line_number || null;
    const content = `**[${issue.severity.toUpperCase()}]** [${issue.component}] ${issue.message_summary}\n\nOccurrences: ${issue.occurrences.length}`;
    
    try {
      const resp = await fetch('/api/llm/findings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: currentFileId,
          finding_type: 'log_line',
          title: `${issue.severity.toUpperCase()}: ${issue.message_summary}`.slice(0, 120),
          content,
          line_number: lineNumber,
          metadata: { source: 'issues_view', severity: issue.severity, component: issue.component }
        })
      });
      if (resp.ok) {
        if (window.savedFindingsManager) window.savedFindingsManager.loadFindings();
        showToast('Issue added to Findings');
      }
    } catch (e) {
      console.error('Failed to save issue finding:', e);
    }
  };
  
  // Save a Log Summary section to findings
  window.saveSectionToFindings = async function(btn) {
    if (!currentFileId) return;
    const section = btn.closest('.ai-insight-section');
    if (!section) return;
    
    const titleEl = section.querySelector('h3');
    const contentEl = section.querySelector('.ai-insight-section-content');
    const title = titleEl ? titleEl.textContent.trim() : 'Log Summary Section';
    const content = contentEl ? contentEl.innerText.trim() : '';
    let metadata = { source: 'log_summary_section' };
    if (contentEl && window.sanitizeFindingHtml) {
      const contentHtml = window.sanitizeFindingHtml(contentEl.innerHTML);
      if (contentHtml) {
        metadata.content_format = 'html';
        metadata.content_html = contentHtml;
      }
    }
    
    try {
      const resp = await fetch('/api/llm/findings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: currentFileId,
          finding_type: 'custom',
          title: `Summary: ${title}`.slice(0, 120),
          content: `**${title}**\n\n${content}`,
          metadata
        })
      });
      if (resp.ok) {
        btn.style.color = '#10b981';
        if (window.savedFindingsManager) window.savedFindingsManager.loadFindings();
        showToast('Section added to Findings');
      }
    } catch (e) {
      console.error('Failed to save section to findings:', e);
    }
  };
  
  // ── Universal "Add to Findings" context menu for analysis reports ──
  (function initReportContextMenu() {
    const menu = document.createElement('div');
    menu.id = 'reportCtxMenu';
    menu.className = 'report-context-menu';
    menu.style.display = 'none';
    menu.innerHTML = `
      <button id="reportCtxAddFinding" class="report-ctx-item">
        <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><path d="M2 2a2 2 0 012-2h8a2 2 0 012 2v13.5a.5.5 0 01-.777.416L8 13.101l-5.223 2.815A.5.5 0 012 15.5V2zm2-1a1 1 0 00-1 1v12.566l4.723-2.482a.5.5 0 01.554 0L13 14.566V2a1 1 0 00-1-1H4z"/></svg>
        Add to Findings
      </button>
    `;
    document.body.appendChild(menu);
    
    let _ctxPayload = null;
    
    function buildBulkMapRowFindingHtml(tr) {
      const table = tr.closest('table');
      if (!table || !table.classList.contains('bulk-map-table')) return null;
      const theadRow = table.querySelector('thead tr');
      if (!theadRow) return null;
      const html = `<table class="bulk-map-table finding-bulk-inline"><thead><tr>${theadRow.innerHTML}</tr></thead><tbody>${tr.outerHTML}</tbody></table>`;
      return window.sanitizeFindingHtml ? window.sanitizeFindingHtml(html) : null;
    }
    
    const addBtn = menu.querySelector('#reportCtxAddFinding');
    addBtn.addEventListener('click', async () => {
      menu.style.display = 'none';
      if (!_ctxPayload || !currentFileId) return;
      try {
        const meta = { source: _ctxPayload.source };
        if (_ctxPayload.content_html) {
          meta.content_format = 'html';
          meta.content_html = _ctxPayload.content_html;
        }
        const resp = await fetch('/api/llm/findings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            file_id: currentFileId,
            finding_type: 'custom',
            title: _ctxPayload.title.slice(0, 120),
            content: _ctxPayload.content,
            line_number: _ctxPayload.line || null,
            metadata: meta
          })
        });
        if (resp.ok) {
          if (window.savedFindingsManager) window.savedFindingsManager.loadFindings();
          showToast('Added to Findings');
        }
      } catch (e) {
        console.error('Failed to save report finding:', e);
        showToast('Failed to save finding', 'error');
      }
    });
    
    document.addEventListener('click', () => { menu.style.display = 'none'; });
    
    function extractRowText(tr) {
      return Array.from(tr.cells).map(c => c.innerText.trim()).join(' | ');
    }
    
    function extractTableHeaders(tr) {
      const table = tr.closest('table');
      if (!table) return null;
      const ths = table.querySelectorAll('thead th');
      if (ths.length === 0) return null;
      return Array.from(ths).map(th => th.innerText.trim());
    }
    
    function formatRowWithHeaders(tr) {
      const headers = extractTableHeaders(tr);
      const cells = Array.from(tr.cells).map(c => c.innerText.trim());
      if (headers && headers.length === cells.length) {
        return cells.map((v, i) => `**${headers[i]}**: ${v}`).join('\n');
      }
      return cells.join(' | ');
    }
    
    function showReportCtx(e, payload) {
      e.preventDefault();
      e.stopPropagation();
      _ctxPayload = payload;
      menu.style.display = 'block';
      const x = Math.min(e.clientX, window.innerWidth - 180);
      const y = Math.min(e.clientY, window.innerHeight - 40);
      menu.style.left = x + 'px';
      menu.style.top = y + 'px';
    }
    
    // Delegate on analysis tab – catch right-click on table rows, cockpit sections, insights
    const analysisTab = document.getElementById('analysis-tab');
    if (analysisTab) {
      analysisTab.addEventListener('contextmenu', (e) => {
        // 1) Table rows in any report (bulk map, bulk activity, file ops, pain tables…)
        const tr = e.target.closest('tr[data-line], tr');
        if (tr && tr.closest('table') && tr.closest('thead') === null) {
          const viewEl = tr.closest('.analysis-view');
          const source = viewEl ? viewEl.id : 'analysis_report';
          const line = tr.dataset.line ? parseInt(tr.dataset.line) : null;
          const formatted = formatRowWithHeaders(tr);
          const shortTitle = extractRowText(tr).slice(0, 100);
          let contentHtml = null;
          if (tr.closest('.bulk-map-table')) {
            contentHtml = buildBulkMapRowFindingHtml(tr);
          }
          showReportCtx(e, { title: shortTitle, content: formatted, line, source, content_html: contentHtml });
          return;
        }
        // 2) Cockpit sections (latency cards, spikes, bottleneck, recommendations…)
        const cockpitSection = e.target.closest('.cockpit-section');
        if (cockpitSection) {
          const heading = cockpitSection.querySelector('h3');
          const sTitle = heading ? heading.textContent.trim() : 'Performance Data';
          const text = cockpitSection.innerText.trim();
          showReportCtx(e, { title: sTitle.slice(0, 120), content: `**${sTitle}**\n\n${text}`, line: null, source: 'performance_cockpit' });
          return;
        }
        // 3) Latency cards
        const latencyCard = e.target.closest('.latency-card');
        if (latencyCard) {
          const text = latencyCard.innerText.trim();
          showReportCtx(e, { title: text.slice(0, 100), content: text, line: null, source: 'latency_profile' });
          return;
        }
        // 4) Insight notices (border-left styled blocks in bulk reports)
        const notice = e.target.closest('[style*="border-left"]');
        if (notice) {
          const text = notice.innerText.trim();
          showReportCtx(e, { title: text.slice(0, 100), content: text, line: null, source: 'analysis_insight' });
        }
      });
    }
    
    // Delegate on log-tab for compact-stats, graph data points
    const logTab = document.getElementById('log-tab');
    if (logTab) {
      logTab.addEventListener('contextmenu', (e) => {
        // Check for stat items in compact stats panel or graph stats
        const statItem = e.target.closest('.compact-stat-item, .stat-card');
        if (statItem) {
          const text = statItem.innerText.trim();
          showReportCtx(e, { title: text.slice(0, 100), content: text, line: null, source: 'log_stats' });
          return;
        }
      });
    }
    
    // Delegate on the log summary view inside analysis-tab
    const logSummaryMain = document.getElementById('logSummaryMainContent');
    if (logSummaryMain) {
      logSummaryMain.addEventListener('contextmenu', (e) => {
        // Right-click on any paragraph, list item, or block within a section's content
        const sectionContent = e.target.closest('.ai-insight-section-content');
        if (!sectionContent) return;
        
        // Find the closest meaningful block
        const block = e.target.closest('p, li, tr, blockquote, .highlight-box, pre');
        if (block) {
          e.preventDefault();
          e.stopPropagation();
          const text = block.innerText.trim();
          const section = sectionContent.closest('.ai-insight-section');
          const sectionTitle = section ? section.querySelector('h3')?.textContent.trim() || '' : '';
          let contentHtml = null;
          if (window.sanitizeFindingHtml) {
            const raw = window.sanitizeFindingHtml(block.outerHTML);
            if (raw) contentHtml = `<div class="finding-html-block">${raw}</div>`;
          }
          showReportCtx(e, {
            title: `${sectionTitle}: ${text}`.slice(0, 120),
            content: `**${sectionTitle}**\n${text}`,
            line: null,
            source: 'log_summary_detail',
            content_html: contentHtml
          });
        }
      });
    }
  })();
  
  // Lightweight toast notification
  function showToast(message, type = 'info') {
    const existing = document.querySelector('.app-toast');
    if (existing) existing.remove();
    
    const toast = document.createElement('div');
    toast.className = `app-toast app-toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => toast.classList.add('visible'), 10);
    setTimeout(() => {
      toast.classList.remove('visible');
      setTimeout(() => toast.remove(), 300);
    }, 2000);
  }
  window.showToast = showToast;

  function renderFindings() {
      findingsList.innerHTML = "";
      
      // Update findings count badge
      const countBadge = document.getElementById('findingsCountBadge');
      if (countBadge) {
          countBadge.textContent = findings.length > 0 ? findings.length : '';
      }
      
      if (findings.length === 0) {
          findingsList.innerHTML = '<p class="placeholder-text">No findings yet. Right-click on log lines to add them.</p>';
          return;
      }
      findings.forEach((f, idx) => {
          const div = document.createElement("div");
          div.className = "finding-item";
          div.style.fontFamily = "monospace";
          div.style.fontSize = "0.75rem";
          
          // Create a container for the log line content with syntax highlighting
          const lineContainer = document.createElement("div");
          lineContainer.className = "finding-line";
          lineContainer.dataset.originalText = f;
          
          // Apply syntax highlighting if available
          if (window.LogColors && window.LogColors.isEnabled()) {
              lineContainer.innerHTML = window.LogColors.highlightLine(f);
          } else {
              lineContainer.textContent = f;
          }
          div.appendChild(lineContainer);
          
          // Add remove button
          const removeBtn = document.createElement("button");
          removeBtn.className = "remove-finding-btn";
          removeBtn.textContent = "×";
          removeBtn.onclick = (e) => {
              e.stopPropagation();
              findings.splice(idx, 1);
              renderFindings();
          };
          div.appendChild(removeBtn);
          
          findingsList.appendChild(div);
      });
  }
  
  // Export findings to text file
  function exportFindings() {
      if (findings.length === 0) return;
      
      const content = findings.join('\n\n---\n\n');
      const filename = `findings_${currentFileName || 'log'}_${new Date().toISOString().slice(0,10)}.txt`;
      
      // Check if running in PyWebView
      if (window.pywebview && window.pywebview.api && window.pywebview.api.save_file) {
          window.pywebview.api.save_file(filename, content).then(result => {
              if (result) {
                  console.log('Findings exported successfully');
              }
          }).catch(err => {
              console.error('Failed to export findings:', err);
          });
      } else {
          // Browser fallback
          const blob = new Blob([content], { type: 'text/plain' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
      }
  }
  
  function fetchTaskProperties() {
    if (!currentFileId) return;
    
    const taskPropertiesContent = document.getElementById('taskPropertiesContent');
    if (!taskPropertiesContent) return;
    
    taskPropertiesContent.innerHTML = '<p class="placeholder-text-small">Loading properties...</p>';
    
    fetch(`/api/files/${currentFileId}/task-properties`)
      .then(res => res.json())
      .then(props => {
        renderTaskProperties(props);
      })
      .catch(err => {
        console.error('Failed to load task properties:', err);
        taskPropertiesContent.innerHTML = '<p class="placeholder-text-small" style="color: #ef4444;">Failed to load properties</p>';
      });
  }
  
  function renderTaskProperties(props) {
    const taskPropertiesContent = document.getElementById('taskPropertiesContent');
    if (!taskPropertiesContent) return;
    
    let html = '';
    
    // Log Rollover Warning (compact version)
    if (props.is_rollover) {
      html += `
        <div style="background: #451a03; border: 1px solid #f59e0b; border-radius: 4px; padding: 6px; margin-bottom: 8px;">
          <div style="display: flex; align-items: center; gap: 4px;">
            <span style="font-size: 0.9rem;">🔄</span>
            <span style="color: #fbbf24; font-weight: bold; font-size: 0.7rem;">Log Rollover</span>
          </div>
        </div>
      `;
    }
    
    // Tiles section - show key info from log summary
    const summaryData = window.logSummaryData;
    if (summaryData) {
      const errClass = summaryData.error_count > 0 ? 'error' : 'success';
      const warnClass = summaryData.warning_count > 0 ? 'warning' : 'success';
      
      html += `<div class="task-props-tiles">`;
      
      // Task Name tile (full width)
      if (summaryData.task_name) {
        html += `
          <div class="task-props-tile full-width">
            <span class="task-props-tile-label">Task Name</span>
            <span class="task-props-tile-value highlight">${summaryData.task_name}</span>
          </div>
        `;
      }
      
      // Source & Target (full width each)
      if (summaryData.source_endpoint) {
        html += `
          <div class="task-props-tile full-width source-tile">
            <span class="task-props-tile-label">Source</span>
            <span class="task-props-tile-value">${summaryData.source_endpoint}</span>
          </div>
        `;
      }
      if (summaryData.target_endpoint) {
        html += `
          <div class="task-props-tile full-width target-tile">
            <span class="task-props-tile-label">Target</span>
            <span class="task-props-tile-value">${summaryData.target_endpoint}</span>
          </div>
        `;
      }
      
      // Version & Duration
      if (summaryData.version) {
        html += `
          <div class="task-props-tile">
            <span class="task-props-tile-label">Version</span>
            <span class="task-props-tile-value">${summaryData.version}</span>
          </div>
        `;
      }
      if (summaryData.duration) {
        html += `
          <div class="task-props-tile">
            <span class="task-props-tile-label">Duration</span>
            <span class="task-props-tile-value">${summaryData.duration}</span>
          </div>
        `;
      }
      
      // Tables & Bulk Operations
      html += `
        <div class="task-props-tile">
          <span class="task-props-tile-label">Tables</span>
          <span class="task-props-tile-value highlight">${summaryData.tables_count || 0}</span>
        </div>
        <div class="task-props-tile">
          <span class="task-props-tile-label">Bulk Operations</span>
          <span class="task-props-tile-value">${summaryData.bulk_operations || 0}</span>
        </div>
      `;
      
      // Errors & Warnings
      html += `
        <div class="task-props-tile">
          <span class="task-props-tile-label">Errors</span>
          <span class="task-props-tile-value ${errClass}">${summaryData.error_count || 0}</span>
        </div>
        <div class="task-props-tile">
          <span class="task-props-tile-label">Warnings</span>
          <span class="task-props-tile-value ${warnClass}">${summaryData.warning_count || 0}</span>
        </div>
      `;
      
      html += `</div>`;
      
      // Status badges row
      html += `<div class="task-props-status-row">`;
      
      const flClass = summaryData.full_load_completed ? 'success' : 'pending';
      const flIcon = summaryData.full_load_completed ? '✓' : '○';
      html += `
        <div class="task-props-status-badge ${flClass}">
          ${flIcon} Full Load ${summaryData.full_load_completed ? 'Completed' : 'Not Completed'}
        </div>
      `;
      
      const cdcClass = summaryData.cdc_started ? 'success' : 'pending';
      const cdcIcon = summaryData.cdc_started ? '✓' : '○';
      html += `
        <div class="task-props-status-badge ${cdcClass}">
          ${cdcIcon} CDC ${summaryData.cdc_started ? 'Started' : 'Not Started'}
        </div>
      `;
      
      html += `</div>`;
    }
    
    // Run Mode - This is the key operational info for the panel
    if (props.run_mode) {
      const mode = props.run_mode;
      const isFreshStart = mode.start_mode.toLowerCase().includes('fresh');
      const isResume = mode.start_mode.toLowerCase().includes('resume');
      const modeColor = isFreshStart ? '#10b981' : isResume ? '#f59e0b' : '#3b82f6';
      
      html += `
        <div class="property-section" style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #374151;">
          <div class="property-label">Run Mode</div>
          <div class="property-value">${mode.running_mode}</div>
        </div>
        <div class="property-section">
          <div class="property-label">Start Mode</div>
          <div class="property-value" style="color: ${modeColor}; font-weight: bold;">${mode.start_mode}</div>
        </div>
      `;
    } else if (props.is_rollover) {
      html += `
        <div class="property-section" style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #374151;">
          <div class="property-label">Run Mode</div>
          <div class="property-value" style="color: #6b7280; font-style: italic; font-size: 0.7rem;">Not available (rollover)</div>
        </div>
      `;
    }
    
    // Active Loggers - Important for troubleshooting
    if (props.loggers && props.loggers.length > 0) {
      html += `
        <div class="property-section" style="border-top: 1px solid #374151; padding-top: 8px; margin-top: 8px;">
          <div class="property-label">Active Loggers (${props.loggers.length})</div>
      `;
      
      props.loggers.forEach(logger => {
        const levelColor = logger.to_level === 'TRACE' ? '#ef4444' : 
                          logger.to_level === 'VERBOSE' ? '#f59e0b' : '#3b82f6';
        html += `
          <div class="logger-item">
            <span class="logger-name">${logger.component}</span>
            <span class="logger-level" style="background: ${levelColor};">${logger.to_level}</span>
          </div>
        `;
      });
      
      html += `</div>`;
    }
    
    // Incomplete log warning
    if (summaryData && summaryData.incomplete_log_warning) {
      html += `
        <div style="margin-top: 10px; padding: 6px; background: rgba(245, 158, 11, 0.2); border: 1px solid #f59e0b; border-radius: 4px;">
          <div style="display: flex; align-items: center; gap: 4px;">
            <span style="color: #fcd34d; font-weight: bold; font-size: 0.7rem;">⚠ Incomplete Log</span>
          </div>
          <div style="font-size: 0.65rem; color: #fcd34d; margin-top: 3px;">${summaryData.incomplete_log_warning}</div>
        </div>
      `;
    }
    
    // Key Events section
    if (summaryData && summaryData.key_events && summaryData.key_events.length > 0) {
      html += `
        <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #374151;">
          <div class="property-label" style="margin-bottom: 6px;">Key Events</div>
      `;
      summaryData.key_events.forEach(e => {
        html += `
          <div class="key-event" style="font-size: 0.75rem;">
            <span class="key-event-line">L${e.line + 1}</span>
            <span class="key-event-name">${e.event}</span>
          </div>
        `;
      });
      html += `</div>`;
    }
    
    taskPropertiesContent.innerHTML = html;
  }
  
  function fetchBulkMap() {
    if (!currentFileId) return;
    
    const bulkMapLink = document.getElementById('bulkMapLink');
    const bulkMapCount = document.getElementById('bulkMapCount');
    
    if (!bulkMapLink) return;
    
    // Show loading state
    bulkMapLink.style.display = 'flex';
    bulkMapCount.textContent = '(loading...)';
    bulkMapCount.style.opacity = '0.6';
    
    fetch(`/api/files/${currentFileId}/bulk-map?limit=500`)
      .then(res => res.json())
      .then(response => {
        bulkMapCount.style.opacity = '1';
        // Handle new response format with messages, stats, insights
        const messages = response.messages || response;  // Backward compatible
        const stats = response.stats || null;
        const insights = response.insights || [];
        
        if (!messages || messages.length === 0) {
          // Hide the link if no bulk map messages
          bulkMapLink.style.display = 'none';
          return;
        }
        
        // Show the link
        bulkMapLink.style.display = 'flex';
        bulkMapCount.textContent = `(${messages.length})`;
        
        // Store messages and insights for later rendering
        window.bulkMapData = messages;
        window.bulkMapStats = stats;
        window.bulkMapInsights = insights;
      })
      .catch(err => {
        console.error('Failed to load bulk map:', err);
        bulkMapLink.style.display = 'none';
      });
  }
  
  function renderBulkMap(messages, targetElement, stats, insights) {
    const bulkMapContent = targetElement || document.getElementById('bulkMapMainContent');
    if (!bulkMapContent) return;
    
    // Clear existing content completely
    bulkMapContent.innerHTML = '';
    
    // Get stats and insights from global if not passed
    stats = stats || window.bulkMapStats;
    insights = insights || window.bulkMapInsights || [];
    
    // Group by table
    const tableMap = {};
    messages.forEach(msg => {
      // Extract table name from message: bulk_map: seq 140324:140360 INSERT 'FICCOR'.'CTRPEDTI' (id=1)
      const tableMatch = msg.text.match(/(?:INSERT|UPDATE|DELETE|MERGE)\s+'([^']+)'\.+'([^']+)'/);
      const seqMatch = msg.text.match(/seq\s+([\d:]+)/);
      const operationMatch = msg.text.match(/\]\w:\s+bulk_map:\s+seq\s+[\d:]+\s+(\w+)/);
      const idMatch = msg.text.match(/\(id=(\d+)\)/);
      const timestampMatch = msg.text.match(/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})/);
      
      if (tableMatch) {
        const schema = tableMatch[1];
        const table = tableMatch[2];
        const fullTableName = `${schema}.${table}`;
        const seq = seqMatch ? seqMatch[1] : 'N/A';
        const seqParts = seq.split(':');
        const seqStart = seqParts[0];
        const seqEnd = seqParts[1] || seqParts[0];
        const rowCount = seqParts.length === 2 ? parseInt(seqEnd) - parseInt(seqStart) + 1 : 1;
        
        let operation = operationMatch ? operationMatch[1] : 'MERGE';
        
        // Unknown operation means MERGE
        if (operation === 'UNKNOWN') {
          operation = 'MERGE';
        }
        
        if (!tableMap[fullTableName]) {
          tableMap[fullTableName] = [];
        }
        
        tableMap[fullTableName].push({
          seq: seq,
          seqStart: seqStart,
          seqEnd: seqEnd,
          rowCount: rowCount,
          operation: operation,
          tableId: idMatch ? idMatch[1] : null,
          timestamp: timestampMatch ? timestampMatch[1] : null,
          line: msg.line,
          text: msg.text,
          gap_to_finish: msg.gap_to_finish  // Gap from backend
        });
      }
    });
    
    // Create tabs for each table
    const sortedTables = Object.keys(tableMap).sort();
    
    if (sortedTables.length === 0) {
      bulkMapContent.innerHTML = '<p class="placeholder-text-small">No bulk map messages found</p>';
      return;
    }
    
    // Create header
    const header = document.createElement('div');
    header.style.margin = '0 0 8px 0';
    header.style.fontSize = '0.75rem';
    header.style.color = '#10b981';
    header.style.display = 'flex';
    header.style.alignItems = 'center';
    header.style.gap = '4px';
    header.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
        <path d="M2 3a1 1 0 011-1h10a1 1 0 011 1v10a1 1 0 01-1 1H3a1 1 0 01-1-1V3zm2 1v2h2V4H4zm3 0v2h2V4H7zm3 0v2h2V4h-2zM4 7v2h2V7H4zm3 0v2h2V7H7zm3 0v2h2V7h-2zM4 10v2h2v-2H4zm3 0v2h2v-2H7zm3 0v2h2v-2h-2z"/>
      </svg>
      <span>Bulk Map Operations</span>
    `;
    bulkMapContent.appendChild(header);
    
    // Render Performance Insights - compact notices
    if (insights && insights.length > 0) {
      const insightsDiv = document.createElement('div');
      insightsDiv.style.cssText = 'margin-bottom: 8px;';
      
      let insightsHtml = '';
      insights.forEach(insight => {
        const colors = { warning: '#f59e0b', info: '#3b82f6', error: '#ef4444' };
        const color = colors[insight.severity] || colors.info;
        insightsHtml += `<div style="margin-bottom: 6px; padding: 6px 10px; background: #1f2937; border-left: 3px solid ${color}; border-radius: 3px; font-size: 0.7rem; display: flex; align-items: center; gap: 8px;">
          <span style="color: ${color}; font-weight: 600; white-space: nowrap;">${insight.title}:</span>
          <span style="color: #d1d5db; flex: 1;">${insight.message}</span>
          <span style="color: #10b981; cursor: help;" title="${insight.recommendation}">💡</span>
        </div>`;
      });
      
      insightsDiv.innerHTML = insightsHtml;
      bulkMapContent.appendChild(insightsDiv);
    }
    
    // Render Statistics summary
    if (stats && stats.total_operations > 0) {
      const statsDiv = document.createElement('div');
      const singlePctColor = stats.single_record_percent > 40 ? '#ef4444' : stats.single_record_percent > 20 ? '#f59e0b' : '#10b981';
      statsDiv.style.cssText = 'margin-bottom: 8px; padding: 6px 10px; background: #111827; border-radius: 4px; display: flex; flex-wrap: wrap; gap: 12px; font-size: 0.65rem;';
      statsDiv.innerHTML = `
        <span><span style="color: #6b7280;">Ops:</span> <span style="color: #e5e7eb; font-weight: bold;">${stats.total_operations}</span></span>
        <span><span style="color: #6b7280;">Single (1:1):</span> <span style="color: ${singlePctColor}; font-weight: bold;">${stats.single_record_operations} (${stats.single_record_percent}%)</span></span>
        <span><span style="color: #6b7280;">Avg Batch:</span> <span style="color: #3b82f6; font-weight: bold;">${stats.avg_batch_size} rec</span></span>
        <span><span style="color: #6b7280;">Max:</span> <span style="color: #10b981; font-weight: bold;">${stats.max_batch_size.toLocaleString()} rec</span></span>
        <span><span style="color: #6b7280;">Avg Apply:</span> <span style="color: #9ca3af;">${stats.avg_gap_seconds}s</span></span>`;
      bulkMapContent.appendChild(statsDiv);
    }
    
    // Create tabs wrapper
    const tabsWrapper = document.createElement('div');
    tabsWrapper.className = 'bm-tabs-wrapper';
    
    // Create tabs header
    const tabsHeader = document.createElement('div');
    tabsHeader.className = 'bm-tabs-header';
    tabsHeader.id = 'bmTabsHeader';
    
    // Create panels container
    const panelsContainer = document.createElement('div');
    panelsContainer.className = 'bm-panels-container';
    panelsContainer.id = 'bmPanelsContainer';
    
    // Create tab buttons and panels
    sortedTables.forEach((tableName, idx) => {
      const operations = tableMap[tableName];
      
      // Create tab button
      const tabButton = document.createElement('button');
      tabButton.className = `bm-tab-button ${idx === 0 ? 'bm-active' : ''}`;
      tabButton.setAttribute('data-table', tableName);
      tabButton.innerHTML = `
        ${tableName.split('.')[1] || tableName}
        <span class="bm-tab-count">${operations.length}</span>
      `;
      tabButton.addEventListener('click', () => switchBulkMapTab(tableName));
      tabsHeader.appendChild(tabButton);
      
      // Create tab panel
      const panel = document.createElement('div');
      panel.className = `bm-tab-panel ${idx === 0 ? 'bm-active' : ''}`;
      panel.setAttribute('data-table', tableName);
      
      // Calculate operation counts
      const operationCounts = { INSERT: 0, UPDATE: 0, DELETE: 0, MERGE: 0 };
      let singleRecordCount = 0;
      operations.forEach(op => {
        operationCounts[op.operation] = (operationCounts[op.operation] || 0) + 1;
        if (op.rowCount === 1) {
          singleRecordCount++;
        }
      });
      
      // Check if MERGE is being used (important for target like Databricks)
      const hasMerge = operationCounts.MERGE > 0;
      
      // Build panel content
      let panelHTML = `
        <div class="table-summary">
          <div class="table-summary-grid" style="grid-template-columns: repeat(${hasMerge ? 6 : 5}, 1fr);">
            <div class="table-summary-stat">
              <div class="table-summary-stat-label">INSERT</div>
              <div class="table-summary-stat-value" style="color: #10b981;">${operationCounts.INSERT || 0}</div>
            </div>
            <div class="table-summary-stat">
              <div class="table-summary-stat-label">UPDATE</div>
              <div class="table-summary-stat-value" style="color: #3b82f6;">${operationCounts.UPDATE || 0}</div>
            </div>
            <div class="table-summary-stat">
              <div class="table-summary-stat-label">DELETE</div>
              <div class="table-summary-stat-value" style="color: #ef4444;">${operationCounts.DELETE || 0}</div>
            </div>
            ${hasMerge ? `<div class="table-summary-stat">
              <div class="table-summary-stat-label">MERGE</div>
              <div class="table-summary-stat-value" style="color: #a855f7; font-weight: bold;">${operationCounts.MERGE}</div>
            </div>` : ''}
            <div class="table-summary-stat">
              <div class="table-summary-stat-label">SINGLE (1:1)</div>
              <div class="table-summary-stat-value" style="color: #fbbf24; font-weight: bold;">${singleRecordCount}</div>
            </div>
            <div class="table-summary-stat">
              <div class="table-summary-stat-label">TOTAL</div>
              <div class="table-summary-stat-value" style="color: #e5e7eb; font-weight: bold;">${operations.length}</div>
            </div>
          </div>
        </div>
        <table class="bulk-map-table">
          <thead>
            <tr>
              <th style="width: 18%;">Sequence</th>
              <th style="width: 10%;">Records</th>
              <th style="width: 13%;">Operation</th>
              <th style="width: 16%;">Time</th>
              <th style="width: 10%;">Gap</th>
              <th style="width: 10%;">RPS</th>
              <th style="width: 23%;">Line</th>
            </tr>
          </thead>
          <tbody>
      `;
      
      // First pass: collect all gaps to calculate average
      const timeGaps = [];
      operations.forEach((op) => {
        if (op.gap_to_finish !== null && op.gap_to_finish !== undefined) {
          timeGaps.push(op.gap_to_finish);
        }
      });
      
      // Calculate average gap
      const avgGap = timeGaps.length > 0 ? timeGaps.reduce((a, b) => a + b, 0) / timeGaps.length : 0;
      
      // Second pass: render rows
      operations.forEach((op) => {
        const opClass = op.operation.toLowerCase();
        let timeGap = op.gap_to_finish;
        let gapClass = '';
        let rps = null;
        
        if (timeGap !== null && timeGap !== undefined) {
          // Calculate RPS (records per second)
          if (timeGap > 0) {
            rps = (op.rowCount / timeGap).toFixed(2);
          }
          
          // Only mark as red (large) if above average
          if (timeGap > avgGap && avgGap > 0) {
            gapClass = 'gap-large';
          } else if (timeGap < 0.5) {
            gapClass = 'gap-small';
          } else if (timeGap < 2) {
            gapClass = 'gap-medium';
          }
        }
        
        // Check if this is a single record operation (1:1)
        const isSingleRecord = op.rowCount === 1;
        const rowClass = isSingleRecord ? 'single-record-row' : '';
        
        panelHTML += `
          <tr class="${gapClass} ${rowClass}" data-line="${op.line}" title="Click to jump to log line ${op.line}">
            <td style="font-family: monospace;">${op.seq}</td>
            <td style="font-family: monospace;">${Math.round(op.rowCount).toLocaleString()}</td>
            <td><span class="operation-badge operation-${opClass}">${op.operation}</span></td>
            <td style="color: #9ca3af; font-family: monospace; font-size: 0.65rem;">${op.timestamp ? op.timestamp.split('T')[1] : 'N/A'}</td>
            <td style="font-family: monospace; font-size: 0.65rem; ${gapClass === 'gap-large' ? 'color: #ef4444; font-weight: bold;' : gapClass === 'gap-medium' ? 'color: #f59e0b;' : 'color: #10b981;'}">${timeGap ? '+' + timeGap.toFixed(2) + 's' : '-'}</td>
            <td style="font-family: monospace; font-size: 0.65rem; color: #3b82f6;">${rps ? rps : '-'}</td>
            <td style="color: #6b7280; font-size: 0.65rem;">${op.line}</td>
          </tr>
        `;
      });
      
      panelHTML += `
          </tbody>
        </table>
      `;
      
      panel.innerHTML = panelHTML;
      panelsContainer.appendChild(panel);
    });
    
    // Append everything
    tabsWrapper.appendChild(tabsHeader);
    tabsWrapper.appendChild(panelsContainer);
    bulkMapContent.appendChild(tabsWrapper);
    
    // Add click handlers to jump to log line
    panelsContainer.querySelectorAll('tbody tr[data-line]').forEach(row => {
      row.addEventListener('click', () => {
        const lineNum = parseInt(row.dataset.line);
        
        // Switch to Log View tab
        const logViewTab = document.querySelector('.tab-btn[data-tab="log-tab"]');
        if (logViewTab) logViewTab.click();
        
        showBulkMapNotification();

        // Jump to the line
        setTimeout(() => {
          jumpToLineAndHighlight(lineNum, '');
        }, 100);
      });
    });
  }
  
  // Helper to set active report link
  function setActiveReportLink(activeId) {
    const reportLinks = ['logSummaryLink', 'bulkMapLink', 'bulkActivityLink', 'fileOperationsLink', 'issuesLink', 'performanceCockpitLink', 'releaseNotesLink'];
    reportLinks.forEach(id => {
      const link = document.getElementById(id);
      if (link) {
        if (id === activeId) {
          link.classList.add('active');
        } else {
          link.classList.remove('active');
        }
      }
    });
  }
  
  // Switch to bulk map view in main area
  window.showBulkMapInMain = function() {
    // Hide all analysis views
    document.querySelectorAll('.analysis-view').forEach(v => v.style.display = 'none');
    document.getElementById('threadActivityControls').style.display = 'none';
    
    // Show bulk map view
    const bulkMapView = document.getElementById('bulkMapMainView');
    bulkMapView.style.display = 'block';
    
    // Set active report link
    setActiveReportLink('bulkMapLink');
    
    // Render bulk map if data is available
    if (window.bulkMapData) {
      renderBulkMap(window.bulkMapData, null, window.bulkMapStats, window.bulkMapInsights);
    }
  };
  
  function fetchBulkActivity() {
    if (!currentFileId) {
      console.log('No file ID for bulk activity');
      return;
    }
    
    const bulkActivityLink = document.getElementById('bulkActivityLink');
    const bulkActivityBadge = document.getElementById('bulkActivityBadge');
    
    if (!bulkActivityLink) {
      console.log('Bulk activity link element not found');
      return;
    }
    
    console.log('Fetching bulk activity analysis...');
    
    fetch(`/api/files/${currentFileId}/bulk-activity`)
      .then(res => {
        console.log('Bulk activity response status:', res.status);
        return res.json();
      })
      .then(analysis => {
        console.log('Bulk activity analysis:', analysis);
        
        if (analysis.summary.total_batches === 0 && analysis.one_by_one.length === 0) {
          console.log('No bulk activity data, hiding link');
          bulkActivityLink.style.display = 'none';
          return;
        }
        
        console.log('Showing bulk activity link with', analysis.summary.total_batches, 'batches');
        bulkActivityLink.style.display = 'flex';
        bulkActivityBadge.textContent = `(${analysis.summary.total_batches} batches)`;
        
        // Store analysis for later rendering
        window.bulkActivityData = analysis;
        
        // Show/hide file operations link based on whether there are file operations
        const fileOpsLink = document.getElementById('fileOperationsLink');
        const fileOpsCount = document.getElementById('fileOperationsCount');
        if (fileOpsLink && analysis.file_operations && analysis.file_operations.length > 0) {
          console.log('Showing file operations link with', analysis.file_operations.length, 'operations');
          fileOpsLink.style.display = 'flex';
          fileOpsCount.textContent = `(${analysis.file_operations.length})`;
          window._tempFileOperations = analysis.file_operations;
          window._tempFileOpsStats = analysis.file_ops_stats || null;
          window._tempFileOpsInsights = analysis.file_ops_insights || [];
        } else if (fileOpsLink) {
          fileOpsLink.style.display = 'none';
        }
      })
      .catch(err => {
        console.error('Failed to load bulk activity:', err);
        bulkActivityLink.style.display = 'none';
      });
  }
  
  function renderBulkActivity(analysis, targetElement) {
    const bulkActivityContent = targetElement || document.getElementById('bulkActivityMainContent');
    if (!bulkActivityContent) return;
    
    // Clear existing content first
    bulkActivityContent.innerHTML = '';
    
    // Group bulk map data by table if available
    const bulkMapByTable = {};
    if (window.bulkMapData) {
      window.bulkMapData.forEach(msg => {
        const tableMatch = msg.text.match(/(?:INSERT|UPDATE|DELETE|MERGE)\s+'([^']+)'\.+'([^']+)'/);
        if (tableMatch) {
          const tableName = `${tableMatch[1]}.${tableMatch[2]}`;
          if (!bulkMapByTable[tableName]) {
            bulkMapByTable[tableName] = [];
          }
          
          const seqMatch = msg.text.match(/seq\s+([\d:]+)/);
          const operationMatch = msg.text.match(/\]\w:\s+bulk_map:\s+seq\s+[\d:]+\s+(\w+)/);
          const timestampMatch = msg.text.match(/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})/);
          
          const seqParts = seqMatch ? seqMatch[1].split(':') : ['0'];
          const seqStart = parseInt(seqParts[0]);
          const seqEnd = seqParts[1] ? parseInt(seqParts[1]) : seqStart;
          const rowCount = seqParts.length === 2 ? seqEnd - seqStart + 1 : 1;
          
          bulkMapByTable[tableName].push({
            seq: seqMatch ? seqMatch[1] : 'N/A',
            operation: operationMatch ? operationMatch[1] : 'MERGE',
            timestamp: timestampMatch ? timestampMatch[1] : null,
            line: msg.line,
            text: msg.text,
            gap_to_finish: msg.gap_to_finish,  // Gap from backend
            rowCount: rowCount
          });
        }
      });
    }
    
    let html = '';
    const summary = analysis.summary;
    
    // Generate Performance Insights for Bulk Activity
    const bulkActivityInsights = [];
    
    // Insight: File operations efficiency correlation
    if (analysis.file_operations && analysis.file_operations.length > 1) {
      const fileOps = analysis.file_operations;
      const sizes = fileOps.map(op => op.file_size);
      const times = fileOps.map(op => op.upload_time);
      
      const avgSize = sizes.reduce((a, b) => a + b, 0) / sizes.length;
      const avgTime = times.reduce((a, b) => a + b, 0) / times.length;
      const minSize = Math.min(...sizes);
      const maxSize = Math.max(...sizes);
      const sizeRatio = maxSize / minSize;
      
      // Check for latency-dominated uploads
      if (sizeRatio > 10) {
        const smallest = fileOps.find(op => op.file_size === minSize);
        const largest = fileOps.find(op => op.file_size === maxSize);
        
        if (smallest && largest) {
          const timeRatio = largest.upload_time / smallest.upload_time;
          if (timeRatio < 2) {
            bulkActivityInsights.push({
              type: 'file_upload_latency',
              severity: 'warning',
              title: 'Network Latency Dominates Upload Time',
              message: `File sizes vary ${sizeRatio.toFixed(0)}x (${smallest.file_size_str} to ${largest.file_size_str}), but upload times are similar (~${avgTime.toFixed(1)}s). This indicates fixed network overhead is the bottleneck, not data transfer speed.`,
              recommendation: 'Batch more changes together to reduce the number of file uploads and minimize the impact of connection overhead.'
            });
          }
        }
      }
      
      // Check if too many small batches
      const smallBatches = analysis.batches ? analysis.batches.filter(b => b.changes < 100) : [];
      if (smallBatches.length > analysis.batches?.length * 0.5) {
        bulkActivityInsights.push({
          type: 'many_small_batches',
          severity: 'info',
          title: 'Many Small Batches',
          message: `${smallBatches.length} of ${analysis.batches.length} batches (${Math.round(smallBatches.length * 100 / analysis.batches.length)}%) contain fewer than 100 changes. Small batches increase file upload overhead.`,
          recommendation: 'Review batch settings or consider if transaction patterns are causing frequent small commits.'
        });
      }
    }
    
    // Insight: Frequent bulk finish reasons indicating issues
    if (analysis.bulk_finish_reasons) {
      const memoryFinishes = analysis.bulk_finish_reasons['MEM'] || 0;
      const timeoutFinishes = (analysis.bulk_finish_reasons['TIM'] || 0) + (analysis.bulk_finish_reasons['TMO'] || 0);
      const pkConflicts = (analysis.bulk_finish_reasons['PKi'] || 0) + 
                          (analysis.bulk_finish_reasons['PKu'] || 0) + 
                          (analysis.bulk_finish_reasons['PKd'] || 0);
      
      if (memoryFinishes > summary.total_batches * 0.1) {
        bulkActivityInsights.push({
          type: 'memory_pressure',
          severity: 'warning',
          title: 'Memory Pressure Detected',
          message: `${memoryFinishes} batches (${Math.round(memoryFinishes * 100 / summary.total_batches)}%) closed due to memory limits. This forces smaller batches and more frequent file uploads.`,
          recommendation: 'Consider increasing apply memory settings or reducing the number of tables in the task.'
        });
      }
      
      if (timeoutFinishes > summary.total_batches * 0.2) {
        bulkActivityInsights.push({
          type: 'timeout_batches',
          severity: 'info',
          title: 'Timeout-Triggered Batches',
          message: `${timeoutFinishes} batches (${Math.round(timeoutFinishes * 100 / summary.total_batches)}%) closed due to timeout. This is normal for low-traffic periods but may indicate suboptimal batch interval settings.`,
          recommendation: 'If timeouts are frequent during high-activity periods, consider adjusting batch timeout settings.'
        });
      }
      
      if (pkConflicts > 0) {
        bulkActivityInsights.push({
          type: 'pk_conflicts',
          severity: 'warning',
          title: 'Primary Key Conflicts',
          message: `${pkConflicts} batches encountered PK conflicts requiring batch separation. This reduces efficiency.`,
          recommendation: 'Review source transaction patterns or consider enabling change data coalescing.'
        });
      }
    }
    
    // Insight: One-by-one mode
    if (summary.one_by_one_switches > 0) {
      bulkActivityInsights.push({
        type: 'one_by_one',
        severity: 'error',
        title: 'One-by-One Processing Detected',
        message: `${summary.one_by_one_switches} tables switched to one-by-one mode. This dramatically reduces apply performance.`,
        recommendation: 'Check for constraint violations, data type mismatches, or target table issues causing bulk apply failures.'
      });
    }
    
    // Render Performance Insights - compact notices
    if (bulkActivityInsights.length > 0) {
      bulkActivityInsights.forEach(insight => {
        const colors = { warning: '#f59e0b', info: '#3b82f6', error: '#ef4444' };
        const c = colors[insight.severity] || colors.info;
        html += `<div style="margin-bottom:4px;padding:4px 8px;background:#1f2937;border-left:3px solid ${c};border-radius:2px;font-size:0.65rem;display:flex;align-items:center;gap:6px;"><span style="color:${c};font-weight:600;white-space:nowrap;">${insight.title}:</span><span style="color:#d1d5db;flex:1;">${insight.message}</span><span style="color:#10b981;cursor:help;" title="${insight.recommendation}">💡</span></div>`;
      });
    }
    
    // Summary Section
    const avgChg = summary.total_batches > 0 ? Math.round(summary.total_changes / summary.total_batches) : 0;
    html += `<div class="bulk-activity-section"><div style="margin:0 0 6px 0;font-size:0.7rem;color:#fbbf24;display:flex;align-items:center;gap:4px;"><svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M2 3a1 1 0 011-1h10a1 1 0 011 1v1a1 1 0 01-1 1H3a1 1 0 01-1-1V3zM2 7a1 1 0 011-1h10a1 1 0 011 1v1a1 1 0 01-1 1H3a1 1 0 01-1-1V7zM2 11a1 1 0 011-1h10a1 1 0 011 1v1a1 1 0 01-1 1H3a1 1 0 01-1-1v-1z"/></svg><span>Summary</span></div><div class="bulk-stats-grid"><div class="bulk-stat-item"><div class="bulk-stat-label">Total Batches</div><div class="bulk-stat-value">${summary.total_batches}</div></div><div class="bulk-stat-item"><div class="bulk-stat-label">Total Changes</div><div class="bulk-stat-value">${summary.total_changes.toLocaleString()}</div></div><div class="bulk-stat-item"><div class="bulk-stat-label">Total Applies</div><div class="bulk-stat-value">${summary.total_applies}</div></div><div class="bulk-stat-item"><div class="bulk-stat-label">Avg/Batch</div><div class="bulk-stat-value">${avgChg}</div></div></div>`;
    
    const warnSvg = '<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path fill-rule="evenodd" d="M8.982 1.566a1.13 1.13 0 00-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 018 5zm0 8a1 1 0 100-2 1 1 0 000 2z"/></svg>';
    
    if (summary.one_by_one_switches > 0) {
      html += `<div class="bulk-stats-warning">${warnSvg}<span style="color:#f59e0b;font-weight:bold;">One-by-One</span><span>${summary.one_by_one_switches} switches</span></div>`;
    }
    
    if (summary.no_bulk_total > 0 || summary.no_pk_total > 0) {
      html += '<div class="bulk-stats-issues">';
      if (summary.no_bulk_total > 0) {
        html += `<span style="color:#ef4444;display:flex;align-items:center;gap:4px;">${warnSvg}${summary.no_bulk_total} no-bulk</span>`;
      }
      if (summary.no_pk_total > 0) {
        html += `<span style="color:#ef4444;display:flex;align-items:center;gap:4px;">${warnSvg}${summary.no_pk_total} no-PK</span>`;
      }
      html += '</div>';
    }
    
    // Display bulk finish reasons
    if (analysis.bulk_finish_reasons && Object.keys(analysis.bulk_finish_reasons).length > 0) {
      const reasonLabels = {
        'MEM': { label: 'Mem', color: '#ef4444' },
        'TIM': { label: 'Stream TMO', color: '#f59e0b' },
        'TMO': { label: 'Bulk TMO', color: '#f59e0b' },
        'RES': { label: 'Resume', color: '#3b82f6' },
        'SNG': { label: 'Single', color: '#10b981' },
        'PKi': { label: 'PK-ins', color: '#8b5cf6' },
        'PKu': { label: 'PK-upd', color: '#8b5cf6' },
        'PKd': { label: 'PK-del', color: '#8b5cf6' },
        'Normal': { label: 'Normal', color: '#10b981' }
      };
      let reasonsHtml = '<div style="margin-top:8px;padding:6px;background:#1f2937;border-radius:3px;"><div style="font-size:0.65rem;color:#9ca3af;margin-bottom:4px;">Close Reasons:</div><div style="display:flex;flex-wrap:wrap;gap:4px;">';
      for (const [reason, count] of Object.entries(analysis.bulk_finish_reasons)) {
        const info = reasonLabels[reason] || { label: reason, color: '#9ca3af' };
        reasonsHtml += `<span style="display:inline-flex;align-items:center;gap:3px;padding:2px 6px;background:#111827;border-radius:2px;font-size:0.6rem;"><span style="color:${info.color};font-weight:bold;">${reason}</span><span style="color:#9ca3af;">${info.label}:</span><span style="color:#e5e7eb;font-weight:bold;">${count}</span></span>`;
      }
      reasonsHtml += '</div></div>';
      html += reasonsHtml;
    }
    
    // Display file operations statistics
    if (summary.file_operations_count && summary.file_operations_count > 0) {
      const avgC = (summary.file_compress_time_total / summary.file_operations_count).toFixed(2);
      const avgU = (summary.file_upload_time_total / summary.file_operations_count).toFixed(2);
      const tot = (summary.file_compress_time_total + summary.file_upload_time_total).toFixed(2);
      html += `<div style="margin-top:8px;padding:6px;background:#1f2937;border-radius:3px;"><div style="font-size:0.65rem;color:#9ca3af;margin-bottom:4px;">File Ops (${summary.file_operations_count}):</div><div style="display:flex;gap:12px;flex-wrap:wrap;font-size:0.6rem;"><span><span style="color:#9ca3af;">Compress:</span><span style="color:#3b82f6;font-weight:bold;margin-left:3px;">${avgC}s</span></span><span><span style="color:#9ca3af;">Upload:</span><span style="color:#10b981;font-weight:bold;margin-left:3px;">${avgU}s</span></span><span><span style="color:#9ca3af;">Total:</span><span style="color:#e5e7eb;font-weight:bold;margin-left:3px;">${tot}s</span></span></div></div>`;
    }
    
    html += '</div>';
    
    // Batches Section
    if (analysis.batches && analysis.batches.length > 0) {
      html += `<div class="bulk-activity-section"><div style="margin:0 0 6px 0;font-size:0.7rem;color:#10b981;display:flex;align-items:center;gap:4px;"><svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M3.5 0a.5.5 0 01.5.5V1h8V.5a.5.5 0 011 0V1h1a2 2 0 012 2v11a2 2 0 01-2 2H2a2 2 0 01-2-2V3a2 2 0 012-2h1V.5a.5.5 0 01.5-.5zM2 2a1 1 0 00-1 1v1h14V3a1 1 0 00-1-1H2zm13 3H1v9a1 1 0 001 1h12a1 1 0 001-1V5z"/></svg><span>Batches (${analysis.batches.length})</span></div><table class="bulk-activity-table"><thead><tr><th style="width:6%;">#</th><th style="width:18%;">Time</th><th style="width:12%;">Changes</th><th style="width:10%;">Applies</th><th style="width:14%;">Reason</th><th>Tables</th></tr></thead><tbody>`;
      
      analysis.batches.slice(0, 50).forEach((batch, idx) => {
        const rc = batch.finish_reason === 'Normal' ? 'normal' : batch.finish_reason.includes('timeout') ? 'timeout' : 'memory';
        const tbls = batch.tables.length > 0 ? batch.tables.slice(0, 2).join(', ') + (batch.tables.length > 2 ? ` +${batch.tables.length - 2}` : '') : 'N/A';
        html += `<tr><td style="color:#9ca3af;">${idx + 1}</td><td style="font-family:monospace;color:#9ca3af;">${batch.start_time || 'N/A'}</td><td>${batch.changes.toLocaleString()}</td><td>${batch.applies}</td><td><span class="batch-reason-badge batch-reason-${rc}">${batch.finish_reason}</span></td><td style="font-size:0.6rem;color:#9ca3af;">${tbls}</td></tr>`;
      });
      
      html += '</tbody></table>';
      if (analysis.batches.length > 50) {
        html += `<p style="text-align:center;color:#9ca3af;font-size:0.6rem;margin:4px 0;">Showing 50 of ${analysis.batches.length}</p>`;
      }
      html += '</div>';
    }
    
    // One-by-One Section
    if (analysis.one_by_one && analysis.one_by_one.length > 0) {
      html += `<div class="bulk-activity-section"><div style="margin:0 0 6px 0;font-size:0.7rem;color:#f59e0b;display:flex;align-items:center;gap:4px;">${warnSvg}<span>One-by-One (${analysis.one_by_one.length})</span></div><table class="bulk-activity-table"><thead><tr><th style="width:35%;">Table</th><th style="width:25%;">Start</th><th style="width:25%;">End</th><th style="width:15%;">Failed</th></tr></thead><tbody>`;
      
      analysis.one_by_one.forEach(obo => {
        const fc = obo.failed_executions > 0 ? '#ef4444' : '#10b981';
        html += `<tr><td style="font-family:monospace;color:#fbbf24;">${obo.table}</td><td style="color:#9ca3af;font-family:monospace;">${obo.start_time||'N/A'}</td><td style="color:#9ca3af;font-family:monospace;">${obo.end_time||'N/A'}</td><td style="color:${fc};">${obo.failed_executions}</td></tr>`;
      });
      
      html += '</tbody></table></div>';
    }
    
    // Store data for later processing
    window._tempPerTableStats = analysis.per_table_stats;
    window._tempBulkMapByTable = bulkMapByTable;
    window._tempFileOperations = analysis.file_operations;
    window._tempFileOpsStats = analysis.file_ops_stats || null;
    window._tempFileOpsInsights = analysis.file_ops_insights || [];
    
    if (html === '') {
      html = '<p class="placeholder-text-small">No bulk activity data found</p>';
    }
    
    bulkActivityContent.innerHTML = html;
    
    // Create Per-Table Tabs section using new DOM-based approach
    if ((window._tempPerTableStats && window._tempPerTableStats.length > 0) || (window._tempBulkMapByTable && Object.keys(window._tempBulkMapByTable).length > 0)) {
      const perTableStats = window._tempPerTableStats || [];
      const bulkMapByTable = window._tempBulkMapByTable || {};
      
      // Create a merged list of all tables from both per_table_stats and bulk_map
      const allTableNames = new Set();
      perTableStats.forEach(stat => allTableNames.add(stat.table));
      Object.keys(bulkMapByTable).forEach(table => allTableNames.add(table));
      
      // Build a unified table list with stats
      const unifiedTableStats = Array.from(allTableNames).map(tableName => {
        const existingStat = perTableStats.find(s => s.table === tableName);
        return existingStat || {
          table: tableName,
          insert: 0,
          update: 0,
          delete: 0,
          total: 0
        };
      });
      
      // Sort by bulk map operations count (descending)
      unifiedTableStats.sort((a, b) => {
        const aCount = (bulkMapByTable[a.table] || []).length;
        const bCount = (bulkMapByTable[b.table] || []).length;
        return bCount - aCount;
      });
      
      // Create section wrapper
      const section = document.createElement('div');
      section.className = 'bulk-activity-section';
      
      // Create header
      const header = document.createElement('div');
      header.style.cssText = 'margin:0 0 6px 0;font-size:0.7rem;color:#3b82f6;display:flex;align-items:center;gap:4px;';
      header.innerHTML = '<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M2 4a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V4zm2-1a1 1 0 00-1 1v1h10V4a1 1 0 00-1-1H4zM3 7v5a1 1 0 001 1h8a1 1 0 001-1V7H3z"/></svg><span>Table Details</span>';
      section.appendChild(header);
      
      // Create tabs wrapper
      const tabsWrapper = document.createElement('div');
      tabsWrapper.className = 'ba-tabs-wrapper';
      
      // Create tabs header
      const tabsHeader = document.createElement('div');
      tabsHeader.className = 'ba-tabs-header';
      tabsHeader.id = 'baTabsHeader';
      
      // Create panels container
      const panelsContainer = document.createElement('div');
      panelsContainer.className = 'ba-panels-container';
      panelsContainer.id = 'baPanelsContainer';
      
      // Create tabs and panels
      unifiedTableStats.forEach((stat, idx) => {
        // Create tab button with bulk map operations count (not total changes)
        const bulkMapForThisTable = bulkMapByTable[stat.table] || [];
        const operationsCount = bulkMapForThisTable.length;
        
        const tabButton = document.createElement('button');
        tabButton.className = `ba-tab-button ${idx === 0 ? 'ba-active' : ''}`;
        tabButton.setAttribute('data-table', stat.table);
        tabButton.innerHTML = `${stat.table.split('.')[1] || stat.table}<span class="ba-tab-count">${operationsCount.toLocaleString()}</span>`;
        tabButton.addEventListener('click', () => switchBulkTableTab(stat.table));
        tabsHeader.appendChild(tabButton);
        
        // Create panel
        const panel = document.createElement('div');
        panel.className = `ba-tab-panel ${idx === 0 ? 'ba-active' : ''}`;
        panel.setAttribute('data-table', stat.table);
        
        // Calculate stats from bulk map data
        const bulkMapForTable = bulkMapByTable[stat.table] || [];
        const operationCounts = { INSERT: 0, UPDATE: 0, DELETE: 0, MERGE: 0 };
        let singleRecordCount = 0;
        bulkMapForTable.forEach(op => {
          operationCounts[op.operation] = (operationCounts[op.operation] || 0) + 1;
          if (op.rowCount === 1) {
            singleRecordCount++;
          }
        });
        
        // Build panel content - include MERGE if present
        const hasMerge = operationCounts.MERGE > 0;
        const totOps = (operationCounts.INSERT + operationCounts.UPDATE + operationCounts.DELETE + operationCounts.MERGE).toLocaleString();
        let panelHTML = `<div class="table-summary"><div class="table-summary-grid" style="grid-template-columns:repeat(${hasMerge ? 6 : 5},1fr);"><div class="table-summary-stat"><div class="table-summary-stat-label">INSERT</div><div class="table-summary-stat-value" style="color:#10b981;">${operationCounts.INSERT.toLocaleString()}</div></div><div class="table-summary-stat"><div class="table-summary-stat-label">UPDATE</div><div class="table-summary-stat-value" style="color:#3b82f6;">${operationCounts.UPDATE.toLocaleString()}</div></div><div class="table-summary-stat"><div class="table-summary-stat-label">DELETE</div><div class="table-summary-stat-value" style="color:#ef4444;">${operationCounts.DELETE.toLocaleString()}</div></div>${hasMerge ? `<div class="table-summary-stat"><div class="table-summary-stat-label">MERGE</div><div class="table-summary-stat-value" style="color:#a855f7;font-weight:bold;">${operationCounts.MERGE.toLocaleString()}</div></div>` : ''}<div class="table-summary-stat"><div class="table-summary-stat-label">SINGLE</div><div class="table-summary-stat-value" style="color:#fbbf24;font-weight:bold;">${singleRecordCount.toLocaleString()}</div></div><div class="table-summary-stat"><div class="table-summary-stat-label">TOTAL</div><div class="table-summary-stat-value" style="color:#e5e7eb;font-weight:bold;">${totOps}</div></div></div></div>`;
        
        if (bulkMapForTable.length > 0) {
          panelHTML += `<div style="margin:6px 0 4px 0;font-size:0.65rem;color:#10b981;display:flex;align-items:center;gap:4px;"><svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor"><path d="M2 3a1 1 0 011-1h10a1 1 0 011 1v10a1 1 0 01-1 1H3a1 1 0 01-1-1V3zm2 1v2h2V4H4zm3 0v2h2V4H7zm3 0v2h2V4h-2zM4 7v2h2V7H4zm3 0v2h2V7H7zm3 0v2h2V7h-2zM4 10v2h2v-2H4zm3 0v2h2v-2H7zm3 0v2h2v-2h-2z"/></svg><span>Bulk Map (${bulkMapForTable.length})</span></div><table class="bulk-activity-table"><thead><tr><th style="width:20%;">Seq</th><th style="width:10%;">Recs</th><th style="width:13%;">Op</th><th style="width:16%;">Time</th><th style="width:10%;">Gap</th><th style="width:10%;">RPS</th><th style="width:21%;">Line</th></tr></thead><tbody>`;
          
          // Calculate gaps
          const timeGaps = [];
          bulkMapForTable.forEach((op) => {
            if (op.gap_to_finish !== null && op.gap_to_finish !== undefined) {
              timeGaps.push(op.gap_to_finish);
            }
          });
          const avgGap = timeGaps.length > 0 ? timeGaps.reduce((a, b) => a + b, 0) / timeGaps.length : 0;
          
          // Render rows
          bulkMapForTable.forEach((op) => {
            const opClass = op.operation.toLowerCase();
            let timeGap = op.gap_to_finish;
            let gapClass = '';
            let rps = null;
            
            if (timeGap !== null && timeGap !== undefined) {
              if (timeGap > 0) {
                rps = (op.rowCount / timeGap).toFixed(2);
              }
              
              if (timeGap > avgGap && avgGap > 0) {
                gapClass = 'gap-large';
              } else if (timeGap < 0.5) {
                gapClass = 'gap-small';
              } else if (timeGap < 2) {
                gapClass = 'gap-medium';
              }
            }
            
            const isSingleRecord = op.rowCount === 1;
            const rowClass = isSingleRecord ? 'single-record-row' : '';
            
            panelHTML += `
              <tr class="${gapClass} ${rowClass}" data-line="${op.line}" style="cursor: pointer;" title="Click to jump to log line ${op.line}">
                <td style="font-family: monospace;">${op.seq}</td>
                <td style="font-family: monospace;">${Math.round(op.rowCount).toLocaleString()}</td>
                <td><span class="operation-badge operation-${opClass}">${op.operation}</span></td>
                <td style="color: #9ca3af; font-family: monospace; font-size: 0.65rem;">${op.timestamp ? op.timestamp.split('T')[1] : 'N/A'}</td>
                <td style="font-family: monospace; font-size: 0.65rem; ${gapClass === 'gap-large' ? 'color: #ef4444; font-weight: bold;' : gapClass === 'gap-medium' ? 'color: #f59e0b;' : 'color: #10b981;'}">${timeGap ? '+' + timeGap.toFixed(2) + 's' : '-'}</td>
                <td style="font-family: monospace; font-size: 0.65rem; color: #3b82f6;">${rps ? rps : '-'}</td>
                <td style="color: #6b7280; font-size: 0.65rem;">${op.line}</td>
              </tr>
            `;
          });
          
          panelHTML += `</tbody></table>`;
        } else {
          panelHTML += `<p style="color: #6b7280; font-size: 0.7rem; margin: 12px 0;">No bulk map data available for this table.</p>`;
        }
        
        panel.innerHTML = panelHTML;
        panelsContainer.appendChild(panel);
      });
      
      // Assemble and append
      tabsWrapper.appendChild(tabsHeader);
      tabsWrapper.appendChild(panelsContainer);
      section.appendChild(tabsWrapper);
      bulkActivityContent.appendChild(section);
      
      // Clean up temp variables
      delete window._tempPerTableStats;
      delete window._tempBulkMapByTable;
    }
    
    // Add click handlers for bulk map operations
    bulkActivityContent.querySelectorAll('tbody tr[data-line]').forEach(row => {
      row.addEventListener('click', () => {
        const lineNum = parseInt(row.dataset.line);
        
        // Switch to Log View tab
        const logViewTab = document.querySelector('.tab-btn[data-tab="log-tab"]');
        if (logViewTab) logViewTab.click();
        
        showBulkMapNotification();

        // Jump to the line
        setTimeout(() => {
          jumpToLineAndHighlight(lineNum, '');
        }, 100);
      });
    });
  }
  
  // Switch between bulk table tabs (for bulk activity) - new implementation
  window.switchBulkTableTab = function(tableName) {
    const tabsHeader = document.getElementById('baTabsHeader');
    const panelsContainer = document.getElementById('baPanelsContainer');
    
    if (!tabsHeader || !panelsContainer) return;
    
    // Update tab buttons
    const tabs = tabsHeader.querySelectorAll('.ba-tab-button');
    tabs.forEach(tab => {
      if (tab.getAttribute('data-table') === tableName) {
        tab.classList.add('ba-active');
      } else {
        tab.classList.remove('ba-active');
      }
    });
    
    // Update panels
    const panels = panelsContainer.querySelectorAll('.ba-tab-panel');
    panels.forEach(panel => {
      if (panel.getAttribute('data-table') === tableName) {
        panel.classList.add('ba-active');
      } else {
        panel.classList.remove('ba-active');
      }
    });
  };
  
  // Switch between bulk map tabs (new implementation)
  window.switchBulkMapTab = function(tableName) {
    const tabsHeader = document.getElementById('bmTabsHeader');
    const panelsContainer = document.getElementById('bmPanelsContainer');
    
    if (!tabsHeader || !panelsContainer) return;
    
    // Update tab buttons
    const tabs = tabsHeader.querySelectorAll('.bm-tab-button');
    tabs.forEach(tab => {
      if (tab.getAttribute('data-table') === tableName) {
        tab.classList.add('bm-active');
      } else {
        tab.classList.remove('bm-active');
      }
    });
    
    // Update panels
    const panels = panelsContainer.querySelectorAll('.bm-tab-panel');
    panels.forEach(panel => {
      if (panel.getAttribute('data-table') === tableName) {
        panel.classList.add('bm-active');
      } else {
        panel.classList.remove('bm-active');
      }
    });
  };
  
  // Switch to bulk activity view in main area
  window.showBulkActivityInMain = function() {
    // Hide all analysis views
    document.querySelectorAll('.analysis-view').forEach(v => v.style.display = 'none');
    document.getElementById('threadActivityControls').style.display = 'none';
    
    // Show bulk activity view
    const bulkActivityView = document.getElementById('bulkActivityMainView');
    bulkActivityView.style.display = 'block';
    
    // Set active report link
    setActiveReportLink('bulkActivityLink');
    
    // Render bulk activity if data is available
    if (window.bulkActivityData) {
      renderBulkActivity(window.bulkActivityData);
    }
  };

  // Switch to file operations view in main area
  window.showFileOperationsInMain = function() {
    // Hide all analysis views
    document.querySelectorAll('.analysis-view').forEach(v => v.style.display = 'none');
    document.getElementById('threadActivityControls').style.display = 'none';
    
    // Show file operations view
    const fileOpsView = document.getElementById('fileOperationsMainView');
    fileOpsView.style.display = 'block';
    
    // Set active report link
    setActiveReportLink('fileOperationsLink');
    
    // Render file operations if data is available
    if (window._tempFileOperations) {
      renderFileOperations(window._tempFileOperations, window._tempFileOpsStats, window._tempFileOpsInsights);
    }
  };

  function renderFileOperations(fileOperations, stats, insights) {
    const fileOpsContent = document.getElementById('fileOperationsMainContent');
    if (!fileOpsContent) return;
    
    fileOpsContent.innerHTML = '';
    
    if (!fileOperations || fileOperations.length === 0) {
      fileOpsContent.innerHTML = '<p class="placeholder-text-small">No file operations found</p>';
      return;
    }
    
    let html = `
      <div style="margin: 0 0 16px 0; font-size: 0.85rem; color: #3b82f6; display: flex; align-items: center; gap: 6px;">
        <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor">
          <path d="M4 0a2 2 0 00-2 2v12a2 2 0 002 2h8a2 2 0 002-2V2a2 2 0 00-2-2H4zm0 1h8a1 1 0 011 1v12a1 1 0 01-1 1H4a1 1 0 01-1-1V2a1 1 0 011-1z"/>
          <path d="M5.5 6.5A.5.5 0 016 6h4a.5.5 0 010 1H6a.5.5 0 01-.5-.5zm0 2A.5.5 0 016 8h4a.5.5 0 010 1H6a.5.5 0 01-.5-.5zm0 2A.5.5 0 016 10h4a.5.5 0 010 1H6a.5.5 0 01-.5-.5z"/>
        </svg>
        <span style="font-weight: 500;">File Upload Operations (${fileOperations.length})</span>
      </div>
    `;
    
    // Render Performance Insights - compact notices
    if (insights && insights.length > 0) {
      insights.forEach(insight => {
        const colors = { warning: '#f59e0b', info: '#3b82f6', error: '#ef4444' };
        const color = colors[insight.severity] || colors.info;
        html += `<div style="margin-bottom: 6px; padding: 6px 10px; background: #1f2937; border-left: 3px solid ${color}; border-radius: 3px; font-size: 0.7rem; display: flex; align-items: center; gap: 8px;">
          <span style="color: ${color}; font-weight: 600; white-space: nowrap;">${insight.title}:</span>
          <span style="color: #d1d5db; flex: 1;">${insight.message}</span>
          <span style="color: #10b981; cursor: help;" title="${insight.recommendation}">💡</span>
        </div>`;
      });
    }
    
    // Render Statistics summary
    if (stats) {
      const formatBytes = (bytes) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
      };
      
      html += `
        <div style="margin-bottom: 8px; padding: 6px 10px; background: #111827; border-radius: 4px; display: flex; flex-wrap: wrap; gap: 12px; font-size: 0.65rem;">
          <span><span style="color: #6b7280;">Data:</span> <span style="color: #e5e7eb; font-weight: bold;">${formatBytes(stats.total_data_bytes)}</span></span>
          <span><span style="color: #6b7280;">Time:</span> <span style="color: #e5e7eb; font-weight: bold;">${stats.total_upload_time}s</span></span>
          <span><span style="color: #6b7280;">Throughput:</span> <span style="color: #3b82f6; font-weight: bold;">${stats.avg_throughput_kbps} KB/s</span></span>
          <span><span style="color: #6b7280;">Size:</span> <span style="color: #9ca3af;">${formatBytes(stats.min_size)} - ${formatBytes(stats.max_size)}</span></span>
          <span><span style="color: #6b7280;">Time:</span> <span style="color: #9ca3af;">${stats.min_time}s - ${stats.max_time}s</span></span>
        </div>`;
    }
    
    // Calculate average throughput for highlighting
    const avgThroughput = fileOperations.reduce((sum, op) => sum + (op.throughput_kbps || 0), 0) / fileOperations.length;
    
    html += `
      <table class="bulk-map-table">
        <thead>
          <tr>
            <th style="width: 15%;">File Name</th>
            <th style="width: 25%;">Tables</th>
            <th style="width: 10%;">File Size</th>
            <th style="width: 10%;">Compress</th>
            <th style="width: 10%;">Upload</th>
            <th style="width: 10%;">Total</th>
            <th style="width: 10%;">Throughput</th>
            <th style="width: 10%;">Completed</th>
          </tr>
        </thead>
        <tbody>
    `;
    
    fileOperations.forEach((fileOp, idx) => {
      const endTime = fileOp.upload_end ? fileOp.upload_end.split('T')[1] : 'N/A';
      const rowClass = idx % 2 === 0 ? '' : 'alt-row';
      const tablesDisplay = fileOp.tables || 'N/A';
      const throughput = fileOp.throughput_kbps || 0;
      
      // Color throughput based on performance relative to average
      let throughputColor = '#10b981'; // green for good
      let throughputStyle = '';
      if (throughput < avgThroughput * 0.5) {
        throughputColor = '#ef4444'; // red for low
        throughputStyle = 'font-weight: bold;';
      } else if (throughput < avgThroughput * 0.8) {
        throughputColor = '#f59e0b'; // yellow for medium
      }
      
      // Format throughput display
      let throughputDisplay = `${throughput.toFixed(0)} KB/s`;
      if (throughput > 1024) {
        throughputDisplay = `${(throughput / 1024).toFixed(1)} MB/s`;
      }
      
      html += `
        <tr class="${rowClass}">
          <td style="font-family: monospace; color: #10b981; font-weight: 500;">${fileOp.file_name}</td>
          <td style="font-family: monospace; color: #3b82f6; font-size: 0.7rem;" title="${tablesDisplay}">${tablesDisplay}</td>
          <td style="color: #e5e7eb; font-weight: bold;">${fileOp.file_size_str}</td>
          <td style="color: #9ca3af;">${fileOp.compress_time}s</td>
          <td style="color: #10b981;">${fileOp.upload_time}s</td>
          <td style="color: #e5e7eb; font-weight: bold;">${fileOp.total_time}s</td>
          <td style="color: ${throughputColor}; ${throughputStyle} font-family: monospace; font-size: 0.7rem;">${throughputDisplay}</td>
          <td style="font-family: monospace; color: #9ca3af; font-size: 0.65rem;">${endTime}</td>
        </tr>
      `;
    });
    
    html += `</tbody></table>`;
    fileOpsContent.innerHTML = html;
  }

  // Fetch and display possible issues
  function fetchIssues() {
    if (!currentFileId) return;
    
    const issuesLink = document.getElementById('issuesLink');
    const issuesCount = document.getElementById('issuesCount');
    
    if (!issuesLink) return;
    
    // Show loading state
    issuesLink.style.display = 'flex';
    issuesCount.textContent = '(analyzing...)';
    issuesCount.style.opacity = '0.6';
    
    fetch(`/api/files/${currentFileId}/issues`)
      .then(res => res.json())
      .then(data => {
        issuesCount.style.opacity = '1';
        
        if (data.summary.total_issues === 0) {
          issuesLink.style.display = 'none';
          return;
        }
        
        issuesLink.style.display = 'flex';
        issuesCount.textContent = `(${data.summary.total_issues})`;
        window.issuesData = data;
      })
      .catch(err => {
        console.error('Failed to load issues:', err);
        issuesLink.style.display = 'none';
        issuesCount.style.opacity = '1';
      });
  }
  
  // Show issues in main view
  window.showIssuesInMain = function() {
    // Hide ALL other views
    document.querySelectorAll('.analysis-view').forEach(v => v.style.display = 'none');
    document.getElementById('threadActivityControls').style.display = 'none';
    
    // Show issues view (uses flexbox layout)
    document.getElementById('issuesMainView').style.display = 'flex';
    
    // Set active report link
    setActiveReportLink('issuesLink');
    
    if (window.issuesData) {
      renderIssues(window.issuesData);
    }
  };
  
  // Helper function to highlight SQL column in INSERT/UPDATE statements
  function highlightSQLColumn(text, columnNumber) {
    if (!columnNumber || !text) {
      return escapeHtml(text);
    }
    
    // Check if this line contains an INSERT or UPDATE statement with column names
    const insertMatch = text.match(/INSERT\s+INTO\s+[^\(]+\(([^)]+)\)/i);
    const updateMatch = text.match(/UPDATE\s+[^\s]+\s+SET\s+(.+?)(?:WHERE|$)/i);
    
    let columnNames = null;
    let columnStartIndex = -1;
    
    if (insertMatch) {
      columnNames = insertMatch[1];
      columnStartIndex = text.indexOf(columnNames);
    } else if (updateMatch) {
      columnNames = updateMatch[1];
      columnStartIndex = text.indexOf(columnNames);
    }
    
    if (!columnNames || columnStartIndex === -1) {
      return escapeHtml(text);
    }
    
    // Parse column names - split by comma, handling quoted identifiers
    const columns = [];
    let current = '';
    let inQuotes = false;
    let quoteChar = null;
    
    for (let i = 0; i < columnNames.length; i++) {
      const char = columnNames[i];
      
      if ((char === '"' || char === "'") && (!inQuotes || quoteChar === char)) {
        inQuotes = !inQuotes;
        quoteChar = inQuotes ? char : null;
        current += char;
      } else if (char === ',' && !inQuotes) {
        if (current.trim()) {
          columns.push(current.trim());
        }
        current = '';
      } else {
        current += char;
      }
    }
    
    if (current.trim()) {
      columns.push(current.trim());
    }
    
    // Get the target column (1-indexed)
    if (columnNumber > 0 && columnNumber <= columns.length) {
      const targetColumn = columns[columnNumber - 1];
      console.log(`SQL Column Highlighting: Column #${columnNumber} = "${targetColumn}" in line with ${columns.length} columns`);
      
      // Split text into parts: before columns, columns section, after columns
      const beforeColumns = text.substring(0, columnStartIndex);
      const afterColumns = text.substring(columnStartIndex + columnNames.length);
      
      // Escape the before and after parts
      let result = escapeHtml(beforeColumns);
      
      // Process the columns section - escape each column but highlight the target
      let occurrenceIndex = 0;
      let processedColumns = columnNames;
      
      // Strip quotes from target column for matching
      const columnNameOnly = targetColumn.replace(/^["']|["']$/g, '');
      const safePattern = columnNameOnly.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      
      // Match the column with optional quotes
      const columnRegex = new RegExp(`(["']?)(${safePattern})(["']?)`, 'gi');
      
      processedColumns = processedColumns.replace(columnRegex, (match, quote1, colName, quote2) => {
        occurrenceIndex++;
        const escapedQuote1 = escapeHtml(quote1);
        const escapedColName = escapeHtml(colName);
        const escapedQuote2 = escapeHtml(quote2);
        
        if (occurrenceIndex === columnNumber) {
          // Highlight this occurrence
          return `${escapedQuote1}<span class="sql-column-highlight">${escapedColName}</span>${escapedQuote2}`;
        }
        return `${escapedQuote1}${escapedColName}${escapedQuote2}`;
      });
      
      // Escape any remaining characters in the columns section that weren't part of the column names
      // Split by the column names and escape the separators
      result += processedColumns;
      result += escapeHtml(afterColumns);
      
      return result;
    }
    
    return escapeHtml(text);
  }
  
    function renderIssues(data) {
    const issuesContent = document.getElementById('issuesMainContent');
    if (!issuesContent) return;
    
    // Build compact inline timeline
    let timelineHtml = '';
    if (data.timeline && data.timeline.events.length > 0) {
      const startTime = data.timeline.start_time || '';
      const endTime = data.timeline.end_time || '';
      
      timelineHtml = `
        <div class="issues-timeline-inline">
          <span class="timeline-time">${formatTimelineTime(startTime)}</span>
          <div class="timeline-bar">
            ${data.timeline.events.map((evt, idx) => `
              <div class="timeline-dot ${evt.severity}" 
                   style="left: ${evt.position}%;" 
                   data-line="${evt.line_number}"
                   onclick="scrollToIssueByLine(${evt.line_number}, this)"
                   title="${evt.severity.toUpperCase()} at ${formatTimelineTime(evt.timestamp)}">
              </div>
            `).join('')}
          </div>
          <span class="timeline-time">${formatTimelineTime(endTime)}</span>
        </div>
      `;
    }
    
    // Left side: Issues list container
    let listHtml = `
      <div class="issues-list-container">
        <div class="issues-compact-header">
          <div class="issues-header-row">
            <div class="issues-title">
              <svg width="12" height="12" viewBox="0 0 16 16" fill="#ef4444">
                <path d="M8.982 1.566a1.13 1.13 0 00-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 018 5zm0 8a1 1 0 100-2 1 1 0 000 2z"/>
              </svg>
              <span>Issues</span>
            </div>
            <div class="issues-stats-inline">
              <span class="stat-badge total">${data.summary.total_issues} total</span>
              ${data.summary.fatal_count > 0 ? `<span class="stat-badge fatal">${data.summary.fatal_count} fatal</span>` : ''}
              <span class="stat-badge error">${data.summary.error_count} errors</span>
              <span class="stat-badge warning">${data.summary.warning_count} warnings</span>
            </div>
            <div class="font-size-controls">
              <button class="font-size-btn" onclick="adjustFontSize('issues', -1)" title="Decrease font size">A-</button>
              <button class="font-size-btn" onclick="adjustFontSize('issues', 1)" title="Increase font size">A+</button>
            </div>
          </div>
          ${timelineHtml}
        </div>
        <div class="issues-list" id="issuesList">
    `;
    
    // Render each issue group
    data.issues.forEach((issue, idx) => {
      const groupId = `issue-group-${idx}`;
      const firstTimestamp = issue.occurrences[0]?.timestamp || '';
      
      // Get all line numbers for this issue group
      const groupLineNumbers = issue.occurrences.map(occ => occ.line_number);
      
      listHtml += `
        <div class="issue-group" id="${groupId}" data-lines="${groupLineNumbers.join(',')}" data-issue-idx="${idx}">
          <div class="issue-group-header" onclick="toggleIssueGroup('${groupId}')">
            <svg class="issue-expand-icon" width="8" height="8" viewBox="0 0 16 16" fill="currentColor">
              <path fill-rule="evenodd" d="M4.646 1.646a.5.5 0 01.708 0l6 6a.5.5 0 010 .708l-6 6a.5.5 0 01-.708-.708L10.293 8 4.646 2.354a.5.5 0 010-.708z"/>
            </svg>
            <span class="issue-severity-badge ${issue.severity}">${issue.severity}</span>
            <span class="issue-component">[${issue.component}]</span>
            <span class="issue-message" title="${escapeHtml(issue.message_summary)}">${escapeHtml(issue.message_summary)}</span>
            <span class="issue-timestamp">${formatTimelineTime(firstTimestamp)}</span>
            <span class="issue-count">${issue.occurrences.length}x</span>
            <button class="issue-resolve-icon-btn" onclick="event.stopPropagation(); window.saveIssueFinding(${idx});" title="Add to Findings">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                <path d="M2 2a2 2 0 012-2h8a2 2 0 012 2v13.5a.5.5 0 01-.777.416L8 13.101l-5.223 2.815A.5.5 0 012 15.5V2zm2-1a1 1 0 00-1 1v12.566l4.723-2.482a.5.5 0 01.554 0L13 14.566V2a1 1 0 00-1-1H4z"/>
              </svg>
            </button>
            <button class="issue-resolve-icon-btn" onclick="event.stopPropagation(); window.openIssueResolution(${idx});" title="Get Resolution">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                <path d="M11.742 10.344a6.5 6.5 0 10-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 001.415-1.414l-3.85-3.85a1.007 1.007 0 00-.115-.1zM12 6.5a5.5 5.5 0 11-11 0 5.5 5.5 0 0111 0z"/>
              </svg>
            </button>
          </div>
          <div class="issue-group-content">
      `;
      
      // Show first 5 occurrences
      issue.occurrences.slice(0, 5).forEach(occ => {
        const severityClass = issue.severity === 'warning' ? 'warning-line' : 'error-line';
        
        // Extract column number from error message if present
        const columnMatch = occ.text.match(/Column:\s*(\d+)/i);
        const columnNumber = columnMatch ? parseInt(columnMatch[1]) : null;
        
        listHtml += `
          <div class="issue-occurrence">
            ${occ.timestamp ? `<div class="occurrence-time">${occ.timestamp}</div>` : ''}
        `;
        
        // Before context - check for SQL statements to highlight
        occ.before.forEach(ctx => {
          const highlightedText = highlightSQLColumn(ctx.text, columnNumber);
          console.log('Before context length:', ctx.text.length, 'Highlighted length:', highlightedText.length);
          listHtml += `<div class="issue-context-line before"><span class="issue-line-number">${ctx.line + 1}</span>${highlightedText}</div>`;
        });
        
        // The issue line itself - with severity-based styling
        listHtml += `<div class="issue-context-line issue-line ${severityClass}"><span class="issue-line-number">${occ.line_number + 1}</span>${escapeHtml(occ.text)}</div>`;
        
        // After context
        occ.after.forEach(ctx => {
          const highlightedText = highlightSQLColumn(ctx.text, columnNumber);
          listHtml += `<div class="issue-context-line after"><span class="issue-line-number">${ctx.line + 1}</span>${highlightedText}</div>`;
        });
        
        listHtml += `</div>`;
      });
      
      if (issue.occurrences.length > 5) {
        listHtml += `<p style="text-align: center; color: #6b7280; font-size: 0.7rem; margin: 8px 0;">... and ${issue.occurrences.length - 5} more occurrences</p>`;
      }
      
      // Add Google search button for error codes (in actions row if needed)
      if (issue.error_code) {
        listHtml += `
          <div class="issue-actions-row" style="display: flex; gap: 8px; margin-top: 8px; padding-top: 8px; border-top: 1px solid #1f2937;">
            <button class="issue-google-btn" onclick="event.stopPropagation(); window.open('https://www.google.com/search?q=' + encodeURIComponent('Qlik Replicate ${issue.error_code}'), '_blank')">
              <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
                <path d="M11.742 10.344a6.5 6.5 0 10-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 001.415-1.414l-3.85-3.85a1.007 1.007 0 00-.115-.1zM12 6.5a5.5 5.5 0 11-11 0 5.5 5.5 0 0111 0z"/>
              </svg>
              Google: ${issue.error_code}
            </button>
          </div>
        `;
      }
      
      listHtml += `
          </div>
        </div>
      `;
    });
    
    listHtml += `</div></div>`; // Close issues-list and issues-list-container

    // Bottom: Resolution panel with toggle bar (initially collapsed)
    const panelHtml = `
      <div id="issueResolutionPanel" class="issue-resolution-panel collapsed">
        <div class="issue-resolution-toggle-bar" onclick="window.toggleResolutionPanel()">
          <div class="issue-resolution-toggle-title">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
              <path fill-rule="evenodd" d="M1.646 4.646a.5.5 0 01.708 0L8 10.293l5.646-5.647a.5.5 0 01.708.708l-6 6a.5.5 0 01-.708 0l-6-6a.5.5 0 010-.708z"/>
            </svg>
            <span id="resolutionPanelTitle">Resolution Panel</span>
          </div>
          <span class="issue-resolution-toggle-hint" id="resolutionPanelHint">Click the 🔍 icon on any issue</span>
        </div>
        <div class="issue-resolution-inner">
          <div class="issue-resolution-placeholder">
            <svg width="32" height="32" viewBox="0 0 16 16" fill="currentColor" style="opacity: 0.4;">
              <path d="M11.742 10.344a6.5 6.5 0 10-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 001.415-1.414l-3.85-3.85a1.007 1.007 0 00-.115-.1zM12 6.5a5.5 5.5 0 11-11 0 5.5 5.5 0 0111 0z"/>
            </svg>
            <p>Click the <strong>🔍 icon</strong> on any issue header<br>to see AI insights, KB articles, and web search.</p>
          </div>
        </div>
      </div>
    `;

    issuesContent.innerHTML = listHtml + panelHtml;
  }
  
  // Toggle resolution panel collapse state
  window.toggleResolutionPanel = function() {
    const panel = document.getElementById('issueResolutionPanel');
    if (panel) {
      panel.classList.toggle('collapsed');
    }
  };
  
  // Format timeline time for display
  function formatTimelineTime(timestamp) {
    if (!timestamp) return '';
    // Extract time portion (HH:MM:SS) from timestamp
    const timeMatch = timestamp.match(/(\d{2}:\d{2}:\d{2})/);
    return timeMatch ? timeMatch[1] : timestamp;
  }
  
  // Toggle issue group expansion
  window.toggleIssueGroup = function(groupId) {
    const group = document.getElementById(groupId);
    if (!group) return;
    
    const isExpanding = !group.classList.contains('expanded');
    
    // Close all other expanded groups (accordion behavior)
    document.querySelectorAll('.issue-group.expanded').forEach(g => {
      if (g.id !== groupId) {
        g.classList.remove('expanded');
      }
    });
    
    // Clear all active timeline dots
    document.querySelectorAll('.timeline-dot.active').forEach(dot => dot.classList.remove('active'));
    
    // Toggle this group
    group.classList.toggle('expanded');
    
    // If expanding, highlight corresponding timeline dots
    if (isExpanding) {
      const lineNumbers = group.dataset.lines ? group.dataset.lines.split(',').map(Number) : [];
      lineNumbers.forEach(lineNum => {
        const dot = document.querySelector(`.timeline-dot[data-line="${lineNum}"]`);
        if (dot) {
          dot.classList.add('active');
        }
      });
    }
  };

  // Cache for resolution results and hidden finding ids
  window.issueResolutionCache = {};

  function renderIssueResolutionLoading(issue) {
    const panel = document.getElementById('issueResolutionPanel');
    if (!panel) return;
    
    // Expand the panel and update title
    panel.classList.remove('collapsed');
    const titleEl = document.getElementById('resolutionPanelTitle');
    const hintEl = document.getElementById('resolutionPanelHint');
    if (titleEl) titleEl.textContent = `Resolution: ${issue.message_summary.slice(0, 50)}${issue.message_summary.length > 50 ? '...' : ''}`;
    if (hintEl) hintEl.textContent = 'Loading...';
    
    // Highlight the selected issue group
    document.querySelectorAll('.issue-group.selected').forEach(g => g.classList.remove('selected'));
    
    // Update inner content
    const inner = panel.querySelector('.issue-resolution-inner');
    if (inner) {
      inner.innerHTML = `
        <div class="issue-resolution-loading">
          <div class="ai-loading-spinner"></div>
          <p>Loading insights for this issue...</p>
        </div>
      `;
    }
  }

  function renderIssueResolution(data, issue, occ, cacheKey) {
    const panel = document.getElementById('issueResolutionPanel');
    if (!panel) return;

    // Update toggle bar with severity-colored text
    const titleEl = document.getElementById('resolutionPanelTitle');
    const hintEl = document.getElementById('resolutionPanelHint');
    if (titleEl) titleEl.innerHTML = `<span class="resolution-severity-${issue.severity}">Resolution: ${issue.severity.toUpperCase()}</span>`;
    if (hintEl) hintEl.textContent = `[${issue.component}] • Line ${occ.line_number + 1}`;

    // Get data
    const kbMatches = (data.kb && data.kb.matches) || [];
    const aiReport = data.ai_report;
    const tavily = data.tavily;
    const tavilyConfigured = data.tavily_configured;
    const searchQuery = data.query || '';

    // Store the current query in cache for editing
    const cache = window.issueResolutionCache[cacheKey];
    if (cache) cache.searchQuery = searchQuery;

    // Build sections in order: Web Search Result (if has answer) → AI Report → KB → Web Search (with editable query at bottom)

    // Web Search Result section (only if we have results)
    let webResultHtml = '';
    if (tavily && tavily.answer) {
      webResultHtml = `
        <div class="issue-resolution-section" style="border-left: 3px solid #f59e0b;">
          <h4>🌐 Web Search Result</h4>
          <div class="issue-search-query">Search: "${escapeHtml(searchQuery)}"</div>
          <div class="issue-tavily-ans">
            <div class="issue-tavily-header">
              <span style="color: #22c55e;">✓ Answer found</span>
              <div class="issue-tavily-actions">
                <button class="issue-btn" onclick="window.thumbsUpIssueResolution('${cacheKey}')" title="Good answer - save for future">👍</button>
                <button class="issue-btn" onclick="window.saveIssueResolutionToFindings('${cacheKey}')" title="Save to Findings">
                  <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M2 2a2 2 0 012-2h8a2 2 0 012 2v13.5a.5.5 0 01-.777.416L8 13.101l-5.223 2.815A.5.5 0 012 15.5V2z"/>
                  </svg>
                  Save
                </button>
                <button class="issue-btn" onclick="window.thumbsDownIssueResolution('${cacheKey}')" title="Not helpful - search again">👎</button>
              </div>
            </div>
            <div class="issue-tavily-body">${escapeHtml(tavily.answer)}</div>
            ${(tavily.sources && tavily.sources.length > 0) ? `
              <div class="issue-tavily-sources">
                <strong>Sources:</strong> ${tavily.sources.map(s => `<a href="${s.url}" target="_blank">${s.title || 'Link'}</a>`).join(' • ')}
              </div>
            ` : ''}
          </div>
        </div>
      `;
    }

    // AI Report section
    let aiHtml = '';
    if (aiReport && aiReport.excerpt) {
      aiHtml = `
        <div class="issue-resolution-section" style="border-left: 3px solid #8b5cf6;">
          <h4>🤖 AI Report Excerpt</h4>
          <div class="issue-ai-snippet">
            <div class="issue-ai-body">${escapeHtml(aiReport.excerpt)}</div>
            <div class="issue-ai-footer">
              <a href="#" onclick="window.goToAIReport(); return false;" class="issue-link">View Full AI Report →</a>
            </div>
          </div>
        </div>
      `;
    } else {
      aiHtml = `
        <div class="issue-resolution-section">
          <h4>🤖 AI Report</h4>
          <p class="placeholder-text-small" style="margin: 0;">No AI report generated yet. <a href="#" onclick="window.goToAIReport(); return false;" class="issue-link">Generate one from AI Insights tab</a>.</p>
        </div>
      `;
    }

    // KB section - only if matches found
    let kbHtml = '';
    if (kbMatches.length > 0) {
      kbHtml = `
        <div class="issue-resolution-section" style="border-left: 3px solid #10b981;">
          <h4>📚 Knowledge Base (${kbMatches.length} match${kbMatches.length > 1 ? 'es' : ''})</h4>
          ${kbMatches.map((m, i) => {
            const title = m.source || `KB Article ${i + 1}`;
            const link = m.url ? `<a href="${m.url}" target="_blank" class="issue-link">${escapeHtml(title)}</a>` : escapeHtml(title);
            const similarity = m.similarity ? ` (${Math.round(m.similarity * 100)}% match)` : '';
            return `
              <div class="issue-kb-match">
                <div class="issue-kb-header">
                  <span>${link}${similarity}</span>
                  <button class="issue-btn-small" onclick="window.saveKBToFindings('${cacheKey}', ${i})" title="Save to Findings">
                    <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor">
                      <path d="M2 2a2 2 0 012-2h8a2 2 0 012 2v13.5a.5.5 0 01-.777.416L8 13.101l-5.223 2.815A.5.5 0 012 15.5V2z"/>
                    </svg>
                  </button>
                </div>
                <div class="issue-kb-content">${escapeHtml(m.content || '')}</div>
              </div>
            `;
          }).join('')}
        </div>
      `;
    }

    // Web Search section with editable query (always at bottom if no result yet)
    let webSearchHtml = '';
    if (!tavily || !tavily.answer) {
      const statusMsg = !tavilyConfigured 
        ? '<span style="color: #f87171;">Tavily API key not configured. Add it in AI Settings.</span>'
        : 'Edit the query below and click Search to find solutions online.';
      webSearchHtml = `
        <div class="issue-resolution-section" style="border-left: 3px solid #6b7280;">
          <h4>🌐 Web Search</h4>
          <p class="placeholder-text-small" style="margin: 0 0 10px 0;">${statusMsg}</p>
          <div class="issue-search-input-row">
            <input type="text" id="issueSearchQueryInput" class="issue-search-input" value="${escapeHtml(searchQuery)}" placeholder="Enter search query...">
            <button class="issue-resolve-btn" onclick="window.runIssueWebSearchWithQuery('${cacheKey}')" ${!tavilyConfigured ? 'disabled' : ''}>
              <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
                <path d="M11.742 10.344a6.5 6.5 0 10-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 001.415-1.414l-3.85-3.85a1.007 1.007 0 00-.115-.1zM12 6.5a5.5 5.5 0 11-11 0 5.5 5.5 0 0111 0z"/>
              </svg>
              Search
            </button>
          </div>
        </div>
      `;
    }

    // Build header with full error message (no search button in header anymore)
    const headerHtml = `
      <div class="issue-resolution-header">
        <div style="flex: 1; min-width: 0;">
          <div class="issue-resolution-title">
            <span class="issue-severity-badge ${issue.severity}">${issue.severity}</span>
            Full Error Message
          </div>
          <div class="issue-full-error">${escapeHtml(occ.text || issue.message_summary)}</div>
          <div class="issue-resolution-meta">
            [${issue.component}] • Line ${occ.line_number + 1} • ${issue.occurrences.length} occurrence${issue.occurrences.length > 1 ? 's' : ''}
          </div>
        </div>
        <button class="issue-btn back-btn" onclick="window.clearIssueResolution()" title="Close">✕</button>
      </div>
    `;

    // Build content: Header → Web Result (if any) → AI Report → KB → Web Search (if no result)
    const inner = panel.querySelector('.issue-resolution-inner');
    if (inner) {
      inner.innerHTML = headerHtml + webResultHtml + aiHtml + kbHtml + webSearchHtml;
    }
  }
  
  // Run web search with custom/edited query
  window.runIssueWebSearchWithQuery = function(cacheKey) {
    const input = document.getElementById('issueSearchQueryInput');
    const customQuery = input ? input.value.trim() : '';
    
    const cache = window.issueResolutionCache[cacheKey];
    if (!cache) return;
    
    // Store custom query in cache
    cache.customQuery = customQuery;
    
    runIssueWebSearch(cacheKey, customQuery);
  };
  
  // Go to AI Report tab
  window.goToAIReport = function() {
    // Switch to Resources tab and select AI Insights subtab
    document.querySelector('[data-tab="resources-tab"]')?.click();
    setTimeout(() => {
      document.querySelector('[data-subtab="insights-subtab"]')?.click();
    }, 100);
  };
  
  // Save KB article to findings
  window.saveKBToFindings = async function(cacheKey, kbIndex) {
    const cache = window.issueResolutionCache[cacheKey];
    if (!cache) return;
    
    const { data, issue, occ } = cache;
    const kbMatch = (data.kb?.matches || [])[kbIndex];
    if (!kbMatch) return;
    
    const title = kbMatch.source || `KB Article for ${issue.message_summary.slice(0, 50)}`;
    const content = `**KB Article:** ${kbMatch.source || 'Unknown'}\n\n${kbMatch.content || ''}\n\n**URL:** ${kbMatch.url || 'N/A'}`;
    
    try {
      await fetch('/api/llm/findings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: currentFileId,
          finding_type: 'custom',
          title: title.slice(0, 120),
          content,
          line_number: occ.line_number,
          metadata: { source: 'kb_article', url: kbMatch.url }
        })
      });
      
      // Refresh findings
      if (window.savedFindingsManager) {
        window.savedFindingsManager.loadFindings();
      }
      
      // Show brief feedback
      const btn = event.target.closest('button');
      if (btn) {
        const originalHtml = btn.innerHTML;
        btn.innerHTML = '✓';
        btn.style.color = '#22c55e';
        setTimeout(() => {
          btn.innerHTML = originalHtml;
          btn.style.color = '';
        }, 1500);
      }
    } catch (e) {
      console.error('Failed to save KB to findings:', e);
    }
  };
  
  // Thumbs up - save good answer to DB for future retrieval
  window.thumbsUpIssueResolution = async function(cacheKey) {
    const cache = window.issueResolutionCache[cacheKey];
    if (!cache) return;
    
    const { data, issue, occ } = cache;
    if (!data.tavily?.answer) return;
    
    // Save to findings as a verified resolution
    const content = `**Issue:** ${issue.message_summary}\n\n**Verified Answer:** ${data.tavily.answer}\n\n**Sources:**\n${(data.tavily.sources || []).map(s => `- ${s.title || s.url}: ${s.url}`).join('\n') || 'N/A'}`;
    
    try {
      await fetch('/api/llm/findings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: currentFileId,
          finding_type: 'custom',
          title: `✓ Verified: ${issue.message_summary}`.slice(0, 120),
          content,
          line_number: occ.line_number,
          metadata: { source: 'verified_resolution', search_query: data.query, thumbs_up: true }
        })
      });
      
      // TODO: Also save to vector store for future retrieval
      
      // Refresh findings
      if (window.savedFindingsManager) {
        window.savedFindingsManager.loadFindings();
      }
      
      // Show feedback on the button
      const btn = event.target.closest('button');
      if (btn) {
        btn.textContent = '✓ Saved!';
        btn.style.color = '#22c55e';
        btn.disabled = true;
      }
    } catch (e) {
      console.error('Failed to save verified resolution:', e);
    }
  };

  function openIssueResolution(index) {
    if (!window.issuesData || !window.issuesData.issues) return;
    const issue = window.issuesData.issues[index];
    if (!issue || !issue.occurrences || issue.occurrences.length === 0) return;
    const occ = issue.occurrences[0];
    const cacheKey = `issue-${index}`;

    // If clicking a different issue, collapse the panel first then reopen
    const panel = document.getElementById('issueResolutionPanel');
    const currentCache = window.issueResolutionCache[window.currentResolutionKey];
    if (window.currentResolutionKey && window.currentResolutionKey !== cacheKey && panel && !panel.classList.contains('collapsed')) {
      // Different issue selected - collapse first
      panel.classList.add('collapsed');
    }
    window.currentResolutionKey = cacheKey;

    // Mark the selected issue group
    document.querySelectorAll('.issue-group.selected').forEach(g => g.classList.remove('selected'));
    const selectedGroup = document.getElementById(`issue-group-${index}`);
    if (selectedGroup) {
      selectedGroup.classList.add('selected');
    }

    renderIssueResolutionLoading(issue);

    // Build context snippet from the primary occurrence
    const snippet = [occ.text]
      .concat((occ.before || []).map(b => b.text))
      .concat((occ.after || []).map(a => a.text))
      .slice(0, 6)
      .join('\n');

    const body = {
      message_summary: issue.message_summary,
      error_code: issue.error_code,
      line_number: occ.line_number,
      component: issue.component,
      context_snippet: snippet,
      full_error_text: occ.text,  // Pass the full error line
      search: false
    };

    fetch(`/api/llm/issues/${currentFileId}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
      .then(res => res.json())
      .then(data => {
        window.issueResolutionCache[cacheKey] = { data, issue, occ, hiddenFindingId: null, searchQuery: data.query };
        renderIssueResolution(data, issue, occ, cacheKey);
      })
      .catch(err => {
        const panel = document.getElementById('issueResolutionPanel');
        if (panel) {
          const hintEl = document.getElementById('resolutionPanelHint');
          if (hintEl) hintEl.textContent = 'Error loading';
          
          const inner = panel.querySelector('.issue-resolution-inner');
          if (inner) {
            inner.innerHTML = `
              <p class="placeholder-text-small" style="color:#ef4444; padding: 20px; text-align: center;">
                Failed to load resolution: ${err.message}
              </p>
            `;
          }
        }
      });
  }

  function runIssueWebSearch(cacheKey, customQuery = null) {
    const cache = window.issueResolutionCache[cacheKey];
    if (!cache) return;
    const { issue, occ } = cache;

    // Show loading state in the inner section only (keep header visible)
    const panel = document.getElementById('issueResolutionPanel');
    if (panel) {
      const inner = panel.querySelector('.issue-resolution-inner');
      if (inner) {
        inner.innerHTML = `
          <div class="issue-resolution-loading">
            <div class="ai-loading-spinner"></div>
            <p>Searching the web...</p>
          </div>
        `;
      }
    }

    const snippet = cache.data?.context || '';

    const body = {
      message_summary: issue.message_summary,
      error_code: issue.error_code,
      line_number: occ.line_number,
      component: issue.component,
      context_snippet: snippet,
      full_error_text: occ.text,
      custom_query: customQuery || null,  // Pass custom query if provided
      search: true
    };

    fetch(`/api/llm/issues/${currentFileId}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
      .then(res => res.json())
      .then(async (data) => {
        // Auto-save hidden finding when we have a web answer
        let hiddenId = cache.hiddenFindingId;
        if (data.tavily && data.tavily.answer) {
          const content = `**Issue:** ${issue.message_summary}\n\n**Answer:** ${data.tavily.answer}`;
          try {
            const resp = await fetch('/api/llm/findings', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                file_id: currentFileId,
                finding_type: 'custom',
                title: `Resolution: ${issue.message_summary}`.slice(0, 120),
                content,
                line_number: occ.line_number,
                metadata: { auto_saved: true, source: 'issue_resolution', search_query: data.query }
              })
            });
            if (resp.ok) {
              const saved = await resp.json();
              hiddenId = saved.id;
            }
          } catch (e) {
            console.warn('Auto-save resolution failed', e);
          }
        }

        window.issueResolutionCache[cacheKey] = { ...cache, data, hiddenFindingId: hiddenId, searchQuery: data.query };
        renderIssueResolution(data, issue, occ, cacheKey);
      })
      .catch(err => {
        const panel = document.getElementById('issueResolutionPanel');
        if (panel) {
          const inner = panel.querySelector('.issue-resolution-inner');
          if (inner) {
            inner.innerHTML = `
              <p class="placeholder-text-small" style="color:#ef4444; padding: 20px; text-align: center;">
                Web search failed: ${err.message}
              </p>
            `;
          }
        }
      });
  }

  async function thumbsDownIssueResolution(cacheKey) {
    const cache = window.issueResolutionCache[cacheKey];
    if (!cache) return;
    const { issue, occ } = cache;
    
    const hiddenId = cache.hiddenFindingId;
    if (hiddenId) {
      try {
        await fetch(`/api/llm/findings/${hiddenId}`, { method: 'DELETE' });
      } catch (e) {
        console.warn('Failed to delete hidden finding', e);
      }
      cache.hiddenFindingId = null;
    }
    
    // Clear the tavily result so user can search again
    if (cache.data) {
      cache.data.tavily = null;
      cache.data.tavily_error = null;
    }
    
    // Re-render the panel to show the search input again
    renderIssueResolution(cache.data, issue, occ, cacheKey);
  }

  async function saveIssueResolutionToFindings(cacheKey) {
    const cache = window.issueResolutionCache[cacheKey];
    if (!cache) return;
    const { data, issue, occ, hiddenFindingId } = cache;

    const answer = data.tavily?.answer || 'Resolution details not available';
    const sources = (data.tavily?.sources || []).map(s => `- ${s.title || s.url}: ${s.url}`).join('\n');
    const content = `**Issue:** ${issue.message_summary}\n\n**Answer:** ${answer}\n\n**Sources:**\n${sources || 'N/A'}`;

    // Find the save button and show loading state
    const btn = event?.target?.closest('button');
    const originalHtml = btn ? btn.innerHTML : '';
    if (btn) {
      btn.innerHTML = '...';
      btn.disabled = true;
    }

    try {
      await fetch('/api/llm/findings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: currentFileId,
          finding_type: 'custom',
          title: `Resolution: ${issue.message_summary}`.slice(0, 120),
          content,
          line_number: occ.line_number,
          metadata: { source: 'issue_resolution', search_query: data.query }
        })
      });

      // Remove hidden if it existed
      if (hiddenFindingId) {
        try {
          await fetch(`/api/llm/findings/${hiddenFindingId}`, { method: 'DELETE' });
        } catch (e) {
          console.warn('Failed to delete hidden finding after promotion', e);
        }
        cache.hiddenFindingId = null;
      }

      // Refresh findings list badge
      if (window.savedFindingsManager) {
        window.savedFindingsManager.loadFindings();
      }

      // Show success on button, don't replace the whole panel
      if (btn) {
        btn.innerHTML = '✓ Saved!';
        btn.style.color = '#22c55e';
        setTimeout(() => {
          btn.innerHTML = originalHtml;
          btn.style.color = '';
          btn.disabled = false;
        }, 2000);
      }
    } catch (e) {
      console.error('Failed to save to findings:', e);
      if (btn) {
        btn.innerHTML = 'Error';
        btn.style.color = '#ef4444';
        setTimeout(() => {
          btn.innerHTML = originalHtml;
          btn.style.color = '';
          btn.disabled = false;
        }, 2000);
      }
    }
  }

  function clearIssueResolution() {
    const panel = document.getElementById('issueResolutionPanel');
    if (panel) {
      // Collapse and reset
      panel.classList.add('collapsed');
      
      // Reset toggle bar text
      const titleEl = document.getElementById('resolutionPanelTitle');
      const hintEl = document.getElementById('resolutionPanelHint');
      if (titleEl) titleEl.textContent = 'Resolution Panel';
      if (hintEl) hintEl.textContent = 'Click the 🔍 icon on any issue';
      
      // Reset inner content
      const inner = panel.querySelector('.issue-resolution-inner');
      if (inner) {
        inner.innerHTML = `
          <div class="issue-resolution-placeholder">
            <svg width="32" height="32" viewBox="0 0 16 16" fill="currentColor" style="opacity: 0.4;">
              <path d="M11.742 10.344a6.5 6.5 0 10-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 001.415-1.414l-3.85-3.85a1.007 1.007 0 00-.115-.1zM12 6.5a5.5 5.5 0 11-11 0 5.5 5.5 0 0111 0z"/>
            </svg>
            <p>Click the <strong>🔍 icon</strong> on any issue header<br>to see AI insights, KB articles, and web search.</p>
          </div>
        `;
      }
    }
    // Clear selected state from issue groups
    document.querySelectorAll('.issue-group.selected').forEach(g => g.classList.remove('selected'));
  }

  // Expose resolution helpers globally for inline handlers
  window.openIssueResolution = openIssueResolution;
  window.runIssueWebSearch = runIssueWebSearch;
  window.thumbsDownIssueResolution = thumbsDownIssueResolution;
  window.saveIssueResolutionToFindings = saveIssueResolutionToFindings;
  window.clearIssueResolution = clearIssueResolution;
  
  // Font size adjustment for reports
  const fontSizeScales = [0.75, 0.85, 1.0, 1.15, 1.3];
  let issuesFontScale = 2; // Default index (1.0)
  let summaryFontScale = 2; // Default index (1.0)
  
  window.adjustFontSize = function(target, delta) {
    console.log('adjustFontSize called:', target, delta);
    if (target === 'issues') {
      issuesFontScale = Math.max(0, Math.min(fontSizeScales.length - 1, issuesFontScale + delta));
      const scale = fontSizeScales[issuesFontScale];
      const list = document.getElementById('issuesList');
      if (list) {
        list.style.setProperty('--font-scale', scale);
        console.log('Issues font scale set to:', scale);
      }
    } else if (target === 'summary') {
      summaryFontScale = Math.max(0, Math.min(fontSizeScales.length - 1, summaryFontScale + delta));
      const scale = fontSizeScales[summaryFontScale];
      const section = document.getElementById('logSummarySection');
      if (section) {
        section.style.setProperty('--font-scale', scale);
        console.log('Summary font scale set to:', scale);
      }
    }
  };
  
  // Scroll to issue by line number (called from timeline marker click)
  window.scrollToIssueByLine = function(lineNumber, clickedDot) {
    if (!window.issuesData || !window.issuesData.issues) return;
    
    // Clear all active timeline dots first
    document.querySelectorAll('.timeline-dot.active').forEach(dot => dot.classList.remove('active'));
    
    // Find the issue group that contains this line number
    let foundGroupIdx = -1;
    for (let i = 0; i < window.issuesData.issues.length; i++) {
      const issue = window.issuesData.issues[i];
      const hasLine = issue.occurrences.some(occ => occ.line_number === lineNumber);
      if (hasLine) {
        foundGroupIdx = i;
        break;
      }
    }
    
    if (foundGroupIdx >= 0) {
      const groupId = `issue-group-${foundGroupIdx}`;
      const group = document.getElementById(groupId);
      if (group) {
        // Close all other expanded groups (accordion behavior)
        document.querySelectorAll('.issue-group.expanded').forEach(g => {
          if (g.id !== groupId) {
            g.classList.remove('expanded');
          }
        });
        
        // Expand this group
        group.classList.add('expanded');
        
        // Highlight all timeline dots for this group
        const lineNumbers = group.dataset.lines ? group.dataset.lines.split(',').map(Number) : [];
        lineNumbers.forEach(lineNum => {
          const dot = document.querySelector(`.timeline-dot[data-line="${lineNum}"]`);
          if (dot) {
            dot.classList.add('active');
          }
        });
        
        // Scroll to it with a small delay to allow expansion
        setTimeout(() => {
          group.scrollIntoView({ behavior: 'smooth', block: 'center' });
          
          // Flash highlight effect
          group.style.boxShadow = '0 0 0 2px #3b82f6';
          setTimeout(() => {
            group.style.boxShadow = '';
          }, 1500);
        }, 50);
      }
    }
  };
  
  // Escape HTML to prevent XSS
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
  
  // Fetch and display log summary
  function fetchLogSummary() {
    if (!currentFileId) return;
    
    const summaryLink = document.getElementById('logSummaryLink');
    const releaseNotesLink = document.getElementById('releaseNotesLink');
    if (!summaryLink) return;
    
    // Show loading state
    summaryLink.style.display = 'flex';
    summaryLink.style.opacity = '0.6';
    summaryLink.title = 'Generating summary...';
    
    fetch(`/api/files/${currentFileId}/log-summary`)
      .then(res => res.json())
      .then(data => {
        summaryLink.style.opacity = '1';
        summaryLink.title = '';
        summaryLink.style.display = 'flex';
        window.logSummaryData = data;
        
        // Show Release Notes link if we have version info
        if (releaseNotesLink && data.version) {
          releaseNotesLink.style.display = 'flex';
          window.taskVersion = data.version;
          window.sourceEndpoint = data.source_endpoint;
          window.targetEndpoint = data.target_endpoint;
        }
        
        // Re-render task properties now that we have summary data for tiles
        fetchTaskProperties();
        
        // Auto-show log summary as default view when data loads
        // This ensures summary is the first thing users see in Analysis tab
        setTimeout(() => {
          showLogSummaryInMain();
        }, 100);
      })
      .catch(err => {
        console.error('Failed to load log summary:', err);
        summaryLink.style.display = 'none';
      });
  }
  
  // Show log summary in main view
  window.showLogSummaryInMain = function() {
    // Hide ALL other views
    document.querySelectorAll('.analysis-view').forEach(v => v.style.display = 'none');
    document.getElementById('threadActivityControls').style.display = 'none';
    
    // Show log summary view
    document.getElementById('logSummaryMainView').style.display = 'block';
    
    // Set active report link
    setActiveReportLink('logSummaryLink');
    
    // Clear "NEW" badge when viewing
    const newBadge = document.getElementById('logSummaryNewBadge');
    if (newBadge) newBadge.style.display = 'none';
    
    if (window.logSummaryData) {
      renderLogSummary(window.logSummaryData);
    }
  };
  
  function renderLogSummary(data) {
    const summaryContent = document.getElementById('logSummaryMainContent');
    if (!summaryContent) return;
    
    // Store data for fallback
    window.logSummaryData = data;
    
    // Show loading state first
    summaryContent.innerHTML = `
      <div class="log-summary-section" id="logSummarySection">
        <div class="summary-header-row">
          <div class="summary-title">
            <svg width="16" height="16" viewBox="0 0 512 512" fill="currentColor" style="color:#8b5cf6;">
              <path d="M327.5 85.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 128l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 128l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 64 426.8 7.5C425.1 3 420.8 0 416 0s-9.1 3-10.8 7.5L384 64 327.5 85.2zM9.3 240C3.6 242.6 0 248.3 0 254.6s3.6 11.9 9.3 14.5L26.3 277l8.1 3.7 .6 .3 88.3 40.8L164.1 410l.3 .6 3.7 8.1 7.9 17.1c2.6 5.7 8.3 9.3 14.5 9.3s11.9-3.6 14.5-9.3l7.9-17.1 3.7-8.1 .3-.6 40.8-88.3L346 281l.6-.3 8.1-3.7 17.1-7.9c5.7-2.6 9.3-8.3 9.3-14.5s-3.6-11.9-9.3-14.5l-17.1-7.9-8.1-3.7-.6-.3-88.3-40.8L217 99.1l-.3-.6L213 90.3l-7.9-17.1c-2.6-5.7-8.3-9.3-14.5-9.3s-11.9 3.6-14.5 9.3l-7.9 17.1-3.7 8.1-.3 .6-40.8 88.3L35.1 228.1l-.6 .3-8.1 3.7L9.3 240z"/>
            </svg>
            <span>Log Summary</span>
          </div>
        </div>
        <div class="ai-generating-notice">
          <div class="generating-spinner"></div>
          <div class="generating-text">Loading AI insights...</div>
        </div>
      </div>
    `;
    
    // Load AI insights
    loadAiInsightsForLogSummary(data);
  }
  
  // Load AI insights for the new Log Summary view
  function loadAiInsightsForLogSummary(summaryData) {
    const summaryContent = document.getElementById('logSummaryMainContent');
    if (!summaryContent || !currentFileId) {
      renderFallbackSummary(summaryContent, summaryData, 'No file loaded');
      return;
    }
    
    // Check AI config first
    fetch('/api/llm/config')
      .then(res => res.json())
      .then(config => {
        if (!config.is_configured) {
          renderFallbackSummary(summaryContent, summaryData, 'AI service not configured. Configure your API key in AI Settings to enable AI insights.');
          return;
        }
        
        // Try to fetch existing report
        return fetch(`/api/llm/report/${currentFileId}`)
          .then(res => res.json())
          .then(report => {
            if (report && report.report_content && report.exists !== false) {
              renderAiInsightsSummary(summaryContent, summaryData, report.report_content, report.chart_image_base64, report);
            } else if (window.aiReportManager && window.aiReportManager.isGenerating) {
              renderGeneratingSummary(summaryContent, summaryData);
            } else {
              renderFallbackSummary(summaryContent, summaryData, 'No AI report generated yet. The report will be generated automatically, or you can generate it from the Findings tab.');
            }
          });
      })
      .catch(err => {
        console.error('Failed to load AI config or report:', err);
        renderFallbackSummary(summaryContent, summaryData, 'Failed to load AI insights. Please try again.');
      });
  }
  
  // Render AI insights with collapsible sections
  function renderAiInsightsSummary(container, summaryData, reportContent, chartImageBase64, reportObj) {
    const sections = parseMarkdownIntoSections(reportContent);
    
    // Filter out empty sections more aggressively
    const validSections = sections.filter(s => {
      if (!s.content) return false;
      const cleaned = s.content.trim();
      if (!cleaned) return false;
      if (isEmptyHtmlContent(cleaned)) return false;
      return true;
    });
    
    if (validSections.length === 0) {
      renderFallbackSummary(container, summaryData, 'AI report has no content. Please regenerate the report.');
      return;
    }
    
    let html = `<div class="log-summary-section" id="logSummarySection"><div class="summary-header-row"><div class="summary-title"><svg width="16" height="16" viewBox="0 0 512 512" fill="currentColor" style="color:#8b5cf6;"><path d="M327.5 85.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 128l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 128l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 64 426.8 7.5C425.1 3 420.8 0 416 0s-9.1 3-10.8 7.5L384 64 327.5 85.2zM9.3 240C3.6 242.6 0 248.3 0 254.6s3.6 11.9 9.3 14.5L26.3 277l8.1 3.7 .6 .3 88.3 40.8L164.1 410l.3 .6 3.7 8.1 7.9 17.1c2.6 5.7 8.3 9.3 14.5 9.3s11.9-3.6 14.5-9.3l7.9-17.1 3.7-8.1 .3-.6 40.8-88.3L346 281l.6-.3 8.1-3.7 17.1-7.9c5.7-2.6 9.3-8.3 9.3-14.5s-3.6-11.9-9.3-14.5l-17.1-7.9-8.1-3.7-.6-.3-88.3-40.8L217 99.1l-.3-.6L213 90.3l-7.9-17.1c-2.6-5.7-8.3-9.3-14.5-9.3s-11.9 3.6-14.5 9.3l-7.9 17.1-3.7 8.1-.3 .6-40.8 88.3L35.1 228.1l-.6 .3-8.1 3.7L9.3 240z"/></svg><span>Log Summary</span></div><button class="view-full-report-btn" onclick="goToFullReport()" title="View full AI report in Findings tab"><svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M8.636 3.5a.5.5 0 00-.5-.5H1.5A1.5 1.5 0 000 4.5v10A1.5 1.5 0 001.5 16h10a1.5 1.5 0 001.5-1.5V7.864a.5.5 0 00-1 0V14.5a.5.5 0 01-.5.5h-10a.5.5 0 01-.5-.5v-10a.5.5 0 01.5-.5h6.636a.5.5 0 00.5-.5z"/><path d="M16 .5a.5.5 0 00-.5-.5h-5a.5.5 0 000 1h3.793L6.146 9.146a.5.5 0 10.708.708L15 1.707V5.5a.5.5 0 001 0v-5z"/></svg>Full Report</button></div><div class="ai-disclaimer"><svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor"><path d="M8 15A7 7 0 118 1a7 7 0 010 14zm0 1A8 8 0 108 0a8 8 0 000 16z"/><path d="M5.255 5.786a.237.237 0 00.241.247h.825c.138 0 .248-.113.266-.25.09-.656.54-1.134 1.342-1.134.686 0 1.314.343 1.314 1.168 0 .635-.374.927-.965 1.371-.673.489-1.206 1.06-1.168 1.987l.003.217a.25.25 0 00.25.246h.811a.25.25 0 00.25-.25v-.105c0-.718.273-.927 1.01-1.486.609-.463 1.244-.977 1.244-2.056 0-1.511-1.276-2.241-2.673-2.241-1.267 0-2.655.59-2.75 2.286zm1.557 5.763c0 .533.425.927 1.01.927.609 0 1.028-.394 1.028-.927 0-.552-.42-.94-1.029-.94-.584 0-1.009.388-1.009.94z"/></svg>AI-generated content may contain inaccuracies. Always verify important findings.</div>`;
    html += renderOracleLogSummaryInsightOnly(summaryData);
    
    // Render only sections with actual content
    validSections.forEach((section, idx) => {
      const isFirst = idx === 0;
      const titleLower = section.title.toLowerCase();
      
      // Determine highlight class based on section title
      let highlightClass = '';
      if (titleLower.includes('health') || titleLower.includes('score')) {
        highlightClass = 'highlight-health';
      } else if (titleLower.includes('finding') || titleLower.includes('key')) {
        highlightClass = 'highlight-findings';
      } else if (titleLower.includes('summary') || titleLower.includes('solution') || 
                 titleLower.includes('bottom line') || titleLower.includes('conclusion') || 
                 titleLower.includes('recommendation') || titleLower.includes('action') || 
                 titleLower.includes('issue')) {
        highlightClass = 'highlight-section';
      }
      
      let classes = 'ai-insight-section';
      if (isFirst) classes += ' expanded';
      if (highlightClass) classes += ' ' + highlightClass;
      
      html += `<div class="${classes}" data-section-idx="${idx}"><div class="ai-insight-section-header" onclick="toggleInsightSection(this)"><span class="ai-insight-section-toggle">▶</span><h3>${escapeHtml(section.title)}</h3><button class="save-section-btn" onclick="event.stopPropagation(); window.saveSectionToFindings(this)" title="Add section to Findings"><svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor"><path d="M2 2a2 2 0 012-2h8a2 2 0 012 2v13.5a.5.5 0 01-.777.416L8 13.101l-5.223 2.815A.5.5 0 012 15.5V2zm2-1a1 1 0 00-1 1v12.566l4.723-2.482a.5.5 0 01.554 0L13 14.566V2a1 1 0 00-1-1H4z"/></svg></button></div><div class="ai-insight-section-content">${section.content}</div></div>`;
    });
    
    // Latency chart as collapsed section
    if (chartImageBase64) {
      html += '<div class="ai-insight-section" data-section-idx="chart"><div class="ai-insight-section-header" onclick="toggleInsightSection(this)"><span class="ai-insight-section-toggle">▶</span><h3>Latency Chart (sent to model)</h3></div><div class="ai-insight-section-content"><img src="data:image/png;base64,' + chartImageBase64 + '" alt="Latency Over Time" style="width:100%;border-radius:6px;border:1px solid #374151" /></div></div>';
    }

    // Sources / references as collapsed section
    if (reportObj && ((reportObj.kb_references && reportObj.kb_references.length > 0) || (reportObj.release_notes_references && reportObj.release_notes_references.length > 0))) {
      const dbIcon = '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="#10b981" stroke-width="1.3" title="Indexed (ChromaDB)"><ellipse cx="8" cy="3" rx="6" ry="2.5"/><path d="M2 3v10c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5V3"/><path d="M2 8c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5"/></svg>';
      const webIcon = '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="#60a5fa" stroke-width="1.3" title="Web search"><circle cx="8" cy="8" r="6.5"/><path d="M1.5 8h13M8 1.5c2 2.2 3 4.8 3 6.5s-1 4.3-3 6.5c-2-2.2-3-4.8-3-6.5s1-4.3 3-6.5"/></svg>';
      let refsHtml = '';
      if (reportObj.kb_references && reportObj.kb_references.length > 0) {
        refsHtml += '<div style="margin-bottom:8px"><div style="font-size:0.7rem;color:#9ca3af;text-transform:uppercase;margin-bottom:4px;font-weight:600">Knowledge Base</div>';
        for (const kb of reportObj.kb_references) {
          const icon = kb.source === 'web' ? webIcon : dbIcon;
          const link = kb.url ? '<a href="' + kb.url + '" target="_blank" style="color:#60a5fa;text-decoration:none;font-size:0.78rem">' + escapeHtml(kb.title) + '</a>' : '<span style="color:#e5e7eb;font-size:0.78rem">' + escapeHtml(kb.title) + '</span>';
          refsHtml += '<div style="display:flex;align-items:flex-start;gap:5px;padding:2px 0">' + icon + ' ' + link + '</div>';
        }
        refsHtml += '</div>';
      }
      if (reportObj.release_notes_references && reportObj.release_notes_references.length > 0) {
        refsHtml += '<div><div style="font-size:0.7rem;color:#9ca3af;text-transform:uppercase;margin-bottom:4px;font-weight:600">Release Notes</div>';
        for (const rn of reportObj.release_notes_references) {
          const icon = rn.source === 'web' ? webIcon : dbIcon;
          const fixTag = rn.fix_id ? ' <span style="padding:1px 3px;background:#06b6d4;color:#111827;border-radius:2px;font-size:0.6rem;font-weight:bold">' + rn.fix_id + '</span>' : '';
          const link = rn.url ? '<a href="' + rn.url + '" target="_blank" style="color:#60a5fa;text-decoration:none;font-size:0.78rem">' + escapeHtml(rn.title) + '</a>' : '<span style="color:#e5e7eb;font-size:0.78rem">' + escapeHtml(rn.title) + '</span>';
          refsHtml += '<div style="display:flex;align-items:flex-start;gap:5px;padding:2px 0">' + icon + ' ' + link + fixTag + '</div>';
        }
        refsHtml += '</div>';
      }
      html += '<div class="ai-insight-section" data-section-idx="refs"><div class="ai-insight-section-header" onclick="toggleInsightSection(this)"><span class="ai-insight-section-toggle">▶</span><h3>Sources</h3></div><div class="ai-insight-section-content">' + refsHtml + '</div></div>';
    }

    html += '</div>';
    container.innerHTML = html;
  }
  
  // Check if HTML content is effectively empty
  function isEmptyHtmlContent(html) {
    if (!html) return true;
    // Remove HTML tags, whitespace, newlines, and check if anything meaningful remains
    const textOnly = html
      .replace(/<[^>]*>/g, '')  // Remove HTML tags
      .replace(/&nbsp;/g, ' ')   // Replace nbsp
      .replace(/\s+/g, ' ')      // Normalize whitespace
      .trim();
    // Consider empty if less than 10 characters (very short text)
    return textOnly.length < 10;
  }
  
  // Parse markdown into sections based on headers
  function parseMarkdownIntoSections(markdown) {
    if (!markdown) return [{ title: 'Summary', content: '<p>No content available</p>' }];
    
    // Clean up markdown - normalize line endings and remove excessive whitespace
    markdown = markdown.replace(/\r\n/g, '\n').replace(/\n{3,}/g, '\n\n');
    
    const lines = markdown.split('\n');
    const sections = [];
    let currentSection = null;
    let currentContent = [];
    let preHeaderContent = [];
    
    lines.forEach(line => {
      // Check for headers (## or ### or # for main title)
      const h1Match = line.match(/^#\s+(.+)$/);
      const h2Match = line.match(/^##\s+(.+)$/);
      const h3Match = line.match(/^###\s+(.+)$/);
      
      if (h1Match || h2Match || h3Match) {
        // Save previous section if it has content
        if (currentSection) {
          const content = currentContent.filter(l => l.trim()).join('\n');
          if (content.trim()) {
            sections.push({
              title: currentSection,
              content: convertMarkdownToHtml(content)
            });
          }
        }
        currentSection = h1Match ? h1Match[1] : (h2Match ? h2Match[1] : h3Match[1]);
        currentContent = [];
      } else if (currentSection) {
        // Only add non-empty lines or preserve single blank lines for paragraph breaks
        if (line.trim() || (currentContent.length > 0 && currentContent[currentContent.length - 1].trim())) {
          currentContent.push(line);
        }
      } else {
        // Content before first header
        if (line.trim()) {
          preHeaderContent.push(line);
        }
      }
    });
    
    // Don't forget the last section
    if (currentSection) {
      const content = currentContent.filter(l => l.trim()).join('\n');
      if (content.trim()) {
        sections.push({
          title: currentSection,
          content: convertMarkdownToHtml(content)
        });
      }
    }
    
    // If no sections found, create one from all content
    if (sections.length === 0 && markdown.trim()) {
      sections.push({
        title: 'Analysis',
        content: convertMarkdownToHtml(markdown)
      });
    }
    
    // Add overview section if there was meaningful content before first header
    if (preHeaderContent.length > 0) {
      const overviewContent = preHeaderContent.join('\n').trim();
      if (overviewContent) {
        sections.unshift({
          title: 'Overview',
          content: convertMarkdownToHtml(overviewContent)
        });
      }
    }
    
    return sections;
  }
  
  // Convert markdown to HTML (simplified version)
  function convertMarkdownToHtml(md) {
    if (!md) return '';
    
    // Clean up input - remove excessive whitespace and empty lines
    let html = md.trim()
      .replace(/\r\n/g, '\n')
      .replace(/\n{2,}/g, '\n')  // Multiple newlines to single
      .replace(/^\s*\n/gm, '');   // Remove empty lines
    
    if (!html.trim()) return '';
    
    // Escape HTML first
    html = html.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    
    // Code blocks
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // Bold and italic
    html = html.replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em>$1</em></strong>');
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    
    // Headers (h4 and lower since h2/h3 are section headers)
    html = html.replace(/^####\s+(.+)$/gm, '<h4>$1</h4>');
    
    // Lists - handle bullet points
    html = html.replace(/^[-*]\s+(.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
    
    // Numbered lists
    html = html.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>');
    
    // Convert remaining lines to paragraphs, but skip empty lines
    const lines = html.split('\n').filter(line => line.trim());
    html = lines.map(line => {
      const trimmed = line.trim();
      if (!trimmed) return '';
      if (trimmed.startsWith('<')) return trimmed;
      return `<p>${trimmed}</p>`;
    }).filter(line => line).join('');
    
    // Status highlights - expanded list
    html = html.replace(/\b(Healthy|OK|Good|Success|Successful|Complete|Completed|Normal|Stable)\b/gi, '<span class="status-healthy">$1</span>');
    html = html.replace(/\b(Warning|Caution|Moderate|Attention|Watch|Note)\b/gi, '<span class="status-warning">$1</span>');
    html = html.replace(/\b(Critical|Error|Errors|Failed|Failure|Severe|Fatal|Issue|Issues|Problem|Problems)\b/gi, '<span class="status-critical">$1</span>');
    html = html.replace(/\b(Info|Information|CDC|Full Load|Replication)\b/gi, '<span class="status-info">$1</span>');
    
    return html;
  }
  
  // Toggle insight section expansion
  window.toggleInsightSection = function(header) {
    const section = header.closest('.ai-insight-section');
    section.classList.toggle('expanded');
  };
  
  // Go to full AI report in Findings tab
  window.goToFullReport = function() {
    // Click on Resources tab
    const resourcesTab = document.querySelector('[data-tab="resources-tab"]');
    if (resourcesTab) {
      resourcesTab.click();
    }
  };
  
  // Listen for AI report completion to refresh Log Summary
  window.addEventListener('aiReportReady', (event) => {
    const { fileId, manual } = event.detail;
    // Only refresh if we're viewing the same file and Log Summary is visible
    if (fileId === currentFileId) {
      const logSummaryView = document.getElementById('logSummaryMainView');
      if (logSummaryView && logSummaryView.style.display !== 'none') {
        loadAiInsightsForLogSummary(window.logSummaryData);
      }
      
      // Show "NEW" badge on Log Summary when a manual report is generated
      if (manual) {
        const badge = document.getElementById('logSummaryNewBadge');
        if (badge) badge.style.display = 'inline-flex';
      }
    }
  });
  
  /** Redo log open→close times vary enough to mention in Log Summary (no raw rows). */
  function oracleRedoLogSpreadNotable(olp) {
    if (!olp || !(olp.session_count > 1)) return false;
    const st = olp.duration_seconds_stats || {};
    const max = st.max;
    const min = st.min;
    const p95 = st.p95;
    const avg = st.avg;
    if (max == null || min == null) return false;
    const typical = p95 != null && p95 > 0 ? p95 : avg != null && avg > 0 ? avg : null;
    if (typical != null && max >= typical * 2.5) return true;
    if (min > 0 && max / min >= 5) return true;
    return false;
  }

  function oracleTraceNotableForSummary(olp, ora) {
    if (ora && ora.has_red_flags) return true;
    return oracleRedoLogSpreadNotable(olp);
  }

  /** Log Summary: concise Oracle insight — full detail is in the Performance Cockpit only. */
  function renderOracleLogSummaryInsightOnly(summaryData) {
    if (!summaryData) return '';
    const olp = summaryData.oracle_redo_log_processing || {};
    const ora = summaryData.oracle_redo_read_analysis || {};
    if (!oracleTraceNotableForSummary(olp, ora)) return '';
    const st = olp.duration_seconds_stats || {};

    let h =
      '<div class="log-summary-oracle-insight" style="margin:12px 0;padding:12px 14px;border:1px solid rgba(251,191,36,0.35);border-radius:8px;background:rgba(120,53,15,0.15);">';
    h +=
      '<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">' +
      '<span style="font-size:1rem;">⚠</span>' +
      '<strong style="font-size:0.8rem;color:#fbbf24;">Oracle source — fluctuations detected</strong>' +
      '</div>';

    const bullets = [];

    if (oracleRedoLogSpreadNotable(olp)) {
      const typical = st.p95 != null && st.p95 > 0 ? st.p95 : st.avg != null ? st.avg : null;
      let msg =
        'Redo log hold times swing from <strong>' +
        (st.min != null ? st.min : '—') + 's</strong> to <strong>' +
        (st.max != null ? st.max : '—') + 's</strong>';
      if (typical != null) {
        msg += ' (typical ~' + (typeof typical === 'number' ? typical.toFixed(1) : typical) + 's)';
      }
      msg +=
        '. This usually means intermittent storage or I/O pressure on archived redo logs — ' +
        'not a steady bottleneck, but worth investigating if latency spikes correlate.';
      bullets.push(msg);
    }

    if (ora.has_red_flags) {
      const nGroups = ora.high_variance_group_count || 'multiple';
      bullets.push(
        '<strong>' + nGroups + '</strong> group(s) of similar redo block reads differ by ≥2× in duration. ' +
        'This points to uneven disk I/O on the source — check storage latency and host load.'
      );
    }

    h += '<ul style="margin:0;padding-left:18px;font-size:0.75rem;color:#d1d5db;line-height:1.5;">';
    bullets.forEach(b => { h += '<li style="margin-bottom:4px;">' + b + '</li>'; });
    h += '</ul>';

    h +=
      '<div style="margin-top:8px;font-size:0.7rem;color:#9ca3af;">' +
      'See <strong style="color:#c4b5fd;cursor:pointer;" onclick="window.showPerformanceCockpitInMain()">Performance Cockpit</strong> ' +
      'for per-session paths, line numbers, and drill-down detail.' +
      '</div>';

    h += '</div>';
    return h;
  }

  /** Full Oracle trace tables and lists — only in Performance Cockpit. */
  function renderOracleRedoCockpitSections(data) {
    if (!data) return '';
    const olp = data.oracle_redo_log_processing || {};
    const ora = data.oracle_redo_read_analysis || {};
    const hasOlp = (olp.session_count || 0) > 0;
    const hasOra = (ora.total_events_over_floor || 0) > 0 || ora.has_red_flags;
    if (!hasOlp && !hasOra) return '';
    let h = '<div class="cockpit-section oracle-trace-section"><h3>Oracle source (trace)</h3>';
    h +=
      '<div style="background:rgba(139,92,246,0.08);border:1px solid rgba(139,92,246,0.25);border-radius:8px;padding:10px 12px;margin-bottom:12px;font-size:0.75rem;color:#d1d5db;line-height:1.45;">';
    h +=
      '<strong style="color:#c4b5fd;">What this shows:</strong> Each row is one archived redo log file from <code>Going to open Redo Log</code> through <code>Close Redo log</code> (same path). ';
    h +=
      'Duration is how long Replicate held that log open. Big swings vs typical times (p95/avg) often point to storage latency, ASM/archivelog load, or transient I/O contention—use the slowest rows below to correlate with wall-clock time.';
    h += '</div>';
    if (hasOlp) {
      const st = olp.duration_seconds_stats || {};
      h +=
        '<p style="color:#9ca3af;font-size:0.75rem;margin:0 0 8px 0;">Time from <code>Going to open Redo Log</code> to <code>Close Redo log</code> (same path), from indexed log.</p>';
      h += `<p><strong>${olp.session_count}</strong> archived redo log session(s)</p>`;
      h += `<p style="font-size:0.8rem;">Duration per log (seconds): min <strong>${st.min != null ? st.min : '—'}</strong> · max <strong>${st.max != null ? st.max : '—'}</strong> · avg <strong>${st.avg != null ? st.avg : '—'}</strong> · p95 <strong>${st.p95 != null ? st.p95 : '—'}</strong></p>`;
      h += '<p style="font-size:0.72rem;color:#9ca3af;margin:8px 0 4px 0;">Longest sessions (for investigation):</p>';
      h += '<ul style="margin:8px 0 0 16px;font-size:0.75rem;color:#d1d5db;">';
      (olp.longest_sessions || []).forEach((s) => {
        h += `<li><strong>${s.duration_seconds}s</strong> — thread ${s.thread_id != null ? s.thread_id : '—'} — lines ${s.line_open}–${s.line_close}<br/><span style="color:#9ca3af;">${escapeHtml(s.redo_path_tail || '')}</span></li>`;
      });
      h += '</ul>';
    }
    if (hasOra) {
      h += '<h4 style="margin-top:14px;font-size:0.85rem;">Archived redo reads (&gt;200 ms)</h4>';
      h += `<p style="font-size:0.78rem;color:#9ca3af;margin:0 0 8px 0;">Per-block read times from trace. High variance between similar reads suggests uneven I/O.</p>`;
      h += `<p style="font-size:0.8rem;">${ora.total_events_over_floor || 0} event(s) in index.`;
      if (ora.has_red_flags) {
        h +=
          ' <span style="color:#f87171;">≥2× variance between similar reads (same size, thread, code path).</span>';
      }
      h += '</p><ul style="margin:8px 0 0 16px;font-size:0.75rem;">';
      (ora.high_variance_groups || []).slice(0, 5).forEach((g) => {
        const lines = (g.samples || []).map((x) => `L${x.line_number} (${x.read_ms} ms)`).join(', ');
        h += `<li>${g.bytes} bytes · ${g.multiplier}× · ${lines}</li>`;
      });
      h += '</ul>';
    }
    h += '</div>';
    return h;
  }

  // Render fallback summary when AI is not available
  function renderFallbackSummary(container, summaryData, reason) {
    if (!container) return;
    
    const data = summaryData || window.logSummaryData || {};
    const errCls = data.error_count > 0 ? ' error' : ' success';
    const warnCls = data.warning_count > 0 ? ' warning' : ' success';
    const flBg = data.full_load_completed ? '#064e3b' : '#1f2937';
    const flC = data.full_load_completed ? '#10b981' : '#6b7280';
    const cdcBg = data.cdc_started ? '#064e3b' : '#1f2937';
    const cdcC = data.cdc_started ? '#10b981' : '#6b7280';
    const checkSvg = '<path d="M16 8A8 8 0 110 8a8 8 0 0116 0zm-3.97-3.03a.75.75 0 00-1.08.022L7.477 9.417 5.384 7.323a.75.75 0 00-1.06 1.06L6.97 11.03a.75.75 0 001.079-.02l3.992-4.99a.75.75 0 00-.01-1.05z"/>';
    const circleSvg = '<path d="M8 15A7 7 0 118 1a7 7 0 010 14zm0 1A8 8 0 108 0a8 8 0 000 16z"/>';
    
    let html = `
      <div class="log-summary-section" id="logSummarySection">
        <div class="summary-header-row">
          <div class="summary-title">
            <svg width="16" height="16" viewBox="0 0 512 512" fill="currentColor" style="color:#8b5cf6;">
              <path d="M327.5 85.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 128l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 128l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 64 426.8 7.5C425.1 3 420.8 0 416 0s-9.1 3-10.8 7.5L384 64 327.5 85.2zM9.3 240C3.6 242.6 0 248.3 0 254.6s3.6 11.9 9.3 14.5L26.3 277l8.1 3.7 .6 .3 88.3 40.8L164.1 410l.3 .6 3.7 8.1 7.9 17.1c2.6 5.7 8.3 9.3 14.5 9.3s11.9-3.6 14.5-9.3l7.9-17.1 3.7-8.1 .3-.6 40.8-88.3L346 281l.6-.3 8.1-3.7 17.1-7.9c5.7-2.6 9.3-8.3 9.3-14.5s-3.6-11.9-9.3-14.5l-17.1-7.9-8.1-3.7-.6-.3-88.3-40.8L217 99.1l-.3-.6L213 90.3l-7.9-17.1c-2.6-5.7-8.3-9.3-14.5-9.3s-11.9 3.6-14.5 9.3l-7.9 17.1-3.7 8.1-.3 .6-40.8 88.3L35.1 228.1l-.6 .3-8.1 3.7L9.3 240z"/>
            </svg>
            <span>Log Summary</span>
          </div>
        </div>
        
        <div class="ai-not-available-notice">
          <div class="notice-header">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
              <path d="M8.982 1.566a1.13 1.13 0 00-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 018 5zm0 8a1 1 0 100-2 1 1 0 000 2z"/>
            </svg>
            <span class="notice-title">AI Insights Not Available</span>
          </div>
          <div class="notice-message">${reason}</div>
          <div class="notice-action">
            <button onclick="document.getElementById('aiSettingsBtn').click();">Configure AI Settings</button>
          </div>
        </div>
        
        <div style="margin-top: 16px;">
          <h4 style="margin: 0 0 12px 0; font-size: 0.85rem; color: #9ca3af;">Task Overview</h4>
          
          <div class="summary-grid">
            <div class="summary-card">
              <div class="summary-card-title">Task Name</div>
              <div class="summary-card-value highlight">${data.task_name || 'N/A'}</div>
            </div>
            <div class="summary-card">
              <div class="summary-card-title">Version</div>
              <div class="summary-card-value">${data.version || 'N/A'}</div>
            </div>
            <div class="summary-card">
              <div class="summary-card-title">Duration</div>
              <div class="summary-card-value">${data.duration || 'N/A'}</div>
            </div>
            <div class="summary-card">
              <div class="summary-card-title">Tables</div>
              <div class="summary-card-value highlight">${data.tables_count || 0}</div>
            </div>
          </div>
          
          <div class="summary-grid" style="margin-top: 8px;">
            <div class="summary-card">
              <div class="summary-card-title">Errors</div>
              <div class="summary-card-value${errCls}">${data.error_count || 0}</div>
            </div>
            <div class="summary-card">
              <div class="summary-card-title">Warnings</div>
              <div class="summary-card-value${warnCls}">${data.warning_count || 0}</div>
            </div>
            <div class="summary-card">
              <div class="summary-card-title">Running Mode</div>
              <div class="summary-card-value">${data.running_mode || 'N/A'}</div>
            </div>
            <div class="summary-card">
              <div class="summary-card-title">Start Mode</div>
              <div class="summary-card-value">${data.start_mode || 'N/A'}</div>
            </div>
          </div>
          
          <div style="margin:12px 0;display:flex;gap:6px;flex-wrap:wrap;">
            <div style="display:flex;align-items:center;gap:4px;padding:4px 8px;background:${flBg};border-radius:4px;">
              <svg width="12" height="12" viewBox="0 0 16 16" fill="${flC}">${data.full_load_completed ? checkSvg : circleSvg}</svg>
              <span style="font-size:0.7rem;color:${flC};">Full Load ${data.full_load_completed ? 'Completed' : 'Not Completed'}</span>
            </div>
            <div style="display:flex;align-items:center;gap:4px;padding:4px 8px;background:${cdcBg};border-radius:4px;">
              <svg width="12" height="12" viewBox="0 0 16 16" fill="${cdcC}">${data.cdc_started ? checkSvg : circleSvg}</svg>
              <span style="font-size:0.7rem;color:${cdcC};">CDC ${data.cdc_started ? 'Started' : 'Not Started'}</span>
            </div>
          </div>
          ${renderOracleLogSummaryInsightOnly(data)}
    `;
    
    // Key Events
    if (data.key_events && data.key_events.length > 0) {
      html += '<div style="margin-top: 12px;"><h4 style="margin: 0 0 8px 0; font-size: 0.8rem; color: #9ca3af;">Key Events</h4>';
      data.key_events.forEach(e => {
        html += `<div class="key-event"><span class="key-event-line">L${e.line + 1}</span><span class="key-event-name">${e.event}</span></div>`;
      });
      html += '</div>';
    }
    
    html += '</div></div>';
    container.innerHTML = html;
  }
  
  // Render generating state
  function renderGeneratingSummary(container, summaryData) {
    if (!container) return;
    
    container.innerHTML = `
      <div class="log-summary-section" id="logSummarySection">
        <div class="summary-header-row">
          <div class="summary-title">
            <svg width="16" height="16" viewBox="0 0 512 512" fill="currentColor" style="color:#8b5cf6;">
              <path d="M327.5 85.2c-4.5 1.7-7.5 6-7.5 10.8s3 9.1 7.5 10.8L384 128l21.2 56.5c1.7 4.5 6 7.5 10.8 7.5s9.1-3 10.8-7.5L448 128l56.5-21.2c4.5-1.7 7.5-6 7.5-10.8s-3-9.1-7.5-10.8L448 64 426.8 7.5C425.1 3 420.8 0 416 0s-9.1 3-10.8 7.5L384 64 327.5 85.2zM9.3 240C3.6 242.6 0 248.3 0 254.6s3.6 11.9 9.3 14.5L26.3 277l8.1 3.7 .6 .3 88.3 40.8L164.1 410l.3 .6 3.7 8.1 7.9 17.1c2.6 5.7 8.3 9.3 14.5 9.3s11.9-3.6 14.5-9.3l7.9-17.1 3.7-8.1 .3-.6 40.8-88.3L346 281l.6-.3 8.1-3.7 17.1-7.9c5.7-2.6 9.3-8.3 9.3-14.5s-3.6-11.9-9.3-14.5l-17.1-7.9-8.1-3.7-.6-.3-88.3-40.8L217 99.1l-.3-.6L213 90.3l-7.9-17.1c-2.6-5.7-8.3-9.3-14.5-9.3s-11.9 3.6-14.5 9.3l-7.9 17.1-3.7 8.1-.3 .6-40.8 88.3L35.1 228.1l-.6 .3-8.1 3.7L9.3 240z"/>
            </svg>
            <span>Log Summary</span>
          </div>
        </div>
        <div class="ai-generating-notice">
          <div class="generating-spinner"></div>
          <div class="generating-text">Generating AI insights... This may take a moment.</div>
        </div>
      </div>
    `;
    
    // Don't poll - we'll rely on the aiReportReady event instead
    // The event will be dispatched when the report is ready
  }
  
  // Initialize Reports Panel Toggle
  const toggleReportsBtn = document.getElementById('toggleReportsPanel');
  const reportsPanel = document.getElementById('reportsPanel');
  
  if (toggleReportsBtn && reportsPanel) {
    // Load saved state
    const panelCollapsed = localStorage.getItem('reportsPanelCollapsed') === 'true';
    if (panelCollapsed) {
      reportsPanel.classList.add('collapsed');
    }
    
    toggleReportsBtn.addEventListener('click', () => {
      reportsPanel.classList.toggle('collapsed');
      localStorage.setItem('reportsPanelCollapsed', reportsPanel.classList.contains('collapsed'));
    });
  }
  
  // Initialize floating export button
  const floatingExportBtn = document.getElementById('floatingExportBtn');
  if (floatingExportBtn) {
    floatingExportBtn.addEventListener('click', exportSearchResults);
  }

  // ============================================================
  // PERFORMANCE COCKPIT
  // ============================================================
  
  window.performanceCockpitData = null;
  
  window.showPerformanceCockpitInMain = function() {
    // Hide all analysis views
    document.querySelectorAll('.analysis-view').forEach(v => v.style.display = 'none');
    
    // Hide thread activity controls
    document.getElementById('threadActivityControls').style.display = 'none';
    
    // Show performance cockpit view
    const view = document.getElementById('performanceCockpitMainView');
    if (view) {
      view.style.display = 'block';
    }
    
    // Set active report link
    setActiveReportLink('performanceCockpitLink');
    
    // Fetch and render
    if (!window.performanceCockpitData && currentFileId) {
      fetchPerformanceCockpit();
    } else if (window.performanceCockpitData) {
      renderPerformanceCockpit(window.performanceCockpitData);
    }
  };
  
  // Check if performance cockpit has meaningful data before showing the link
  function fetchPerformanceCockpitCheck() {
    if (!currentFileId) return;
    
    const performanceCockpitLink = document.getElementById('performanceCockpitLink');
    
    fetch(`/api/files/${currentFileId}/performance-cockpit`)
      .then(res => res.json())
      .then(data => {
        // Check if there's meaningful data to show
        const hasLatencyData = data.latency_profile?.data_points > 0;
        const hasBatchData = data.batch_profile?.total_batches > 0;
        const hasPainTables = data.pain_tables?.length > 0;
        const hasFileOps = data.file_operations?.count > 0;
        const hasConfig = data.config && Object.keys(data.config).length > 0;
        const olp = data.oracle_redo_log_processing || {};
        const ora = data.oracle_redo_read_analysis || {};
        const hasOracleTrace =
          (olp.session_count || 0) > 0 ||
          (ora.total_events_over_floor || 0) > 0 ||
          ora.has_red_flags;
        
        const hasMeaningfulData =
          hasLatencyData || hasBatchData || hasPainTables || hasFileOps || hasConfig || hasOracleTrace;
        
        if (hasMeaningfulData) {
          window.performanceCockpitData = data;
          if (performanceCockpitLink) performanceCockpitLink.style.display = 'flex';
        } else {
          window.performanceCockpitData = null;
          if (performanceCockpitLink) performanceCockpitLink.style.display = 'none';
        }
      })
      .catch(err => {
        console.error('Failed to check performance cockpit:', err);
        if (performanceCockpitLink) performanceCockpitLink.style.display = 'none';
      });
  }

  function fetchPerformanceCockpit() {
    if (!currentFileId) return;
    
    const content = document.getElementById('performanceCockpitMainContent');
    if (content) {
      content.innerHTML = `
        <div style="text-align: center; padding: 40px;">
          <div class="loading-spinner"></div>
          <p style="margin-top: 16px; color: #9ca3af;">Analyzing performance metrics...</p>
        </div>
      `;
    }
    
    // If we already have the data from the check, use it
    if (window.performanceCockpitData) {
      renderPerformanceCockpit(window.performanceCockpitData);
      return;
    }
    
    fetch(`/api/files/${currentFileId}/performance-cockpit`)
      .then(res => res.json())
      .then(data => {
        window.performanceCockpitData = data;
        renderPerformanceCockpit(data);
      })
      .catch(err => {
        console.error('Failed to load performance cockpit:', err);
        if (content) {
          content.innerHTML = `<p style="color: #ef4444; text-align: center; padding: 20px;">Failed to load performance cockpit: ${err.message}</p>`;
        }
      });
  }
  
  function renderPerformanceCockpit(data) {
    const content = document.getElementById('performanceCockpitMainContent');
    if (!content) return;
    
    // Build HTML parts - no whitespace between sections
    const parts = [];
    
    // Header
    parts.push(`<div class="cockpit-container"><div class="cockpit-header"><h2 style="margin:0;display:flex;align-items:center;gap:6px;"><svg width="20" height="20" viewBox="0 0 16 16" fill="#8b5cf6"><path d="M8 0a8 8 0 100 16A8 8 0 008 0zM7 3.5a.5.5 0 011 0v4.793l2.354 2.353a.5.5 0 01-.708.708l-2.5-2.5A.5.5 0 017 8.5v-5z"/></svg>Performance Cockpit</h2><span style="color:#9ca3af;font-size:0.7rem;">${data.latency_profile?.data_points || 0} data points</span></div>`);
    
    // Task Configuration (moved to top)
    if (data.config && Object.keys(data.config).length > 0) {
      parts.push(`<div class="cockpit-section config-section"><h3>Task Configuration</h3>${renderConfig(data.config)}</div>`);
    }
    
    // Bottleneck
    parts.push(`<div class="cockpit-section bottleneck-section"><h3>Latency Bottleneck Analysis</h3>${renderBottleneckIndicator(data.bottleneck, data.latency_profile)}</div>`);
    
    // Latency Profile
    parts.push(`<div class="cockpit-section"><h3>Latency Profile</h3><div class="latency-profile-grid">${renderLatencyProfile(data.latency_profile)}</div></div>`);
    
    // Spikes & Plateaus
    parts.push(`<div class="cockpit-row"><div class="cockpit-section half"><h3>Latency Spikes <span class="badge">${data.spikes?.count || 0}</span></h3>${renderSpikes(data.spikes)}</div><div class="cockpit-section half"><h3>Latency Plateaus <span class="badge">${data.plateaus?.count || 0}</span></h3>${renderPlateaus(data.plateaus)}</div></div>`);
    
    parts.push(renderOracleRedoCockpitSections(data));
    
    // Batch Analysis
    const batchIssuesHtml = renderBatchIssues(data.batch_issues);
    parts.push(`<div class="cockpit-section"><h3>Batch Behavior Analysis</h3><div class="batch-analysis-grid">${renderBatchAnalysis(data.batch_profile)}</div>${batchIssuesHtml}</div>`);
    
    // Pain Tables
    parts.push(`<div class="cockpit-section"><h3>Pain Tables (by performance impact)</h3>${renderPainTables(data.pain_tables)}</div>`);
    
    // File Operations (conditional)
    if (data.file_operations?.count > 0) {
      parts.push(`<div class="cockpit-section"><h3>File Operations Summary</h3>${renderFileOperationsSummary(data.file_operations)}</div>`);
    }
    
    // Recommendations
    parts.push(`<div class="cockpit-section recommendations-section"><h3>Recommendations</h3>${renderRecommendations(data.recommendations)}</div>`);
    
    // Error Correlation (conditional)
    if (data.error_correlation && data.error_correlation.total_correlated_errors > 0) {
      parts.push(`<div class="cockpit-section"><h3>Error Correlation Analysis</h3>${renderErrorCorrelation(data.error_correlation)}</div>`);
    }
    
    // MERGE Analysis (conditional)
    if (data.merge_analysis && data.merge_analysis.merge_enabled) {
      parts.push(`<div class="cockpit-section"><h3>MERGE vs Standard Bulk Analysis</h3>${renderMergeAnalysis(data.merge_analysis)}</div>`);
    }
    
    // CDC Pipeline Analysis (conditional)
    if (data.cdc_pipeline && data.cdc_pipeline.has_issues) {
      parts.push(`<div class="cockpit-section"><h3>CDC Pipeline Health</h3>${renderCDCPipeline(data.cdc_pipeline)}</div>`);
    }
    
    // Source Analysis (conditional)
    if (data.source_analysis && (data.source_analysis.total_source_errors > 0 || data.source_analysis.total_reconnects > 0)) {
      parts.push(`<div class="cockpit-section"><h3>Source-Side Analysis</h3>${renderSourceAnalysis(data.source_analysis)}</div>`);
    }
    
    parts.push(`</div>`); // Close cockpit-container
    
    content.innerHTML = parts.join('');
    
    // Render charts if Plotly is available
    if (data.batch_profile?.closure_reasons && Object.keys(data.batch_profile.closure_reasons).length > 0) {
      renderClosureReasonChart(data.batch_profile.closure_reasons);
    }
  }
  
  function renderBottleneckIndicator(bottleneck, latencyProfile) {
    if (!latencyProfile) return '<p style="color:#9ca3af;font-size:0.7rem;">No bottleneck data</p>';
    
    // Latency breakdown:
    // - Source Latency = time to capture data from source database
    // - Target Latency = total end-to-end time (this is what matters most)
    // - Handling Latency = Target - Source = time spent processing/applying at target
    const sourceAvg = latencyProfile.source?.avg || 0;
    const targetAvg = latencyProfile.target?.avg || 0;
    const handlingAvg = latencyProfile.handling?.avg || 0;
    
    // Calculate what portion of total target latency is source vs target-side processing
    // Since Target = Source + Handling, we show both contributions
    const srcPct = targetAvg > 0 ? (sourceAvg / targetAvg) * 100 : 50;
    const tgtProcessingPct = targetAvg > 0 ? (handlingAvg / targetAvg) * 100 : 50;
    
    // Determine dominant factor
    let label, labelColor;
    if (srcPct > 60) {
      label = 'Source Capture Dominant';
      labelColor = '#f59e0b';  // Orange (source color)
    } else if (tgtProcessingPct > 60) {
      label = 'Target Apply Dominant';
      labelColor = '#3b82f6';  // Blue (target color)
    } else {
      label = 'Balanced';
      labelColor = '#10b981';  // Green
    }
    
    // Build info text
    let infoHtml = '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:8px;text-align:center;font-size:0.65rem;color:#9ca3af">';
    infoHtml += `<div><div style="color:#f59e0b;font-weight:600">${sourceAvg.toFixed(2)}s</div><div>Source Capture</div></div>`;
    infoHtml += `<div><div style="color:#10b981;font-weight:600">${handlingAvg.toFixed(2)}s</div><div>Target Apply</div></div>`;
    infoHtml += `<div><div style="color:#3b82f6;font-weight:600">${targetAvg.toFixed(2)}s</div><div>Total (Target)</div></div>`;
    infoHtml += '</div>';
    
    return `<div class="bottleneck-gauge"><div class="bottleneck-label" style="color:${labelColor};font-weight:600">${label}</div><div class="bottleneck-bar"><div style="width:${srcPct.toFixed(1)}%;background:#f59e0b;padding:4px 0;text-align:center;font-size:0.65rem;color:#111"><span>Source ${srcPct.toFixed(0)}%</span></div><div style="width:${tgtProcessingPct.toFixed(1)}%;background:#10b981;padding:4px 0;text-align:center;font-size:0.65rem;color:#111"><span>Target ${tgtProcessingPct.toFixed(0)}%</span></div></div>${infoHtml}<p style="color:#6b7280;font-size:0.6rem;margin:8px 0 0;text-align:center;font-style:italic">Target Latency = Source Capture + Target Apply (Handling)</p></div>`;
  }
  
  function renderLatencyProfile(profile) {
    if (!profile) return '<p style="color:#9ca3af;font-size:0.7rem;">No latency data</p>';
    
    const f = (val) => val?.toFixed(2) || '0.00';
    
    // Use consistent colors: Source=Orange, Target=Blue, Handling=Green
    return `<div class="latency-card" style="border-left:3px solid #f59e0b"><div class="latency-card-header" style="color:#f59e0b">Source Capture</div><div class="latency-card-value">${f(profile.source?.avg)}s <span>avg</span></div><div class="latency-card-stats"><span>p50:${f(profile.source?.p50)}s</span><span>p95:${f(profile.source?.p95)}s</span><span>max:${f(profile.source?.max)}s</span></div></div><div class="latency-card" style="border-left:3px solid #10b981"><div class="latency-card-header" style="color:#10b981">Target Apply</div><div class="latency-card-value">${f(profile.handling?.avg)}s <span>avg</span></div><div class="latency-card-stats"><span>p50:${f(profile.handling?.p50)}s</span><span>p95:${f(profile.handling?.p95)}s</span><span>max:${f(profile.handling?.max)}s</span></div></div><div class="latency-card" style="border-left:3px solid #3b82f6"><div class="latency-card-header" style="color:#3b82f6">Total (End-to-End)</div><div class="latency-card-value">${f(profile.target?.avg)}s <span>avg</span></div><div class="latency-card-stats"><span>p50:${f(profile.target?.p50)}s</span><span>p95:${f(profile.target?.p95)}s</span><span>max:${f(profile.target?.max)}s</span></div></div>`;
  }
  
  function renderSpikes(spikes) {
    if (!spikes || spikes.count === 0) {
      return '<p style="color:#10b981;font-size:0.7rem;">✓ No significant spikes</p>';
    }
    
    let html = '<div class="spikes-list">';
    spikes.items.slice(0, 5).forEach(spike => {
      // Map driver to consistent colors: source=orange, handling=green (target apply)
      const isSource = spike.driver === 'source';
      const color = isSource ? '#f59e0b' : '#10b981';
      const driverLabel = isSource ? 'Source' : 'Target';
      html += `<div class="spike-item" onclick="jumpToLineAndHighlight(${spike.line_number},'')"><div class="spike-value">${spike.value}s</div><div class="spike-details"><span class="spike-multiplier">${spike.multiplier}x</span><span class="spike-driver" style="color:${color}">${driverLabel}</span><span class="spike-time">${spike.timestamp?.substring(11,19)||''}</span></div></div>`;
    });
    if (spikes.count > 5) {
      html += `<p style="color:#6b7280;font-size:0.6rem;margin:4px 0 0;">+${spikes.count - 5} more</p>`;
    }
    html += '</div>';
    return html;
  }
  
  function renderPlateaus(plateaus) {
    if (!plateaus || plateaus.count === 0) {
      return '<p style="color:#10b981;font-size:0.7rem;">✓ No sustained high-latency periods</p>';
    }
    
    let html = '<div class="plateaus-list">';
    plateaus.items.slice(0, 3).forEach(plateau => {
      html += `<div class="plateau-item" onclick="jumpToLineAndHighlight(${plateau.start_line},'')"><div class="plateau-value">${plateau.avg_latency}s avg</div><div class="plateau-details"><span>${plateau.duration_points} pts</span><span>L${plateau.start_line}-${plateau.end_line}</span></div></div>`;
    });
    html += '</div>';
    return html;
  }
  
  function renderBatchAnalysis(batchProfile) {
    if (!batchProfile || batchProfile.total_batches === 0) {
      return '<p style="color:#9ca3af;font-size:0.7rem;">No batch data</p>';
    }
    
    const sz = batchProfile.size_stats || {};
    const dur = batchProfile.duration_stats || {};
    const warn = sz.single_record_pct > 20 ? ' warning' : '';
    
    return `<div class="batch-stat-card"><div class="batch-stat-value">${batchProfile.total_batches}</div><div class="batch-stat-label">Total Batches</div></div><div class="batch-stat-card"><div class="batch-stat-value">${sz.avg?.toFixed(1)||0}</div><div class="batch-stat-label">Avg Size</div></div><div class="batch-stat-card"><div class="batch-stat-value">${dur.avg?.toFixed(1)||0}s</div><div class="batch-stat-label">Avg Duration</div></div><div class="batch-stat-card${warn}"><div class="batch-stat-value">${sz.single_record_pct?.toFixed(1)||0}%</div><div class="batch-stat-label">Single-Record</div></div><div id="closureReasonChart" class="closure-reason-chart"></div>`;
  }
  
  function renderClosureReasonChart(closureReasons) {
    const chartDiv = document.getElementById('closureReasonChart');
    if (!chartDiv || !window.Plotly) return;
    
    const labels = Object.keys(closureReasons);
    const values = Object.values(closureReasons);
    
    const closureColors = {
      'PKi': '#ef4444',
      'PKu': '#f97316',
      'PKd': '#f59e0b',
      'MEM': '#8b5cf6',
      'TIM': '#3b82f6',
      'TMO': '#06b6d4',
      'SNG': '#10b981',
      'RES': '#84cc16',
      'LOAD': '#6b7280',
      'Normal': '#22c55e'
    };
    
    const colors = labels.map(l => closureColors[l] || '#6b7280');
    
    const data = [{
      type: 'pie',
      values: values,
      labels: labels,
      marker: { colors: colors },
      textinfo: 'label+percent',
      textposition: 'inside',
      hole: 0.4,
      hoverinfo: 'label+value+percent'
    }];
    
    const layout = {
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'transparent',
      font: { color: '#9ca3af', size: 9 },
      margin: { t: 5, b: 5, l: 5, r: 5 },
      showlegend: false,
      height: 100
    };
    
    Plotly.newPlot(chartDiv, data, layout, { displayModeBar: false });
  }
  
  function renderBatchIssues(issues) {
    if (!issues || issues.length === 0) return '';
    
    let html = '<div class="batch-issues">';
    issues.forEach(issue => {
      const c = issue.severity === 'warning' ? '#f59e0b' : '#3b82f6';
      html += `<div class="batch-issue" style="border-left-color:${c}"><div class="batch-issue-title">${issue.title}</div><div class="batch-issue-message">${issue.message}</div><div class="batch-issue-recommendation">${issue.recommendation}</div></div>`;
    });
    html += '</div>';
    return html;
  }
  
  function renderPainTables(tables) {
    if (!tables || tables.length === 0) {
      return '<p style="color:#10b981;font-size:0.7rem;">✓ No problematic tables detected</p>';
    }
    
    let html = '<div class="pain-tables-table"><table><thead><tr><th>Table</th><th>Pain</th><th>Apply Time</th><th>Ops</th><th>1-by-1</th><th>Errors</th><th>PK</th></tr></thead><tbody>';
    
    tables.forEach(t => {
      const pk = t.has_pk === null ? '?' : (t.has_pk ? '✓' : '✗');
      const pkC = t.has_pk === false ? '#ef4444' : '#10b981';
      const oboC = t.one_by_one_count > 0 ? ' warning' : '';
      const errC = t.error_count > 0 ? ' error' : '';
      html += `<tr><td class="table-name" title="${t.table_name}">${t.table_name}</td><td class="pain-score">${t.pain_score}</td><td>${t.total_apply_time}s</td><td>${t.total_operations}</td><td class="${oboC}">${t.one_by_one_count}</td><td class="${errC}">${t.error_count}</td><td style="color:${pkC}">${pk}</td></tr>`;
    });
    
    html += '</tbody></table></div>';
    return html;
  }
  
  function renderFileOperationsSummary(fileOps) {
    if (!fileOps || fileOps.count === 0) return '';
    
    const fmtSz = (b) => b < 1024 ? `${b} B` : b < 1048576 ? `${(b/1024).toFixed(1)} KB` : `${(b/1048576).toFixed(2)} MB`;
    
    return `<div class="file-ops-summary"><div class="file-ops-stat"><span class="file-ops-value">${fileOps.count}</span><span class="file-ops-label">Files</span></div><div class="file-ops-stat"><span class="file-ops-value">${fmtSz(fileOps.total_size_bytes)}</span><span class="file-ops-label">Total</span></div><div class="file-ops-stat"><span class="file-ops-value">${fileOps.avg_upload_time?.toFixed(2)}s</span><span class="file-ops-label">Avg Upload</span></div><div class="file-ops-stat"><span class="file-ops-value">${fileOps.avg_throughput_kbps?.toFixed(0)} KB/s</span><span class="file-ops-label">Throughput</span></div></div>`;
  }
  
  function renderRecommendations(recommendations) {
    if (!recommendations || recommendations.length === 0) {
      return '<p style="color:#10b981;font-size:0.7rem;">✓ No specific recommendations</p>';
    }
    
    let html = '<div class="recommendations-list">';
    recommendations.forEach(rec => {
      const c = rec.priority === 'high' ? '#ef4444' : rec.priority === 'medium' ? '#f59e0b' : '#3b82f6';
      const actions = rec.actions?.length ? `<ul class="recommendation-actions">${rec.actions.map(a => `<li>${a}</li>`).join('')}</ul>` : '';
      html += `<div class="recommendation-card" style="--priority-color:${c}"><div class="recommendation-header"><span class="recommendation-priority ${rec.priority}">${rec.priority}</span><span class="recommendation-area">${rec.area}</span><span class="recommendation-title">${rec.title}</span></div><div class="recommendation-description">${rec.description}</div>${actions}</div>`;
    });
    html += '</div>';
    return html;
  }
  
  function renderConfig(config) {
    if (!config || Object.keys(config).length === 0) return '';
    
    const configLabels = {
      'bulk_timeout_ms': 'Bulk Timeout',
      'bulk_timeout_min_ms': 'Bulk Timeout Min',
      'bulk_max_file_size_kb': 'Max File Size',
      'parallel_apply_threads': 'Parallel Threads',
      'source_type': 'Source Type',
      'target_type': 'Target Type',
      'apply_mode': 'Apply Mode',
      'merge_enabled': 'MERGE Mode'
    };
    
    // Check if MERGE is enabled or detected
    const mergeEnabled = config.merge_enabled || config.apply_mode === 'merge';
    
    let html = '';
    
    // Show MERGE badge prominently if enabled
    if (mergeEnabled) {
      html += `<div class="config-merge-banner" style="margin-bottom:12px;padding:8px 12px;background:linear-gradient(135deg,rgba(168,85,247,0.2),rgba(168,85,247,0.1));border:1px solid #a855f7;border-radius:6px;display:flex;align-items:center;gap:8px;">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="#a855f7"><path d="M8 0a8 8 0 100 16A8 8 0 008 0zm3.5 7.5a.5.5 0 010 1H5.707l2.147 2.146a.5.5 0 01-.708.708l-3-3a.5.5 0 010-.708l3-3a.5.5 0 11.708.708L5.707 7.5H11.5z"/></svg>
        <span style="color:#a855f7;font-weight:600;font-size:0.8rem;">MERGE Mode Active</span>
        <span style="color:#9ca3af;font-size:0.7rem;">Using MERGE statements for CDC apply</span>
      </div>`;
    }
    
    html += '<div class="config-grid">';
    Object.entries(config).forEach(([key, value]) => {
      // Skip merge_enabled as we show it as a banner
      if (key === 'merge_enabled' && mergeEnabled) return;
      
      const label = configLabels[key] || key.replace(/_/g, ' ');
      let displayValue = value;
      
      if (key.includes('timeout') && typeof value === 'number') {
        displayValue = `${(value / 1000).toFixed(0)}s`;
      } else if (key.includes('size') && typeof value === 'number') {
        displayValue = `${(value / 1024).toFixed(0)} MB`;
      } else if (key === 'apply_mode') {
        displayValue = `<span style="color:${value === 'merge' ? '#a855f7' : '#3b82f6'};font-weight:600;text-transform:uppercase;">${value}</span>`;
      }
      
      html += `
        <div class="config-item">
          <span class="config-label">${label}</span>
          <span class="config-value">${displayValue}</span>
        </div>
      `;
    });
    html += '</div>';
    return html;
  }
  
  function renderErrorCorrelation(correlation) {
    if (!correlation) return '';
    
    let html = `
      <div class="error-correlation-summary">
        <div class="correlation-stat">
          <span class="correlation-value">${correlation.total_correlated_errors}</span>
          <span class="correlation-label">Errors During High Latency</span>
        </div>
        <div class="correlation-stat">
          <span class="correlation-value">${correlation.high_latency_windows}</span>
          <span class="correlation-label">High Latency Windows</span>
        </div>
        <div class="correlation-stat">
          <span class="correlation-value">${correlation.high_latency_threshold}s</span>
          <span class="correlation-label">High Latency Threshold (p75)</span>
        </div>
      </div>
    `;
    
    // Errors by type
    if (correlation.errors_by_type && Object.keys(correlation.errors_by_type).length > 0) {
      html += '<div class="correlation-breakdown"><h4>Error Types During High Latency</h4><div class="error-type-grid">';
      Object.entries(correlation.errors_by_type).forEach(([type, count]) => {
        const typeColors = {
          'connection': '#ef4444',
          'timeout': '#f59e0b',
          'memory': '#8b5cf6',
          'sql': '#3b82f6',
          'other': '#6b7280'
        };
        html += `
          <div class="error-type-item" style="border-left-color: ${typeColors[type] || '#6b7280'}">
            <span class="error-type-count">${count}</span>
            <span class="error-type-name">${type}</span>
          </div>
        `;
      });
      html += '</div></div>';
    }
    
    // Errors by component
    if (correlation.errors_by_component && Object.keys(correlation.errors_by_component).length > 0) {
      html += '<div class="correlation-breakdown"><h4>Errors by Component</h4><div class="error-component-list">';
      Object.entries(correlation.errors_by_component)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 6)
        .forEach(([comp, count]) => {
          const short = getComponentShort(comp);
          html += `<div class="error-component-item"><span class="comp-name">${comp}</span><span class="comp-count">${count}</span>`
            + (short ? `<span class="comp-context">${short}</span>` : '')
            + `</div>`;
        });
      html += '</div></div>';
    }
    
    // Sample errors
    if (correlation.sample_errors && correlation.sample_errors.length > 0) {
      html += '<div class="correlation-samples"><h4>Sample Errors (click to navigate)</h4>';
      correlation.sample_errors.slice(0, 5).forEach(err => {
        html += `
          <div class="sample-error" onclick="jumpToLineAndHighlight(${err.line_number}, '')">
            <span class="sample-time">${err.timestamp?.substring(11, 19) || ''}</span>
            <span class="sample-comp">[${err.component}]</span>
            <span class="sample-text">${escapeHtml(err.text?.substring(0, 100) || '')}...</span>
          </div>
        `;
      });
      html += '</div>';
    }
    
    return html;
  }
  
  function renderMergeAnalysis(mergeData) {
    if (!mergeData || !mergeData.summary) return '';
    
    const summary = mergeData.summary;
    
    let html = `
      <div class="merge-summary">
        <div class="merge-stat highlight">
          <span class="merge-value">${summary.merge_percent}%</span>
          <span class="merge-label">MERGE Operations</span>
        </div>
        <div class="merge-stat">
          <span class="merge-value">${summary.total_merge_operations.toLocaleString()}</span>
          <span class="merge-label">Total MERGE</span>
        </div>
        <div class="merge-stat">
          <span class="merge-value">${summary.total_standard_operations.toLocaleString()}</span>
          <span class="merge-label">Standard Bulk</span>
        </div>
        <div class="merge-stat">
          <span class="merge-value">${summary.tables_using_merge}</span>
          <span class="merge-label">Tables Using MERGE</span>
        </div>
      </div>
    `;
    
    // Tables with MERGE
    if (mergeData.tables_with_merge && mergeData.tables_with_merge.length > 0) {
      html += '<div class="merge-tables"><h4>Tables Using MERGE</h4><table class="merge-table">';
      html += '<thead><tr><th>Table</th><th>MERGE</th><th>Standard</th><th>MERGE %</th></tr></thead><tbody>';
      mergeData.tables_with_merge.slice(0, 10).forEach(t => {
        html += `
          <tr>
            <td class="table-name" title="${t.table_name}">${t.table_name}</td>
            <td class="merge-count">${t.merge_count.toLocaleString()}</td>
            <td>${t.standard_count.toLocaleString()}</td>
            <td class="merge-pct">${t.merge_percent}%</td>
          </tr>
        `;
      });
      html += '</tbody></table></div>';
    }
    
    return html;
  }
  
  function renderCDCPipeline(pipeline) {
    if (!pipeline) return '';
    
    const healthColors = { 'healthy': '#10b981', 'warning': '#f59e0b', 'critical': '#ef4444' };
    const hc = healthColors[pipeline.health_status] || '#6b7280';
    const healthLabel = pipeline.health_status === 'healthy' ? '✓ Healthy' : pipeline.health_status === 'warning' ? '⚠ Warning' : '✗ Critical';
    
    let html = `<div class="pipeline-status" style="display:flex;align-items:center;gap:8px;margin-bottom:8px;"><span style="padding:3px 8px;background:${hc}22;color:${hc};border-radius:3px;font-size:0.7rem;font-weight:bold;">${healthLabel}</span></div>`;
    
    html += '<div class="pipeline-metrics" style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;">';
    html += `<div class="pipeline-metric"><span class="metric-value" style="color:#f59e0b;">${pipeline.memory_warnings || 0}</span><span class="metric-label">Memory Warnings</span></div>`;
    html += `<div class="pipeline-metric"><span class="metric-value" style="color:#ef4444;">${pipeline.overflow_events || 0}</span><span class="metric-label">Overflow Events</span></div>`;
    html += `<div class="pipeline-metric"><span class="metric-value" style="color:#ef4444;">${pipeline.disconnections || 0}</span><span class="metric-label">Disconnections</span></div>`;
    html += `<div class="pipeline-metric"><span class="metric-value" style="color:#10b981;">${pipeline.reconnections || 0}</span><span class="metric-label">Reconnections</span></div>`;
    html += '</div>';
    
    if (pipeline.health_status !== 'healthy') {
      html += '<div class="pipeline-hint" style="margin-top:8px;padding:6px;background:#1f2937;border-radius:3px;font-size:0.65rem;color:#9ca3af;">';
      if (pipeline.memory_warnings > 0) {
        html += '<p style="margin:0 0 4px;"><span style="color:#f59e0b;">●</span> Memory warnings indicate sorter buffer pressure. Consider increasing stream_buffer_size.</p>';
      }
      if (pipeline.disconnections > 0) {
        html += '<p style="margin:0;"><span style="color:#ef4444;">●</span> Target disconnections affect apply performance. Check target database connectivity.</p>';
      }
      html += '</div>';
    }
    
    return html;
  }
  
  function renderSourceAnalysis(source) {
    if (!source) return '';
    
    const healthColors = { 'healthy': '#10b981', 'warning': '#f59e0b', 'critical': '#ef4444' };
    const hc = healthColors[source.health_status] || '#6b7280';
    const healthLabel = source.health_status === 'healthy' ? '✓ Healthy' : source.health_status === 'warning' ? '⚠ Warning' : '✗ Critical';
    
    let html = `<div class="source-status" style="display:flex;align-items:center;gap:8px;margin-bottom:8px;"><span style="padding:3px 8px;background:${hc}22;color:${hc};border-radius:3px;font-size:0.7rem;font-weight:bold;">${healthLabel}</span></div>`;
    
    html += '<div class="source-metrics" style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px;">';
    html += `<div class="source-metric"><span class="metric-value" style="color:#3b82f6;">${source.total_reconnects || 0}</span><span class="metric-label">Reconnects</span></div>`;
    html += `<div class="source-metric"><span class="metric-value" style="color:#ef4444;">${source.network_issues || 0}</span><span class="metric-label">Network Issues</span></div>`;
    html += `<div class="source-metric"><span class="metric-value" style="color:#f59e0b;">${source.contention_issues || 0}</span><span class="metric-label">Contention</span></div>`;
    html += `<div class="source-metric"><span class="metric-value" style="color:#8b5cf6;">${source.resource_issues || 0}</span><span class="metric-label">Resource Issues</span></div>`;
    html += `<div class="source-metric"><span class="metric-value" style="color:#6b7280;">${source.total_source_errors || 0}</span><span class="metric-label">Total Errors</span></div>`;
    html += '</div>';
    
    // Investigation hints
    if (source.investigation_hints && source.investigation_hints.length > 0) {
      html += '<div class="source-hints" style="margin-top:8px;padding:6px;background:#1f2937;border-radius:3px;">';
      html += '<h4 style="margin:0 0 4px;font-size:0.7rem;color:#9ca3af;">Investigation Hints</h4>';
      html += '<ul style="margin:0;padding-left:16px;font-size:0.65rem;color:#d1d5db;">';
      source.investigation_hints.forEach(hint => {
        html += `<li style="margin:2px 0;">${hint}</li>`;
      });
      html += '</ul></div>';
    }
    
    return html;
  }

  // ============================================================
  // RELEASE NOTES INTEGRATION
  // ============================================================
  
  window.showReleaseNotesInMain = function() {
    // Hide ALL other views
    document.querySelectorAll('.analysis-view').forEach(v => v.style.display = 'none');
    document.getElementById('threadActivityControls').style.display = 'none';
    
    // Show release notes view
    const view = document.getElementById('releaseNotesMainView');
    if (view) {
      view.style.display = 'block';
    }
    
    // Set active report link
    setActiveReportLink('releaseNotesLink');
    
    // Render the release notes interface
    renderReleaseNotesInterface();
  };
  
  // Parse Qlik Replicate version to get release month
  // Format: YYYY.MM.X.XXX where MM is the month number directly (11 = November)
  function parseReplicateVersion(version) {
    if (!version) return { version: 'Unknown', releaseDate: null, releaseMonth: null };
    
    const match = version.match(/^(\d{4})\.(\d{1,2})/);
    if (!match) return { version, releaseDate: null, releaseMonth: null };
    
    const year = parseInt(match[1]);
    const month = parseInt(match[2]);
    
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 
                        'July', 'August', 'September', 'October', 'November', 'December'];
    
    if (month < 1 || month > 12) return { version, releaseDate: null, releaseMonth: null };
    
    return {
      version,
      releaseMonth: monthNames[month - 1],
      releaseYear: year,
      releaseDate: `${monthNames[month - 1]} ${year}`
    };
  }
  
  function renderReleaseNotesInterface() {
    const content = document.getElementById('releaseNotesMainContent');
    if (!content) return;
    
    const version = window.taskVersion || 'Unknown';
    const versionInfo = parseReplicateVersion(version);
    const sourceEndpoint = window.sourceEndpoint || 'Unknown';
    const targetEndpoint = window.targetEndpoint || 'Unknown';
    const releaseNotesUrl = 'https://community.qlik.com/t5/Release-Notes/tkb-p/ReleaseNotes';
    
    const releaseLabel = versionInfo.releaseDate ? 
      '<span style="color:#10b981;font-size:0.7rem;margin-left:8px;">(' + versionInfo.releaseDate + ' Release)</span>' : '';
    
    let h = '<div style="max-width:900px;margin:0 auto;padding:16px">';
    h += '<div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">';
    h += '<svg width="28" height="28" viewBox="0 0 16 16" fill="#06b6d4"><path d="M4.5 3a2.5 2.5 0 0 1 5 0v9a1.5 1.5 0 0 1-3 0V5a.5.5 0 0 1 1 0v7a.5.5 0 0 0 1 0V3a1.5 1.5 0 1 0-3 0v9a2.5 2.5 0 0 0 5 0V5a.5.5 0 0 1 1 0v7a3.5 3.5 0 1 1-7 0V3z"/></svg>';
    h += '<div><h2 style="margin:0;font-size:1.1rem">Qlik Replicate Release Notes</h2>';
    h += '<p style="margin:2px 0 0;font-size:0.75rem;color:#9ca3af">Find relevant fixes and enhancements for your configuration</p></div></div>';

    // Configuration card
    h += '<div style="background:#1f2937;border-radius:8px;padding:16px;margin-bottom:20px">';
    h += '<h3 style="margin:0 0 12px;font-size:0.85rem;color:#e5e7eb">Your Configuration</h3>';
    h += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px">';
    h += '<div style="background:#111827;padding:10px;border-radius:6px">';
    h += '<div style="font-size:0.65rem;color:#9ca3af;text-transform:uppercase;margin-bottom:4px">Replicate Version</div>';
    h += '<div style="font-size:0.9rem;color:#3b82f6;font-weight:bold">' + version + releaseLabel + '</div></div>';
    h += '<div style="background:#111827;padding:10px;border-radius:6px">';
    h += '<div style="font-size:0.65rem;color:#9ca3af;text-transform:uppercase;margin-bottom:4px">Source Endpoint</div>';
    h += '<div style="font-size:0.85rem;color:#10b981">' + sourceEndpoint + '</div></div>';
    h += '<div style="background:#111827;padding:10px;border-radius:6px">';
    h += '<div style="font-size:0.65rem;color:#9ca3af;text-transform:uppercase;margin-bottom:4px">Target Endpoint</div>';
    h += '<div style="font-size:0.85rem;color:#f59e0b">' + targetEndpoint + '</div></div></div></div>';

    // Indexed release notes results placeholder
    h += '<div id="releaseNotesResults" style="margin-bottom:20px">';
    h += '<div style="text-align:center;padding:24px;color:#9ca3af;font-size:0.8rem">';
    h += '<div class="loading-spinner" style="margin:0 auto 8px;width:24px;height:24px;border:2px solid #374151;border-top-color:#06b6d4;border-radius:50%;animation:spin 1s linear infinite"></div>';
    h += 'Searching indexed release notes...</div></div>';

    // Search on community fallback
    h += '<div style="background:linear-gradient(135deg,#1e3a5f,#1e1b4b);border:1px solid #3b82f6;border-radius:8px;padding:16px">';
    h += '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">';
    h += '<div><h3 style="margin:0 0 6px;font-size:0.9rem;color:#e5e7eb">Search on Qlik Community</h3>';
    h += '<p style="margin:0;font-size:0.75rem;color:#9ca3af">Browse the official release notes knowledge base</p></div>';
    h += '<a href="' + releaseNotesUrl + '" target="_blank" style="display:inline-flex;align-items:center;gap:6px;padding:10px 20px;background:#3b82f6;color:white;text-decoration:none;border-radius:6px;font-size:0.85rem;font-weight:600">Open Release Notes <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path fill-rule="evenodd" d="M8.636 3.5a.5.5 0 0 0-.5-.5H1.5A1.5 1.5 0 0 0 0 4.5v10A1.5 1.5 0 0 0 1.5 16h10a1.5 1.5 0 0 0 1.5-1.5V7.864a.5.5 0 0 0-1 0V14.5a.5.5 0 0 1-.5.5h-10a.5.5 0 0 1-.5-.5v-10a.5.5 0 0 1 .5-.5h6.636a.5.5 0 0 0 .5-.5z"/><path fill-rule="evenodd" d="M16 .5a.5.5 0 0 0-.5-.5h-5a.5.5 0 0 0 0 1h3.793L6.146 9.146a.5.5 0 1 0 .708.708L15 1.707V5.5a.5.5 0 0 0 1 0v-5z"/></svg></a></div></div>';

    h += '</div>';
    content.innerHTML = h;

    // Fetch release notes, filtered by detected version and endpoints
    if (currentFileId) {
      const rnParams = new URLSearchParams();
      if (versionInfo.releaseMonth && versionInfo.releaseYear) {
        rnParams.set('release_version', versionInfo.releaseMonth + ' ' + versionInfo.releaseYear);
      }
      if (sourceEndpoint && sourceEndpoint !== 'Unknown') {
        rnParams.set('source_endpoint', sourceEndpoint);
      }
      if (targetEndpoint && targetEndpoint !== 'Unknown') {
        rnParams.set('target_endpoint', targetEndpoint);
      }
      const rnQuery = rnParams.toString();
      let rnUrl = `/api/llm/release-notes/${currentFileId}` + (rnQuery ? '?' + rnQuery : '');
      fetch(rnUrl)
        .then(res => res.json())
        .then(data => {
          window._rnData = data;
          window._rnActiveFilters = new Set();
          _renderReleaseNotesEntries();
        })
        .catch(err => {
          console.error('Failed to fetch release notes:', err);
          const container = document.getElementById('releaseNotesResults');
          if (container) {
            container.innerHTML = '<div style="background:#1f2937;border-radius:8px;padding:16px;text-align:center">'
              + '<p style="margin:0;font-size:0.8rem;color:#f38ba8">Failed to load release notes: ' + err.message + '</p></div>';
          }
        });
    }
  }

  // ============================================================
  // RELEASE NOTES FILTER + RENDERING
  // ============================================================

  const _rnComponentGroups = {
    'Endpoint-Specific': comp => false,
    'Server / Engine': comp => ['server', 'engine', 'common', 'general', 'setup'].includes(comp),
    'Security': comp => comp === 'security',
    'Sorter': comp => comp === 'sorter',
    'Logging': comp => ['logging', 'log stream'].includes(comp),
    'Apply / Load': comp => ['batch optimized apply', 'transactional apply', 'full load'].includes(comp),
    'Metadata': comp => ['metadata manager', 'metadata'].includes(comp),
  };

  function _classifyComponent(comp, isEndpointSpecific) {
    if (!comp) return 'Other';
    if (isEndpointSpecific) return 'Endpoint-Specific';
    const lower = comp.toLowerCase();
    for (const [group, testFn] of Object.entries(_rnComponentGroups)) {
      if (group === 'Endpoint-Specific') continue;
      if (testFn(lower)) return group;
    }
    return 'Other';
  }

  function _renderReleaseNotesEntries() {
    const data = window._rnData;
    const activeFilters = window._rnActiveFilters;
    const container = document.getElementById('releaseNotesResults');
    if (!container || !data) return;

    if (data.indexed_count === 0) {
      container.innerHTML = '<div style="background:#1f2937;border-radius:8px;padding:20px;text-align:center">'
        + '<svg width="32" height="32" viewBox="0 0 16 16" fill="#6b7280" style="margin-bottom:8px"><path d="M4.5 3a2.5 2.5 0 0 1 5 0v9a1.5 1.5 0 0 1-3 0V5a.5.5 0 0 1 1 0v7a.5.5 0 0 0 1 0V3a1.5 1.5 0 1 0-3 0v9a2.5 2.5 0 0 0 5 0V5a.5.5 0 0 1 1 0v7a3.5 3.5 0 1 1-7 0V3z"/></svg>'
        + '<p style="margin:0 0 4px;font-size:0.85rem;color:#e5e7eb">No release notes indexed</p>'
        + '<p style="margin:0;font-size:0.75rem;color:#9ca3af">Run the release notes loader (<code style="background:#374151;padding:2px 4px;border-radius:3px;font-size:0.7rem">python kb-assistant/build_release_notes_cache.py</code>) to index Qlik Replicate release notes for correlation analysis.</p></div>';
      return;
    }

    const allResults = data.results || [];
    const hasEol = data.eol_warnings && data.eol_warnings.length > 0;

    // Build group counts from all results
    const groupCounts = {};
    for (const rn of allResults) {
      const g = _classifyComponent(rn.component, rn.endpoint_specific);
      groupCounts[g] = (groupCounts[g] || 0) + 1;
    }

    // Determine visible results (if no filters active, show all)
    const noFilter = activeFilters.size === 0;
    const filtered = noFilter ? allResults : allResults.filter(rn => {
      const g = _classifyComponent(rn.component, rn.endpoint_specific);
      return activeFilters.has(g);
    });

    if (!filtered.length && !hasEol) {
      container.innerHTML = '<div style="background:#1f2937;border-radius:8px;padding:16px;text-align:center">'
        + '<p style="margin:0;font-size:0.8rem;color:#9ca3af">No matching release notes found for this log file\'s configuration. '
        + data.indexed_count + ' entries are indexed.</p></div>';
      return;
    }

    let rh = '';

    // Filter chips
    const groupOrder = ['Endpoint-Specific', 'Server / Engine', 'Security', 'Sorter', 'Logging', 'Apply / Load', 'Metadata', 'Other'];
    const presentGroups = groupOrder.filter(g => groupCounts[g]);
    if (presentGroups.length > 1) {
      rh += '<div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px">';
      for (const g of presentGroups) {
        const isActive = activeFilters.has(g);
        const count = groupCounts[g] || 0;
        const bgActive = g === 'Endpoint-Specific' ? '#78350f' : '#1e3a5f';
        const bgInactive = '#1f2937';
        const colorActive = g === 'Endpoint-Specific' ? '#fcd34d' : '#93c5fd';
        const colorInactive = '#6b7280';
        const border = isActive ? (g === 'Endpoint-Specific' ? '#f59e0b' : '#3b82f6') : '#374151';
        rh += '<button class="rn-filter-chip" data-group="' + g + '" style="'
            + 'background:' + (isActive ? bgActive : bgInactive) + ';'
            + 'color:' + (isActive ? colorActive : colorInactive) + ';'
            + 'border:1px solid ' + border + ';'
            + 'border-radius:12px;padding:2px 10px;font-size:0.65rem;cursor:pointer;display:inline-flex;align-items:center;gap:4px;transition:all 0.15s">'
            + g + ' <span style="opacity:0.7">(' + count + ')</span></button>';
      }
      if (!noFilter) {
        rh += '<button class="rn-filter-chip" data-group="__clear__" style="'
            + 'background:transparent;color:#9ca3af;border:1px solid #374151;'
            + 'border-radius:12px;padding:2px 10px;font-size:0.65rem;cursor:pointer">Clear filters</button>';
      }
      rh += '</div>';
    }

    // EOL warnings
    if (hasEol) {
      rh += '<div style="background:#451a03;border:1px solid #92400e;border-radius:8px;padding:14px;margin-bottom:14px">';
      rh += '<div style="display:flex;align-items:center;gap:6px;margin-bottom:8px">';
      rh += '<svg width="16" height="16" viewBox="0 0 16 16" fill="#f59e0b"><path d="M8 1L1 14h14L8 1zm0 4v4m0 2v1"/></svg>';
      rh += '<h3 style="margin:0;font-size:0.85rem;color:#fbbf24">End of Support Warnings</h3></div>';
      for (const eol of data.eol_warnings) {
        const vBadge = eol.version ? '<span style="padding:1px 5px;background:#78350f;color:#fcd34d;border-radius:3px;font-size:0.6rem">' + eol.version + '</span> ' : '';
        const eolLink = eol.url
          ? '<a href="' + eol.url + '" target="_blank" title="View source release notes" style="color:#fbbf24;text-decoration:none;display:inline-flex;align-items:center;gap:3px;font-size:0.65rem;margin-left:auto;white-space:nowrap">'
            + '<svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor"><path d="M8.636 3.5a.5.5 0 0 0-.5-.5H1.5A1.5 1.5 0 0 0 0 4.5v10A1.5 1.5 0 0 0 1.5 16h10a1.5 1.5 0 0 0 1.5-1.5V7.864a.5.5 0 0 0-1 0V14.5a.5.5 0 0 1-.5.5h-10a.5.5 0 0 1-.5-.5v-10a.5.5 0 0 1 .5-.5h6.636a.5.5 0 0 0 .5-.5z"/><path d="M16 .5a.5.5 0 0 0-.5-.5h-5a.5.5 0 0 0 0 1h3.793L6.146 9.146a.5.5 0 1 0 .708.708L15 1.707V5.5a.5.5 0 0 0 1 0v-5z"/></svg>'
            + 'Source</a>'
          : '';
        rh += '<div style="background:#78350f;border-radius:5px;padding:8px 10px;margin-bottom:5px;border-left:3px solid #f59e0b">';
        rh += '<div style="display:flex;align-items:center;gap:5px;margin-bottom:2px">';
        rh += '<span style="padding:1px 5px;background:#dc2626;color:#fff;border-radius:3px;font-size:0.6rem;font-weight:600">End of Support</span>' + vBadge + eolLink + '</div>';
        rh += '<p style="margin:0;font-size:0.78rem;color:#fef3c7;line-height:1.4">' + eol.description + '</p>';
        rh += '</div>';
      }
      rh += '</div>';
    }

    // RECOB entries
    if (filtered.length > 0) {
      rh += '<div style="background:#1f2937;border-radius:8px;padding:16px">';
      rh += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">';
      rh += '<h3 style="margin:0;font-size:0.85rem;color:#e5e7eb">Resolved Issues & Enhancements</h3>';
      rh += '<span style="font-size:0.7rem;color:#6b7280">' + filtered.length + (noFilter ? '' : ' / ' + allResults.length) + ' entries</span></div>';

      for (const rn of filtered) {
        const isRecob = rn.fix_id && rn.fix_id.startsWith('RECOB-');
        const isFuture = rn.future_release;
        const isEndpointSpecific = rn.endpoint_specific === true;
        const borderColor = isFuture ? '#7c3aed' : isEndpointSpecific ? '#f59e0b' : (rn.entry_type === 'Enhancement' ? '#10b981' : '#374151');
        const typeBadgeBg = rn.entry_type === 'Enhancement' ? '#10b981' : (rn.entry_type === 'Issue' ? '#ef4444' : '#6b7280');
        const typeBadge = rn.entry_type ? '<span style="padding:1px 5px;background:' + typeBadgeBg + ';color:#fff;border-radius:3px;font-size:0.6rem;font-weight:600">' + rn.entry_type + '</span>' : '';
        const fixBadge = rn.fix_id ? '<span style="padding:1px 5px;background:#06b6d4;color:#111827;border-radius:3px;font-size:0.65rem;font-weight:bold;font-family:monospace">' + rn.fix_id + '</span>' : '';
        const futureBadge = isFuture ? '<span style="padding:1px 5px;background:#7c3aed;color:#e9d5ff;border-radius:3px;font-size:0.6rem;font-weight:600">Future Release</span>' : '';
        const versionBadge = rn.version ? '<span style="padding:1px 5px;background:#374151;color:#9ca3af;border-radius:3px;font-size:0.6rem">' + rn.version + '</span>' : '';
        const compBadge = rn.component ? '<span style="padding:1px 5px;background:' + (isEndpointSpecific ? '#78350f' : '#1e3a5f') + ';color:' + (isEndpointSpecific ? '#fcd34d' : '#93c5fd') + ';border-radius:3px;font-size:0.6rem">' + rn.component + '</span>' : '';

        rh += '<div style="background:' + (isFuture ? '#1a1033' : '#111827') + ';border-radius:6px;padding:10px 12px;margin-bottom:6px;border-left:3px solid ' + borderColor + '">';
        rh += '<div style="display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-bottom:4px">' + fixBadge + typeBadge + compBadge + futureBadge + versionBadge + '</div>';

        const srcLink = rn.url
          ? '<a href="' + rn.url + '" target="_blank" title="View source release notes" style="color:#60a5fa;text-decoration:none;display:inline-flex;align-items:center;gap:3px;font-size:0.65rem;margin-left:auto;white-space:nowrap">'
            + '<svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor"><path d="M8.636 3.5a.5.5 0 0 0-.5-.5H1.5A1.5 1.5 0 0 0 0 4.5v10A1.5 1.5 0 0 0 1.5 16h10a1.5 1.5 0 0 0 1.5-1.5V7.864a.5.5 0 0 0-1 0V14.5a.5.5 0 0 1-.5.5h-10a.5.5 0 0 1-.5-.5v-10a.5.5 0 0 1 .5-.5h6.636a.5.5 0 0 0 .5-.5z"/><path d="M16 .5a.5.5 0 0 0-.5-.5h-5a.5.5 0 0 0 0 1h3.793L6.146 9.146a.5.5 0 1 0 .708.708L15 1.707V5.5a.5.5 0 0 0 1 0v-5z"/></svg>'
            + 'Source</a>'
          : '';

        if (isRecob && rn.description) {
          rh += '<p style="margin:0;font-size:0.78rem;color:#d1d5db;line-height:1.45">' + rn.description + '</p>';
        } else if (rn.title) {
          const titleLink = rn.url ? '<a href="' + rn.url + '" target="_blank" style="color:#e5e7eb;text-decoration:none;font-size:0.78rem;font-weight:500">' + rn.title + '</a>' : '<span style="color:#e5e7eb;font-size:0.78rem;font-weight:500">' + rn.title + '</span>';
          rh += '<div>' + titleLink + '</div>';
          if (rn.description) {
            rh += '<p style="margin:4px 0 0;font-size:0.72rem;color:#9ca3af;line-height:1.4">' + rn.description.substring(0, 200) + (rn.description.length > 200 ? '...' : '') + '</p>';
          }
        }

        const rnTitle = (rn.fix_id || '') + ' ' + (rn.title || rn.description || '');
        const rnSaveBtn = '<button class="rn-save-finding-btn" data-rn-title="' + escapeHtml(rnTitle.trim()).replace(/"/g, '&quot;') + '" data-rn-url="' + (rn.url || '') + '" data-rn-version="' + (rn.version || '') + '" title="Add to Findings" style="background:none;border:1px solid #374151;border-radius:3px;padding:2px 5px;cursor:pointer;color:#9ca3af;font-size:0.6rem;display:inline-flex;align-items:center;gap:3px;transition:all 0.15s">'
          + '<svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor"><path d="M2 2a2 2 0 012-2h8a2 2 0 012 2v13.5a.5.5 0 01-.777.416L8 13.101l-5.223 2.815A.5.5 0 012 15.5V2zm2-1a1 1 0 00-1 1v12.566l4.723-2.482a.5.5 0 01.554 0L13 14.566V2a1 1 0 00-1-1H4z"/></svg>'
          + 'Save</button>';

        rh += '<div style="display:flex;align-items:center;gap:8px;margin-top:4px">';
        if (rn.salesforce_case && rn.salesforce_case !== 'N/A') {
          rh += '<span style="font-size:0.6rem;color:#6b7280">SF Case: ' + rn.salesforce_case + '</span>';
        }
        rh += rnSaveBtn + srcLink + '</div>';
        rh += '</div>';
      }
      rh += '</div>';
    }

    container.innerHTML = rh;

    // Bind filter chip clicks
    container.querySelectorAll('.rn-filter-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const group = chip.dataset.group;
        if (group === '__clear__') {
          window._rnActiveFilters.clear();
        } else if (window._rnActiveFilters.has(group)) {
          window._rnActiveFilters.delete(group);
        } else {
          window._rnActiveFilters.add(group);
        }
        _renderReleaseNotesEntries();
      });
    });
    
    // Bind release note "Save to Findings" buttons
    container.querySelectorAll('.rn-save-finding-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (!currentFileId) return;
        const title = btn.dataset.rnTitle || 'Release Note';
        const url = btn.dataset.rnUrl || '';
        const version = btn.dataset.rnVersion || '';
        const content = `**Release Note:** ${title}` + (version ? `\n**Version:** ${version}` : '') + (url ? `\n**URL:** ${url}` : '');
        
        try {
          const resp = await fetch('/api/llm/findings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              file_id: currentFileId,
              finding_type: 'custom',
              title: title.slice(0, 120),
              content,
              metadata: { source: 'release_notes', url, version }
            })
          });
          if (resp.ok) {
            btn.innerHTML = '<svg width="10" height="10" viewBox="0 0 16 16" fill="#10b981"><path d="M13.854 3.646a.5.5 0 010 .708l-7 7a.5.5 0 01-.708 0l-3.5-3.5a.5.5 0 11.708-.708L6.5 10.293l6.646-6.647a.5.5 0 01.708 0z"/></svg> Saved';
            btn.style.color = '#10b981';
            btn.style.borderColor = '#10b981';
            if (window.savedFindingsManager) window.savedFindingsManager.loadFindings();
          }
        } catch (err) {
          console.error('Failed to save release note finding:', err);
        }
      });
    });
  }

  // ============================================================
  // UNAVAILABLE REPORTS
  // ============================================================

  const unavailableReportDefs = {
    logSummaryLink:          { name: 'Log Summary',   reason: 'Log summary data could not be extracted from this log file' },
    performanceCockpitLink:  { name: 'Performance',   reason: 'No performance or latency data was found in this log file' },
    bulkMapLink:             { name: 'Bulk Map',      reason: 'No bulk-map (Full Load table mapping) operations were detected in this log' },
    bulkActivityLink:        { name: 'Bulk Activity',  reason: 'No bulk-load activity was detected in this log file' },
    fileOperationsLink:      { name: 'File Ops',      reason: 'No file-transfer operations were found in this log file' },
    issuesLink:              { name: 'Issues',        reason: 'No issues were detected, or the log has not been fully analyzed yet' },
    releaseNotesLink:        { name: 'Release Notes', reason: 'Task version could not be detected from the log, so release notes cannot be matched' },
  };

  function updateUnavailableReports() {
    const section = document.getElementById('unavailableReportsSection');
    const list = document.getElementById('unavailableReportsList');
    if (!section || !list) return;

    let html = '';
    let count = 0;
    for (const [id, def] of Object.entries(unavailableReportDefs)) {
      const el = document.getElementById(id);
      if (el && el.style.display === 'none') {
        count++;
        html += '<div class="unavailable-report-item" style="padding:5px 8px 5px 24px;cursor:default" title="' + def.reason + '">';
        html += '<span style="font-size:0.75rem;color:#4b5563">' + def.name + '</span>';
        html += '<p style="margin:2px 0 0;font-size:0.65rem;color:#374151;line-height:1.3">' + def.reason + '</p>';
        html += '</div>';
      }
    }

    if (count > 0) {
      list.innerHTML = html;
      section.style.display = 'block';
    } else {
      section.style.display = 'none';
    }
  }

  // Toggle unavailable reports section
  const unavailToggle = document.getElementById('unavailableReportsToggle');
  if (unavailToggle) {
    unavailToggle.addEventListener('click', () => {
      const list = document.getElementById('unavailableReportsList');
      const arrow = document.getElementById('unavailableReportsArrow');
      if (!list) return;
      const isOpen = list.style.display !== 'none';
      list.style.display = isOpen ? 'none' : 'block';
      if (arrow) arrow.style.transform = isOpen ? 'rotate(0deg)' : 'rotate(90deg)';
    });
  }

  // ============================================================
  // AI INTEGRATION
  // ============================================================
  
  // AI Settings button handler
  const aiSettingsBtn = document.getElementById('aiSettingsBtn');
  if (aiSettingsBtn) {
    aiSettingsBtn.addEventListener('click', () => {
      if (window.aiConfigModal) {
        window.aiConfigModal.open();
      }
    });
  }
  
  // Connect AI config changes to AI assistant
  if (window.aiConfigModal && window.aiAssistant) {
    window.aiConfigModal.onConfigSaved = (config) => {
      window.aiAssistant.onConfigChanged(config);
    };
  }
  
  // Update AI settings indicator based on configuration status
  function updateAISettingsIndicator() {
    const indicators = document.querySelectorAll('.ai-settings-indicator');
    if (!indicators.length) return;

    fetch('/api/llm/config')
      .then(res => res.json())
      .then(config => {
        indicators.forEach((indicator) => {
          if (config.is_configured) {
            indicator.classList.add('configured');
            indicator.title = 'AI Configured';
          } else {
            indicator.classList.remove('configured');
            indicator.title = 'AI Not Configured';
          }
        });
      })
      .catch(() => {
        indicators.forEach((indicator) => {
          indicator.classList.remove('configured');
        });
      });
  }
  
  // Initial check
  updateAISettingsIndicator();
  
  // Render AI report section in its container
  function renderAIReportSection() {
    if (!currentFileId) return;
    
    const container = document.getElementById('aiReportContainer');
    if (container && window.aiReportManager) {
      window.aiReportManager.render(container, currentFileId);
    }
  }
  
  // Hook into tab switching for resources tab
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.dataset.tab === 'resources-tab') {
        // Render AI report section when resources tab is clicked
        setTimeout(renderAIReportSection, 50);
      }
    });
  });
  
  // Also render AI report when a file is loaded
  const originalLoadFile = loadFile;
  loadFile = function(id) {
    originalLoadFile(id);
    // Mount AI Insights markup before setFileId so container exists when auto-generate updates the UI
    renderAIReportSection();
    if (window.aiReportManager) {
      window.aiReportManager.setFileId(id);
    }
  };

  // Dismiss splash screen and reveal the app
  const appRoot = document.getElementById('app-root');
  const splash = document.getElementById('splash-screen');
  if (appRoot) appRoot.style.visibility = '';
  if (splash) {
    splash.classList.add('hidden');
    splash.addEventListener('transitionend', () => splash.remove(), { once: true });
  }

});
