"""
Humanizer - Convert Structured Data to Human-Readable Text Without AI

This module provides template-based output generation:
- No AI model calls
- Deterministic, reproducible output
- Proper grammar handling (pluralization, etc.)
- Clean, readable markdown output
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

try:
    import inflect
    _inflect_engine = inflect.engine()
except ImportError:
    _inflect_engine = None
    
from jinja2 import Environment, BaseLoader, select_autoescape

logger = logging.getLogger(__name__)


# =============================================================================
# Jinja2 Environment with Custom Filters
# =============================================================================

def _pluralize(count: int, singular: str, plural: Optional[str] = None) -> str:
    """Pluralize a word based on count."""
    if count == 1:
        return singular
    if plural:
        return plural
    if _inflect_engine:
        return _inflect_engine.plural(singular)
    # Simple fallback
    return singular + "s"


def _format_number(value: Any) -> str:
    """Format a number with commas."""
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return str(value)


def _format_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f} seconds"
    elif seconds < 3600:
        mins = seconds / 60
        return f"{mins:.1f} minutes"
    else:
        hours = seconds / 3600
        return f"{hours:.1f} hours"


def _format_bytes(bytes_val: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


# Create Jinja2 environment
_jinja_env = Environment(
    loader=BaseLoader(),
    autoescape=select_autoescape(['html', 'xml'])
)

# Register custom filters
_jinja_env.filters['pluralize'] = lambda c, s, p=None: _pluralize(c, s, p)
_jinja_env.filters['number'] = _format_number
_jinja_env.filters['duration'] = _format_duration
_jinja_env.filters['bytes'] = _format_bytes


# =============================================================================
# Response Templates
# =============================================================================

TEMPLATES = {
    # Count responses
    "COUNT_ERRORS": """
{%- if error_count == 0 -%}
No errors found in this log file.
{%- elif error_count == 1 -%}
Found **1 error** in the log file.
{%- else -%}
Found **{{ error_count | number }}** errors in the log file.
{%- endif -%}
""",

    "COUNT_TABLES": """
{%- if table_count == 0 -%}
No tables found in this log file.
{%- elif table_count == 1 -%}
Found **1 table** in the log file.
{%- else -%}
Found **{{ table_count }}** tables in the log file.
{%- endif -%}
""",

    "COUNT_BATCHES": """
{%- if batch_count == 0 -%}
No batches found in this log file.
{%- elif batch_count == 1 -%}
Found **1 batch** in the log file.
{%- else -%}
Found **{{ batch_count | number }}** batches in the log file.
{%- endif -%}
""",

    "COUNT_OPERATIONS": """
Found **{{ total | number }}** total operations:
- Inserts: {{ inserts | number }}
- Updates: {{ updates | number }}
- Deletes: {{ deletes | number }}
- Merges: {{ merges | number }}
""",

    # List responses
    "LIST_TABLES": """
{%- if tables | length == 0 -%}
No tables found in the log file.
{%- else -%}
Found **{{ tables | length }}** {{ tables | length | pluralize('table', 'tables') }} in the log:

{% for table in tables[:20] -%}
- **{{ table.name }}**: {{ table.operations | number }} operations, {{ table.apply_time | round(1) }}s apply time
{% endfor -%}
{%- if tables | length > 20 %}
... and {{ tables | length - 20 }} more tables.
{%- endif -%}
{%- endif -%}
""",

    "LIST_ERRORS": """
{%- if error_count == 0 -%}
No errors found in the log file.
{%- else -%}
Found **{{ error_count | number }}** {{ error_count | pluralize('error', 'errors') }}. Here are the most recent:

{% for error in errors[:10] -%}
- Line {{ error.line }}: `{{ error.text[:100] }}{% if error.text | length > 100 %}...{% endif %}`
{% endfor -%}
{%- endif -%}
""",

    "LIST_BATCH_REASONS": """
{%- if total_batches == 0 -%}
No batch data found in the log file.
{%- else -%}
Batch closure reasons ({{ total_batches | number }} total batches):

{% for reason, count in reasons.items() | sort(attribute='1', reverse=true) -%}
- **{{ reason }}**: {{ count | number }} ({{ ((count / total_batches) * 100) | round(1) }}%)
{% endfor -%}
{%- endif -%}
""",

    # Stats responses
    "STATS_LATENCY": """
**Latency Statistics** ({{ data_points | number }} data points):

| Component | Avg | Max | P95 |
|-----------|-----|-----|-----|
| Source | {{ source.avg | round(2) }}s | {{ source.max | round(2) }}s | {{ source.p95 | round(2) }}s |
| Handling | {{ handling.avg | round(2) }}s | {{ handling.max | round(2) }}s | {{ handling.p95 | round(2) }}s |
| Target | {{ target.avg | round(2) }}s | {{ target.max | round(2) }}s | {{ target.p95 | round(2) }}s |
""",

    "STATS_BOTTLENECK": """
**Primary Bottleneck: {{ bottleneck | upper }}**

Average latencies:
- Source: {{ avg_source | round(2) }}s
- Handling: {{ avg_handling | round(2) }}s
- Target: {{ avg_target | round(2) }}s
""",

    # Summary response
    "SUMMARY": """
## Log Summary: {{ filename }}

**Health Status: {{ health }}**

### Overview
- **File Size:** {{ size_bytes | bytes }}
- **Lines:** {{ line_count | number }}
- **Tables:** {{ table_count }}
- **Batches:** {{ batch_count | number }}
- **Total Operations:** {{ total_operations | number }}
- **Errors:** {{ error_count | number }}
""",

    # Time responses
    "TIME_RANGE": """
**Log Time Range:**

- Start: {{ start_time }}
- End: {{ end_time }}
- Duration: {{ duration_seconds | duration }}
""",

    # KB Fusion responses
    "KB_FUSION": """
## Log Analysis

{{ local_facts }}

---

## Related Knowledge Base Articles

{% for article in kb_articles -%}
### {{ article.title }}
{{ article.content[:500] }}{% if article.content | length > 500 %}...{% endif %}

{% if article.url %}[Read more]({{ article.url }}){% endif %}

{% endfor -%}
""",

    # No answer found
    "NO_LOCAL_ANSWER": """
I couldn't find specific data to answer this question from the log analysis.

{% if suggestion -%}
**Suggestion:** {{ suggestion }}
{%- endif %}
""",
}


# =============================================================================
# Humanizer Class
# =============================================================================

@dataclass
class HumanizedResponse:
    """Result from humanizer."""
    text: str
    template_used: str
    data: Dict[str, Any]


class Humanizer:
    """
    Converts structured data to human-readable text without AI.
    
    Usage:
        humanizer = Humanizer()
        response = humanizer.format("COUNT_ERRORS", {"error_count": 42})
        print(response.text)  # "Found **42** errors in the log file."
    """
    
    def __init__(self, custom_templates: Optional[Dict[str, str]] = None):
        """
        Initialize humanizer with optional custom templates.
        
        Args:
            custom_templates: Dict of template_name -> template_string
        """
        self.templates = {**TEMPLATES}
        if custom_templates:
            self.templates.update(custom_templates)
    
    def format(self, template_name: str, data: Dict[str, Any]) -> HumanizedResponse:
        """
        Format data using a named template.
        
        Args:
            template_name: Name of template to use
            data: Data to fill into template
            
        Returns:
            HumanizedResponse with formatted text
        """
        template_str = self.templates.get(template_name)
        if not template_str:
            logger.warning(f"Template '{template_name}' not found")
            return HumanizedResponse(
                text=f"[Template '{template_name}' not found]",
                template_used=template_name,
                data=data
            )
        
        try:
            template = _jinja_env.from_string(template_str)
            text = template.render(**data).strip()
            return HumanizedResponse(
                text=text,
                template_used=template_name,
                data=data
            )
        except Exception as e:
            logger.error(f"Template rendering failed: {e}")
            return HumanizedResponse(
                text=f"[Error rendering template: {e}]",
                template_used=template_name,
                data=data
            )
    
    def format_count(self, entity: str, count: int) -> str:
        """
        Format a simple count response.
        
        Args:
            entity: What we're counting (errors, tables, etc.)
            count: The count value
            
        Returns:
            Formatted string
        """
        if count == 0:
            return f"No {entity} found in this log file."
        elif count == 1:
            singular = entity.rstrip('s') if entity.endswith('s') else entity
            return f"Found **1 {singular}** in the log file."
        else:
            return f"Found **{count:,} {entity}** in the log file."
    
    def format_list(self, entity: str, items: List[str], max_items: int = 20) -> str:
        """
        Format a list response.
        
        Args:
            entity: What we're listing (tables, errors, etc.)
            items: List of items
            max_items: Maximum items to show
            
        Returns:
            Formatted string
        """
        if not items:
            return f"No {entity} found in the log file."
        
        result = f"Found **{len(items)}** {entity}:\n\n"
        for item in items[:max_items]:
            result += f"- {item}\n"
        
        if len(items) > max_items:
            result += f"\n... and {len(items) - max_items} more."
        
        return result
    
    def format_kb_fusion(
        self, 
        local_facts: str, 
        kb_articles: List[Dict[str, str]]
    ) -> str:
        """
        Format a KB fusion response (local facts + KB articles).
        
        Args:
            local_facts: Local analysis results
            kb_articles: List of relevant KB articles
            
        Returns:
            Formatted string combining both sources
        """
        return self.format("KB_FUSION", {
            "local_facts": local_facts,
            "kb_articles": kb_articles
        }).text


# =============================================================================
# Singleton Instance
# =============================================================================

_humanizer: Optional[Humanizer] = None


def get_humanizer() -> Humanizer:
    """Get the singleton Humanizer instance."""
    global _humanizer
    if _humanizer is None:
        _humanizer = Humanizer()
    return _humanizer


# =============================================================================
# Convenience Functions
# =============================================================================

def humanize(template_name: str, data: Dict[str, Any]) -> str:
    """
    Quick humanization using default humanizer.
    
    Args:
        template_name: Name of template
        data: Data for template
        
    Returns:
        Formatted string
    """
    return get_humanizer().format(template_name, data).text


def humanize_count(entity: str, count: int) -> str:
    """Quick count formatting."""
    return get_humanizer().format_count(entity, count)


def humanize_list(entity: str, items: List[str]) -> str:
    """Quick list formatting."""
    return get_humanizer().format_list(entity, items)
