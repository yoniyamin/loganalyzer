"""Report web search: live API vs prep-time Tavily/KB."""

from backend.llm.prompts import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_WITH_WEB_SEARCH,
    get_analysis_system_prompt,
    replace_analysis_system_prompt,
)
from backend.llm.report_generator import (
    PROVIDER_GEMINI,
    PROVIDER_LMSTUDIO,
    PROVIDER_OPENROUTER,
    resolve_live_web_search,
)


def test_resolve_live_web_search_off_when_user_disabled():
    assert resolve_live_web_search(
        user_web_search=False,
        provider=PROVIDER_GEMINI,
        tavily_configured=True,
    ) is False


def test_resolve_live_web_search_off_when_tavily_configured():
    assert resolve_live_web_search(
        user_web_search=True,
        provider=PROVIDER_GEMINI,
        tavily_configured=True,
    ) is False
    assert resolve_live_web_search(
        user_web_search=True,
        provider=PROVIDER_OPENROUTER,
        tavily_configured=True,
    ) is False


def test_resolve_live_web_search_on_gemini_without_tavily():
    assert resolve_live_web_search(
        user_web_search=True,
        provider=PROVIDER_GEMINI,
        tavily_configured=False,
    ) is True


def test_resolve_live_web_search_off_for_local_providers():
    assert resolve_live_web_search(
        user_web_search=True,
        provider=PROVIDER_LMSTUDIO,
        tavily_configured=False,
    ) is False


def test_replace_analysis_system_prompt_strips_web_instructions():
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_WITH_WEB_SEARCH},
        {"role": "user", "content": "analyze"},
    ]
    updated = replace_analysis_system_prompt(messages, web_search=False)
    assert updated[0]["content"] == get_analysis_system_prompt(web_search=False)
    assert SYSTEM_PROMPT in updated[0]["content"]
    assert messages[0]["content"] == SYSTEM_PROMPT_WITH_WEB_SEARCH
