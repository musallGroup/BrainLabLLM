"""Lookup tool for the lab's internal MediaWiki instance. No tkinter import,
no dependency on main.py - same module shape as meeting.py/diarization.py/
agent.py.

This is deliberately not "web search": Ollama's own hosted web_search/
web_fetch tools route every request through ollama.com's cloud servers,
which have no path into the lab's internal network and could never reach
this wiki. This module talks to the wiki directly instead, with no cloud
dependency and no API key.
"""

import html.parser
import re
import urllib.parse

import requests

WIKI_DOMAIN = "wiki2.bio2.rwth-aachen.de"
# http, not https - the site's TLS cert is issued for a different hostname
# (intraweb.bio2.rwth-aachen.de), so forcing https breaks the connection.
WIKI_BASE_URL = f"http://{WIKI_DOMAIN}/index.php/"

MAX_WIKI_PAGE_CHARS = 8000  # 2x chunk_text()'s per-chunk target - generous but bounded
REQUEST_TIMEOUT_SECONDS = 15

# MediaWiki wraps every heading's edit links in this class, and appends a
# "Retrieved from ..." footer with this class - both live *inside*
# #mw-content-text and need to be stripped explicitly. Navigation/sidebar/
# footer chrome, by contrast, are structural siblings of #mw-content-text,
# not children, so they're already excluded just by scoping collection to
# inside that div - no special-casing needed for those.
SKIP_CLASS_MARKERS = ("mw-editsection", "printfooter")

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img",
    "input", "link", "meta", "param", "source", "track", "wbr",
}
BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "br", "blockquote", "ul", "ol", "table"}

# Cheap sanity check on page titles, not a security boundary - the domain
# can't be changed by page_title regardless (WIKI_BASE_URL is a fixed
# string prefix), this just rejects obviously-malformed input earlier with
# a clearer error than an eventual 404 would.
TITLE_RE = re.compile(r"^[\w \-().,'&/]+$")


class WikiError(Exception):
    """A user-facing wiki-fetch failure - reported back to the model as a
    tool result, never raised as an unhandled exception in the caller."""


class _MediaWikiContentExtractor(html.parser.HTMLParser):
    """Extracts just the article text from a MediaWiki page's raw HTML.
    Collection is scoped to inside <div id="mw-content-text"> - navigation/
    sidebar/footer chrome are structural siblings of that div, not children,
    so they're excluded automatically without needing to be named. Content
    nested *inside* that div that still isn't real article text (edit-section
    links, the trailing printfooter) is stripped via SKIP_CLASS_MARKERS.

    HTMLParser never calls handle_endtag for void elements (br, img, hr,
    ...) - depth must only be pushed/popped for non-void tags, or the
    "still inside #mw-content-text" check silently drifts and breaks
    partway through a real page.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.content_open_depth = None  # depth at which #mw-content-text opened; None until found
        self.skip_open_depth = None  # depth at which a stripped subtree opened
        self.chunks = []

    @property
    def in_content(self):
        return self.content_open_depth is not None

    @property
    def skipping(self):
        return self.skip_open_depth is not None

    def handle_starttag(self, tag, attrs):
        self._handle_open(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag, attrs):
        self._handle_open(tag, attrs, self_closing=True)

    def _handle_open(self, tag, attrs, self_closing):
        attrs_dict = dict(attrs)
        is_void = self_closing or tag in VOID_TAGS

        if self.in_content and not self.skipping:
            css_class = attrs_dict.get("class", "")
            if tag in ("script", "style") or any(marker in css_class for marker in SKIP_CLASS_MARKERS):
                if not is_void:
                    self.skip_open_depth = self.depth
                    self.depth += 1
                return

        if not self.in_content and tag == "div" and attrs_dict.get("id") == "mw-content-text":
            self.content_open_depth = self.depth
            if not is_void:
                self.depth += 1
            return

        if self.in_content and not self.skipping and tag in BLOCK_TAGS:
            self.chunks.append("\n")

        if not is_void:
            self.depth += 1

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return  # no matching depth was pushed for these on open
        self.depth -= 1
        if self.skipping and self.depth == self.skip_open_depth:
            self.skip_open_depth = None
        elif self.in_content and self.depth == self.content_open_depth:
            self.content_open_depth = None

    def handle_data(self, data):
        if self.in_content and not self.skipping:
            self.chunks.append(data)

    def get_text(self):
        lines = [line.strip() for line in "".join(self.chunks).split("\n")]
        return "\n\n".join(line for line in lines if line)


def _validate_page_title(page_title):
    if not page_title or ".." in page_title or not TITLE_RE.match(page_title):
        raise WikiError(f"invalid page title: {page_title!r}")


def fetch_wiki_page(page_title):
    """Fetch and extract the readable text of a page on the lab's internal
    wiki. page_title: exact MediaWiki page title (spaces and underscores are
    interchangeable, same as on the wiki itself).

    Returns {"title", "url", "content", "truncated"}. Raises WikiError for
    anything the model should be told about (page not found, unreachable) -
    the caller is expected to convert this into a tool-result message, not
    let it propagate as an unhandled exception.
    """
    _validate_page_title(page_title)
    url = WIKI_BASE_URL + urllib.parse.quote(page_title.replace(" ", "_"))

    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.exceptions.RequestException as exc:
        raise WikiError(f"could not reach the wiki: {exc}")

    if response.status_code == 404:
        raise WikiError(
            f"no page titled {page_title!r} exists on the wiki - check the exact title "
            "(MediaWiki titles are case-sensitive after the first letter)."
        )
    if not response.ok:
        raise WikiError(f"wiki returned an error (HTTP {response.status_code})")

    # requests falls back to Latin-1 when a response has no explicit charset
    # in its Content-Type header - this wiki declares UTF-8 via <meta
    # charset> in the HTML body, not the header, so the fallback would
    # otherwise mangle non-ASCII text.
    response.encoding = "utf-8"

    extractor = _MediaWikiContentExtractor()
    extractor.feed(response.text)
    text = extractor.get_text()
    if not text:
        raise WikiError(f"page {page_title!r} has no readable article content.")

    truncated = len(text) > MAX_WIKI_PAGE_CHARS
    if truncated:
        text = text[:MAX_WIKI_PAGE_CHARS]

    return {"title": page_title, "url": url, "content": text, "truncated": truncated}


WIKI_FETCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "fetch_wiki_page",
        "description": (
            "Fetch and read a page on the lab's internal wiki "
            f"({WIKI_DOMAIN}). Use this when the user's question might be answered by "
            "lab-specific documentation there (lab rules, procedures, equipment, protocols, "
            "group-specific topics) rather than general knowledge. Only this one wiki can be "
            "fetched, no other websites."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "page_title": {
                    "type": "string",
                    "description": (
                        "Exact page title, e.g. 'Systems_Neurophysiology' - spaces and "
                        "underscores are equivalent."
                    ),
                }
            },
            "required": ["page_title"],
        },
    },
}
