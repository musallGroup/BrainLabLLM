"""Tests for main.answer_with_tools - the bounded tool-calling loop that lets
a Chat message use wiki.fetch_wiki_page and/or websearch.search_web,
additively (either, both, or neither enabled). Mocks agent.query_ollama_chat
and the tool functions themselves, matching tests/test_agent_live.py's
established mocked-loop style - no network, no Tk."""

from unittest import mock

import agent
import main
import websearch
import wiki


def test_no_tool_call_returns_plain_content():
    def fake_query(api_url, model, messages, tools=None, should_stop=None, options=None):
        return {"role": "assistant", "content": "Just a normal answer, no lookup needed."}

    with mock.patch.object(agent, "query_ollama_chat", side_effect=fake_query):
        content, pages_used, queries_used = main.answer_with_tools([{"role": "user", "content": "hi"}], use_wiki=True)

    assert content == "Just a normal answer, no lookup needed."
    assert pages_used == []
    assert queries_used == []


def test_dispatches_fetch_and_returns_final_answer():
    responses = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_1", "function": {"name": "fetch_wiki_page", "arguments": {"page_title": "Systems_Neurophysiology"}}}
            ],
        },
        {"role": "assistant", "content": "According to the wiki, the lab covers systems neurophysiology."},
    ]
    call_log = []

    def fake_query(api_url, model, messages, tools=None, should_stop=None, options=None):
        call_log.append(list(messages))
        return responses[len(call_log) - 1]

    fake_page = {"title": "Systems_Neurophysiology", "url": "http://wiki2.bio2.rwth-aachen.de/index.php/Systems_Neurophysiology", "content": "...", "truncated": False}

    with mock.patch.object(agent, "query_ollama_chat", side_effect=fake_query), \
         mock.patch.object(wiki, "fetch_wiki_page", return_value=fake_page) as mock_fetch:
        content, pages_used, queries_used = main.answer_with_tools(
            [{"role": "user", "content": "what does the wiki say?"}], use_wiki=True
        )

    mock_fetch.assert_called_once_with("Systems_Neurophysiology")
    assert content == "According to the wiki, the lab covers systems neurophysiology."
    assert pages_used == ["Systems_Neurophysiology"]
    assert queries_used == []
    # The second call must have seen the tool result as context.
    second_call_messages = call_log[1]
    assert any(m.get("role") == "tool" for m in second_call_messages)


def test_wiki_error_is_fed_back_gracefully_not_raised():
    responses = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_1", "function": {"name": "fetch_wiki_page", "arguments": {"page_title": "Nonexistent_Page"}}}
            ],
        },
        {"role": "assistant", "content": "I couldn't find that page on the wiki."},
    ]
    call_log = []

    def fake_query(api_url, model, messages, tools=None, should_stop=None, options=None):
        call_log.append(list(messages))
        return responses[len(call_log) - 1]

    with mock.patch.object(agent, "query_ollama_chat", side_effect=fake_query), \
         mock.patch.object(wiki, "fetch_wiki_page", side_effect=wiki.WikiError("no page titled 'Nonexistent_Page' exists")):
        content, pages_used, queries_used = main.answer_with_tools(
            [{"role": "user", "content": "look up Nonexistent_Page"}], use_wiki=True
        )

    assert content == "I couldn't find that page on the wiki."
    assert pages_used == []  # fetch failed, so nothing was actually used
    tool_message = next(m for m in call_log[1] if m.get("role") == "tool")
    assert "no page titled" in tool_message["content"]


def test_dispatches_search_and_returns_final_answer():
    responses = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "function": {"name": "search_web", "arguments": {"query": "qwen3.6 release date"}}}],
        },
        {"role": "assistant", "content": "Qwen3.6 was released in April 2026, according to search results."},
    ]
    call_log = []

    def fake_query(api_url, model, messages, tools=None, should_stop=None, options=None):
        call_log.append(list(messages))
        return responses[len(call_log) - 1]

    fake_results = [{"title": "Qwen3.6 announcement", "url": "http://example.com", "snippet": "released April 2026"}]

    with mock.patch.object(agent, "query_ollama_chat", side_effect=fake_query), \
         mock.patch.object(websearch, "search_web", return_value=fake_results) as mock_search:
        content, pages_used, queries_used = main.answer_with_tools(
            [{"role": "user", "content": "when was qwen3.6 released?"}], use_websearch=True
        )

    mock_search.assert_called_once_with("qwen3.6 release date")
    assert content == "Qwen3.6 was released in April 2026, according to search results."
    assert pages_used == []
    assert queries_used == ["qwen3.6 release date"]


def test_websearch_error_is_fed_back_gracefully_not_raised():
    responses = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "function": {"name": "search_web", "arguments": {"query": "asdkjaslkdj"}}}],
        },
        {"role": "assistant", "content": "I couldn't find anything about that."},
    ]
    call_log = []

    def fake_query(api_url, model, messages, tools=None, should_stop=None, options=None):
        call_log.append(list(messages))
        return responses[len(call_log) - 1]

    with mock.patch.object(agent, "query_ollama_chat", side_effect=fake_query), \
         mock.patch.object(websearch, "search_web", side_effect=websearch.WebSearchError("no results found for 'asdkjaslkdj'")):
        content, pages_used, queries_used = main.answer_with_tools(
            [{"role": "user", "content": "look up asdkjaslkdj"}], use_websearch=True
        )

    assert content == "I couldn't find anything about that."
    assert queries_used == []
    tool_message = next(m for m in call_log[1] if m.get("role") == "tool")
    assert "no results found" in tool_message["content"]


def test_both_tools_enabled_can_use_either():
    responses = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "function": {"name": "fetch_wiki_page", "arguments": {"page_title": "Systems_Neurophysiology"}}}],
        },
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_2", "function": {"name": "search_web", "arguments": {"query": "latest neuroscience news"}}}],
        },
        {"role": "assistant", "content": "Combining wiki and web info: ..."},
    ]
    call_log = []

    def fake_query(api_url, model, messages, tools=None, should_stop=None, options=None):
        call_log.append(list(messages))
        assert len(tools) == 2  # both schemas offered when both are enabled
        return responses[len(call_log) - 1]

    fake_page = {"title": "Systems_Neurophysiology", "url": "http://x", "content": "...", "truncated": False}
    fake_results = [{"title": "News", "url": "http://example.com", "snippet": "..."}]

    with mock.patch.object(agent, "query_ollama_chat", side_effect=fake_query), \
         mock.patch.object(wiki, "fetch_wiki_page", return_value=fake_page), \
         mock.patch.object(websearch, "search_web", return_value=fake_results):
        content, pages_used, queries_used = main.answer_with_tools(
            [{"role": "user", "content": "compare wiki and current news"}], use_wiki=True, use_websearch=True
        )

    assert content == "Combining wiki and web info: ..."
    assert pages_used == ["Systems_Neurophysiology"]
    assert queries_used == ["latest neuroscience news"]


def test_neither_tool_enabled_offers_no_tools():
    def fake_query(api_url, model, messages, tools=None, should_stop=None, options=None):
        assert tools == []
        return {"role": "assistant", "content": "plain answer"}

    with mock.patch.object(agent, "query_ollama_chat", side_effect=fake_query):
        content, pages_used, queries_used = main.answer_with_tools([{"role": "user", "content": "hi"}])

    assert content == "plain answer"


def test_respects_should_stop_before_first_call():
    with mock.patch.object(agent, "query_ollama_chat") as mock_query:
        content, pages_used, queries_used = main.answer_with_tools(
            [{"role": "user", "content": "hi"}], use_wiki=True, should_stop=lambda: True
        )

    mock_query.assert_not_called()
    assert content == ""
    assert pages_used == []
    assert queries_used == []


def test_bounded_iterations_stops_and_returns_fallback_message():
    call_count = {"n": 0}

    def fake_infinite_tool_caller(api_url, model, messages, tools=None, should_stop=None, options=None):
        call_count["n"] += 1
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": f"call_{call_count['n']}", "function": {"name": "fetch_wiki_page", "arguments": {"page_title": "Loop"}}}
            ],
        }

    fake_page = {"title": "Loop", "url": "http://x", "content": "...", "truncated": False}

    with mock.patch.object(agent, "query_ollama_chat", side_effect=fake_infinite_tool_caller), \
         mock.patch.object(wiki, "fetch_wiki_page", return_value=fake_page):
        content, pages_used, queries_used = main.answer_with_tools([{"role": "user", "content": "hi"}], use_wiki=True)

    assert call_count["n"] == main.MAX_TOOL_LOOKUP_ITERATIONS
    assert "wasn't able" in content.lower()


def test_unknown_tool_name_reported_back_without_crashing():
    responses = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "function": {"name": "some_other_tool", "arguments": {}}}],
        },
        {"role": "assistant", "content": "Never mind, here's an answer anyway."},
    ]
    call_log = []

    def fake_query(api_url, model, messages, tools=None, should_stop=None, options=None):
        call_log.append(list(messages))
        return responses[len(call_log) - 1]

    with mock.patch.object(agent, "query_ollama_chat", side_effect=fake_query):
        content, pages_used, queries_used = main.answer_with_tools([{"role": "user", "content": "hi"}], use_wiki=True)

    assert content == "Never mind, here's an answer anyway."
    tool_message = next(m for m in call_log[1] if m.get("role") == "tool")
    assert "unknown tool" in tool_message["content"].lower()


def test_wiki_tool_call_ignored_when_wiki_not_enabled():
    """A model calling fetch_wiki_page when only web search was enabled
    should be treated the same as any other unknown tool, not dispatched."""
    responses = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "function": {"name": "fetch_wiki_page", "arguments": {"page_title": "X"}}}],
        },
        {"role": "assistant", "content": "ok"},
    ]
    call_log = []

    def fake_query(api_url, model, messages, tools=None, should_stop=None, options=None):
        call_log.append(list(messages))
        return responses[len(call_log) - 1]

    with mock.patch.object(agent, "query_ollama_chat", side_effect=fake_query), \
         mock.patch.object(wiki, "fetch_wiki_page") as mock_fetch:
        main.answer_with_tools([{"role": "user", "content": "hi"}], use_websearch=True)

    mock_fetch.assert_not_called()
    tool_message = next(m for m in call_log[1] if m.get("role") == "tool")
    assert "unknown tool" in tool_message["content"].lower()
