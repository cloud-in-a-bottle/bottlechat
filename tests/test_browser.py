import re

from openhost_test_harness import OpenhostStack
from playwright.sync_api import Page
from playwright.sync_api import expect


def test_a_conversation_can_be_had_in_the_browser(stack: OpenhostStack, page: Page) -> None:
    stack.playwright_login(page)
    page.goto(stack.url)

    expect(page.get_by_role("heading", name="What's on your mind?")).to_be_visible()
    composer = page.get_by_role("textbox", name="Message")
    expect(composer).to_be_enabled(timeout=15_000)

    composer.fill("how do python generators work")
    page.get_by_role("button", name="Send message").click()

    expect(page.get_by_text("how do python generators work")).to_be_visible()
    expect(page.get_by_text("Generators are lazy iterators.")).to_be_visible(timeout=60_000)
    # The URL becomes the chat's stable link as soon as the chat exists.
    expect(page).to_have_url(re.compile(r"/c/[^/]+$"))

    # The generated title lands in the sidebar without a reload.
    active_row = page.locator('.chat-row[data-active="true"] .chat-row__title')
    expect(active_row).to_have_text("Python generators", timeout=60_000)


def test_a_chat_survives_a_reload_and_is_searchable(stack: OpenhostStack, page: Page) -> None:
    stack.playwright_login(page)
    page.goto(stack.url)
    composer = page.get_by_role("textbox", name="Message")
    expect(composer).to_be_enabled(timeout=15_000)
    composer.fill("tell me about capybaras")
    page.get_by_role("button", name="Send message").click()
    expect(page.get_by_text("Generators are lazy iterators.")).to_be_visible(timeout=60_000)

    chat_url = page.url
    page.reload()
    expect(page.get_by_text("tell me about capybaras")).to_be_visible()
    expect(page.get_by_text("Generators are lazy iterators.")).to_be_visible()
    assert page.url == chat_url

    page.get_by_label("Search chats").fill("capybaras")
    expect(page.locator(".chat-row__snippet mark")).to_have_text("capybaras", timeout=10_000)


def test_reasoning_is_shown_in_a_collapsible_block(stack: OpenhostStack, page: Page) -> None:
    stack.playwright_login(page)
    page.goto(stack.url)
    expect(page.get_by_role("textbox", name="Message")).to_be_enabled(timeout=15_000)
    page.get_by_label("Reasoning effort").select_option("high")
    page.get_by_role("textbox", name="Message").fill("think hard about this")
    page.get_by_role("button", name="Send message").click()

    expect(page.get_by_text("Generators are lazy iterators.")).to_be_visible(timeout=60_000)
    toggle = page.locator(".reasoning__toggle")
    expect(toggle).to_be_visible()
    # Collapsed once the answer arrives, so the answer is what you see.
    expect(page.locator(".reasoning__body")).to_have_count(0)
    toggle.click()
    expect(page.locator(".reasoning__body")).to_contain_text("The user wants a short explanation")


def test_a_shared_link_renders_for_a_logged_out_visitor(stack: OpenhostStack, page: Page, browser) -> None:  # type: ignore[no-untyped-def]
    stack.playwright_login(page)
    page.goto(stack.url)
    expect(page.get_by_role("textbox", name="Message")).to_be_enabled(timeout=15_000)
    page.get_by_role("textbox", name="Message").fill("something worth sharing")
    page.get_by_role("button", name="Send message").click()
    expect(page.get_by_text("Generators are lazy iterators.")).to_be_visible(timeout=60_000)

    page.get_by_role("button", name="Share").click()
    page.get_by_role("button", name="Create link").click()
    share_url = page.locator(".share-url input").input_value()
    assert "/share/" in share_url

    anonymous = browser.new_context()
    try:
        visitor = anonymous.new_page()
        visitor.goto(share_url)
        expect(visitor.get_by_text("something worth sharing")).to_be_visible(timeout=20_000)
        expect(visitor.get_by_text("Shared from bottlechat")).to_be_visible()
        # A read-only view: no way to keep talking.
        expect(visitor.get_by_role("textbox", name="Message")).to_have_count(0)
    finally:
        anonymous.close()


def test_the_mobile_layout_hides_the_sidebar_behind_a_drawer(stack: OpenhostStack, page: Page) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    stack.playwright_login(page)
    page.goto(stack.url)

    sidebar = page.locator(".sidebar")
    expect(sidebar).to_have_attribute("data-open", "false")
    expect(sidebar).not_to_be_in_viewport()

    page.get_by_label("Open chat history").click()
    expect(sidebar).to_have_attribute("data-open", "true")
    expect(sidebar).to_be_in_viewport()

    # Following a chat link closes the drawer again rather than leaving it over the answer.
    page.get_by_role("link", name="bottlechat").click()
    expect(sidebar).not_to_be_in_viewport()
