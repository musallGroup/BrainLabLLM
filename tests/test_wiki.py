from unittest import mock

import pytest

import wiki

# Shaped like the real page (confirmed by fetching the live wiki during
# development): real content lives inside #mw-content-text, chrome (nav/
# sidebar/footer) is a *sibling* of that div (excluded automatically by
# scoping), and mw-editsection/printfooter/comments are nested *inside* the
# content div and need explicit stripping.
SAMPLE_HTML = """<!DOCTYPE html>
<html>
<head><title>Systems Neurophysiology - Wiki Bio2</title></head>
<body>
<div id="column-one">
  <div id="p-navigation"><a href="/Main_Page">Nav link that should be excluded</a></div>
</div>
<div id="bodyContent" class="monobook-body">
  <!-- start content -->
  <div id="mw-content-text" class="mw-body-content"><div class="mw-content-ltr mw-parser-output" lang="en" dir="ltr">
    <h2><span class="mw-headline" id="Overview">Overview</span><span class="mw-editsection">[<a href="/edit">edit</a>]</span></h2>
    <p>This is the real article text about <b>Systems Neurophysiology</b>.</p>
    <p>A second paragraph with a <a href="/Other_Page">wiki link</a> inside it.</p>
    <ul>
      <li>First bullet point</li>
      <li>Second bullet point</li>
    </ul>
    <br/>
    <img src="/diagram.png" alt="diagram"/>
    <!--
    NewPP limit report
    Parser cache timing info that should never appear in extracted text
    -->
    <div class="printfooter" data-nosnippet="">Retrieved from "<a href="/index.php?title=X&amp;oldid=209">http://wiki2.bio2.rwth-aachen.de/index.php?title=X&amp;oldid=209</a>"</div>
  </div></div>
  <!-- end content -->
</div>
<div id="footer">Site footer text that should be excluded</div>
</body>
</html>
"""


def _extract(html):
    extractor = wiki._MediaWikiContentExtractor()
    extractor.feed(html)
    return extractor.get_text()


def test_extractor_gets_real_content():
    text = _extract(SAMPLE_HTML)
    assert "This is the real article text about Systems Neurophysiology." in text
    assert "A second paragraph with a wiki link inside it." in text
    assert "First bullet point" in text
    assert "Second bullet point" in text


def test_extractor_excludes_sibling_chrome():
    text = _extract(SAMPLE_HTML)
    assert "Nav link that should be excluded" not in text
    assert "Site footer text that should be excluded" not in text


def test_extractor_strips_editsection_links():
    text = _extract(SAMPLE_HTML)
    assert "Overview" in text  # the real heading text is kept
    assert "[edit]" not in text  # but the edit-section link right after it is not


def test_extractor_strips_printfooter_and_comments():
    text = _extract(SAMPLE_HTML)
    assert "Retrieved from" not in text
    assert "NewPP limit report" not in text
    assert "Parser cache timing info" not in text


def test_extractor_real_saved_page():
    """Regression check against the actual page fetched from the live wiki
    during development (docs/architecture.md documents this verification)."""
    text = _extract(REAL_SAVED_PAGE_HTML)
    assert "BrainCloud" in text
    assert "Brain Lab Rules" in text
    assert "edit source" not in text
    assert "Retrieved from" not in text


def test_extractor_annotates_internal_links_with_real_page_title():
    """MediaWiki link text and the actual page title routinely differ (piped
    links) - the model needs the real title, not the visible label, to make
    a working follow-up fetch_wiki_page call."""
    text = _extract(REAL_SAVED_PAGE_HTML)
    assert 'Brain Lab Rules [page_title: "Brain_Lab_Rules"]' in text


def test_extractor_does_not_annotate_edit_or_permalink_links():
    text = _extract(REAL_SAVED_PAGE_HTML)
    # The printfooter's permalink (index.php?title=...&oldid=...) and the
    # editsection's edit link are both stripped entirely (already covered by
    # other tests), so no [page_title: ...] marker should appear for either.
    assert text.count("[page_title:") == 1


def test_extractor_does_not_annotate_non_index_php_links():
    html_with_short_link = SAMPLE_HTML  # uses href="/Other_Page", not /index.php/Other_Page
    text = _extract(html_with_short_link)
    assert "[page_title:" not in text
    assert "A second paragraph with a wiki link inside it." in text


def test_url_construction_replaces_spaces_with_underscores():
    with mock.patch("wiki.requests.get") as mock_get:
        mock_get.return_value = _fake_response(200, SAMPLE_HTML)
        wiki.fetch_wiki_page("Some Page Name")
    called_url = mock_get.call_args[0][0]
    assert called_url == "http://wiki2.bio2.rwth-aachen.de/index.php/Some_Page_Name"


def test_url_stays_http_not_https():
    assert wiki.WIKI_BASE_URL.startswith("http://")
    assert not wiki.WIKI_BASE_URL.startswith("https://")


@pytest.mark.parametrize("bad_title", ["", "../../etc/passwd", "..", "a" * 3 + "/../b"])
def test_invalid_page_titles_are_rejected_before_any_request(bad_title):
    with mock.patch("wiki.requests.get") as mock_get:
        with pytest.raises(wiki.WikiError):
            wiki.fetch_wiki_page(bad_title)
    mock_get.assert_not_called()


def _fake_response(status_code, text):
    response = mock.MagicMock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 300
    response.text = text
    return response


def test_fetch_wiki_page_404_raises_wiki_error_with_helpful_message():
    with mock.patch("wiki.requests.get", return_value=_fake_response(404, "")):
        with pytest.raises(wiki.WikiError, match="no page titled"):
            wiki.fetch_wiki_page("Definitely_Not_A_Real_Page")


def test_fetch_wiki_page_non_404_error_status_raises_wiki_error():
    with mock.patch("wiki.requests.get", return_value=_fake_response(500, "")):
        with pytest.raises(wiki.WikiError, match="HTTP 500"):
            wiki.fetch_wiki_page("Some_Page")


def test_fetch_wiki_page_connection_error_raises_wiki_error():
    import requests

    with mock.patch("wiki.requests.get", side_effect=requests.exceptions.ConnectionError("no route")):
        with pytest.raises(wiki.WikiError, match="could not reach the wiki"):
            wiki.fetch_wiki_page("Some_Page")


def test_fetch_wiki_page_success_returns_clean_content():
    with mock.patch("wiki.requests.get", return_value=_fake_response(200, SAMPLE_HTML)):
        result = wiki.fetch_wiki_page("Systems_Neurophysiology")
    assert result["title"] == "Systems_Neurophysiology"
    assert "This is the real article text" in result["content"]
    assert result["truncated"] is False


def test_fetch_wiki_page_truncates_long_content():
    long_html = SAMPLE_HTML.replace(
        "<p>This is the real article text about <b>Systems Neurophysiology</b>.</p>",
        "<p>" + ("word " * 5000) + "</p>",
    )
    with mock.patch("wiki.requests.get", return_value=_fake_response(200, long_html)):
        result = wiki.fetch_wiki_page("Long_Page")
    assert result["truncated"] is True
    assert len(result["content"]) == wiki.MAX_WIKI_PAGE_CHARS


def test_wiki_fetch_tool_schema_is_well_formed():
    schema = wiki.WIKI_FETCH_TOOL_SCHEMA
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "fetch_wiki_page"
    assert "page_title" in schema["function"]["parameters"]["properties"]
    assert schema["function"]["parameters"]["required"] == ["page_title"]


# Trimmed to the essentials from the real page fetched during development
# (scratchpad/wiki_page.html) - keeps this test file self-contained while
# still exercising the exact structure the live server actually returns.
REAL_SAVED_PAGE_HTML = """<!DOCTYPE html>
<html><head><title>Systems Neurophysiology - Wiki Bio2</title></head>
<body>
<div id="bodyContent" class="monobook-body">
<!-- start content -->
<div id="mw-content-text" class="mw-body-content"><div class="mw-content-ltr mw-parser-output" lang="en" dir="ltr">
<h2><span class="mw-headline" id="Welcome_to_the_BrainCloud">Welcome to the <b>BrainCloud</b></span><span class="mw-editsection"><span class="mw-editsection-bracket">[</span><a href="/index.php?title=Systems_Neurophysiology&amp;action=edit&amp;section=1" title="Edit section's source code: Welcome to the BrainCloud">edit source</a><span class="mw-editsection-bracket">]</span></span></h2>
<p>including a collection of important lab rules, schedules, methods, etc</p>
<ul><li><a href="/index.php/Brain_Lab_Rules">Brain Lab Rules</a></li></ul>
<!--
NewPP limit report
Parsed by mediawiki
Saved in parser cache with key wikibio2-mediawiki-:pcache:idhash:3-0!canonical and timestamp 20260803063526
-->
<div class="printfooter" data-nosnippet="">Retrieved from "<a href="http://wiki2.bio2.rwth-aachen.de/index.php?title=Systems_Neurophysiology&amp;oldid=209">http://wiki2.bio2.rwth-aachen.de/index.php?title=Systems_Neurophysiology&amp;oldid=209</a>"</div></div></div>
<!-- end content -->
</div>
</body></html>
"""
