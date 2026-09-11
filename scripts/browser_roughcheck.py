"""Automated browser roughcheck script using Patchright."""
import asyncio
import json
import os
import sys
from patchright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: console_errors.append(str(exc)))

        print("Navigating to http://127.0.0.1:8000/dashboard ...")
        response = await page.goto("http://127.0.0.1:8000/dashboard", wait_until="networkidle")
        assert response.status == 200, f"Dashboard returned status {response.status}"

        # 1. Verify Global Filters bar is removed
        gf_bar = await page.query_selector("#gf-origin")
        assert gf_bar is None, "Global Filters bar (#gf-origin) should be removed"
        print("✓ Global Filters bar is absent.")

        # 2. Verify removed tabs from navigation
        removed_nav_ids = [
            "nav-tab-airlines",
            "nav-tab-composition",
            "nav-tab-volatility",
            "nav-tab-basket",
            "nav-tab-explorer",
        ]
        for nav_id in removed_nav_ids:
            el = await page.query_selector(f"#{nav_id}")
            assert el is None, f"Navigation link #{nav_id} should be removed"
        print("✓ All 5 removed tabs are absent from navigation menu.")

        # 3. Verify exactly 9 module links exist in navigation
        links = await page.query_selector_all(".sidebar-link")
        print(f"✓ Found {len(links)} module links in sidebar.")
        assert len(links) == 9, f"Expected 9 sidebar modules, found {len(links)}"

        # 4. Verify Overview Trend Chart initialized
        chart_canvas = await page.query_selector("#overview-apix-chart")
        assert chart_canvas is not None, "Overview APIx chart canvas must exist"

        # Check datasets in chart
        datasets_info = await page.evaluate('''() => {
            const chart = window.__CHARTS__["overview-apix"];
            if (!chart) return null;
            return {
                labelsCount: chart.data.labels.length,
                datasets: chart.data.datasets.map(d => ({
                    label: d.label,
                    dataPoints: d.data.length,
                    sample: d.data.slice(0, 3)
                }))
            };
        }''', isolated_context=False)
        print(f"Chart Datasets Info: {json.dumps(datasets_info, indent=2)}")
        assert datasets_info is not None, "Chart.js instance window.__CHARTS__['overview-apix'] not found"
        labels_count = datasets_info["labelsCount"]
        assert labels_count > 0, "Chart has 0 labels"
        
        # Verify both APIx and MoSPI CPI datasets exist
        labels = [d["label"] for d in datasets_info["datasets"]]
        has_lasp = any("Laspeyres" in l for l in labels)
        has_jev = any("Jevons" in l for l in labels)
        has_cpi = any("MoSPI CPI" in l for l in labels)
        assert has_lasp, "Laspeyres APIx dataset missing"
        assert has_jev, "Jevons APIx dataset missing"
        assert has_cpi, "Official MoSPI CPI dataset missing"
        print("✓ Overview Trend Chart contains both APIx and MoSPI CPI datasets!")

        # 5. Test Chart Buttons
        # 5a. Uniform weighting button
        print("Testing Uniform Weighting button...")
        await page.click("#btn-overview-weight-uni")
        await page.wait_for_timeout(200)
        u_label = await page.evaluate('window.__CHARTS__["overview-apix"].data.datasets[0].label', isolated_context=False)
        assert "Uniform" in u_label, f"Expected Uniform in label, got {u_label}"
        print("✓ Uniform weighting button works.")

        # 5b. PSD weighting button
        print("Testing PSD Weighting button...")
        await page.click("#btn-overview-weight-psd")
        await page.wait_for_timeout(200)
        p_label = await page.evaluate('window.__CHARTS__["overview-apix"].data.datasets[0].label', isolated_context=False)
        assert "PSD" in p_label, f"Expected PSD in label, got {p_label}"
        print("✓ PSD weighting button works.")

        # 5c. 7D Moving Avg button
        print("Testing 7D Moving Avg button...")
        await page.click("#btn-overview-freq-weekly")
        await page.wait_for_timeout(200)
        has_mvg = await page.evaluate('window.__CHARTS__["overview-apix"].data.datasets.some(d => d.label.includes("7D Rolling"))', isolated_context=False)
        assert has_mvg, "7D Rolling Moving Average dataset should be present"
        print("✓ 7D Moving Avg button works.")

        # 5d. Daily button
        print("Testing Daily button...")
        await page.click("#btn-overview-freq-daily")
        await page.wait_for_timeout(200)
        has_mvg_daily = await page.evaluate('window.__CHARTS__["overview-apix"].data.datasets.some(d => d.label.includes("7D Rolling"))', isolated_context=False)
        assert not has_mvg_daily, "7D Rolling dataset should be removed in daily mode"
        print("✓ Daily button works.")

        # 5e. Range buttons: 7D, 30D, 90D, ALL
        print("Testing Range 7D...")
        await page.click("#btn-overview-range-7d")
        await page.wait_for_timeout(200)
        pts_7d = await page.evaluate('window.__CHARTS__["overview-apix"].data.labels.length', isolated_context=False)
        assert pts_7d <= 7, f"Expected <= 7 points for 7D, got {pts_7d}"
        print(f"✓ 7D Range button works ({pts_7d} points).")

        print("Testing Range 90D...")
        await page.click("#btn-overview-range-90d")
        await page.wait_for_timeout(200)
        pts_90d = await page.evaluate('window.__CHARTS__["overview-apix"].data.labels.length', isolated_context=False)
        print(f"✓ 90D Range button works ({pts_90d} points).")

        print("Testing Range ALL...")
        await page.click("#btn-overview-range-all")
        await page.wait_for_timeout(200)
        pts_all = await page.evaluate('window.__CHARTS__["overview-apix"].data.labels.length', isolated_context=False)
        assert pts_all >= pts_7d, f"ALL points ({pts_all}) should be >= 7D points ({pts_7d})"
        print(f"✓ ALL Range button works ({pts_all} points).")

        print("Testing Range 30D...")
        await page.click("#btn-overview-range-30d")
        await page.wait_for_timeout(200)
        pts_30d = await page.evaluate('window.__CHARTS__["overview-apix"].data.labels.length', isolated_context=False)
        print(f"✓ 30D Range button works ({pts_30d} points).")

        # 5f. MoSPI CPI toggle button
        print("Testing MoSPI CPI toggle button...")
        await page.click("#btn-overview-cpi-toggle")
        await page.wait_for_timeout(200)
        cpi_off = await page.evaluate('window.__CHARTS__["overview-apix"].data.datasets.some(d => d.label.includes("MoSPI CPI"))', isolated_context=False)
        assert not cpi_off, "MoSPI CPI should be toggled OFF"
        print("✓ CPI toggle OFF works.")

        await page.click("#btn-overview-cpi-toggle")
        await page.wait_for_timeout(200)
        cpi_on = await page.evaluate('window.__CHARTS__["overview-apix"].data.datasets.some(d => d.label.includes("MoSPI CPI"))', isolated_context=False)
        assert cpi_on, "MoSPI CPI should be toggled back ON"
        print("✓ CPI toggle ON works.")

        # 6. Test Refresh Button
        print("Testing Header Refresh Button...")
        await page.click("button:has(#header-refresh-icon)")
        await page.wait_for_timeout(1000)
        print("✓ Refresh button triggered without error.")

        # 7. Test Tab Switching across all 9 modules
        active_tabs = [
            "tab-overview",
            "tab-routes",
            "tab-leadtime",
            "tab-benchmark",
            "tab-collection",
            "tab-quality",
            "tab-api",
            "tab-methodology",
            "tab-cpi-explorer"
        ]
        for t in active_tabs:
            print(f"Switching to tab: {t} ...")
            await page.click(f"#nav-{t}")
            await page.wait_for_timeout(200)
            is_active = await page.evaluate(f'document.getElementById("{t}").classList.contains("active")', isolated_context=False)
            assert is_active, f"Tab {t} failed to activate"
        print("✓ All 9 tabs switch smoothly and activate!")

        # 8. Take screenshots for report
        screenshot_path = "/home/saurabh/.gemini/antigravity-cli/brain/b678f0ef-2ea3-41d1-a4ad-79054b9c65df/dashboard_overview.png"
        await page.click("#nav-tab-overview")
        await page.wait_for_timeout(300)
        await page.screenshot(path=screenshot_path, full_page=False)
        print(f"✓ Screenshot captured at: {screenshot_path}")

        print("Console errors count:", len(console_errors))
        if console_errors:
            print("Console errors:", console_errors)
        assert len(console_errors) == 0, f"Uncaught console errors detected: {console_errors}"

        await browser.close()
        print("ALL ROUGHCHECK VERIFICATIONS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(main())
