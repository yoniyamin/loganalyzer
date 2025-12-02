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
    'ADDONS': 'Only relevant when working with a Replicate add-on. Currently, the only add-ons are user-defined transformations.',
    'ASSERTION': 'Detects anomalies with the data, which might result in replication issues. These warnings are not exposed in the web console and do not trigger notifications.',
    'COMMON': 'Writes low level messages such as network activity. Not recommended to set to "Trace" as it will write a huge amount of data to the log.',
    'COMMUNICATION': 'Provides additional information about the communication between Replicate and the Source and Target components. For example, when using Hadoop, it will print the CURL debug messages.',
    'DATA_RECORD': 'Writes information about each change that occurs. Records when a specific event was captured as well as the event context.',
    'DATA_STRUCTURE': 'Used for internal Replicate data structures and is related to how the code deals with the data and stores it in memory.',
    'FILE_FACTORY': 'Relevant to Hadoop Target, Amazon Redshift and Microsoft Azure SQL Synapse Analytics. This component is responsible for moving the files from Replicate to the target.',
    'FILE_TRANSFER': 'Writes to the log when the File Transfer component is used to push files to a specific location.',
    'INFRASTRUCTURE': 'Records infrastructure information related to the infrastructure layers of Replicate code: ODBC infrastructure, logger infrastructure, opening/closing threads, saving task state, etc.',
    'IO': 'Logs all IO operations (i.e. file operations), such as checking directory size, creating directories, deleting directories, etc.',
    'METADATA_CHANGES': 'Shows the actual DDL changes which are included in the scope (available for specific endpoints).',
    'METADATA_MANAGER': 'Writes information whenever Replicate reads metadata from the source or target, or stores it. Manages tables metadata and dynamic metadata.',
    'PERFORMANCE': 'Currently used for latency only. Logs latency values for source and target endpoints every 30 seconds.',
    'REST_SERVER': 'Handles all REST requests (API and UI). Also shows the interaction between Replicate and Qlik Enterprise Manager.',
    'SERVER': 'The server thread in the task that communicates with the Replicate Server service on task start, stop, etc. Includes init functions for the task.',
    'SORTER': 'The main component in CDC that routes the changes captured from the source to the target. Responsible for synchronizing Full Load and CDC changes, deciding which events to apply as cached changes, and storing transactions until they are committed.',
    'SORTER_STORAGE': 'The storage component of the Sorter which stores transactions in memory and offloads them to disk when the transactions are too large.',
    'SOURCE_CAPTURE': 'The main CDC component on the source side. Used to troubleshoot any CDC source issue. Setting to "Verbose" will record an enormous amount of data.',
    'SOURCE_LOG_DUMP': 'When using Replicate Log Reader, this component creates additional files with dumps of the read changes.',
    'SOURCE_UNLOAD': 'Records source activity related to Full load operations and includes the SELECT statement executed against the source tables prior to Full Load.',
    'STREAM': 'The buffer in memory where data and control commands are kept. There are two types: Data streams and Control streams.',
    'STREAM_COMPONENT': 'Used by the Source, Sorter and Target to interact and communicate with the Stream component.',
    'TABLES_MANAGER': 'Manages the table status including whether they were loaded into the target, the number of events, how the tables are partitioned, etc.',
    'TARGET_APPLY': 'Determines which changes are applied to the target during CDC. Relevant to both Batch optimized apply and Transactional apply methods. Provides information about all Apply issues including missing events, bad data, etc.',
    'TARGET_LOAD': 'Provides information about Full Load operations on the target side. Depending on the target, it may also print the metadata of the target table.',
    'TASK_MANAGER': 'The parent task component that manages the other components in the task. Responsible for issuing commands to start/finish loading tables, create component threads, start or stop tasks, etc.',
    'TRANSFORMATION': 'Logs information related to transformations. When set to "Trace", it will log the actual transformations being used by the task.',
    'UTILITIES': 'In most cases, logs issues related to notifications.',
    'AT_GLOBAL': 'Global task information and licensing details.',
    'METADATA_MANAGE': 'Alternative name for METADATA_MANAGER - manages metadata operations.'
  };
  
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

  // Search
  if (searchBtn) searchBtn.addEventListener("click", performSearch);
  if (searchInput) {
    searchInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") performSearch();
    });
  }

  // Infinite Scroll - only active when viewing "All Lines"
  if (logPreview) {
    logPreview.addEventListener("scroll", () => {
      // Don't load more lines when viewing search results
      if (currentView !== 'all') return;
      
      if (logPreview.scrollTop + logPreview.clientHeight >= logPreview.scrollHeight - 50) {
        if (currentLogStart + 100 < totalLogLines && !isFetchingLog) {
           fetchLogLines(currentLogStart + 100, 100, true);
        }
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
  if (backToBulkMapBtn) {
    backToBulkMapBtn.addEventListener('click', () => {
      // Switch to Analysis tab
      const analysisTab = document.querySelector('.tab-btn[data-tab="analysis-tab"]');
      if (analysisTab) analysisTab.click();
      
      // Show bulk map view
      setTimeout(() => {
        showBulkMapInMain();
        // Hide notification
        backToBulkMapNotification.style.display = 'none';
      }, 100);
    });
  }
  
  if (closeBulkMapNotification) {
    closeBulkMapNotification.addEventListener('click', () => {
      backToBulkMapNotification.style.display = 'none';
    });
  }
  
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
      if (confirm(`Remove preset "${label}"?`)) {
        newTag.remove();
      }
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
  
  function renderFileList(files) {
    fileList.innerHTML = "";
    if (files.length === 0) {
      fileList.innerHTML = '<li class="placeholder-text-small">No files loaded</li>';
      return;
    }
    
    files.forEach(f => {
      const li = document.createElement("li");
      li.className = "recent-file-item" + (f.id === currentFileId ? " active" : "");
      li.dataset.fileId = f.id;
      
      // File icon SVG
      const iconSvg = document.createElement("span");
      iconSvg.innerHTML = `<svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" style="flex-shrink: 0; opacity: 0.5;">
        <path d="M14 4.5V14a2 2 0 01-2 2H4a2 2 0 01-2-2V2a2 2 0 012-2h5.5L14 4.5zm-3 0A1.5 1.5 0 019.5 3V1H4a1 1 0 00-1 1v12a1 1 0 001 1h8a1 1 0 001-1V4.5h-2z"/>
      </svg>`;
      
      const filenameSpan = document.createElement("span");
      filenameSpan.className = "recent-file-name";
      // Shorten very long filenames for display
      const displayName = f.filename.length > 25 
        ? f.filename.substring(0, 22) + '...' 
        : f.filename;
      filenameSpan.textContent = displayName;
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
      };
      
      actionsDiv.appendChild(reindexBtn);
      actionsDiv.appendChild(removeBtn);
      
      // Click to load file
      li.onclick = () => loadFile(f.id);
      
      li.appendChild(iconSvg);
      li.appendChild(filenameSpan);
      li.appendChild(linesSpan);
      li.appendChild(actionsDiv);
      fileList.appendChild(li);
    });
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
       </ul>`,
      () => {
        fileStatusDiv.textContent = `Re-indexing ${filename}...`;
        console.log('Re-indexing file:', fileId);
    
    fetch(`/api/files/${fileId}/reindex`, {
      method: "POST"
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
  function showModal(title, bodyHTML, onConfirm) {
    modalTitle.textContent = title;
    modalBody.innerHTML = bodyHTML;
    modalOverlay.style.display = 'flex';
    
    // If no confirm callback, it's just an info dialog
    if (!onConfirm) {
      modalConfirm.style.display = 'none';
      modalCancel.textContent = 'OK';
    } else {
      modalConfirm.style.display = 'block';
      modalCancel.textContent = 'Cancel';
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
          alert(`Error: ${err.message}`);
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
          fileStatusDiv.textContent = `Status: ${data.status} (${data.line_count} lines)`;
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
        updateStats(data);
        renderAnalysis(data);
      });

    // 2. Get Initial Lines
    fetchLogLines(0, 150, false);
  }
  
  // Clear all data when loading a new file
  function clearAllFileData() {
    // Clear log preview
    if (logPreview) {
      logPreview.innerHTML = '<div class="log-line">Loading...</div>';
    }
    
    // Clear stats panel
    if (statsPanel) {
      statsPanel.innerHTML = '<p class="placeholder-text">Loading file statistics...</p>';
    }
    
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
  }

  function fetchLogLines(start, limit, append) {
    if (!currentFileId || isFetchingLog) return;
    isFetchingLog = true;

    fetch(`/api/files/${currentFileId}/lines?start=${start}&limit=${limit}`)
      .then(res => res.json())
      .then(data => {
        currentLogStart = data.start;
        totalLogLines = data.total;
        loadedCountSpan.textContent = totalLogLines;
        
        renderLines(data.lines, append, data.start);
        isFetchingLog = false;
      })
      .catch(err => isFetchingLog = false);
  }
  
  // Load log lines within a specific range (for latency graph time selection)
  function loadLogLinesInRange(startLine, endLine) {
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
        
        // Update the count display to show the range
        loadedCountSpan.textContent = `${data.lines.length} of ${data.total}`;
        
        renderLines(data.lines, false, data.start);
        isFetchingLog = false;
        
        // Show notification about filtered view
        showTimeRangeNotification(startLine, endLine, data.lines.length, data.total);
      })
      .catch(err => isFetchingLog = false);
  }
  
  // Show notification that log is filtered to a time range
  function showTimeRangeNotification(startLine, endLine, loaded, total) {
    // Check if notification already exists
    let notification = document.getElementById('timeRangeNotification');
    if (!notification) {
      notification = document.createElement('div');
      notification.id = 'timeRangeNotification';
      notification.className = 'time-range-notification';
      logPreview.parentNode.insertBefore(notification, logPreview);
    }
    
    notification.innerHTML = `
      <span>📊 Showing lines ${startLine + 1} - ${endLine + 1} (${loaded} lines from selected time range)</span>
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
    searchResultsDiv.innerHTML = "Searching...";
    
    fetch(`/api/files/${currentFileId}/search?q=${encodeURIComponent(q)}&limit=50`)
      .then(res => res.json())
      .then(matches => {
        searchResultsDiv.innerHTML = "";
        if (matches.length === 0) {
          searchResultsDiv.innerHTML = '<p class="placeholder-text-small">No matches found.</p>';
          lastSearchMatches = [];
          document.getElementById('exportSearchBtn').style.display = 'none';
          return;
        }
        
        // Store matches globally for highlighting in All Lines view
        lastSearchMatches = matches;
        
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
    // Switch to "All Lines" tab first
    const logViewTabs = document.getElementById('logViewTabs');
    const allLinesTab = logViewTabs.querySelector('.log-view-tab[data-view="all"]');
    if (allLinesTab) {
      logViewTabs.querySelectorAll('.log-view-tab').forEach(t => t.classList.remove('active'));
      allLinesTab.classList.add('active');
    }
    
    // Fetch lines around the target (centered)
    const centerStart = Math.max(0, lineNum - 50);
    fetchLogLines(centerStart, 100, false);
    
    // Wait a bit for the lines to render, then highlight
    setTimeout(() => {
      const logLines = logPreview.querySelectorAll('.log-line');
      logLines.forEach(line => {
        line.classList.remove('selected-line');
        if (line.dataset.idx == lineNum) {
          line.classList.add('selected-line');
          line.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      });
    }, 500);
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
      
      // Right-click shows context menu
      div.addEventListener("contextmenu", (e) => showContextMenu(e, m.text));
      
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

  function renderLines(lines, append, startIdx) {
    if (!append) logPreview.innerHTML = "";
    
    // Extract timestamps from existing lines if appending
    let lastTimestamp = null;
    if (append && logPreview.children.length > 0) {
      const lastLine = logPreview.children[logPreview.children.length - 1];
      const tsMatch = lastLine.textContent.match(/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})/);
      if (tsMatch) {
        lastTimestamp = new Date(tsMatch[1]);
      }
    }
    
    lines.forEach((line, idx) => {
      const div = document.createElement("div");
      div.className = "log-line";
      const lineNumber = startIdx + idx + 1; // Line numbers start from 1
      div.dataset.idx = startIdx + idx;
      div.dataset.lineNumber = lineNumber;
      div.dataset.originalText = line;
      
      // Create line number span and text content
      const lineNumSpan = document.createElement("span");
      lineNumSpan.className = "line-number";
      lineNumSpan.textContent = lineNumber;
      div.appendChild(lineNumSpan);
      div.appendChild(document.createTextNode(line));
      
      // Calculate time gap
      const tsMatch = line.match(/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})/);
      if (tsMatch && lastTimestamp) {
        const currentTimestamp = new Date(tsMatch[1]);
        const timeDiff = (currentTimestamp - lastTimestamp) / 1000; // in seconds
        div.dataset.timeGap = timeDiff;
        
        // Classify gap size
        if (timeDiff < 1) {
          div.dataset.gapSize = 'small';
        } else if (timeDiff < 10) {
          div.dataset.gapSize = 'medium';
        } else {
          div.dataset.gapSize = 'large';
        }
      }
      
      if (tsMatch) {
        lastTimestamp = new Date(tsMatch[1]);
      }
      
      div.addEventListener("contextmenu", (e) => showContextMenu(e, line));
      logPreview.appendChild(div);
    });
    
    // Apply time gaps if checkbox is checked
    applyTimeGapsDisplay();
    
    // Apply search highlights if there are any active search matches
    applySearchHighlightsToAllLines();
  }

  function updateStats(data) {
    let html = `<h3>${data.filename}</h3>`;
    
    if (data.performance && data.performance.count > 0) {
       const p = data.performance;
       html += `<p>Performance Samples: ${p.count}</p>`;
       html += `<h4>Source Latency</h4><p>Avg: ${p.source.avg.toFixed(3)}s</p>`;
       html += `<h4>Target Latency</h4><p>Avg: ${p.target.avg.toFixed(3)}s</p>`;
       html += `<h4>Handling Latency</h4><p>Avg: ${p.handling.avg.toFixed(3)}s</p>`;
    } else {
        html += "<p>No performance data.</p>";
    }
    statsPanel.innerHTML = html;
    
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
      
      // Group components by name and show threads
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
          
          // Component header
          const headerDiv = document.createElement("div");
          headerDiv.className = "group-header";
          const threadCount = Object.keys(comp.threads).length;
          headerDiv.innerHTML = `<span class="expand-icon">▶</span> <strong>${comp.name}</strong> <span style="color: #9ca3af;">(${comp.totalCount} msgs, ${threadCount} threads)</span>`;
          headerDiv.onclick = () => {
              const threadList = groupDiv.querySelector('.thread-list-inner');
              const icon = headerDiv.querySelector('.expand-icon');
              const isHidden = threadList.classList.toggle('hidden');
              icon.textContent = isHidden ? '▶' : '▼';
          };
          
          groupDiv.appendChild(headerDiv);
          
          // Thread list (collapsed by default)
          const threadListInner = document.createElement("div");
          threadListInner.className = "thread-list-inner hidden";
          
          // Sort threads by count
          const sortedThreads = Object.values(comp.threads).sort((a, b) => b.count - a.count);
          
          sortedThreads.forEach(t => {
              const threadDiv = document.createElement("div");
              threadDiv.className = "thread-item";
              threadDiv.dataset.threadId = t.thread;
              threadDiv.innerHTML = `Thread ${t.thread}: ${t.count} msgs`;
              threadDiv.onclick = (e) => {
                  e.stopPropagation();
                  console.log('Loading component:', comp.name, 'Thread:', t.thread);
                  loadComponentActivity(comp.name, t.thread);
              };
              threadListInner.appendChild(threadDiv);
          });
          
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
      document.getElementById('bulkMapMainView').style.display = 'none';
      document.getElementById('bulkActivityMainView').style.display = 'none';
      document.getElementById('fileOperationsMainView').style.display = 'none';
      document.getElementById('issuesMainView').style.display = 'none';
      document.getElementById('logSummaryMainView').style.display = 'none';
      
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
      
      // Escape special regex characters in component name
      const escapedComponent = component.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      
      // Build search query - search for thread ID followed by component in brackets
      // The component name in brackets may have trailing spaces, so we match the opening bracket and component
      // Format: ^thread_id:.*\[COMPONENT
      const searchQuery = `^${thread}:.*\\[${escapedComponent}`;
      
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
                  div.textContent = m.text;
                  div.dataset.idx = m.line;
                  div.dataset.originalText = m.text; // Store for searching
                  div.style.cursor = "pointer";
                  
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
      const description = componentDescriptions[component] || 'No description available for this component.';
      
      let html = `
          <div style="padding: 10px; background: #1f2937; border-radius: 6px; margin-bottom: 10px;">
              <h4 style="margin: 0 0 10px 0; color: #3b82f6;">${component}</h4>
              ${thread ? `<p style="margin: 5px 0; font-size: 0.85rem;"><strong>Thread:</strong> ${thread}</p>` : ''}
              <p style="margin: 5px 0; font-size: 0.85rem;"><strong>Messages:</strong> ${messageCount}</p>
          </div>
          
          <div style="padding: 10px; background: #1f2937; border-radius: 6px; margin-bottom: 10px; border-left: 3px solid #6366f1;">
              <h4 style="margin: 0 0 8px 0; color: #818cf8; font-size: 0.85rem;">Component Description</h4>
              <p style="margin: 0; font-size: 0.8rem; color: #d1d5db; line-height: 1.5;">${description}</p>
              <p style="margin: 8px 0 0 0; font-size: 0.7rem; color: #9ca3af;">
                  <a href="https://help.qlik.com/en-US/replicate/November2025/Content/Replicate/Main/Replicate%20Loggers/Loggers.htm" 
                     target="_blank" 
                     style="color: #60a5fa; text-decoration: none;">
                     📖 Qlik Documentation
                  </a>
              </p>
          </div>
      `;
      
      if (taskInfo) {
          html += `
              <div style="padding: 10px; background: #1f2937; border-radius: 6px; border-left: 3px solid #10b981;">
                  <h4 style="margin: 0 0 10px 0; color: #10b981;">Task Start Info</h4>
                  <p style="margin: 5px 0; font-size: 0.85rem;"><strong>Task Name:</strong><br>${taskInfo.taskName}</p>
                  <p style="margin: 5px 0; font-size: 0.85rem;"><strong>Running Mode:</strong><br>${taskInfo.runningMode}</p>
                  <p style="margin: 5px 0; font-size: 0.85rem;"><strong>Start Mode:</strong><br><span style="color: ${taskInfo.startMode.toLowerCase().includes('resume') ? '#f59e0b' : '#10b981'}">${taskInfo.startMode}</span></p>
              </div>
          `;
      }
      
      componentInfo.innerHTML = html;
  }
  
  function renderLatencyGraph(data) {
    if (!data.performance || data.performance.count === 0) {
        document.getElementById('latencyGraph').innerHTML = '<p class="placeholder-text">No performance data available.</p>';
        return;
    }
    
    // Fetch the detailed performance data
    if (!currentFileId) return;
    
    fetch(`/api/files/${currentFileId}/performance`)
        .then(res => res.json())
        .then(perfData => {
            if (!perfData || perfData.length === 0) {
                document.getElementById('latencyGraph').innerHTML = '<p class="placeholder-text">No performance data points found.</p>';
                return;
            }
            
            const timestamps = perfData.map(p => p.timestamp);
            const sourceLatencies = perfData.map(p => p.source_latency);
            const targetLatencies = perfData.map(p => p.target_latency);
            const handlingLatencies = perfData.map(p => p.handling_latency);
            
            const traces = [
                {
                    x: timestamps,
                    y: sourceLatencies,
                    mode: 'lines+markers',
                    name: 'Source Latency',
                    line: { color: '#3b82f6' },
                    marker: { size: 4 }
                },
                {
                    x: timestamps,
                    y: targetLatencies,
                    mode: 'lines+markers',
                    name: 'Target Latency',
                    line: { color: '#10b981' },
                    marker: { size: 4 }
                },
                {
                    x: timestamps,
                    y: handlingLatencies,
                    mode: 'lines+markers',
                    name: 'Handling Latency',
                    line: { color: '#f59e0b' },
                    marker: { size: 4 }
                }
            ];
            
            const layout = {
                title: 'Latency Over Time (drag to select time range)',
                xaxis: { 
                    title: 'Timestamp',
                    type: 'date'
                },
                yaxis: { 
                    title: 'Latency (seconds)'
                },
                margin: { t: 40, r: 20, b: 60, l: 60 },
                hovermode: 'closest',
                dragmode: 'select'  // Enable box selection
            };
            
            const config = { 
                responsive: true,
                modeBarButtonsToAdd: ['select2d', 'lasso2d'],
                displayModeBar: true
            };
            
            Plotly.newPlot('latencyGraph', traces, layout, config);
            
            const graphDiv = document.getElementById('latencyGraph');
            
            // Add click handler to jump to log at that timestamp
            graphDiv.on('plotly_click', function(eventData) {
                if (eventData.points && eventData.points.length > 0) {
                    const point = eventData.points[0];
                    const pointIndex = point.pointIndex;
                    
                    // Use the line_number we now have in perfData
                    const lineNumber = perfData[pointIndex].line_number;
                    
                    console.log('Graph clicked - Point:', pointIndex, 'Line:', lineNumber);
                    
                    if (lineNumber !== undefined && lineNumber !== null) {
                        // Jump directly to the line number
                        jumpToLineAndHighlight(lineNumber, '');
                    } else {
                        console.error('No line number available for this performance data point');
                    }
                }
            });
            
            // Add selection handler to load only log lines within selected time range
            graphDiv.on('plotly_selected', function(eventData) {
                if (eventData && eventData.points && eventData.points.length > 0) {
                    // Get the min and max line numbers from selected points
                    const selectedLineNumbers = eventData.points
                        .map(p => perfData[p.pointIndex].line_number)
                        .filter(ln => ln !== undefined && ln !== null);
                    
                    if (selectedLineNumbers.length > 0) {
                        const minLine = Math.min(...selectedLineNumbers);
                        const maxLine = Math.max(...selectedLineNumbers);
                        
                        console.log('Selected time range - Lines:', minLine, 'to', maxLine);
                        
                        // Load only the lines within this range
                        loadLogLinesInRange(minLine, maxLine);
                    }
                }
            });
        })
        .catch(err => {
            console.error('Failed to load performance data:', err);
            document.getElementById('latencyGraph').innerHTML = '<p class="placeholder-text">Error loading performance data.</p>';
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
      
      // Add to Findings
      const addFindingBtn = document.getElementById("ctx-add-finding");
      addFindingBtn.onclick = () => {
          findings.push(text);
          renderFindings();
          contextMenu.style.display = "none";
      };
      
      // Highlight with color picker
      const colorDots = contextMenu.querySelectorAll('.color-dot');
      
      // Color dot click - highlight with that color
      colorDots.forEach(dot => {
          dot.onclick = (e) => {
              e.stopPropagation();
              const color = dot.getAttribute('data-color');
              currentHighlightColor = color;
              
              // Apply to both main log view and analysis thread view
              [logPreview, threadLogView].forEach(container => {
                  if (!container) return;
                  const logLines = container.querySelectorAll('.log-line');
                  logLines.forEach(line => {
                      if (line.textContent.includes(text.trim()) || (line.dataset.originalText && line.dataset.originalText.includes(text.trim()))) {
                          // Remove old color classes
                          line.classList.remove('highlight-yellow', 'highlight-green', 'highlight-blue', 
                                               'highlight-red', 'highlight-purple', 'highlight-orange');
                          // Add new color class
                          line.classList.add(`highlight-${color}`);
                      }
                  });
              });
              contextMenu.style.display = "none";
          };
      });
      
      // Clear Line Highlight - only clears highlight from the specific clicked line
      const clearLineHighlightBtn = document.getElementById("ctx-clear-line-highlight");
      clearLineHighlightBtn.onclick = () => {
          if (contextMenuTargetElement) {
              contextMenuTargetElement.classList.remove('selected-line', 'highlight-yellow', 'highlight-green', 
                                    'highlight-blue', 'highlight-red', 'highlight-purple', 'highlight-orange',
                                    'search-highlight-line');
          }
          contextMenu.style.display = "none";
      };
      
      // Clear All Highlights
      const clearHighlightBtn = document.getElementById("ctx-clear-highlight");
      clearHighlightBtn.onclick = () => {
          // Clear from both main log view and analysis thread view
          [logPreview, threadLogView].forEach(container => {
              if (!container) return;
              const logLines = container.querySelectorAll('.log-line');
              logLines.forEach(line => {
                  line.classList.remove('selected-line', 'highlight-yellow', 'highlight-green', 
                                        'highlight-blue', 'highlight-red', 'highlight-purple', 'highlight-orange',
                                        'search-highlight-line');
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

  function renderFindings() {
      findingsList.innerHTML = "";
      if (findings.length === 0) {
          findingsList.innerHTML = '<p class="placeholder-text">No findings yet. Right-click on log lines to add them.</p>';
          return;
      }
      findings.forEach((f, idx) => {
          const div = document.createElement("div");
          div.className = "finding-item";
          div.style.fontFamily = "monospace";
          div.style.fontSize = "0.75rem";
          div.textContent = f;
          
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
    
    // Log Rollover Warning
    if (props.is_rollover) {
      html += `
        <div class="property-section" style="background: #451a03; border: 1px solid #f59e0b; border-radius: 4px; padding: 8px; margin-bottom: 10px;">
          <div style="display: flex; align-items: center; gap: 6px;">
            <span style="font-size: 1.2rem;">🔄</span>
            <div>
              <div style="color: #fbbf24; font-weight: bold; font-size: 0.75rem;">Log Rollover</div>
              <div style="color: #d1d5db; font-size: 0.7rem;">This log was created from a rollover. Run mode information may not be available.</div>
            </div>
          </div>
        </div>
      `;
    }
    
    // Task Info
    if (props.task_info) {
      const info = props.task_info;
      html += `
        <div class="property-section">
          <div class="property-label">Task</div>
          <div class="property-value">${info.task_name}</div>
        </div>
        <div class="property-section">
          <div class="property-label">Version</div>
          <div class="property-value">${info.version}</div>
        </div>
        <div class="property-section">
          <div class="property-label">Host</div>
          <div class="property-value">${info.host}</div>
        </div>
        <div class="property-section">
          <div class="property-label">OS</div>
          <div class="property-value" style="font-size: 0.7rem;">${info.os_info}</div>
        </div>
        <div class="property-section">
          <div class="property-label">PID</div>
          <div class="property-value">${info.pid}</div>
        </div>
        <div class="property-section">
          <div class="property-label">Started</div>
          <div class="property-value" style="font-size: 0.7rem;">${info.start_time}</div>
        </div>
      `;
    }
    
    // Run Mode
    if (props.run_mode) {
      const mode = props.run_mode;
      const isFreshStart = mode.start_mode.toLowerCase().includes('fresh');
      const isResume = mode.start_mode.toLowerCase().includes('resume');
      const modeColor = isFreshStart ? '#10b981' : isResume ? '#f59e0b' : '#3b82f6';
      
      html += `
        <div class="property-section" style="border-top: 1px solid #374151; padding-top: 8px; margin-top: 8px;">
          <div class="property-label">Run Mode</div>
          <div class="property-value">${mode.running_mode}</div>
        </div>
        <div class="property-section">
          <div class="property-label">Start Mode</div>
          <div class="property-value" style="color: ${modeColor}; font-weight: bold;">${mode.start_mode}</div>
        </div>
      `;
    } else if (props.is_rollover) {
      // Show rollover info if no run mode found
      html += `
        <div class="property-section" style="border-top: 1px solid #374151; padding-top: 8px; margin-top: 8px;">
          <div class="property-label">Run Mode</div>
          <div class="property-value" style="color: #9ca3af; font-style: italic;">Not available (log rollover)</div>
        </div>
      `;
    }
    
    // Loggers
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
    
    if (html === '') {
      html = '<p class="placeholder-text-small">No task properties found</p>';
    }
    
    taskPropertiesContent.innerHTML = html;
  }
  
  function fetchBulkMap() {
    if (!currentFileId) return;
    
    const bulkMapLink = document.getElementById('bulkMapLink');
    const bulkMapCount = document.getElementById('bulkMapCount');
    
    if (!bulkMapLink) return;
    
    fetch(`/api/files/${currentFileId}/bulk-map?limit=500`)
      .then(res => res.json())
      .then(response => {
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
      
      // Build panel content
      let panelHTML = `
        <div class="table-summary">
          <div class="table-summary-grid" style="grid-template-columns: repeat(5, 1fr);">
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
        
        // Show back to bulk map notification
        if (backToBulkMapNotification) {
          backToBulkMapNotification.style.display = 'block';
        }
        
        // Jump to the line
        setTimeout(() => {
          jumpToLineAndHighlight(lineNum, '');
        }, 100);
      });
    });
  }
  
  // Helper to set active report link
  function setActiveReportLink(activeId) {
    const reportLinks = ['logSummaryLink', 'bulkMapLink', 'bulkActivityLink', 'fileOperationsLink', 'issuesLink'];
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
    document.getElementById('threadLogView').style.display = 'none';
    document.getElementById('bulkActivityMainView').style.display = 'none';
    document.getElementById('fileOperationsMainView').style.display = 'none';
    document.getElementById('threadActivityControls').style.display = 'none';
    document.getElementById('issuesMainView').style.display = 'none';
    document.getElementById('logSummaryMainView').style.display = 'none';
    
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
        const color = colors[insight.severity] || colors.info;
        html += `<div style="margin-bottom: 6px; padding: 6px 10px; background: #1f2937; border-left: 3px solid ${color}; border-radius: 3px; font-size: 0.7rem; display: flex; align-items: center; gap: 8px;">
          <span style="color: ${color}; font-weight: 600; white-space: nowrap;">${insight.title}:</span>
          <span style="color: #d1d5db; flex: 1;">${insight.message}</span>
          <span style="color: #10b981; cursor: help;" title="${insight.recommendation}">💡</span>
        </div>`;
      });
    }
    
    // Summary Section
    html += `
      <div class="bulk-activity-section">
        <div style="margin: 0 0 8px 0; font-size: 0.75rem; color: #fbbf24; display: flex; align-items: center; gap: 4px;">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
            <path d="M2 3a1 1 0 011-1h10a1 1 0 011 1v1a1 1 0 01-1 1H3a1 1 0 01-1-1V3zM2 7a1 1 0 011-1h10a1 1 0 011 1v1a1 1 0 01-1 1H3a1 1 0 01-1-1V7zM2 11a1 1 0 011-1h10a1 1 0 011 1v1a1 1 0 01-1 1H3a1 1 0 01-1-1v-1z"/>
          </svg>
          <span>Summary</span>
        </div>
        <div class="bulk-stats-grid">
          <div class="bulk-stat-item">
            <div class="bulk-stat-label">Total Batches</div>
            <div class="bulk-stat-value">${summary.total_batches}</div>
          </div>
          <div class="bulk-stat-item">
            <div class="bulk-stat-label">Total Changes</div>
            <div class="bulk-stat-value">${summary.total_changes.toLocaleString()}</div>
          </div>
          <div class="bulk-stat-item">
            <div class="bulk-stat-label">Total Applies</div>
            <div class="bulk-stat-value">${summary.total_applies}</div>
          </div>
          <div class="bulk-stat-item">
            <div class="bulk-stat-label">Avg Changes/Batch</div>
            <div class="bulk-stat-value">${summary.total_batches > 0 ? Math.round(summary.total_changes / summary.total_batches) : 0}</div>
          </div>
        </div>
    `;
    
    if (summary.one_by_one_switches > 0) {
      html += `
        <div class="bulk-stats-warning">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" style="color: #f59e0b;">
            <path fill-rule="evenodd" d="M8.982 1.566a1.13 1.13 0 00-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 018 5zm0 8a1 1 0 100-2 1 1 0 000 2z"/>
          </svg>
          <span style="color: #f59e0b; font-weight: bold;">One-by-One Mode</span>
          <span>${summary.one_by_one_switches} switches detected</span>
        </div>
      `;
    }
    
    if (summary.no_bulk_total > 0 || summary.no_pk_total > 0) {
      html += `<div class="bulk-stats-issues">`;
      if (summary.no_bulk_total > 0) {
        html += `<span style="color: #ef4444; display: flex; align-items: center; gap: 4px;">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
            <path fill-rule="evenodd" d="M8.982 1.566a1.13 1.13 0 00-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 018 5zm0 8a1 1 0 100-2 1 1 0 000 2z"/>
          </svg>
          ${summary.no_bulk_total} no-bulk events</span>`;
      }
      if (summary.no_pk_total > 0) {
        html += `<span style="color: #ef4444; display: flex; align-items: center; gap: 4px;">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
            <path fill-rule="evenodd" d="M8.982 1.566a1.13 1.13 0 00-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 018 5zm0 8a1 1 0 100-2 1 1 0 000 2z"/>
          </svg>
          ${summary.no_pk_total} no-PK events</span>`;
      }
      html += `</div>`;
    }
    
    // Display bulk finish reasons
    if (analysis.bulk_finish_reasons && Object.keys(analysis.bulk_finish_reasons).length > 0) {
      html += `
        <div style="margin-top: 12px; padding: 8px; background: #1f2937; border-radius: 4px;">
          <div style="font-size: 0.7rem; color: #9ca3af; margin-bottom: 6px;">Bulk Close Reasons:</div>
          <div style="display: flex; flex-wrap: wrap; gap: 8px;">
      `;
      
      const reasonLabels = {
        'MEM': { label: 'Memory limit', color: '#ef4444' },
        'TIM': { label: 'Stream timeout', color: '#f59e0b' },
        'TMO': { label: 'Bulk timeout', color: '#f59e0b' },
        'RES': { label: 'Resume', color: '#3b82f6' },
        'SNG': { label: 'Single table', color: '#10b981' },
        'PKi': { label: 'PK insert conflict', color: '#8b5cf6' },
        'PKu': { label: 'PK update conflict', color: '#8b5cf6' },
        'PKd': { label: 'PK delete conflict', color: '#8b5cf6' },
        'Normal': { label: 'Normal', color: '#10b981' }
      };
      
      for (const [reason, count] of Object.entries(analysis.bulk_finish_reasons)) {
        const info = reasonLabels[reason] || { label: reason, color: '#9ca3af' };
        html += `
          <span style="display: inline-flex; align-items: center; gap: 4px; padding: 4px 8px; background: #111827; border-radius: 3px; font-size: 0.65rem;">
            <span style="color: ${info.color}; font-weight: bold;">${reason}</span>
            <span style="color: #9ca3af;">${info.label}:</span>
            <span style="color: #e5e7eb; font-weight: bold;">${count}</span>
          </span>
        `;
      }
      
      html += `</div></div>`;
    }
    
    // Display file operations statistics
    if (summary.file_operations_count && summary.file_operations_count > 0) {
      const avgCompressTime = summary.file_compress_time_total / summary.file_operations_count;
      const avgUploadTime = summary.file_upload_time_total / summary.file_operations_count;
      
      html += `
        <div style="margin-top: 12px; padding: 8px; background: #1f2937; border-radius: 4px;">
          <div style="font-size: 0.7rem; color: #9ca3af; margin-bottom: 6px;">File Operations (${summary.file_operations_count} files):</div>
          <div style="display: flex; gap: 16px; flex-wrap: wrap;">
            <span style="font-size: 0.65rem;">
              <span style="color: #9ca3af;">Avg Compress:</span>
              <span style="color: #3b82f6; font-weight: bold; margin-left: 4px;">${avgCompressTime.toFixed(2)}s</span>
            </span>
            <span style="font-size: 0.65rem;">
              <span style="color: #9ca3af;">Avg Upload:</span>
              <span style="color: #10b981; font-weight: bold; margin-left: 4px;">${avgUploadTime.toFixed(2)}s</span>
            </span>
            <span style="font-size: 0.65rem;">
              <span style="color: #9ca3af;">Total Time:</span>
              <span style="color: #e5e7eb; font-weight: bold; margin-left: 4px;">${(summary.file_compress_time_total + summary.file_upload_time_total).toFixed(2)}s</span>
            </span>
          </div>
        </div>
      `;
    }
    
    html += `</div>`;
    
    // Batches Section
    if (analysis.batches && analysis.batches.length > 0) {
      html += `
        <div class="bulk-activity-section">
          <div style="margin: 0 0 8px 0; font-size: 0.75rem; color: #10b981; display: flex; align-items: center; gap: 4px;">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
              <path d="M3.5 0a.5.5 0 01.5.5V1h8V.5a.5.5 0 011 0V1h1a2 2 0 012 2v11a2 2 0 01-2 2H2a2 2 0 01-2-2V3a2 2 0 012-2h1V.5a.5.5 0 01.5-.5zM2 2a1 1 0 00-1 1v1h14V3a1 1 0 00-1-1H2zm13 3H1v9a1 1 0 001 1h12a1 1 0 001-1V5z"/>
            </svg>
            <span>Batch Details (${analysis.batches.length})</span>
          </div>
          <table class="bulk-activity-table">
            <thead>
              <tr>
                <th style="width: 8%;">#</th>
                <th style="width: 18%;">Start Time</th>
                <th style="width: 12%;">Changes</th>
                <th style="width: 10%;">Applies</th>
                <th style="width: 15%;">Reason</th>
                <th>Tables</th>
              </tr>
            </thead>
            <tbody>
      `;
      
      analysis.batches.slice(0, 50).forEach((batch, idx) => {
        const reasonClass = batch.finish_reason === 'Normal' ? 'normal' : 
                           batch.finish_reason.includes('timeout') ? 'timeout' : 'memory';
        
        html += `
          <tr>
            <td style="color: #9ca3af;">${idx + 1}</td>
            <td style="font-family: monospace; color: #9ca3af;">${batch.start_time || 'N/A'}</td>
            <td>${batch.changes.toLocaleString()}</td>
            <td>${batch.applies}</td>
            <td><span class="batch-reason-badge batch-reason-${reasonClass}">${batch.finish_reason}</span></td>
            <td style="font-size: 0.65rem; color: #9ca3af;">${batch.tables.length > 0 ? batch.tables.slice(0, 2).join(', ') + (batch.tables.length > 2 ? ` +${batch.tables.length - 2}` : '') : 'N/A'}</td>
          </tr>
        `;
      });
      
      html += `
            </tbody>
          </table>
      `;
      
      if (analysis.batches.length > 50) {
        html += `<p style="text-align: center; color: #9ca3af; font-size: 0.7rem; margin: 8px 0;">Showing 50 of ${analysis.batches.length} batches</p>`;
      }
      
      html += `</div>`;
    }
    
    // One-by-One Section
    if (analysis.one_by_one && analysis.one_by_one.length > 0) {
      html += `
        <div class="bulk-activity-section">
          <div style="margin: 0 0 8px 0; font-size: 0.75rem; color: #f59e0b; display: flex; align-items: center; gap: 4px;">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
              <path fill-rule="evenodd" d="M8.982 1.566a1.13 1.13 0 00-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 018 5zm0 8a1 1 0 100-2 1 1 0 000 2z"/>
            </svg>
            <span>One-by-One Applies (${analysis.one_by_one.length})</span>
          </div>
          <table class="bulk-activity-table">
            <thead>
              <tr>
                <th style="width: 35%;">Table</th>
                <th style="width: 25%;">Start Time</th>
                <th style="width: 25%;">End Time</th>
                <th style="width: 15%;">Failed</th>
              </tr>
            </thead>
            <tbody>
      `;
      
      analysis.one_by_one.forEach(obo => {
        html += `
          <tr>
            <td style="font-family: monospace; color: #fbbf24;">${obo.table}</td>
            <td style="color: #9ca3af; font-family: monospace;">${obo.start_time || 'N/A'}</td>
            <td style="color: #9ca3af; font-family: monospace;">${obo.end_time || 'N/A'}</td>
            <td style="color: ${obo.failed_executions > 0 ? '#ef4444' : '#10b981'};">${obo.failed_executions}</td>
          </tr>
        `;
      });
      
      html += `</tbody></table></div>`;
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
      header.style.margin = '0 0 8px 0';
      header.style.fontSize = '0.75rem';
      header.style.color = '#3b82f6';
      header.style.display = 'flex';
      header.style.alignItems = 'center';
      header.style.gap = '4px';
      header.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
          <path d="M2 4a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V4zm2-1a1 1 0 00-1 1v1h10V4a1 1 0 00-1-1H4zM3 7v5a1 1 0 001 1h8a1 1 0 001-1V7H3z"/>
        </svg>
        <span>Table Details</span>
      `;
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
        tabButton.innerHTML = `
          ${stat.table.split('.')[1] || stat.table}
          <span class="ba-tab-count">${operationsCount.toLocaleString()}</span>
        `;
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
        
        // Build panel content
        let panelHTML = `
          <div class="table-summary">
            <div class="table-summary-grid" style="grid-template-columns: repeat(5, 1fr);">
              <div class="table-summary-stat">
                <div class="table-summary-stat-label">INSERT</div>
                <div class="table-summary-stat-value" style="color: #10b981;">${operationCounts.INSERT.toLocaleString()}</div>
              </div>
              <div class="table-summary-stat">
                <div class="table-summary-stat-label">UPDATE</div>
                <div class="table-summary-stat-value" style="color: #3b82f6;">${operationCounts.UPDATE.toLocaleString()}</div>
              </div>
              <div class="table-summary-stat">
                <div class="table-summary-stat-label">DELETE</div>
                <div class="table-summary-stat-value" style="color: #ef4444;">${operationCounts.DELETE.toLocaleString()}</div>
              </div>
              <div class="table-summary-stat">
                <div class="table-summary-stat-label">SINGLE (1:1)</div>
                <div class="table-summary-stat-value" style="color: #fbbf24; font-weight: bold;">${singleRecordCount.toLocaleString()}</div>
              </div>
              <div class="table-summary-stat">
                <div class="table-summary-stat-label">TOTAL</div>
                <div class="table-summary-stat-value" style="color: #e5e7eb; font-weight: bold;">${(operationCounts.INSERT + operationCounts.UPDATE + operationCounts.DELETE + operationCounts.MERGE).toLocaleString()}</div>
              </div>
            </div>
          </div>
        `;
        
        if (bulkMapForTable.length > 0) {
          panelHTML += `
            <div style="margin: 8px 0 6px 0; font-size: 0.7rem; color: #10b981; display: flex; align-items: center; gap: 4px;">
              <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
                <path d="M2 3a1 1 0 011-1h10a1 1 0 011 1v10a1 1 0 01-1 1H3a1 1 0 01-1-1V3zm2 1v2h2V4H4zm3 0v2h2V4H7zm3 0v2h2V4h-2zM4 7v2h2V7H4zm3 0v2h2V7H7zm3 0v2h2V7h-2zM4 10v2h2v-2H4zm3 0v2h2v-2H7zm3 0v2h2v-2h-2z"/>
              </svg>
              <span>Bulk Map Operations (${bulkMapForTable.length})</span>
            </div>
            <table class="bulk-activity-table">
              <thead>
                <tr>
                  <th style="width: 20%;">Sequence</th>
                  <th style="width: 10%;">Records</th>
                  <th style="width: 13%;">Operation</th>
                  <th style="width: 16%;">Time</th>
                  <th style="width: 10%;">Gap</th>
                  <th style="width: 10%;">RPS</th>
                  <th style="width: 21%;">Line</th>
                </tr>
              </thead>
              <tbody>
          `;
          
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
        
        // Show back to bulk map notification
        if (backToBulkMapNotification) {
          backToBulkMapNotification.style.display = 'block';
        }
        
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
    document.getElementById('threadLogView').style.display = 'none';
    document.getElementById('bulkMapMainView').style.display = 'none';
    document.getElementById('fileOperationsMainView').style.display = 'none';
    document.getElementById('threadActivityControls').style.display = 'none';
    document.getElementById('issuesMainView').style.display = 'none';
    document.getElementById('logSummaryMainView').style.display = 'none';
    
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
    document.getElementById('threadLogView').style.display = 'none';
    document.getElementById('bulkMapMainView').style.display = 'none';
    document.getElementById('bulkActivityMainView').style.display = 'none';
    document.getElementById('threadActivityControls').style.display = 'none';
    document.getElementById('issuesMainView').style.display = 'none';
    document.getElementById('logSummaryMainView').style.display = 'none';
    
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
    
    fetch(`/api/files/${currentFileId}/issues`)
      .then(res => res.json())
      .then(data => {
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
      });
  }
  
  // Show issues in main view
  window.showIssuesInMain = function() {
    // Hide ALL other views
    document.getElementById('threadLogView').style.display = 'none';
    document.getElementById('threadActivityControls').style.display = 'none';
    document.getElementById('bulkMapMainView').style.display = 'none';
    document.getElementById('bulkActivityMainView').style.display = 'none';
    document.getElementById('fileOperationsMainView').style.display = 'none';
    document.getElementById('logSummaryMainView').style.display = 'none';
    
    // Show issues view (uses flexbox layout)
    document.getElementById('issuesMainView').style.display = 'flex';
    
    // Set active report link
    setActiveReportLink('issuesLink');
    
    if (window.issuesData) {
      renderIssues(window.issuesData);
    }
  };
  
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
                   onclick="scrollToIssueByLine(${evt.line_number})"
                   title="${evt.severity.toUpperCase()} at ${formatTimelineTime(evt.timestamp)}">
              </div>
            `).join('')}
          </div>
          <span class="timeline-time">${formatTimelineTime(endTime)}</span>
        </div>
      `;
    }
    
    let html = `
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
      
      html += `
        <div class="issue-group" id="${groupId}">
          <div class="issue-group-header" onclick="toggleIssueGroup('${groupId}')">
            <svg class="issue-expand-icon" width="8" height="8" viewBox="0 0 16 16" fill="currentColor">
              <path fill-rule="evenodd" d="M4.646 1.646a.5.5 0 01.708 0l6 6a.5.5 0 010 .708l-6 6a.5.5 0 01-.708-.708L10.293 8 4.646 2.354a.5.5 0 010-.708z"/>
            </svg>
            <span class="issue-severity-badge ${issue.severity}">${issue.severity}</span>
            <span class="issue-component">[${issue.component}]</span>
            <span class="issue-message" title="${escapeHtml(issue.message_summary)}">${escapeHtml(issue.message_summary)}</span>
            <span class="issue-timestamp">${formatTimelineTime(firstTimestamp)}</span>
            <span class="issue-count">${issue.occurrences.length}x</span>
          </div>
          <div class="issue-group-content">
      `;
      
      // Show first 5 occurrences
      issue.occurrences.slice(0, 5).forEach(occ => {
        const severityClass = issue.severity === 'warning' ? 'warning-line' : 'error-line';
        
        html += `
          <div class="issue-occurrence">
            ${occ.timestamp ? `<div class="occurrence-time">${occ.timestamp}</div>` : ''}
        `;
        
        // Before context
        occ.before.forEach(ctx => {
          html += `<div class="issue-context-line before"><span class="issue-line-number">${ctx.line + 1}</span>${escapeHtml(ctx.text)}</div>`;
        });
        
        // The issue line itself - with severity-based styling
        html += `<div class="issue-context-line issue-line ${severityClass}"><span class="issue-line-number">${occ.line_number + 1}</span>${escapeHtml(occ.text)}</div>`;
        
        // After context
        occ.after.forEach(ctx => {
          html += `<div class="issue-context-line after"><span class="issue-line-number">${ctx.line + 1}</span>${escapeHtml(ctx.text)}</div>`;
        });
        
        html += `</div>`;
      });
      
      if (issue.occurrences.length > 5) {
        html += `<p style="text-align: center; color: #6b7280; font-size: 0.7rem; margin: 8px 0;">... and ${issue.occurrences.length - 5} more occurrences</p>`;
      }
      
      // Add Google search button for error codes
      if (issue.error_code) {
        html += `
          <button class="issue-google-btn" onclick="window.open('https://www.google.com/search?q=' + encodeURIComponent('${issue.error_code}'), '_blank')">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
              <path d="M11.742 10.344a6.5 6.5 0 10-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 001.415-1.414l-3.85-3.85a1.007 1.007 0 00-.115-.1zM12 6.5a5.5 5.5 0 11-11 0 5.5 5.5 0 0111 0z"/>
            </svg>
            Google: ${issue.error_code}
          </button>
        `;
      }
      
      html += `
          </div>
        </div>
      `;
    });
    
    html += `</div>`;
    issuesContent.innerHTML = html;
  }
  
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
    if (group) {
      group.classList.toggle('expanded');
    }
  };
  
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
  window.scrollToIssueByLine = function(lineNumber) {
    if (!window.issuesData || !window.issuesData.issues) return;
    
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
        // Expand the group
        group.classList.add('expanded');
        
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
    if (!summaryLink) return;
    
    fetch(`/api/files/${currentFileId}/log-summary`)
      .then(res => res.json())
      .then(data => {
        summaryLink.style.display = 'flex';
        window.logSummaryData = data;
      })
      .catch(err => {
        console.error('Failed to load log summary:', err);
        summaryLink.style.display = 'none';
      });
  }
  
  // Show log summary in main view
  window.showLogSummaryInMain = function() {
    // Hide ALL other views
    document.getElementById('threadLogView').style.display = 'none';
    document.getElementById('threadActivityControls').style.display = 'none';
    document.getElementById('bulkMapMainView').style.display = 'none';
    document.getElementById('bulkActivityMainView').style.display = 'none';
    document.getElementById('fileOperationsMainView').style.display = 'none';
    document.getElementById('issuesMainView').style.display = 'none';
    
    // Show log summary view
    document.getElementById('logSummaryMainView').style.display = 'block';
    
    // Set active report link
    setActiveReportLink('logSummaryLink');
    
    if (window.logSummaryData) {
      renderLogSummary(window.logSummaryData);
    }
  };
  
  function renderLogSummary(data) {
    const summaryContent = document.getElementById('logSummaryMainContent');
    if (!summaryContent) return;
    
    let html = `
      <div class="log-summary-section" id="logSummarySection">
        <div class="summary-header-row">
          <div class="summary-title">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" style="color: #8b5cf6;">
              <path d="M2 2a2 2 0 012-2h8a2 2 0 012 2v12a2 2 0 01-2 2H4a2 2 0 01-2-2V2zm2-1a1 1 0 00-1 1v12a1 1 0 001 1h8a1 1 0 001-1V2a1 1 0 00-1-1H4z"/>
              <path d="M5 4h6v1H5V4zm0 2h6v1H5V6zm0 2h6v1H5V8zm0 2h4v1H5v-1z"/>
            </svg>
            <span>Log Summary</span>
          </div>
          <div class="font-size-controls">
            <button class="font-size-btn" onclick="adjustFontSize('summary', -1)" title="Decrease font size">A-</button>
            <button class="font-size-btn" onclick="adjustFontSize('summary', 1)" title="Increase font size">A+</button>
          </div>
        </div>
        
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
            <div class="summary-card-title">Server</div>
            <div class="summary-card-value">${data.server || 'N/A'}</div>
          </div>
          <div class="summary-card">
            <div class="summary-card-title">Duration</div>
            <div class="summary-card-value">${data.duration || 'N/A'}</div>
          </div>
        </div>
        
        <div class="summary-grid">
          <div class="summary-card">
            <div class="summary-card-title">Running Mode</div>
            <div class="summary-card-value">${data.running_mode || 'N/A'}</div>
          </div>
          <div class="summary-card">
            <div class="summary-card-title">Start Mode</div>
            <div class="summary-card-value ${data.start_mode?.toLowerCase().includes('resume') ? 'warning' : ''}">${data.start_mode || 'N/A'}</div>
          </div>
          <div class="summary-card">
            <div class="summary-card-title">Source Endpoint</div>
            <div class="summary-card-value">${data.source_endpoint || 'N/A'}</div>
          </div>
          <div class="summary-card">
            <div class="summary-card-title">Target Endpoint</div>
            <div class="summary-card-value">${data.target_endpoint || 'N/A'}</div>
          </div>
        </div>
        
        <div class="summary-grid">
          <div class="summary-card">
            <div class="summary-card-title">Tables Count</div>
            <div class="summary-card-value highlight">${data.tables_count}</div>
          </div>
          <div class="summary-card">
            <div class="summary-card-title">Errors</div>
            <div class="summary-card-value ${data.error_count > 0 ? 'error' : 'success'}">${data.error_count}</div>
          </div>
          <div class="summary-card">
            <div class="summary-card-title">Warnings</div>
            <div class="summary-card-value ${data.warning_count > 0 ? 'warning' : 'success'}">${data.warning_count}</div>
          </div>
          <div class="summary-card">
            <div class="summary-card-title">Bulk Operations</div>
            <div class="summary-card-value">${data.bulk_operations}</div>
          </div>
        </div>
    `;
    
    // Status indicators
    html += `
      <div style="margin: 8px 0; display: flex; gap: 8px; flex-wrap: wrap;">
        <div style="display: flex; align-items: center; gap: 4px; padding: 4px 8px; background: ${data.full_load_completed ? '#064e3b' : '#1f2937'}; border-radius: 3px;">
          <svg width="12" height="12" viewBox="0 0 16 16" fill="${data.full_load_completed ? '#10b981' : '#6b7280'}">
            ${data.full_load_completed ? '<path d="M16 8A8 8 0 110 8a8 8 0 0116 0zm-3.97-3.03a.75.75 0 00-1.08.022L7.477 9.417 5.384 7.323a.75.75 0 00-1.06 1.06L6.97 11.03a.75.75 0 001.079-.02l3.992-4.99a.75.75 0 00-.01-1.05z"/>' : '<path d="M8 15A7 7 0 118 1a7 7 0 010 14zm0 1A8 8 0 108 0a8 8 0 000 16z"/>'}
          </svg>
          <span style="font-size: 0.65rem; color: ${data.full_load_completed ? '#10b981' : '#6b7280'};">Full Load ${data.full_load_completed ? 'Completed' : 'Not Completed'}</span>
        </div>
        <div style="display: flex; align-items: center; gap: 4px; padding: 4px 8px; background: ${data.cdc_started ? '#064e3b' : '#1f2937'}; border-radius: 3px;">
          <svg width="12" height="12" viewBox="0 0 16 16" fill="${data.cdc_started ? '#10b981' : '#6b7280'}">
            ${data.cdc_started ? '<path d="M16 8A8 8 0 110 8a8 8 0 0116 0zm-3.97-3.03a.75.75 0 00-1.08.022L7.477 9.417 5.384 7.323a.75.75 0 00-1.06 1.06L6.97 11.03a.75.75 0 001.079-.02l3.992-4.99a.75.75 0 00-.01-1.05z"/>' : '<path d="M8 15A7 7 0 118 1a7 7 0 010 14zm0 1A8 8 0 108 0a8 8 0 000 16z"/>'}
          </svg>
          <span style="font-size: 0.65rem; color: ${data.cdc_started ? '#10b981' : '#6b7280'};">CDC ${data.cdc_started ? 'Started' : 'Not Started'}</span>
        </div>
      </div>
    `;
    
    // Incomplete log warning (no "Closing log file" found)
    if (data.incomplete_log_warning) {
      html += `
        <div style="padding: 8px; background: rgba(245, 158, 11, 0.2); border: 1px solid #f59e0b; border-radius: 4px; margin: 8px 0;">
          <div style="display: flex; align-items: center; gap: 6px;">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="#f59e0b">
              <path d="M8.982 1.566a1.13 1.13 0 00-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 018 5zm0 8a1 1 0 100-2 1 1 0 000 2z"/>
            </svg>
            <span style="font-weight: bold; font-size: 0.7rem; color: #fcd34d;">⚠ Incomplete Log</span>
          </div>
          <div style="font-size: 0.65rem; color: #fcd34d; margin-top: 4px;">${data.incomplete_log_warning}</div>
        </div>
      `;
    }
    
    // Fatal error
    if (data.fatal_error) {
      html += `
        <div style="padding: 8px; background: rgba(220, 38, 38, 0.2); border: 1px solid #dc2626; border-radius: 4px; margin: 8px 0;">
          <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="#dc2626">
              <path d="M8.982 1.566a1.13 1.13 0 00-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 018 5zm0 8a1 1 0 100-2 1 1 0 000 2z"/>
            </svg>
            <span style="font-weight: bold; font-size: 0.7rem; color: #fca5a5;">Fatal Error Detected</span>
          </div>
          <div style="font-family: monospace; font-size: 0.6rem; color: #fca5a5; word-break: break-all;">${escapeHtml(data.fatal_error)}</div>
        </div>
      `;
    }
    
    // Key Events
    if (data.key_events && data.key_events.length > 0) {
      html += `
        <div class="key-events-list">
          <h4 style="margin: 0 0 6px 0; font-size: 0.7rem; color: #9ca3af;">Key Events</h4>
      `;
      
      data.key_events.forEach(event => {
        html += `
          <div class="key-event">
            <span class="key-event-line">Line ${event.line + 1}</span>
            <span class="key-event-name">${event.event}</span>
          </div>
        `;
      });
      
      html += `</div>`;
    }
    
    // Log Levels Changed
    if (data.log_levels_changed && data.log_levels_changed.length > 0) {
      html += `
        <div style="margin-top: 8px;">
          <h4 style="margin: 0 0 6px 0; font-size: 0.7rem; color: #9ca3af;">Log Levels Changed</h4>
          <div style="display: flex; flex-wrap: wrap; gap: 4px;">
      `;
      
      data.log_levels_changed.forEach(level => {
        html += `
          <span style="padding: 2px 6px; background: #1f2937; border-radius: 3px; font-size: 0.6rem;">
            <span style="color: #60a5fa;">${level.component}</span>: 
            <span style="color: #6b7280;">${level.from}</span> → 
            <span style="color: #fbbf24;">${level.to}</span>
          </span>
        `;
      });
      
      html += `</div></div>`;
    }
    
    html += `</div>`;
    summaryContent.innerHTML = html;
  }
  
  // Initialize floating export button
  const floatingExportBtn = document.getElementById('floatingExportBtn');
  if (floatingExportBtn) {
    floatingExportBtn.addEventListener('click', exportSearchResults);
  }

});
