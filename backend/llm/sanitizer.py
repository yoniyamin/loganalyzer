"""
PII Sanitization Module for Log Analysis

Uses Presidio for robust PII detection and anonymization.
Provides custom recognizers for log-specific patterns like hostnames,
UNC paths, connection strings, and license information.

This module centralizes all sanitization logic, replacing the duplicated
regex-based sanitization in vectorstore.py and prompts.py.

IMPORTANT DESIGN NOTE:
======================
This sanitizer is intended ONLY for user log data, NOT for KB (Knowledge Base) 
articles. KB articles are documentation/help content and should NOT be sanitized.

Sanitization is applied:
- When embedding log summaries, errors, and anomalies (vectorstore.py)
- When building prompts for LLM analysis (prompts.py)

Sanitization is NOT applied:
- When embedding KB articles (kb-assistant/embedder.py)
- When querying KB articles (vectorstore.query_kb())

LAZY LOADING: Presidio and spaCy are imported on first use (get_sanitizer())
to avoid slow startup when the app loads. The UI appears quickly; NLP loads
when the user first uses AI/PII features.
"""
from __future__ import annotations

import re
import logging
import sys
import warnings
from typing import List, Dict, Any, Optional, Tuple

# Suppress Presidio's verbose warnings (set early; presidio loads later)
logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=UserWarning, module="presidio_analyzer")

# Presidio/spaCy imports are deferred to _ensure_presidio_loaded() for fast app startup


# =============================================================================
# Custom Entity Types for Log Analysis
# =============================================================================

# Entity types we detect
LOG_ENTITIES = [
    # Built-in Presidio recognizers (with dedicated recognizers)
    "IP_ADDRESS",           # Built-in Presidio
    "EMAIL_ADDRESS",        # Built-in Presidio
    "URL",                  # Built-in Presidio
    "PHONE_NUMBER",         # Built-in Presidio - Phone numbers
    "PERSON",               # SpaCy NER via Presidio's SpacyRecognizer
    "NRP",                  # SpaCy NER - Nationalities, religious, political groups
    # NOTE: DATE_TIME removed - timestamps in logs are not PII and are important for analysis
    
    # Custom recognizers for log-specific patterns
    "HOST_AFTER_VERSION",   # Host right after version token in Task Server log header
    "CONNECTION_HOST",      # Host values inside connection strings (SYSTEM/HOST/SERVER/Data Source)
    "CONNECTION_PASSWORD",  # Password values inside connection strings
    "HOSTNAME",             # Custom - FQDN patterns
    "UNC_PATH",             # Custom - Windows UNC paths
    "CONNECTION_STRING",    # Custom - UID=, SERVER=, HOST= values
    "LICENSE_INFO",         # Custom - "Licensed to [Company]"
    "WINDOWS_PATH",         # Custom - Sensitive file paths
    "CLOUD_RESOURCE",       # Custom - Azure/AWS/GCP identifiers
    "HTTP_PATH",            # Custom - HTTPPath and similar
    "TASK_SERVER_INFO",     # Custom - Task Server Log header info
    "REVISION_HASH",        # Custom - Git revision hashes
]

# Terms that SpaCy may incorrectly identify as PERSON or other entities
# These are technical terms common in Qlik Replicate logs
DENYLIST_PATTERNS = [
    # ODBC/SQL error codes and terms
    r"\bHY\d+\b",           # ODBC error codes like HY000
    r"\bNativeError\b",
    r"\bSQLSTATE\b",
    r"\bORA-\d+\b",         # Oracle errors
    r"\bSQL\d+\b",          # SQL errors
    r"\bATT-\d+\b",         # Attunity/Qlik errors
    
    # Common log terms that may be misidentified
    r"\bTarget\s+Load\b",
    r"\bSource\s+Capture\b",
    r"\bFull\s+Load\b",
    r"\bChange\s+Processing\b",
    r"\bApply\s+Changes\b",
    
    # Task names and components
    r"\b[A-Z][a-z]+Task\b",
    r"\b[A-Z][a-z]+Manager\b",
    r"\b[A-Z][a-z]+Handler\b",
    r"\b[A-Z][a-z]+Processor\b",
    r"\b[A-Z][a-z]+Service\b",
    
    # Table names in format SCHEMA.TABLE
    r"\b[A-Z_]+\.[A-Z_]+\b",
]

# Anonymization operators - populated by _ensure_presidio_loaded()
ANONYMIZATION_OPERATORS: Dict[str, Any] = {}

# Human-readable descriptions for each entity type (for preview UI)
ENTITY_DESCRIPTIONS = {
    # Built-in Presidio recognizers
    "IP_ADDRESS": "IP Address",
    "EMAIL_ADDRESS": "Email Address",
    "URL": "URL",
    "PHONE_NUMBER": "Phone Number",
    # DATE_TIME removed - timestamps are important for log analysis
    
    # SpaCy NER entities (second protection layer)
    "PERSON": "Person Name (SpaCy NER)",
    "NRP": "Group/Nationality (SpaCy NER)",
    
    # Custom recognizers
    "HOST_AFTER_VERSION": "Host in Task Server header",
    "CONNECTION_HOST": "Host in connection string",
    "CONNECTION_PASSWORD": "Password in connection string",
    "HOSTNAME": "Server/Hostname",
    "UNC_PATH": "Network Path (UNC)",
    "CONNECTION_STRING": "Connection String",
    "LICENSE_INFO": "License/Company Info",
    "WINDOWS_PATH": "File Path",
    "CLOUD_RESOURCE": "Cloud Resource ID",
    "HTTP_PATH": "HTTP Path",
    "TASK_SERVER_INFO": "Task Server Info",
    "REVISION_HASH": "Revision Hash",
}


# =============================================================================
# Lazy Presidio/spaCy Loader (for fast app startup)
# =============================================================================

def _ensure_presidio_loaded() -> None:
    """
    Load Presidio and spaCy on first use. Injects classes into module namespace
    so create_*_recognizer() and LogSanitizer can use them.
    """
    mod = sys.modules[__name__]
    if getattr(mod, "_presidio_loaded", False):
        return
    from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_anonymizer import AnonymizerEngine
    from presidio_anonymizer.entities import OperatorConfig

    mod.AnalyzerEngine = AnalyzerEngine
    mod.PatternRecognizer = PatternRecognizer
    mod.Pattern = Pattern
    mod.NlpEngineProvider = NlpEngineProvider
    mod.AnonymizerEngine = AnonymizerEngine
    mod.OperatorConfig = OperatorConfig

    # Build ANONYMIZATION_OPERATORS (uses OperatorConfig)
    mod.ANONYMIZATION_OPERATORS = {
        "IP_ADDRESS": OperatorConfig("replace", {"new_value": "[IP_ADDRESS]"}),
        "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[EMAIL]"}),
        "URL": OperatorConfig("replace", {"new_value": "[URL]"}),
        "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[PHONE]"}),
        "PERSON": OperatorConfig("replace", {"new_value": "[PERSON]"}),
        "NRP": OperatorConfig("replace", {"new_value": "[GROUP]"}),
        "HOST_AFTER_VERSION": OperatorConfig("replace", {"new_value": "[HOST]"}),
        "CONNECTION_HOST": OperatorConfig("replace", {"new_value": "[HOST]"}),
        "CONNECTION_PASSWORD": OperatorConfig("replace", {"new_value": "[PASSWORD]"}),
        "HOSTNAME": OperatorConfig("replace", {"new_value": "[HOSTNAME]"}),
        "UNC_PATH": OperatorConfig("replace", {"new_value": "[UNC_PATH]"}),
        "CONNECTION_STRING": OperatorConfig("replace", {"new_value": "[REDACTED]"}),
        "LICENSE_INFO": OperatorConfig("replace", {"new_value": "[COMPANY_NAME]"}),
        "WINDOWS_PATH": OperatorConfig("replace", {"new_value": "[PATH]"}),
        "CLOUD_RESOURCE": OperatorConfig("replace", {"new_value": "[CLOUD_RESOURCE]"}),
        "HTTP_PATH": OperatorConfig("replace", {"new_value": "[REDACTED]"}),
        "TASK_SERVER_INFO": OperatorConfig("replace", {"new_value": "[SERVER_INFO]"}),
        "REVISION_HASH": OperatorConfig("replace", {"new_value": "[REVISION]"}),
    }
    mod._presidio_loaded = True


# =============================================================================
# Custom Recognizers for Log-Specific Patterns
# =============================================================================

def create_hostname_recognizer() -> "PatternRecognizer":
    """
    Recognizer for fully qualified domain names (FQDNs).
    Matches patterns like: server.domain.com, HSP-DBM-APP05.cs.sbsit.eu
    """
    patterns = [
        Pattern(
            name="fqdn_pattern",
            regex=r"\b([A-Za-z0-9][-A-Za-z0-9]*\.)+[A-Za-z]{2,}\b",
            score=0.7
        ),
    ]
    return PatternRecognizer(
        supported_entity="HOSTNAME",
        patterns=patterns,
        name="HostnameRecognizer",
        supported_language="en"
    )


def create_unc_path_recognizer() -> "PatternRecognizer":
    """
    Recognizer for Windows UNC paths.
    Matches patterns like: \\\\server\\share\\folder
    """
    patterns = [
        Pattern(
            name="unc_path_pattern",
            regex=r"\\\\[^\s\\]+\\[^\s]*",
            score=0.9
        ),
    ]
    return PatternRecognizer(
        supported_entity="UNC_PATH",
        patterns=patterns,
        name="UNCPathRecognizer",
        supported_language="en"
    )


def create_connection_string_recognizer() -> "PatternRecognizer":
    """
    Recognizer for connection string sensitive values.
    Matches: UID=value, SERVER=value, HOST=value, Data Source=value, SYSTEM=value
    """
    patterns = [
        Pattern(
            name="uid_pattern",
            regex=r"UID=([^;]+)",
            score=0.85
        ),
        Pattern(
            name="server_pattern",
            regex=r"(?:SERVER|HOST|SYSTEM|Data Source)=([^;]+)",
            score=0.85
        ),
    ]
    return PatternRecognizer(
        supported_entity="CONNECTION_STRING",
        patterns=patterns,
        name="ConnectionStringRecognizer",
        supported_language="en"
    )


def create_connection_host_recognizer() -> "PatternRecognizer":
    """
    Recognizer to capture only host values inside connection strings,
    preserving keys like SYSTEM=/HOST=/SERVER=/Data Source=
    """
    patterns = [
        Pattern(
            name="system_host_value",
            regex=r"(?<=SYSTEM=)[^;]+",
            score=0.9
        ),
        Pattern(
            name="server_host_value",
            regex=r"(?<=SERVER=)[^;]+",
            score=0.9
        ),
        Pattern(
            name="host_host_value",
            regex=r"(?<=HOST=)[^;]+",
            score=0.9
        ),
        Pattern(
            name="datasource_host_value",
            regex=r"(?<=Data Source=)[^;]+",
            score=0.9
        ),
    ]
    return PatternRecognizer(
        supported_entity="CONNECTION_HOST",
        patterns=patterns,
        name="ConnectionHostValueRecognizer",
        supported_language="en"
    )


def create_connection_password_recognizer() -> "PatternRecognizer":
    """
    Recognizer to capture password values inside connection strings (PWD= or PASSWORD=).
    """
    patterns = [
        Pattern(
            name="pwd_value",
            regex=r"(?<=PWD=)[^;]+",
            score=0.9
        ),
        Pattern(
            name="password_value",
            regex=r"(?<=PASSWORD=)[^;]+",
            score=0.9
        ),
    ]
    return PatternRecognizer(
        supported_entity="CONNECTION_PASSWORD",
        patterns=patterns,
        name="ConnectionPasswordRecognizer",
        supported_language="en"
    )


def create_license_info_recognizer() -> "PatternRecognizer":
    """
    Recognizer for license information.
    Matches patterns like: Licensed to Company Name
    """
    patterns = [
        Pattern(
            name="license_pattern",
            regex=r"Licensed to\s+([^,\n]+)",
            score=0.9
        ),
    ]
    return PatternRecognizer(
        supported_entity="LICENSE_INFO",
        patterns=patterns,
        name="LicenseInfoRecognizer",
        supported_language="en"
    )


def create_windows_path_recognizer() -> "PatternRecognizer":
    """
    Recognizer for Windows file paths that may reveal sensitive information.
    Matches patterns like: C:\\Program Files\\AppName\\Instance\\data\\tasks\\
    """
    patterns = [
        Pattern(
            name="program_files_path",
            regex=r"C:\\Program Files\\[^\\]+\\[^\\]+\\",
            score=0.7
        ),
        Pattern(
            name="users_path",
            regex=r"C:\\Users\\[^\\]+\\",
            score=0.8
        ),
    ]
    return PatternRecognizer(
        supported_entity="WINDOWS_PATH",
        patterns=patterns,
        name="WindowsPathRecognizer",
        supported_language="en"
    )


def create_cloud_resource_recognizer() -> "PatternRecognizer":
    """
    Recognizer for cloud resource identifiers (Azure, AWS, GCP).
    Matches patterns like: adb-1234567890.12.azuredatabricks.net
    """
    patterns = [
        Pattern(
            name="azure_databricks",
            regex=r"adb-\d+\.\d+\.[a-z]+\.[a-z]+\.[a-z]+",
            score=0.9
        ),
        Pattern(
            name="aws_resource",
            regex=r"arn:aws:[a-z0-9-]+:[a-z0-9-]*:\d*:[^\s]+",
            score=0.9
        ),
    ]
    return PatternRecognizer(
        supported_entity="CLOUD_RESOURCE",
        patterns=patterns,
        name="CloudResourceRecognizer",
        supported_language="en"
    )


def create_http_path_recognizer() -> "PatternRecognizer":
    """
    Recognizer for HTTP paths and similar resource identifiers.
    Matches patterns like: HTTPPath={...}
    """
    patterns = [
        Pattern(
            name="http_path_pattern",
            regex=r"HTTPPath=\{[^}]+\}",
            score=0.9
        ),
    ]
    return PatternRecognizer(
        supported_entity="HTTP_PATH",
        patterns=patterns,
        name="HTTPPathRecognizer",
        supported_language="en"
    )


def create_task_server_log_recognizer() -> "PatternRecognizer":
    """
    Recognizer for Task Server Log header lines.
    These lines contain server name, OS info, and other sensitive details.
    Example: Task Server Log - TASK_NAME (V2025.5.0.247 SERVER.domain.com Microsoft Windows...)
    """
    patterns = [
        Pattern(
            name="task_server_log_header",
            # Match the full parenthetical section including PID even with nested parentheses
            regex=r"\(V\d+[\w\.\-]*.*?PID:\s*\d+\s*\)",
            score=0.9
        ),
        Pattern(
            name="task_server_log_prefix",
            # Match the lead-in before the parentheses
            regex=r"Task Server Log\s*-\s*[A-Za-z0-9_.-]+",
            score=0.65
        ),
    ]
    return PatternRecognizer(
        supported_entity="TASK_SERVER_INFO",
        patterns=patterns,
        name="TaskServerLogRecognizer",
        supported_language="en"
    )


def create_host_after_version_recognizer() -> "PatternRecognizer":
    """
    Recognizer for the host immediately following the version token in Task Server headers.
    Example match: V2025.5.0.247 HSP-DBM-APP05.cs.sbsit.eu -> captures host only.
    """
    patterns = [
        Pattern(
            name="host_after_version",
            regex=r"(?<=V[\w\.\-]+\s)([A-Za-z0-9][-A-Za-z0-9\.]+)",
            score=0.9
        ),
    ]
    return PatternRecognizer(
        supported_entity="HOST_AFTER_VERSION",
        patterns=patterns,
        name="HostAfterVersionRecognizer",
        supported_language="en"
    )

def create_revision_hash_recognizer() -> "PatternRecognizer":
    """
    Recognizer for Git revision hashes.
    Matches patterns like: Revision:b6b2ebe61b2f25940ff3932dc4c4a7bb9d2691d8
    """
    patterns = [
        Pattern(
            name="revision_hash",
            regex=r"Revision:[a-f0-9]{40}",
            score=0.9
        ),
    ]
    return PatternRecognizer(
        supported_entity="REVISION_HASH",
        patterns=patterns,
        name="RevisionHashRecognizer",
        supported_language="en"
    )


# =============================================================================
# Main Sanitizer Class
# =============================================================================

class LogSanitizer:
    """
    Centralized PII sanitizer for log analysis.
    
    Uses Presidio for robust PII detection with custom recognizers
    for log-specific patterns. Thread-safe and designed for reuse.
    
    Usage:
        sanitizer = get_sanitizer()  # Get singleton instance
        clean_text = sanitizer.sanitize("Log with server.domain.com")
        clean_dict = sanitizer.sanitize_dict({"host": "server.domain.com"})
    """
    
    def __init__(self):
        """Initialize the sanitizer with Presidio engines and custom recognizers."""
        # Create analyzer engine with a simple configuration
        configuration = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}]
        }
        
        # Configure NER model to ignore common false positive entity types
        ner_model_configuration = {
            "labels_to_ignore": ["CARDINAL", "MONEY", "ORDINAL", "QUANTITY", "PERCENT", "WORK_OF_ART", "PRODUCT", "EVENT", "LAW", "LANGUAGE"]
        }
        
        try:
            # Try to use spacy if available
            provider = NlpEngineProvider(nlp_configuration=configuration)
            nlp_engine = provider.create_engine()
            # Create analyzer with only English support to avoid language warnings
            self.analyzer = AnalyzerEngine(
                nlp_engine=nlp_engine,
                supported_languages=["en"]
            )
        except Exception:
            # Fallback: create analyzer without NLP engine (pattern-only mode)
            self.analyzer = AnalyzerEngine(supported_languages=["en"])
        
        self.anonymizer = AnonymizerEngine()
        
        # Register custom recognizers
        self._register_custom_recognizers()
    
    def _register_custom_recognizers(self):
        """Register all custom recognizers for log-specific patterns."""
        custom_recognizers = [
            create_hostname_recognizer(),
            create_unc_path_recognizer(),
            create_connection_string_recognizer(),
            create_connection_host_recognizer(),
            create_connection_password_recognizer(),
            create_license_info_recognizer(),
            create_windows_path_recognizer(),
            create_cloud_resource_recognizer(),
            create_http_path_recognizer(),
            create_task_server_log_recognizer(),
            create_host_after_version_recognizer(),
            create_revision_hash_recognizer(),
        ]
        
        for recognizer in custom_recognizers:
            self.analyzer.registry.add_recognizer(recognizer)
    
    def sanitize(self, text: str) -> str:
        """
        Sanitize a single text string by detecting and anonymizing PII.
        
        Args:
            text: The text to sanitize
            
        Returns:
            Sanitized text with PII replaced by descriptive tags
        """
        if not text:
            return text
        
        # Analyze text for PII entities
        results = self.analyzer.analyze(
            text=text,
            entities=LOG_ENTITIES,
            language="en"
        )
        
        if not results:
            return text
        
        # Filter out false positives using denylist
        results = self._filter_false_positives(text, results)
        
        if not results:
            return text
        
        # Anonymize detected entities
        anonymized = self.anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=ANONYMIZATION_OPERATORS
        )
        
        return anonymized.text
    
    def _filter_false_positives(self, text: str, results) -> list:
        """
        Filter out false positives from Presidio results.
        
        SpaCy NER often misidentifies technical terms as persons or other entities.
        This method removes detections that match known technical patterns.
        """
        filtered = []
        for result in results:
            detected_text = text[result.start:result.end]
            
            # Check if this detection matches any denylist pattern
            is_false_positive = False
            for pattern in DENYLIST_PATTERNS:
                if re.search(pattern, detected_text, re.IGNORECASE):
                    is_false_positive = True
                    break
            
            # Additional heuristics for PERSON entities
            if result.entity_type == "PERSON":
                # Skip if it looks like a technical term (all caps, contains numbers, etc.)
                if detected_text.isupper():
                    is_false_positive = True
                elif re.search(r'\d', detected_text):
                    is_false_positive = True
                elif detected_text.lower() in ['error', 'warning', 'info', 'debug', 'task', 'table', 'source', 'target']:
                    is_false_positive = True
            
            if not is_false_positive:
                filtered.append(result)
        
        return filtered
    
    def sanitize_batch(self, texts: List[str]) -> List[str]:
        """
        Sanitize multiple texts efficiently.
        
        Args:
            texts: List of texts to sanitize
            
        Returns:
            List of sanitized texts
        """
        return [self.sanitize(text) for text in texts]
    
    def sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively sanitize all string values in a dictionary.
        
        Args:
            data: Dictionary to sanitize
            
        Returns:
            New dictionary with sanitized string values
        """
        if not data:
            return data
        
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.sanitize(value)
            elif isinstance(value, dict):
                result[key] = self.sanitize_dict(value)
            elif isinstance(value, list):
                result[key] = self.sanitize_list(value)
            else:
                result[key] = value
        return result
    
    def sanitize_list(self, data: List[Any]) -> List[Any]:
        """
        Recursively sanitize all string values in a list.
        
        Args:
            data: List to sanitize
            
        Returns:
            New list with sanitized string values
        """
        if not data:
            return data
        
        result = []
        for item in data:
            if isinstance(item, str):
                result.append(self.sanitize(item))
            elif isinstance(item, dict):
                result.append(self.sanitize_dict(item))
            elif isinstance(item, list):
                result.append(self.sanitize_list(item))
            else:
                result.append(item)
        return result
    
    def preview_redactions(self, text: str) -> Dict[str, Any]:
        """
        Preview what would be redacted in the text without actually redacting.
        
        This is useful for showing users what sensitive data will be masked
        before sending to the LLM.
        
        Args:
            text: The text to analyze
            
        Returns:
            Dictionary with:
            - original: The original text
            - sanitized: The sanitized text
            - redactions: List of detected items with their type and value
            - summary: Human-readable summary of redactions
        """
        if not text:
            return {
                "original": text,
                "sanitized": text,
                "redactions": [],
                "summary": "No content to analyze"
            }
        
        # Analyze text for PII entities
        results = self.analyzer.analyze(
            text=text,
            entities=LOG_ENTITIES,
            language="en"
        )
        
        # Filter out false positives
        results = self._filter_false_positives(text, results)
        
        if not results:
            return {
                "original": text,
                "sanitized": text,
                "redactions": [],
                "summary": "No sensitive information detected"
            }
        
        # Build redactions list
        redactions = []
        for result in sorted(results, key=lambda x: x.start):
            original_value = text[result.start:result.end]
            entity_type = result.entity_type
            replacement = ANONYMIZATION_OPERATORS.get(entity_type, OperatorConfig("replace", {"new_value": "[REDACTED]"}))
            redactions.append({
                "type": entity_type,
                "type_description": ENTITY_DESCRIPTIONS.get(entity_type, entity_type),
                "original_value": original_value,
                "replacement": replacement.params.get("new_value", "[REDACTED]"),
                "start": result.start,
                "end": result.end,
                "score": result.score
            })
        
        # Get sanitized version
        anonymized = self.anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=ANONYMIZATION_OPERATORS
        )
        
        # Build summary
        type_counts = {}
        for r in redactions:
            desc = r["type_description"]
            type_counts[desc] = type_counts.get(desc, 0) + 1
        
        summary_parts = [f"{count} {name}{'s' if count > 1 else ''}" 
                        for name, count in type_counts.items()]
        summary = f"Found: {', '.join(summary_parts)}" if summary_parts else "No sensitive information detected"
        
        return {
            "original": text,
            "sanitized": anonymized.text,
            "redactions": redactions,
            "summary": summary
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_sanitizer: Optional[LogSanitizer] = None


def get_sanitizer() -> LogSanitizer:
    """
    Get the singleton LogSanitizer instance.
    
    The sanitizer is thread-safe and should be reused for performance.
    Presidio/spaCy are loaded on first call (lazy) for fast app startup.
    
    Returns:
        LogSanitizer instance
    """
    global _sanitizer
    _ensure_presidio_loaded()
    if _sanitizer is None:
        _sanitizer = LogSanitizer()
    return _sanitizer


# =============================================================================
# Convenience Functions (for backward compatibility)
# =============================================================================

def sanitize_text(text: str) -> str:
    """
    Sanitize a text string. Convenience function using singleton.
    
    Args:
        text: Text to sanitize
        
    Returns:
        Sanitized text
    """
    return get_sanitizer().sanitize(text)


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize a dictionary. Convenience function using singleton.
    
    Args:
        data: Dictionary to sanitize
        
    Returns:
        Sanitized dictionary
    """
    return get_sanitizer().sanitize_dict(data)


def sanitize_list(data: List[Any]) -> List[Any]:
    """
    Sanitize a list. Convenience function using singleton.
    
    Args:
        data: List to sanitize
        
    Returns:
        Sanitized list
    """
    return get_sanitizer().sanitize_list(data)


def preview_redactions(text: str) -> Dict[str, Any]:
    """
    Preview what would be redacted in the text.
    Convenience function using singleton.
    
    Args:
        text: Text to analyze
        
    Returns:
        Dictionary with original, sanitized, redactions list, and summary
    """
    return get_sanitizer().preview_redactions(text)
