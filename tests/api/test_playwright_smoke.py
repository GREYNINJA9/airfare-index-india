import pytest
from patchright.async_api import async_playwright


@pytest.mark.asyncio
async def test_patchright_browser_launch_and_navigate() -> None:
    """Verify Patchright can launch Chromium and open example.com."""
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
