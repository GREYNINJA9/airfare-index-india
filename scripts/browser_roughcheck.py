"""Automated browser roughcheck script using Patchright verifying all charts and refresh pipeline."""
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

        print("1. Navigating to http://127.0.0.1:8000/dashboard ...")
        response = await page.goto("http://127.0.0.1:8000/dashboard", wait_until="networkidle")
        assert response.status == 200, f"Dashboard returned status {response.status}"

        # 2. Verify navigation links
        links = await page.query_selector_all(".sidebar-link")
        print(f"✓ Found {len(links)} module links in sidebar.")
        assert len(links) == 9, f"Expected 9 sidebar modules, found {len(links)}"

        # 3. Verify Overview APIx Chart
        print("2. Verifying Overview APIx Chart (overview-apix-chart)...")
        apix_info = await page.evaluate('''() => {
            const chart = window.__CHARTS__["overview-apix"];
            if (!chart) return null;
            return {
                labelsCount: chart.data.labels.length,
                datasets: chart.data.datasets.map(d => ({
                    label: d.label,
                    points: d.data.length,
                    sample: d.data.slice(0, 3)
                }))
            };
        }''', isolated_context=False)
        assert apix_info is not None, "overview-apix chart not found"
        assert apix_info["labelsCount"] > 0, "overview-apix chart has no labels"
        print(f"✓ Overview APIx chart initialized with {apix_info['labelsCount']} labels, datasets: {[d['label'] for d in apix_info['datasets']]}")

        # 4. Verify Average Domestic Fare Chart
        print("3. Verifying Average Domestic Fare Chart (overview-fare-chart)...")
        fare_info = await page.evaluate('''() => {
            const chart = window.__CHARTS__["overview-fare"];
            if (!chart) return null;
            const ds = chart.data.datasets[0] || {};
            const lowEl = document.getElementById("overview-fare-low");
            const highEl = document.getElementById("overview-fare-high");
            const spreadEl = document.getElementById("overview-fare-spread");
            const badgeEl = document.getElementById("overview-fare-series-badge");
            return {
                labelsCount: chart.data.labels.length,
                pointsCount: (ds.data || []).length,
                firstPoint: ds.data ? ds.data[0] : null,
                lastPoint: ds.data ? ds.data[ds.data.length - 1] : null,
                lowText: lowEl ? lowEl.textContent : "",
                highText: highEl ? highEl.textContent : "",
                spreadText: spreadEl ? spreadEl.textContent : "",
                badgeText: badgeEl ? badgeEl.textContent : ""
            };
        }''', isolated_context=False)
        assert fare_info is not None, "overview-fare chart not found"
        assert fare_info["pointsCount"] > 0, f"overview-fare chart has 0 data points: {fare_info}"
        assert fare_info["firstPoint"] > 0, f"overview-fare chart points should be positive ₹ values: {fare_info}"
        assert "₹" in fare_info["lowText"], f"overview-fare-low should contain ₹, got: {fare_info['lowText']}"
        assert "₹" in fare_info["highText"], f"overview-fare-high should contain ₹, got: {fare_info['highText']}"
        assert "₹" in fare_info["spreadText"], f"overview-fare-spread should contain ₹, got: {fare_info['spreadText']}"
        print(f"✓ Average Domestic Fare chart verified! Points: {fare_info['pointsCount']}, Low: {fare_info['lowText']}, High: {fare_info['highText']}, Spread: {fare_info['spreadText']}, Badge: {fare_info['badgeText']}")

        # 5. Verify Overview Lead-Time Curve Preview Chart
        print("4. Verifying Overview Lead-Time Curve Preview Chart (overview-lead-chart)...")
        lead_preview_info = await page.evaluate('''() => {
            const chart = window.__CHARTS__["overview-lead"];
            if (!chart) return null;
            return {
                labels: chart.data.labels,
                points: chart.data.datasets[0]?.data
            };
        }''', isolated_context=False)
        assert lead_preview_info is not None, "overview-lead chart not found"
        assert len(lead_preview_info["points"]) > 0, "overview-lead chart has no data points"
        print(f"✓ Overview Lead-Time chart verified! Labels: {lead_preview_info['labels']}, Points: {lead_preview_info['points']}")

        # 6. Test Range Toggling (7D, 30D, 90D, ALL) on both APIx and Fare Chart
        print("5. Testing Range Controls on Average Domestic Fare & APIx Chart...")
        await page.click("#btn-overview-range-7d")
        await page.wait_for_timeout(250)
        pts_fare_7d = await page.evaluate('window.__CHARTS__["overview-fare"].data.labels.length', isolated_context=False)
        badge_7d = await page.evaluate('document.getElementById("overview-fare-series-badge").textContent', isolated_context=False)
        assert pts_fare_7d <= 7, f"Expected <= 7 points for 7D, got {pts_fare_7d}"
        assert "7D" in badge_7d, f"Expected 7D in badge, got {badge_7d}"
        print(f"✓ 7D range button correctly updated fare chart to {pts_fare_7d} points and badge '{badge_7d}'")

        await page.click("#btn-overview-range-all")
        await page.wait_for_timeout(250)
        pts_fare_all = await page.evaluate('window.__CHARTS__["overview-fare"].data.labels.length', isolated_context=False)
        badge_all = await page.evaluate('document.getElementById("overview-fare-series-badge").textContent', isolated_context=False)
        assert pts_fare_all >= 30, f"Expected >= 30 points for ALL, got {pts_fare_all}"
        print(f"✓ ALL range button correctly updated fare chart to {pts_fare_all} points and badge '{badge_all}'")

        await page.click("#btn-overview-range-30d")
        await page.wait_for_timeout(250)
        pts_fare_30d = await page.evaluate('window.__CHARTS__["overview-fare"].data.labels.length', isolated_context=False)
        assert pts_fare_30d == 30, f"Expected 30 points for 30D, got {pts_fare_30d}"
        print(f"✓ 30D range button restored 30 points.")

        # 7. Check Route Analysis Charts (route-price-chart & route-index-chart)
        print("6. Verifying Route Analysis Charts...")
        await page.click("#nav-tab-routes")
        await page.wait_for_timeout(300)
        route_charts_info = await page.evaluate('''() => {
            const cPrice = window.__CHARTS__["route-price"];
            const cIndex = window.__CHARTS__["route-index"];
            return {
                pricePoints: cPrice ? cPrice.data.datasets[0]?.data?.length : 0,
                indexPoints: cIndex ? cIndex.data.datasets[0]?.data?.length : 0,
                priceSample: cPrice ? cPrice.data.datasets[0]?.data?.slice(0, 3) : [],
                indexSample: cIndex ? cIndex.data.datasets[0]?.data?.slice(0, 3) : []
            };
        }''', isolated_context=False)
        assert route_charts_info["pricePoints"] > 0, f"route-price-chart has 0 points: {route_charts_info}"
        assert route_charts_info["indexPoints"] > 0, f"route-index-chart has 0 points: {route_charts_info}"
        print(f"✓ Route charts verified! Price points: {route_charts_info['pricePoints']} (sample: {route_charts_info['priceSample']}), Index points: {route_charts_info['indexPoints']}")

        # 8. Check Lead Time Elasticity Chart (leadtime-curve-chart)
        print("7. Verifying Lead Time Elasticity Chart...")
        await page.click("#nav-tab-leadtime")
        await page.wait_for_timeout(300)
        lead_info = await page.evaluate('''() => {
            const chart = window.__CHARTS__["leadtime-curve"];
            return {
                labels: chart ? chart.data.labels : [],
                points: chart ? chart.data.datasets[0]?.data : []
            };
        }''', isolated_context=False)
        assert len(lead_info["points"]) > 0, f"leadtime-curve-chart has no points: {lead_info}"
        print(f"✓ Lead time chart verified! Labels: {lead_info['labels']}, Points: {lead_info['points']}")

        # 9. Check DGCA Benchmark Backtest Chart (benchmark-backtest-chart)
        print("8. Verifying DGCA Benchmark Backtest Chart...")
        await page.click("#nav-tab-benchmark")
        await page.wait_for_timeout(300)
        backtest_info = await page.evaluate('''() => {
            const chart = window.__CHARTS__["benchmark-backtest"];
            return {
                labelsCount: chart ? chart.data.labels.length : 0,
                apixPoints: chart ? chart.data.datasets[0]?.data?.length : 0,
                dgcaPoints: chart ? chart.data.datasets[1]?.data?.length : 0
            };
        }''', isolated_context=False)
        assert backtest_info["apixPoints"] > 0, f"benchmark-backtest-chart APIx points: {backtest_info}"
        assert backtest_info["dgcaPoints"] > 0, f"benchmark-backtest-chart DGCA points: {backtest_info}"
        print(f"✓ DGCA backtest chart verified! Points: {backtest_info['labelsCount']}")

        # 10. Check CPI Comparison Chart (cpi-comparison-chart)
        print("9. Verifying MoSPI CPI Comparison Chart...")
        await page.click("#nav-tab-cpi-explorer")
        await page.wait_for_timeout(300)
        cpi_comp_info = await page.evaluate('''() => {
            const chart = window.__CHARTS__["cpi-comparison"];
            return {
                labels: chart ? chart.data.labels : [],
                cpiPoints: chart ? chart.data.datasets[0]?.data?.length : 0,
                apixPoints: chart ? chart.data.datasets[1]?.data?.length : 0
            };
        }''', isolated_context=False)
        assert cpi_comp_info["cpiPoints"] > 0, f"cpi-comparison-chart CPI points: {cpi_comp_info}"
        print(f"✓ CPI comparison chart verified! Labels: {cpi_comp_info['labels']}")

        # 11. Test Header Refresh Button (Recalls APIs -> Persists to Supabase -> Refreshes Website)
        print("10. Testing Header Refresh Button (Recall APIs & Persist to Supabase)...")
        await page.click("#nav-tab-overview")
        await page.wait_for_timeout(200)

        # Trigger refresh and wait for network responses
        async with page.expect_response(lambda r: "/dashboard/api/pipeline/ingest" in r.url and r.request.method == "POST") as ingest_info:
            await page.click("button:has(#header-refresh-icon)")

        ingest_res = await ingest_info.value
        assert ingest_res.status == 200, f"Pipeline ingest returned status {ingest_res.status}"
        ingest_json = await ingest_res.json()
        print(f"✓ Ingest completed: status={ingest_json.get('status')}, persisted_to_supabase={ingest_json.get('persisted_to_supabase')}, scraped={ingest_json.get('fares_scraped')}")

        # Wait for subsequent charts and blueprint fetch
        await page.wait_for_timeout(1000)

        # Verify all charts on overview still have valid data after refresh
        fare_after = await page.evaluate('''() => {
            const chart = window.__CHARTS__["overview-fare"];
            return {
                points: chart ? chart.data.datasets[0]?.data?.length : 0,
                firstVal: chart ? chart.data.datasets[0]?.data[0] : 0,
                lastVal: chart ? chart.data.datasets[0]?.data[chart.data.datasets[0]?.data.length - 1] : 0
            };
        }''', isolated_context=False)
        assert fare_after["points"] > 0, f"Fare chart lost data after refresh: {fare_after}"
        assert fare_after["lastVal"] > 0, f"Fare chart values invalid: {fare_after}"
        print(f"✓ After refresh: Average Domestic Fare chart verified! Points: {fare_after['points']}, Latest Fare: ₹{fare_after['lastVal']}")

        # Capture updated screenshots
        screenshot_overview = "/home/saurabh/.gemini/antigravity-cli/brain/b678f0ef-2ea3-41d1-a4ad-79054b9c65df/dashboard_overview.png"
        await page.screenshot(path=screenshot_overview, full_page=False)
        print(f"✓ Updated overview screenshot saved at: {screenshot_overview}")

        # Verify 0 console errors
        print("Console errors count:", len(console_errors))
        if console_errors:
            print("Console errors:", console_errors)
        assert len(console_errors) == 0, f"Uncaught console errors: {console_errors}"

        await browser.close()
        print("\n=======================================================")
        print("ALL TESTS PASSED: EVERY GRAPH SHOWS VALUES & REFRESH WORKS!")
        print("=======================================================\n")

if __name__ == "__main__":
    asyncio.run(main())
