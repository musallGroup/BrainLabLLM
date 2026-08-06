"""Web search tool via a local SearXNG instance. No tkinter import, no
dependency on main.py - same module shape as wiki.py/meeting.py/agent.py.

Deliberately not routed through Ollama's own hosted web_search tool - same
reasoning as wiki.py: that goes through ollama.com's cloud servers. This
hits a SearXNG instance on the lab network instead (mirroring how the
Ollama server itself is reached), no cloud dependency, no API key, nothing
ever leaves the lab network.

Requires SearXNG to be reachable from wherever this app runs, not just
localhost on the machine hosting it - confirm SEARXNG_URL points at a
reachable address before enabling this in Settings.
"""

import requests

SEARXNG_URL = "http://10.3.2.112:8888/search"
MAX_RESULTS = 5
MAX_SNIPPET_CHARS = 500
REQUEST_TIMEOUT_SECONDS = 15


class WebSearchError(Exception):
    """A user-facing search failure - reported back to the model as a tool
    result, never raised as an unhandled exception in the caller."""


def search_web(query):
    """Search the public web via the lab's local SearXNG instance.

    Returns a list of {"title", "url", "snippet"} dicts, capped at
    MAX_RESULTS. Raises WebSearchError for anything the model should be
    told about (unreachable, no results) - the caller is expected to
    convert this into a tool-result message, not let it propagate as an
    unhandled exception.
    """
    if not query or not query.strip():
        raise WebSearchError("empty search query")

    try:
        response = requests.get(
            SEARXNG_URL,
            params={"q": query, "format": "json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        raise WebSearchError(f"could not reach the search service: {exc}")

    if not response.ok:
        raise WebSearchError(f"search service returned an error (HTTP {response.status_code})")

    try:
        data = response.json()
    except ValueError:
        raise WebSearchError("search service returned an unreadable response")

    results = []
    for item in data.get("results", [])[:MAX_RESULTS]:
        snippet = (item.get("content") or "")[:MAX_SNIPPET_CHARS]
        results.append({"title": item.get("title", ""), "url": item.get("url", ""), "snippet": snippet})

    if not results:
        raise WebSearchError(f"no results found for {query!r}")

    return results


WEB_SEARCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": (
            "Search the public web for current information not in your training data, "
            "or general (non-lab-specific) information. Returns a short list of titles, "
            "URLs, and snippets - base your answer on these and cite the source URLs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms."},
            },
            "required": ["query"],
        },
    },
}
