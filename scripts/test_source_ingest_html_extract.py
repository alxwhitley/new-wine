#!/usr/bin/env python3
"""Behavior checks for stdlib-only queued article body isolation.

No bs4/lxml dependency is available in backend/requirements.txt or this
environment, so source_ingest_queue.html_extract is built entirely on
html.parser.HTMLParser. These tests exercise real markup shapes, not mocks.
"""

import unittest

from source_ingest_queue.html_extract import (
    ExtractedArticle,
    HtmlRejected,
    extract_article_bounded,
)


def _wrap(body: str, *, title: str = "A Real Post Title") -> str:
    return (
        "<html><head><title>%s</title></head><body>%s</body></html>" % (title, body)
    )


class ValidArticleTests(unittest.TestCase):
    def test_extracts_article_tag_text_and_title(self):
        html = _wrap(
            "<article><h1>Grace and Truth</h1>"
            "<p>The first paragraph of the article carries real teaching "
            "content that a reader came here for, spanning enough words to "
            "clear any thin-content floor comfortably by itself already.</p>"
            "<p>The second paragraph continues the same real teaching with "
            "more substantive sentences so the total word count is well "
            "past the minimum floor for a defensible article body to pass.</p>"
            "</article>"
        )

        result = extract_article_bounded(html.encode("utf-8"))

        self.assertIsInstance(result, ExtractedArticle)
        self.assertEqual(result.title, "A Real Post Title")
        self.assertIn("first paragraph of the article", result.text)
        self.assertIn("second paragraph continues", result.text)
        self.assertEqual(result.evidence["container"], "article")
        self.assertGreater(result.word_count, 40)

    def test_falls_back_to_h1_title_when_title_tag_is_empty(self):
        html = (
            "<html><head><title>   </title></head><body>"
            "<article><h1>The Real Heading</h1>"
            "<p>Enough real article prose here to clear the thin-content "
            "floor by a wide margin so this test only exercises title "
            "fallback behavior and nothing about content-length rejection "
            "paths that other tests in this file already cover directly, "
            "with several additional words added here on purpose so the "
            "total count comfortably clears the fifty word minimum floor.</p>"
            "</article></body></html>"
        )

        result = extract_article_bounded(html.encode("utf-8"))
        self.assertEqual(result.title, "The Real Heading")


class NavigationAndFooterRemovalTests(unittest.TestCase):
    def test_strips_nav_header_footer_aside_script_and_style(self):
        html = _wrap(
            "<header><nav><a href='/'>Home</a><a href='/about'>About</a></nav></header>"
            "<article><p>Real article prose that must survive extraction and "
            "stay in the output text after every non-article region around "
            "it has been removed by the extractor's structural filtering.</p>"
            "<p>A second paragraph of real teaching content, long enough "
            "combined with the first to clear the minimum word floor for "
            "a defensible article body on its own without any junk text.</p>"
            "</article>"
            "<aside class='sidebar'><h3>Related posts</h3><ul><li>Other post</li></ul></aside>"
            "<footer><p>Copyright 2026. All rights reserved. Contact us.</p></footer>"
            "<script>trackPageView();</script>"
            "<style>.article { color: red; }</style>"
        )

        result = extract_article_bounded(html.encode("utf-8"))

        self.assertIn("Real article prose", result.text)
        self.assertNotIn("Home", result.text)
        self.assertNotIn("About", result.text)
        self.assertNotIn("Related posts", result.text)
        self.assertNotIn("Other post", result.text)
        self.assertNotIn("Copyright", result.text)
        self.assertNotIn("trackPageView", result.text)
        self.assertNotIn("color: red", result.text)

    def test_strips_class_and_id_marked_junk_regions_without_article_tag(self):
        html = _wrap(
            "<div class='site-nav-wrapper'><a href='/'>Home</a><a href='/x'>X</a></div>"
            "<div id='main-content'>"
            "<h1>A Real Post</h1>"
            "<p>This div-based container carries the genuine article prose "
            "with enough real words to win the heuristic content-density "
            "scoring against every junk-marked sibling region on this page.</p>"
            "<p>A second paragraph keeps the winning container's word count "
            "safely above the minimum floor so this test only exercises "
            "junk-region stripping, not the thin-content rejection path.</p>"
            "</div>"
            "<div class='newsletter-signup'><p>Subscribe to our newsletter for updates!</p></div>"
            "<div id='comments-section'><p>Great post, thanks for sharing this with us!</p></div>"
        )

        result = extract_article_bounded(html.encode("utf-8"))

        self.assertIn("A Real Post", result.text)
        self.assertIn("genuine article prose", result.text)
        self.assertNotIn("Subscribe to our newsletter", result.text)
        self.assertNotIn("Great post, thanks", result.text)


class HeuristicContainerSelectionTests(unittest.TestCase):
    def test_picks_the_largest_low_link_density_container_when_no_article_tag(self):
        html = _wrap(
            "<div class='sidebar-links'>"
            "<a href='/a'>Link A</a><a href='/b'>Link B</a><a href='/c'>Link C</a>"
            "</div>"
            "<div class='post-body'>"
            "<h1>Untagged Post</h1>"
            "<p>Real prose living inside a plain div with no explicit article "
            "or main tag at all, which is common on older or simpler blog "
            "themes that this extractor must still be able to handle well.</p>"
            "<p>A second paragraph of genuine teaching content, long enough "
            "that this container clearly out-scores the link-heavy sidebar "
            "div sitting next to it in the same page's raw HTML markup.</p>"
            "</div>"
        )

        result = extract_article_bounded(html.encode("utf-8"))

        self.assertIn("Real prose living inside a plain div", result.text)
        self.assertNotIn("Link A", result.text)
        self.assertEqual(result.evidence["container"], "heuristic")


class MissingArticleBodyTests(unittest.TestCase):
    def test_rejects_a_page_with_no_defensible_content_container(self):
        html = _wrap(
            "<div class='ad-slot'>Buy now! Limited offer! Click here to save!</div>"
            "<div class='social-share'><a href='#'>Tweet</a><a href='#'>Share</a></div>"
        )

        with self.assertRaises(HtmlRejected) as raised:
            extract_article_bounded(html.encode("utf-8"))
        self.assertEqual(raised.exception.code, "no_article_body")


class LoginPageTests(unittest.TestCase):
    def test_rejects_a_thin_page_with_a_password_field(self):
        html = _wrap(
            "<div class='login-form'>"
            "<h1>Sign in</h1>"
            "<form><input type='text' name='user'>"
            "<input type='password' name='pass'>"
            "<button>Log in</button></form>"
            "</div>"
        )

        with self.assertRaises(HtmlRejected) as raised:
            extract_article_bounded(html.encode("utf-8"))
        self.assertEqual(raised.exception.code, "login_page")

    def test_does_not_reject_a_real_article_that_merely_has_a_login_widget(self):
        long_paragraph = " ".join(["word%d" % i for i in range(200)])
        html = _wrap(
            "<div class='header-login-widget'>"
            "<form><input type='text' name='user'>"
            "<input type='password' name='pass'></form>"
            "</div>"
            "<article><h1>A Full Length Article</h1><p>%s</p></article>" % long_paragraph
        )

        result = extract_article_bounded(html.encode("utf-8"))
        self.assertIn("word0", result.text)
        self.assertIn("word199", result.text)


class EmptyOrThinArticleTests(unittest.TestCase):
    def test_rejects_an_empty_article_container(self):
        html = _wrap("<article></article>")

        with self.assertRaises(HtmlRejected) as raised:
            extract_article_bounded(html.encode("utf-8"))
        self.assertEqual(raised.exception.code, "article_too_thin")

    def test_rejects_an_article_below_the_minimum_word_floor(self):
        html = _wrap("<article><h1>Short</h1><p>Just a few words here.</p></article>")

        with self.assertRaises(HtmlRejected) as raised:
            extract_article_bounded(html.encode("utf-8"))
        self.assertEqual(raised.exception.code, "article_too_thin")


class ExtractionFailureTests(unittest.TestCase):
    def test_wraps_unexpected_parser_faults_as_extraction_failure(self):
        class ExplodingParser:
            def __init__(self, *args, **kwargs):
                pass

            def feed(self, data):
                raise RuntimeError("boom")

            def close(self):
                pass

        html = _wrap("<article><p>Irrelevant content for this fault-injection test.</p></article>")

        with self.assertRaises(HtmlRejected) as raised:
            extract_article_bounded(
                html.encode("utf-8"), parser_factory=ExplodingParser
            )
        self.assertEqual(raised.exception.code, "html_parse_failure")


if __name__ == "__main__":
    unittest.main()
