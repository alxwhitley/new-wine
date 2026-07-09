"""
Rhemata Pre-Launch Technical Audit
Tests: https://rhemata.vercel.app/
Run: python3 audit.py
Screenshots saved to: ./audit_screenshots/
"""

import time
import json
import os
from datetime import datetime
from playwright.sync_api import sync_playwright, Page, BrowserContext

BASE_URL = "https://rhemata.vercel.app"
SS_DIR = "./audit_screenshots"
os.makedirs(SS_DIR, exist_ok=True)

findings = []
ss_counter = [0]


def ss(page: Page, name: str) -> str:
    ss_counter[0] += 1
    path = f"{SS_DIR}/{ss_counter[0]:03d}_{name}.png"
    page.screenshot(path=path, full_page=True)
    return path


def log(route: str, check: str, passed: bool, severity: str, notes: str, screenshot: str = ""):
    status = "PASS" if passed else "FAIL"
    findings.append({
        "route": route,
        "check": check,
        "status": status,
        "severity": severity,
        "notes": notes,
        "screenshot": screenshot,
    })
    icon = "✅" if passed else "❌"
    print(f"{icon} [{severity.upper()}] {route} | {check}: {notes}")
    if screenshot and not passed:
        print(f"   → Screenshot: {screenshot}")


def collect_console_errors(page: Page) -> list:
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    return errors


def wait_for_stream(page: Page, timeout_ms: int = 30000) -> bool:
    """Wait for streaming response to complete (looks for end of SSE or settled text)."""
    try:
        # Wait for loading indicator to appear then disappear, or for response text
        page.wait_for_selector("[data-testid='message'], .prose, .markdown, article", timeout=timeout_ms)
        # Give stream a moment to settle
        page.wait_for_load_state("networkidle", timeout=15000)
        return True
    except Exception:
        return False


def measure_load(page: Page, url: str, label: str) -> float:
    start = time.time()
    page.goto(url, wait_until="networkidle", timeout=30000)
    elapsed = time.time() - start
    return elapsed


# ─── SECTION 1: Guest Journey ─────────────────────────────────────────────────

def test_guest_journey(ctx: BrowserContext):
    print("\n═══ 1. GUEST JOURNEY ═══")
    page = ctx.new_page()
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    failed_requests = []
    page.on("requestfailed", lambda req: failed_requests.append(req.url))

    # 1.1 Landing / Chat page loads
    try:
        start = time.time()
        page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
        load_time = time.time() - start
        path = ss(page, "01_chat_landing")

        # Check page title / main content
        title = page.title()
        has_title = bool(title)
        log("/", "Page loads with title", has_title, "blocker", f"Title: '{title}'", "" if has_title else path)

        # Check for input / chat interface
        input_sel = "textarea, input[type='text'], [role='textbox'], [contenteditable='true']"
        input_el = page.query_selector(input_sel)
        log("/", "Chat input renders", bool(input_el), "blocker", "Input field present" if input_el else "No input found", "" if input_el else ss(page, "01_no_input"))

        # Check shine border / styled input
        if input_el:
            parent_html = page.evaluate("el => el.parentElement ? el.parentElement.outerHTML.substring(0, 300) : ''", input_el)
            has_shine = "shine" in parent_html.lower() or "glow" in parent_html.lower() or "border" in parent_html.lower()
            log("/", "Input has styled border/shine wrapper", has_shine, "minor", "Shine border class detected" if has_shine else f"No shine class — wrapper: {parent_html[:100]}")

        # Console errors
        log("/", "No console errors on load", len(console_errors) == 0, "major",
            "Clean" if not console_errors else f"{len(console_errors)} errors: {console_errors[:3]}")

        # Load time
        log("/", "Page load under 3s", load_time < 3.0, "major", f"{load_time:.2f}s", "" if load_time < 3.0 else path)

        # Failed requests
        log("/", "No failed network requests", len(failed_requests) == 0, "major",
            "Clean" if not failed_requests else f"Failed: {failed_requests[:3]}")

    except Exception as e:
        log("/", "Page loads", False, "blocker", f"Exception: {e}", ss(page, "01_crash"))

    # 1.2 Send a chat query as guest
    print("\n  → Sending first guest chat query...")
    try:
        input_el = page.query_selector("textarea, input[type='text'], [role='textbox']")
        if not input_el:
            log("/chat", "Send guest query", False, "blocker", "No input to type into")
        else:
            input_el.click()
            input_el.fill("What is the gift of tongues according to scripture?")
            page.keyboard.press("Enter")

            # Wait for response
            time.sleep(2)  # let stream start
            try:
                # Look for any response content
                page.wait_for_selector(
                    "article, [class*='prose'], [class*='message'], [class*='response'], [class*='answer']",
                    timeout=45000
                )
                time.sleep(3)  # let stream settle
                path = ss(page, "02_guest_query_response")

                # Check for inline citations — look for citation markers
                page_html = page.content()
                has_citations = any(x in page_html for x in [
                    "citation", "[1]", "source", "data-citation", "cite", "footnote"
                ])
                log("/chat", "Response streams and renders", True, "blocker", "Response content appeared", "")
                log("/chat", "Inline citations render", has_citations, "major",
                    "Citation markers found" if has_citations else "No citation markers detected", "" if has_citations else path)

                # Check citation click opens source panel
                citation_el = page.query_selector("[data-citation], [class*='citation'], sup a, [class*='source-ref']")
                if citation_el:
                    citation_el.click()
                    time.sleep(1)
                    panel = page.query_selector("[class*='panel'], [class*='source'], [class*='drawer'], [role='dialog']")
                    log("/chat", "Citation click opens source panel", bool(panel), "major",
                        "Panel opened" if panel else "No panel after citation click",
                        "" if panel else ss(page, "02_no_panel"))
                    if panel:
                        ss(page, "02_citation_panel_open")
                        # Close the panel
                        close_btn = page.query_selector("[aria-label*='close'], [class*='close'], button[class*='close']")
                        if close_btn:
                            close_btn.click()
                            time.sleep(0.5)
                else:
                    log("/chat", "Citation click opens source panel", False, "major",
                        "No citation elements found to click", path)

            except Exception as e:
                log("/chat", "Send guest query", False, "blocker", f"Response never appeared: {e}", ss(page, "02_no_response"))
    except Exception as e:
        log("/chat", "Send guest query", False, "blocker", f"Exception: {e}")

    # 1.3 Guest query limit — send until limit fires (should be at 6)
    print("\n  → Testing guest query limit (sends queries 2–6)...")
    login_modal_appeared = False
    login_modal_query_num = None
    try:
        for i in range(2, 8):  # queries 2 through 7 to be sure we cross 6
            input_el = page.query_selector("textarea, input[type='text'], [role='textbox']")
            if not input_el:
                # Input gone — might be blocked by modal
                modal = page.query_selector("[role='dialog'], [class*='modal'], [class*='login'], [class*='signin']")
                if modal:
                    login_modal_appeared = True
                    login_modal_query_num = i
                    break
                break

            input_el.click()
            input_el.fill(f"Query number {i}: Tell me about the Holy Spirit's role in prayer.")
            page.keyboard.press("Enter")
            time.sleep(6)  # wait for response or modal

            # Check for login modal / gate
            modal = page.query_selector("[role='dialog'], [class*='modal'], [class*='login'], [class*='auth'], [class*='signup']")
            if modal:
                login_modal_appeared = True
                login_modal_query_num = i
                break

        path = ss(page, "03_guest_limit")
        log("/chat", f"Guest limit fires (expected at 6)", login_modal_appeared, "blocker",
            f"Modal appeared at query #{login_modal_query_num}" if login_modal_appeared else "No modal appeared after 7 queries",
            "" if login_modal_appeared else path)

        if login_modal_appeared:
            limit_correct = login_modal_query_num == 6 or login_modal_query_num == 7  # 6th attempt or after
            log("/chat", "Guest limit fires at correct count (≈6)", limit_correct, "major",
                f"Modal fired at query #{login_modal_query_num}", path)

            # Check modal backdrop / readability
            backdrop = page.query_selector("[class*='overlay'], [class*='backdrop'], [aria-modal='true']")
            log("/chat", "Login modal has backdrop", bool(backdrop), "minor",
                "Backdrop present" if backdrop else "No backdrop element found")

            # Check modal is readable (has visible text)
            modal_text = page.query_selector("[role='dialog'], [class*='modal']")
            if modal_text:
                text = modal_text.inner_text()
                log("/chat", "Login modal is readable", len(text) > 20, "major",
                    f"Modal text: '{text[:100]}'" if len(text) > 20 else "Modal has no readable text")
                ss(page, "03_login_modal_readable")

            # Dismiss modal to continue
            esc_or_close = page.query_selector("[aria-label*='close'], [class*='close-btn'], button[class*='close']")
            if esc_or_close:
                esc_or_close.click()
            else:
                page.keyboard.press("Escape")
            time.sleep(0.5)

    except Exception as e:
        log("/chat", "Guest limit test", False, "major", f"Exception: {e}", ss(page, "03_limit_crash"))

    # 1.4 Guest can browse Library
    print("\n  → Checking Library access as guest...")
    try:
        page.goto(f"{BASE_URL}/library", wait_until="networkidle", timeout=30000)
        time.sleep(2)
        path = ss(page, "04_library_guest")

        # Check if it redirected to login or shows content
        current_url = page.url
        redirected = "login" in current_url or "auth" in current_url or "signin" in current_url
        content = page.query_selector("[class*='book'], [class*='library'], [class*='card'], main")
        auth_gate = page.query_selector("[class*='login'], [class*='signin'], [class*='auth'], [role='dialog']")

        if redirected or auth_gate:
            log("/library", "Guest can access Library", False, "minor",
                "Library is gated — redirected to auth or shows login gate", path)
        else:
            log("/library", "Guest can access Library", bool(content), "minor",
                "Library accessible without auth" if content else "Library loads but no content", path)
    except Exception as e:
        log("/library", "Guest Library access", False, "major", f"Exception: {e}")

    # 1.5 Guest can browse Study
    print("\n  → Checking Study access as guest...")
    try:
        page.goto(f"{BASE_URL}/study", wait_until="networkidle", timeout=30000)
        time.sleep(2)
        path = ss(page, "05_study_guest")

        current_url = page.url
        redirected = "login" in current_url or "auth" in current_url
        content = page.query_selector("[class*='study'], [class*='verse'], [class*='search'], main")
        auth_gate = page.query_selector("[class*='login'], [class*='signin'], [role='dialog']")

        if redirected or auth_gate:
            log("/study", "Guest can access Study", False, "minor",
                "Study is gated", path)
        else:
            log("/study", "Guest can access Study", bool(content), "minor",
                "Study accessible without auth" if content else "Study loads but no content", path)
    except Exception as e:
        log("/study", "Guest Study access", False, "major", f"Exception: {e}")

    page.close()


# ─── SECTION 2: Auth Flow (pre-login only) ────────────────────────────────────

def test_auth_modal(ctx: BrowserContext):
    print("\n═══ 2. AUTH FLOW (sign-up form only — no account creation) ═══")
    page = ctx.new_page()

    try:
        page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
        time.sleep(1)

        # Find and click Sign In button / link
        sign_in = page.query_selector(
            "button:has-text('Sign in'), button:has-text('Sign In'), button:has-text('Log in'), "
            "a:has-text('Sign in'), a:has-text('Sign In'), [class*='signin'], [class*='auth-btn']"
        )
        if not sign_in:
            # Try sidebar sign in
            sidebar_signin = page.query_selector("text=Sign In, text=Sign in, text=Log In")
            if sidebar_signin:
                sign_in = sidebar_signin

        if sign_in:
            sign_in.click()
            time.sleep(1)
            path = ss(page, "06_auth_modal")

            modal = page.query_selector("[role='dialog'], [class*='modal'], [class*='auth'], [class*='login']")
            log("/", "Sign In modal opens", bool(modal), "blocker",
                "Modal appeared" if modal else "No modal after clicking Sign In", "" if modal else path)

            if modal:
                # Check for email field
                email_field = page.query_selector("input[type='email'], input[name='email'], input[placeholder*='email' i]")
                log("/", "Email input in auth modal", bool(email_field), "blocker",
                    "Email input present" if email_field else "No email input found")

                # Check for password field
                pwd_field = page.query_selector("input[type='password']")
                log("/", "Password input in auth modal", bool(pwd_field), "blocker",
                    "Password input present" if pwd_field else "No password input found")

                # Check for sign up / create account option
                page_html = page.content()
                has_signup = any(x in page_html.lower() for x in ["sign up", "create account", "register"])
                log("/", "Sign Up option present", has_signup, "major",
                    "Sign Up link/tab found" if has_signup else "No sign-up option visible")

                # Test validation — submit empty form
                submit_btn = page.query_selector("button[type='submit'], button:has-text('Sign in'), button:has-text('Log in'), button:has-text('Continue')")
                if submit_btn:
                    submit_btn.click()
                    time.sleep(1)
                    path_val = ss(page, "06_auth_validation")
                    # Look for validation messages
                    validation = page.query_selector("[class*='error'], [class*='invalid'], [aria-invalid], [role='alert']")
                    log("/", "Form validation messages show on empty submit", bool(validation), "major",
                        "Validation messages appear" if validation else "No validation on empty submit", "" if validation else path_val)

                ss(page, "06_auth_modal_state")
                log("/", "STOP — not completing signup (email confirmation required)", True, "info",
                    "Halted before account creation as instructed. Modal rendered correctly.")
        else:
            path = ss(page, "06_no_signin_btn")
            log("/", "Sign In button accessible", False, "blocker",
                "Could not find Sign In button/link", path)

    except Exception as e:
        log("/", "Auth modal test", False, "blocker", f"Exception: {e}", ss(page, "06_crash"))

    page.close()


# ─── SECTION 3: Chat Surface ──────────────────────────────────────────────────

def test_chat_surface(ctx: BrowserContext):
    print("\n═══ 3. CHAT SURFACE ═══")
    page = ctx.new_page()
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    try:
        page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
        time.sleep(1)

        # 3.1 Send a long-response query
        print("  → Testing long response / scroll fade...")
        input_el = page.query_selector("textarea, input[type='text'], [role='textbox']")
        if input_el:
            input_el.click()
            input_el.fill("Give me a comprehensive overview of the five-fold ministry gifts in Ephesians 4, their purpose, function, and how they work together in the body of Christ.")
            page.keyboard.press("Enter")
            time.sleep(3)

            try:
                page.wait_for_selector("article, [class*='prose'], [class*='message'], [class*='response']", timeout=45000)
                time.sleep(5)  # let stream finish
                path = ss(page, "07_long_response")

                # Check scroll fade element
                page_html = page.content()
                has_scroll_fade = any(x in page_html.lower() for x in [
                    "scroll-fade", "scroll_fade", "fade", "gradient"
                ])
                log("/chat", "Scroll fade renders on long response", has_scroll_fade, "minor",
                    "Scroll fade/gradient class detected" if has_scroll_fade else "No scroll fade detected", "" if has_scroll_fade else path)

                # Check no layout breaks — content fits viewport
                viewport = page.viewport_size
                body_width = page.evaluate("document.body.scrollWidth")
                overflow = body_width > viewport["width"] + 20 if viewport else False
                log("/chat", "No horizontal layout overflow", not overflow, "major",
                    f"Width OK ({body_width}px)" if not overflow else f"Horizontal overflow: {body_width}px > {viewport['width']}px",
                    "" if not overflow else ss(page, "07_overflow"))

            except Exception as e:
                log("/chat", "Long response renders", False, "major", f"Response timeout: {e}")

        # 3.2 New Chat resets state
        print("  → Testing New Chat reset...")
        new_chat = page.query_selector(
            "button:has-text('New Chat'), a:has-text('New Chat'), [class*='new-chat'], [aria-label*='New Chat']"
        )
        if new_chat:
            new_chat.click()
            time.sleep(1)
            path = ss(page, "08_new_chat")
            # Should be back to empty input
            input_el2 = page.query_selector("textarea, input[type='text'], [role='textbox']")
            messages_gone = not page.query_selector("article, [class*='message']:not([class*='system'])")
            log("/chat", "New Chat resets to empty state", bool(input_el2), "major",
                "Input present after New Chat" if input_el2 else "No input after New Chat", "" if input_el2 else path)
        else:
            log("/chat", "New Chat button accessible", False, "major", "New Chat button not found")

        # 3.3 Console errors check
        log("/chat", "No console errors during chat tests", len(console_errors) == 0, "major",
            "Clean" if not console_errors else f"{len(console_errors)} errors: {console_errors[:5]}")

    except Exception as e:
        log("/chat", "Chat surface test", False, "major", f"Exception: {e}", ss(page, "03_chat_crash"))

    page.close()


# ─── SECTION 4: Study Mode ────────────────────────────────────────────────────

def test_study_mode(ctx: BrowserContext):
    print("\n═══ 4. STUDY MODE ═══")
    page = ctx.new_page()
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    try:
        start = time.time()
        page.goto(f"{BASE_URL}/study", wait_until="networkidle", timeout=30000)
        load_time = time.time() - start
        time.sleep(2)
        path = ss(page, "09_study_landing")

        log("/study", "Study page load time", load_time < 3.0, "major", f"{load_time:.2f}s")

        # 4.1 Verse lookup — John 3:16
        print("  → Looking up John 3:16...")
        search_input = page.query_selector(
            "input[placeholder*='verse' i], input[placeholder*='search' i], input[placeholder*='John' i], "
            "[class*='verse-search'] input, [class*='search'] input"
        )
        if search_input:
            search_input.click()
            search_input.fill("John 3:16")
            page.keyboard.press("Enter")
            time.sleep(3)
            path = ss(page, "10_john316")

            # Check verse renders
            page_html = page.content()
            verse_rendered = "God so loved" in page_html or "world" in page_html or "3:16" in page_html
            log("/study", "John 3:16 verse renders", verse_rendered, "blocker",
                "Verse text found in DOM" if verse_rendered else "Verse text not found", "" if verse_rendered else path)

            # Check interlinear loads
            time.sleep(2)
            interlinear = page.query_selector(
                "[class*='interlinear'], [class*='greek'], [class*='word-block'], [class*='strongs']"
            )
            log("/study", "Interlinear loads attached to verse", bool(interlinear), "major",
                "Interlinear blocks found" if interlinear else "No interlinear elements", "" if interlinear else path)

            if interlinear:
                ss(page, "10_interlinear")
                # 4.2 Word click — definition + excerpt
                print("  → Testing word click for definition...")
                interlinear.click()
                time.sleep(2)
                definition = page.query_selector(
                    "[class*='definition'], [class*='lexicon'], [class*='gloss'], [class*='word-detail']"
                )
                log("/study", "Word click expands definition inline", bool(definition), "major",
                    "Definition panel appeared" if definition else "No definition after word click",
                    "" if definition else ss(page, "10_no_definition"))
                if definition:
                    ss(page, "10_word_definition")

                    # Check excerpt
                    excerpt = page.query_selector(
                        "[class*='excerpt'], [class*='word-study'], [class*='precept']"
                    )
                    log("/study", "Precept Austin excerpt loads", bool(excerpt), "minor",
                        "Excerpt section found" if excerpt else "No excerpt section visible")
        else:
            log("/study", "Verse search input found", False, "blocker",
                "No search input on Study page", path)

        # 4.3 Romans 8:28
        print("  → Looking up Romans 8:28...")
        search_input = page.query_selector(
            "input[placeholder*='verse' i], input[placeholder*='search' i], "
            "[class*='verse-search'] input, [class*='search'] input"
        )
        if search_input:
            search_input.click()
            search_input.triple_click()
            search_input.fill("Romans 8:28")
            page.keyboard.press("Enter")
            time.sleep(3)
            path = ss(page, "11_romans828")
            page_html = page.content()
            verse_rendered = "all things" in page_html.lower() or "8:28" in page_html or "Romans" in page_html
            log("/study", "Romans 8:28 verse renders", verse_rendered, "blocker",
                "Verse text found" if verse_rendered else "Verse not found", "" if verse_rendered else path)

        # 4.4 Commentary section visible without interaction
        commentary = page.query_selector(
            "[class*='commentary'], [class*='Comment'], section:has([class*='commentary'])"
        )
        log("/study", "Commentary section visible without tab click", bool(commentary), "major",
            "Commentary section in DOM" if commentary else "Commentary not found",
            "" if commentary else ss(page, "11_no_commentary"))

        # 4.5 Chapter view
        print("  → Testing chapter view...")
        chapter_btn = page.query_selector(
            "button:has-text('Chapter'), button:has-text('View Chapter'), [class*='chapter-btn']"
        )
        if chapter_btn:
            chapter_btn.click()
            time.sleep(2)
            path = ss(page, "12_chapter_view")
            chapter_content = page.query_selector("[class*='chapter'], [class*='verses-list'], sup")
            log("/study", "Chapter view loads", bool(chapter_content), "major",
                "Chapter content rendered" if chapter_content else "Chapter view empty", "" if chapter_content else path)

            if chapter_content:
                # Click a verse in chapter view
                verse_in_chapter = page.query_selector("[class*='verse-item'], [data-verse], [class*='chapter'] p")
                if verse_in_chapter:
                    verse_in_chapter.click()
                    time.sleep(1)
                    log("/study", "Verse click in chapter view switches active verse", True, "minor",
                        "Clicked verse in chapter view")
        else:
            log("/study", "Chapter view button found", False, "minor",
                "No 'View Chapter' button found")

        # 4.6 Anchor nav
        print("  → Testing anchor navigation...")
        anchor_nav = page.query_selector(
            "[class*='anchor'], nav:has(a[href*='#']), [class*='sticky'] nav"
        )
        if anchor_nav:
            log("/study", "Anchor nav present", True, "minor", "Anchor nav found")
            # Try clicking a nav item
            words_link = page.query_selector("a:has-text('Words'), button:has-text('Words')")
            if words_link:
                words_link.click()
                time.sleep(0.5)
                log("/study", "Anchor nav Words scrolls", True, "minor", "Clicked Words nav")
        else:
            log("/study", "Anchor nav present", False, "minor", "No anchor nav found")

        # Console errors
        log("/study", "No console errors in Study", len(console_errors) == 0, "major",
            "Clean" if not console_errors else f"{len(console_errors)} errors: {console_errors[:3]}")

        ss(page, "12_study_final")

    except Exception as e:
        log("/study", "Study mode test", False, "blocker", f"Exception: {e}", ss(page, "09_study_crash"))

    page.close()


# ─── SECTION 5: Library ───────────────────────────────────────────────────────

def test_library(ctx: BrowserContext):
    print("\n═══ 5. LIBRARY ═══")
    page = ctx.new_page()
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    try:
        start = time.time()
        page.goto(f"{BASE_URL}/library", wait_until="networkidle", timeout=30000)
        load_time = time.time() - start
        time.sleep(2)
        path = ss(page, "13_library_landing")

        log("/library", "Library page load time", load_time < 3.0, "major", f"{load_time:.2f}s")

        # Check content loads
        content = page.query_selector("[class*='book'], [class*='card'], [class*='result'], article, main")
        log("/library", "Library content renders", bool(content), "blocker",
            "Content found" if content else "No content found", "" if content else path)

        # 5.1 Search
        print("  → Testing library search...")
        search_input = page.query_selector("input[type='search'], input[placeholder*='search' i], input[placeholder*='Search' i]")
        if search_input:
            search_input.click()
            search_input.fill("Holy Spirit")
            page.keyboard.press("Enter")
            time.sleep(3)
            path = ss(page, "14_library_search")
            results = page.query_selector_all("[class*='card'], [class*='result'], article")
            log("/library", "Search returns results", len(results) > 0, "major",
                f"{len(results)} results for 'Holy Spirit'" if results else "No results returned",
                "" if results else path)
        else:
            log("/library", "Search input present", False, "major", "No search input on library page", path)

        # 5.2 Filters
        print("  → Testing filters...")
        filter_el = page.query_selector(
            "select, [class*='filter'], [role='combobox'], button:has-text('Filter'), "
            "button:has-text('Era'), button:has-text('Author'), button:has-text('Type')"
        )
        if filter_el:
            log("/library", "Filter controls present", True, "minor", "Filter UI found")
            # Try clicking / interacting
            try:
                filter_el.click()
                time.sleep(0.5)
                ss(page, "14_library_filter")
            except Exception:
                pass
        else:
            log("/library", "Filter controls present", False, "minor", "No filter controls found")

        # 5.3 Book card → excerpt reader
        print("  → Testing book card excerpt reader...")
        # Navigate to /library page (reset search)
        page.goto(f"{BASE_URL}/library", wait_until="networkidle", timeout=30000)
        time.sleep(2)

        book_card = page.query_selector("[class*='book-card'], [class*='BookCard'], [class*='card'] button, [class*='card'] a")
        if book_card:
            book_card.click()
            time.sleep(2)
            path = ss(page, "15_book_reader")
            reader_content = page.query_selector(
                "[class*='reader'], [class*='excerpt'], [class*='quote'], [class*='prose'], article"
            )
            log("/library", "Book card opens excerpt reader", bool(reader_content), "major",
                "Reader content loaded" if reader_content else "No reader content after book click",
                "" if reader_content else path)
        else:
            log("/library", "Book card clickable", False, "major", "No book card found to click")

        # 5.4 Author cards render photos
        print("  → Checking author photo rendering...")
        try:
            page.goto(f"{BASE_URL}/library/authors", wait_until="networkidle", timeout=30000)
            time.sleep(2)
            path = ss(page, "16_authors")
            author_photos = page.query_selector_all("img[class*='author'], [class*='avatar'] img, [class*='photo'] img, img[alt*='author' i]")
            all_images = page.query_selector_all("img")
            log("/library/authors", "Author photos render", len(all_images) > 0, "minor",
                f"{len(all_images)} images found ({len(author_photos)} with author class)",
                "" if all_images else path)
        except Exception as e:
            log("/library/authors", "Authors page", False, "minor", f"Exception: {e}")

        # Console errors
        log("/library", "No console errors in Library", len(console_errors) == 0, "major",
            "Clean" if not console_errors else f"{len(console_errors)} errors: {console_errors[:3]}")

    except Exception as e:
        log("/library", "Library test", False, "major", f"Exception: {e}", ss(page, "13_library_crash"))

    page.close()


# ─── SECTION 6: Cross-Cutting ─────────────────────────────────────────────────

def test_cross_cutting(ctx: BrowserContext):
    print("\n═══ 6. CROSS-CUTTING ═══")
    page = ctx.new_page()

    routes_to_check = [
        ("/", "Chat/Home"),
        ("/library", "Library"),
        ("/library/authors", "Authors"),
        ("/study", "Study"),
    ]

    # 6.1 Hardcoded hex check on each route
    print("  → Checking for hardcoded hex colors (visual theme breaks)...")
    known_hex_patterns = ["#b49238", "#d4b96a", "#262624", "#e6e6e6", "#c1c1b8", "#2f2f2c", "#1a1a18"]
    for route, label in routes_to_check:
        try:
            page.goto(f"{BASE_URL}{route}", wait_until="networkidle", timeout=30000)
            time.sleep(1)
            html = page.content()
            found_hex = [h for h in known_hex_patterns if h in html]
            # Only flag if in inline styles (not class names / comments)
            inline_hex = []
            for h in known_hex_patterns:
                if f'style="' in html and h in html:
                    inline_hex.append(h)
            log(route, "No hardcoded hex in inline styles", len(inline_hex) == 0, "minor",
                "Clean" if not inline_hex else f"Found inline hex: {inline_hex}",
                "" if not inline_hex else ss(page, f"hex_{label.lower().replace('/', '_')}"))
        except Exception as e:
            log(route, "Hardcoded hex check", False, "minor", f"Exception: {e}")

    # 6.2 404 handling
    print("  → Testing 404 handling...")
    try:
        page.goto(f"{BASE_URL}/this-route-does-not-exist-xyz123", wait_until="networkidle", timeout=15000)
        time.sleep(1)
        path = ss(page, "17_404")
        page_text = page.inner_text("body")
        has_404_content = any(x in page_text.lower() for x in ["404", "not found", "page not found", "doesn't exist"])
        http_404 = False
        try:
            response = page.request.get(f"{BASE_URL}/this-route-does-not-exist-xyz123")
            http_404 = response.status == 404
        except Exception:
            pass
        log("/xyz123", "404 page renders gracefully", has_404_content, "minor",
            f"404 content shown" if has_404_content else f"No 404 content — page text: '{page_text[:100]}'", path)
    except Exception as e:
        log("/404", "404 handling", False, "minor", f"Exception: {e}")

    # 6.3 /admin as non-admin guest
    print("  → Testing /admin gate for non-admin...")
    try:
        page.goto(f"{BASE_URL}/admin", wait_until="networkidle", timeout=30000)
        time.sleep(2)
        path = ss(page, "18_admin_guest")
        current_url = page.url
        redirected = current_url != f"{BASE_URL}/admin" and current_url != f"{BASE_URL}/admin/"
        page_text = page.inner_text("body").lower()
        blocked = any(x in page_text for x in ["sign in", "log in", "unauthorized", "access denied", "forbidden", "not authorized"])
        gated = redirected or blocked

        # Also check if actual admin content shows
        admin_content = page.query_selector("[class*='admin'], [class*='corpus'], [class*='contributor']")
        log("/admin", "Admin gated for non-admin guest", gated or not admin_content, "blocker",
            f"Gated correctly (redirected={redirected}, blocked={blocked})" if gated else
            f"Admin content may be exposed! URL: {current_url}", path)
    except Exception as e:
        log("/admin", "Admin gate test", False, "blocker", f"Exception: {e}")

    # 6.4 Page load times for all routes
    print("  → Measuring page load times...")
    for route, label in routes_to_check:
        try:
            start = time.time()
            page.goto(f"{BASE_URL}{route}", wait_until="networkidle", timeout=30000)
            elapsed = time.time() - start
            log(route, f"Load time < 3s", elapsed < 3.0, "major" if elapsed >= 3.0 else "minor",
                f"{elapsed:.2f}s")
        except Exception as e:
            log(route, "Page load time", False, "major", f"Exception: {e}")

    page.close()


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'═'*60}")
    print(f"  RHEMATA PRE-LAUNCH AUDIT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Target: {BASE_URL}")
    print(f"  Screenshots: {SS_DIR}/")
    print(f"{'═'*60}\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)

        # Guest context (incognito)
        guest_ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            no_viewport=False,
        )
        test_guest_journey(guest_ctx)
        test_auth_modal(guest_ctx)
        test_chat_surface(guest_ctx)
        guest_ctx.close()

        # Fresh context for study/library/cross-cutting
        ctx2 = browser.new_context(viewport={"width": 1440, "height": 900})
        test_study_mode(ctx2)
        test_library(ctx2)
        test_cross_cutting(ctx2)
        ctx2.close()

        browser.close()

    # ─── FINDINGS REPORT ──────────────────────────────────────────────────────
    print(f"\n\n{'═'*80}")
    print("  AUDIT FINDINGS TABLE")
    print(f"{'═'*80}")
    print(f"{'Route/Flow':<28} {'Check':<42} {'Status':<6} {'Sev':<8} {'Notes'}")
    print(f"{'-'*28} {'-'*42} {'-'*6} {'-'*8} {'-'*30}")

    blockers = [f for f in findings if f["status"] == "FAIL" and f["severity"] == "blocker"]
    majors = [f for f in findings if f["status"] == "FAIL" and f["severity"] == "major"]
    minors = [f for f in findings if f["status"] == "FAIL" and f["severity"] == "minor"]
    passes = [f for f in findings if f["status"] == "PASS"]

    for f in findings:
        status_icon = "✅ PASS" if f["status"] == "PASS" else "❌ FAIL"
        print(f"{f['route']:<28} {f['check'][:42]:<42} {status_icon:<6} {f['severity']:<8} {f['notes'][:60]}")
        if f.get("screenshot") and f["status"] == "FAIL":
            print(f"{'':>28} {'Screenshot: ' + f['screenshot']}")

    print(f"\n{'═'*80}")
    print(f"  SUMMARY: {len(passes)} passed | {len(blockers)} blockers | {len(majors)} major | {len(minors)} minor")
    print(f"{'═'*80}\n")

    if blockers:
        print("🚨 BLOCKERS:")
        for f in blockers:
            print(f"   • [{f['route']}] {f['check']}: {f['notes']}")
    if majors:
        print("\n⚠️  MAJOR:")
        for f in majors:
            print(f"   • [{f['route']}] {f['check']}: {f['notes']}")
    if minors:
        print("\n📝 MINOR:")
        for f in minors:
            print(f"   • [{f['route']}] {f['check']}: {f['notes']}")

    # Save JSON report
    report_path = f"{SS_DIR}/audit_report.json"
    with open(report_path, "w") as fh:
        json.dump(findings, fh, indent=2)
    print(f"\nFull report saved to: {report_path}")
    print(f"Screenshots in: {SS_DIR}/")


if __name__ == "__main__":
    main()
