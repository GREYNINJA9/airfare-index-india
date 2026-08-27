import pytest
from playwright.async_api import async_playwright


@pytest.mark.asyncio
async def test_playwright_browser_launch_and_navigate() -> None:
    """Verify Chromium launches, navigates to safe test URL, and asserts title."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Safe public test page only - DO NOT scrape airline sites in smoke tests
        response = await page.goto("https://example.com", timeout=30000)

        assert response is not None
        assert response.status == 200

        title = await page.title()
        assert "Example Domain" in title

        await browser.close()
