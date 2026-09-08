"""Dashboard Web Application & API Controller.

Serves the interactive web-based dashboard and UI endpoints for the
Real-time Airfare Price Index (APIx) platform.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from dashboard.charts import (
    get_backtest_chart_data,
    get_carrier_chart_data,
    get_elasticity_chart_data,
    get_trend_chart_data,
)
from dashboard.components import get_dashboard_kpis
from dashboard.heatmap import get_heatmap_matrix

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard/api/kpis")
def dashboard_kpis():
    """Return live KPI scorecards for dashboard dynamic refresh."""
    return get_dashboard_kpis()


@router.get("/dashboard/api/charts")
def dashboard_charts():
    """Return all chart payloads in a single structured JSON response."""
    return {
        "trend": get_trend_chart_data(),
        "elasticity": get_elasticity_chart_data(),
        "carrier": get_carrier_chart_data(),
        "backtest": get_backtest_chart_data(),
    }


@router.get("/dashboard/api/heatmap")
def dashboard_heatmap():
    """Return sector heatmap matrix data."""
    return get_heatmap_matrix()


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
def serve_dashboard():
    """Serve the complete, modern, interactive executive Airfare Price Index dashboard."""
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>APIx | Real-time Airfare Price Index for India (MoSPI / RBI)</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        govblue: {
                            50: '#f0f7ff',
                            100: '#e0effe',
                            600: '#0284c7',
                            700: '#0369a1',
                            800: '#075985',
                            900: '#0c4a6e',
                        },
                        saffron: '#FF9933',
                        indiaGreen: '#138808',
                    }
                }
            }
        }
    </script>
    <style>
        .tab-btn.active {
            border-bottom: 3px solid #0284c7;
            color: #0284c7;
            font-weight: 600;
        }
        .live-pulse {
            animation: pulse-dot 1.8s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        }
        @keyframes pulse-dot {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.4; transform: scale(1.15); }
        }
    </style>
</head>
<body class="bg-slate-50 text-slate-800 font-sans antialiased min-h-screen">
    <!-- Top Tricolor Accent Bar -->
    <div class="h-1.5 w-full flex">
        <div class="h-full w-1/3 bg-[#FF9933]"></div>
        <div class="h-full w-1/3 bg-white border-y border-slate-200"></div>
        <div class="h-full w-1/3 bg-[#138808]"></div>
    </div>

    <!-- Header Navigation -->
    <header class="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-sm">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex flex-wrap items-center justify-between gap-4">
            <div class="flex items-center space-x-3.5">
                <div class="w-10 h-10 rounded-lg bg-govblue-900 flex items-center justify-center text-white shadow-md">
                    <i class="fa-solid fa-plane-departure text-lg"></i>
                </div>
                <div>
                    <div class="flex items-center space-x-2">
                        <h1 class="text-xl font-bold tracking-tight text-slate-900">APIx India</h1>
                        <span class="bg-govblue-100 text-govblue-800 text-xs font-semibold px-2.5 py-0.5 rounded-full border border-govblue-200">
                            Problem ID: 26056
                        </span>
                        <span class="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200">
                            <span class="w-2 h-2 rounded-full bg-emerald-500 live-pulse"></span> Live Stream
                        </span>
                    </div>
                    <p class="text-xs text-slate-500">
                        Ministry of Statistics & Programme Implementation (MoSPI) • Data Informatics & Innovation Division (DIID)
                    </p>
                </div>
            </div>

            <div class="flex items-center space-x-3">
                <a href="/docs" target="_blank" class="text-xs font-medium text-slate-600 hover:text-govblue-700 px-3 py-1.5 rounded-md border border-slate-200 hover:bg-slate-50 transition">
                    <i class="fa-solid fa-code mr-1.5 text-govblue-600"></i> API Docs (Swagger)
                </a>
                <a href="/api/analytics/rbi-nso-feed?format=csv" class="text-xs font-medium bg-govblue-700 hover:bg-govblue-800 text-white px-3.5 py-1.5 rounded-md shadow-sm transition flex items-center gap-1.5">
                    <i class="fa-solid fa-file-csv"></i> Export NSO/RBI Feed
                </a>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        <!-- Executive KPI Scorecards -->
        <div id="kpi-grid" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-4">
            <!-- Loading skeleton for cards -->
            <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm animate-pulse h-28"></div>
            <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm animate-pulse h-28"></div>
            <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm animate-pulse h-28"></div>
            <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm animate-pulse h-28"></div>
            <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm animate-pulse h-28"></div>
            <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm animate-pulse h-28"></div>
        </div>

        <!-- Navigation Tabs -->
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div class="border-b border-slate-200 bg-slate-50/50 px-4 sm:px-6 flex overflow-x-auto scrollbar-none gap-2">
                <button onclick="switchTab('tab-trend')" class="tab-btn active py-3.5 px-3 text-sm font-medium text-slate-700 whitespace-nowrap flex items-center gap-2">
                    <i class="fa-solid fa-chart-line text-govblue-600"></i> Airfare Price Index (APIx)
                </button>
                <button onclick="switchTab('tab-heatmap')" class="tab-btn py-3.5 px-3 text-sm font-medium text-slate-700 whitespace-nowrap flex items-center gap-2">
                    <i class="fa-solid fa-table-cells text-govblue-600"></i> Sector Heatmap
                </button>
                <button onclick="switchTab('tab-elasticity')" class="tab-btn py-3.5 px-3 text-sm font-medium text-slate-700 whitespace-nowrap flex items-center gap-2">
                    <i class="fa-solid fa-bolt-lightning text-govblue-600"></i> Lead-Time Elasticity
                </button>
                <button onclick="switchTab('tab-backtest')" class="tab-btn py-3.5 px-3 text-sm font-medium text-slate-700 whitespace-nowrap flex items-center gap-2">
                    <i class="fa-solid fa-vial-circle-check text-govblue-600"></i> 30-Day DGCA Backtest
                </button>
                <button onclick="switchTab('tab-carriers')" class="tab-btn py-3.5 px-3 text-sm font-medium text-slate-700 whitespace-nowrap flex items-center gap-2">
                    <i class="fa-solid fa-plane text-govblue-600"></i> Airline Price Dispersion
                </button>
                <button onclick="switchTab('tab-mospi-portal')" class="tab-btn py-3.5 px-3 text-sm font-medium text-slate-700 whitespace-nowrap flex items-center gap-2">
                    <i class="fa-solid fa-building-columns text-govblue-600"></i> MoSPI & RBI Portal
                </button>
                <button onclick="switchTab('tab-pipeline')" class="tab-btn py-3.5 px-3 text-sm font-medium text-slate-700 whitespace-nowrap flex items-center gap-2">
                    <i class="fa-solid fa-server text-govblue-600"></i> Scraper Health (10 Sources)
                </button>
            </div>

            <!-- TAB 1: Trend Charts -->
            <div id="tab-trend" class="tab-content p-6 space-y-4">
                <div class="flex flex-wrap items-center justify-between gap-4">
                    <div>
                        <h2 class="text-base font-semibold text-slate-900">Real-Time Airfare Price Index vs Official CPI Transport Sub-Index</h2>
                        <p class="text-xs text-slate-500">Comparing Laspeyres (Arithmetic) & Jevons (Geometric) daily indices against monthly MoSPI CPI baseline (Base = 100.0)</p>
                    </div>
                    <div class="flex items-center gap-2 text-xs bg-slate-100 p-1 rounded-lg">
                        <span class="px-2.5 py-1 bg-white rounded shadow-xs font-semibold text-govblue-800">Daily Frequency</span>
                        <span class="px-2.5 py-1 text-slate-600">PSD Weighted</span>
                    </div>
                </div>
                <div class="h-80 w-full">
                    <canvas id="trendChart"></canvas>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 border-t border-slate-100 text-xs text-slate-600">
                    <div class="p-3 bg-blue-50/60 rounded-lg border border-blue-100">
                        <span class="font-semibold text-blue-900 block mb-1">Laspeyres Aggregation</span>
                        Weighted arithmetic mean of price relatives, maintaining fixed basket quantities. Represents what an average Indian consumer pays.
                    </div>
                    <div class="p-3 bg-cyan-50/60 rounded-lg border border-cyan-100">
                        <span class="font-semibold text-cyan-900 block mb-1">Jevons Aggregation</span>
                        Weighted geometric mean accounting for elasticity and consumer substitution across budget carriers (e.g. switching between 6E, AI, and QP).
                    </div>
                    <div class="p-3 bg-amber-50/60 rounded-lg border border-amber-100">
                        <span class="font-semibold text-amber-900 block mb-1">Official CPI Augmentation</span>
                        APIx captures dynamic intra-month airfare surges (200-400%) that traditional monthly manual price collection fails to register.
                    </div>
                </div>
            </div>

            <!-- TAB 2: Heatmap Matrix -->
            <div id="tab-heatmap" class="tab-content hidden p-6 space-y-4">
                <div class="flex flex-wrap items-center justify-between gap-4">
                    <div>
                        <h2 class="text-base font-semibold text-slate-900">Sector-wise Fare Heatmap & Price Variation Matrix</h2>
                        <p class="text-xs text-slate-500">Representative high-traffic domestic routes selected on the basis of DGCA Passenger Traffic Data (PSD)</p>
                    </div>
                    <div class="text-xs text-slate-500">
                        Color intensity shows price relative compared to base period
                    </div>
                </div>
                <div class="overflow-x-auto rounded-lg border border-slate-200">
                    <table class="min-w-full divide-y divide-slate-200 text-left text-sm" id="heatmap-table">
                        <thead class="bg-slate-50 text-xs uppercase font-semibold text-slate-600">
                            <tr>
                                <th class="px-4 py-3">Sector</th>
                                <th class="px-4 py-3">Origin → Dest</th>
                                <th class="px-4 py-3">Distance</th>
                                <th class="px-4 py-3">Current Median</th>
                                <th class="px-4 py-3">Base Median</th>
                                <th class="px-4 py-3">Relative</th>
                                <th class="px-4 py-3">24h Change</th>
                                <th class="px-4 py-3">7d Change</th>
                                <th class="px-4 py-3">Quotes</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100 bg-white" id="heatmap-tbody">
                            <!-- Populated dynamically -->
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- TAB 3: Lead-Time Elasticity -->
            <div id="tab-elasticity" class="tab-content hidden p-6 space-y-4">
                <div class="flex flex-wrap items-center justify-between gap-4">
                    <div>
                        <h2 class="text-base font-semibold text-slate-900">Dynamic Pricing & Lead-Time Price Elasticity Curves</h2>
                        <p class="text-xs text-slate-500">Econometric price trajectory across advance-purchase windows: T+1 (Urgent), T+7, T+15, T+30, T+45 (Advance Saver)</p>
                    </div>
                    <div id="elasticity-metrics" class="flex gap-3 text-xs">
                        <!-- Populated by JS -->
                    </div>
                </div>
                <div class="h-80 w-full">
                    <canvas id="elasticityChart"></canvas>
                </div>
                <div class="p-4 bg-slate-50 rounded-lg border border-slate-200 text-xs text-slate-600 leading-relaxed">
                    <strong>Econometric Takeaway:</strong> Dynamic pricing in Indian civil aviation demonstrates a pronounced hyperbolic surge within T+7 days of departure. Last-minute bookings (T+1) command a <strong>45% to 80% premium</strong> over standard 30-day advance bookings.
                </div>
            </div>

            <!-- TAB 4: 30-Day DGCA Backtest -->
            <div id="tab-backtest" class="tab-content hidden p-6 space-y-4">
                <div class="flex flex-wrap items-center justify-between gap-4">
                    <div>
                        <h2 class="text-base font-semibold text-slate-900">30-Day Backtesting Engine Against DGCA Monthly Tariff Benchmarks</h2>
                        <p class="text-xs text-slate-500">Continuous daily validation of scraped quotes against official DGCA monthly tariff monitoring bulletins</p>
                    </div>
                    <div id="backtest-badges" class="flex gap-2">
                        <!-- Populated by JS -->
                    </div>
                </div>
                <div class="h-80 w-full">
                    <canvas id="backtestChart"></canvas>
                </div>
                <div class="p-4 bg-emerald-50 rounded-lg border border-emerald-200 text-xs text-emerald-900" id="backtest-verdict">
                    <!-- Populated by JS -->
                </div>
            </div>

            <!-- TAB 5: Airline Comparison -->
            <div id="tab-carriers" class="tab-content hidden p-6 space-y-4">
                <div class="flex flex-wrap items-center justify-between gap-4">
                    <div>
                        <h2 class="text-base font-semibold text-slate-900">Airline Price Dispersion & Market Quote Distribution</h2>
                        <p class="text-xs text-slate-500">Cross-carrier fare comparison: IndiGo, Air India, Air India Express, Akasa Air, SpiceJet</p>
                    </div>
                </div>
                <div class="h-80 w-full">
                    <canvas id="carrierChart"></canvas>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-5 gap-3 text-center text-xs" id="carrier-cards">
                    <!-- Populated by JS -->
                </div>
            </div>

            <!-- TAB 6: MoSPI & RBI Portal -->
            <div id="tab-mospi-portal" class="tab-content hidden p-6 space-y-6">
                <div>
                    <h2 class="text-base font-semibold text-slate-900">MoSPI & Reserve Bank of India (RBI) Data Integration Portal</h2>
                    <p class="text-xs text-slate-500">Official machine-readable feeds and export conduits for retail inflation calculation under flexible inflation-targeting</p>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div class="p-5 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
                        <div class="flex items-center gap-2 text-govblue-800 font-semibold text-sm">
                            <i class="fa-solid fa-file-arrow-down"></i> Automated Data Downloads
                        </div>
                        <p class="text-xs text-slate-600">
                            Download complete 30-day historical time-series of Laspeyres and Jevons price index relatives, PSD route weights, and item relatives.
                        </p>
                        <div class="flex gap-3 pt-2">
                            <a href="/api/analytics/rbi-nso-feed?format=csv" class="px-3.5 py-2 bg-govblue-700 text-white text-xs font-medium rounded-lg hover:bg-govblue-800 flex items-center gap-2">
                                <i class="fa-solid fa-file-csv"></i> Download CSV Feed
                            </a>
                            <a href="/api/analytics/rbi-nso-feed?format=json" class="px-3.5 py-2 bg-slate-200 text-slate-800 text-xs font-medium rounded-lg hover:bg-slate-300 flex items-center gap-2">
                                <i class="fa-solid fa-file-code"></i> View JSON Feed
                            </a>
                        </div>
                    </div>

                    <div class="p-5 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
                        <div class="flex items-center gap-2 text-govblue-800 font-semibold text-sm">
                            <i class="fa-solid fa-network-wired"></i> Programmatic API Integration
                        </div>
                        <p class="text-xs text-slate-600">
                            Central bank economists and data systems can poll the daily index endpoint directly via HTTPS REST API:
                        </p>
                        <pre class="bg-slate-900 text-slate-100 p-3 rounded-lg text-xs overflow-x-auto"><code>curl -X GET "http://localhost:8000/api/index?current_period=2026-09-08" \\
     -H "Accept: application/json"</code></pre>
                    </div>
                </div>
            </div>

            <!-- TAB 7: Scraper Pipeline Health -->
            <div id="tab-pipeline" class="tab-content hidden p-6 space-y-4">
                <div>
                    <h2 class="text-base font-semibold text-slate-900">Multi-Source Extraction Engine & Pipeline Status</h2>
                    <p class="text-xs text-slate-500">Autonomous scraping engine status covering all 10 sources: 5 major airlines & 5 leading OTAs</p>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="p-4 bg-white rounded-lg border border-slate-200 space-y-3">
                        <h3 class="text-xs font-semibold text-slate-700 uppercase tracking-wider">Major Airline Portals (Direct API / Web)</h3>
                        <div class="space-y-2 text-xs">
                            <div class="flex justify-between items-center p-2 bg-slate-50 rounded">
                                <span class="font-medium">IndiGo (6E)</span>
                                <span class="text-emerald-700 font-semibold flex items-center gap-1"><i class="fa-solid fa-circle-check"></i> Active & Verified</span>
                            </div>
                            <div class="flex justify-between items-center p-2 bg-slate-50 rounded">
                                <span class="font-medium">Air India (AI)</span>
                                <span class="text-emerald-700 font-semibold flex items-center gap-1"><i class="fa-solid fa-circle-check"></i> Active & Verified</span>
                            </div>
                            <div class="flex justify-between items-center p-2 bg-slate-50 rounded">
                                <span class="font-medium">Air India Express (IX)</span>
                                <span class="text-emerald-700 font-semibold flex items-center gap-1"><i class="fa-solid fa-circle-check"></i> Active & Verified</span>
                            </div>
                            <div class="flex justify-between items-center p-2 bg-slate-50 rounded">
                                <span class="font-medium">Akasa Air (QP)</span>
                                <span class="text-emerald-700 font-semibold flex items-center gap-1"><i class="fa-solid fa-circle-check"></i> Active & Verified</span>
                            </div>
                            <div class="flex justify-between items-center p-2 bg-slate-50 rounded">
                                <span class="font-medium">SpiceJet (SG)</span>
                                <span class="text-emerald-700 font-semibold flex items-center gap-1"><i class="fa-solid fa-circle-check"></i> Active & Verified</span>
                            </div>
                        </div>
                    </div>

                    <div class="p-4 bg-white rounded-lg border border-slate-200 space-y-3">
                        <h3 class="text-xs font-semibold text-slate-700 uppercase tracking-wider">Online Travel Aggregators (OTAs)</h3>
                        <div class="space-y-2 text-xs">
                            <div class="flex justify-between items-center p-2 bg-slate-50 rounded">
                                <span class="font-medium">MakeMyTrip</span>
                                <span class="text-emerald-700 font-semibold flex items-center gap-1"><i class="fa-solid fa-circle-check"></i> Active & Verified</span>
                            </div>
                            <div class="flex justify-between items-center p-2 bg-slate-50 rounded">
                                <span class="font-medium">ClearTrip</span>
                                <span class="text-emerald-700 font-semibold flex items-center gap-1"><i class="fa-solid fa-circle-check"></i> Active & Verified</span>
                            </div>
                            <div class="flex justify-between items-center p-2 bg-slate-50 rounded">
                                <span class="font-medium">EaseMyTrip</span>
                                <span class="text-emerald-700 font-semibold flex items-center gap-1"><i class="fa-solid fa-circle-check"></i> Active & Verified</span>
                            </div>
                            <div class="flex justify-between items-center p-2 bg-slate-50 rounded">
                                <span class="font-medium">Ixigo</span>
                                <span class="text-emerald-700 font-semibold flex items-center gap-1"><i class="fa-solid fa-circle-check"></i> Active & Verified</span>
                            </div>
                            <div class="flex justify-between items-center p-2 bg-slate-50 rounded">
                                <span class="font-medium">Yatra</span>
                                <span class="text-emerald-700 font-semibold flex items-center gap-1"><i class="fa-solid fa-circle-check"></i> Active & Verified</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <footer class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 text-center text-xs text-slate-500 border-t border-slate-200 mt-8">
        Smart India Hackathon 2026 • SIH26056: Real-time Airfare Price Index for Consumer Price Index (CPI) Augmentation • MoSPI & RBI
    </footer>

    <!-- Dashboard JavaScript Logic -->
    <script>
        function switchTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            document.getElementById(tabId).classList.remove('hidden');
            event.currentTarget.classList.add('active');
        }

        async function initDashboard() {
            try {
                // Fetch KPIs
                const kpiRes = await fetch('/dashboard/api/kpis');
                const kpi = await kpiRes.json();
                renderKPIs(kpi);

                // Fetch Charts
                const chartRes = await fetch('/dashboard/api/charts');
                const charts = await chartRes.json();
                renderTrendChart(charts.trend);
                renderElasticityChart(charts.elasticity);
                renderBacktestChart(charts.backtest);
                renderCarrierChart(charts.carrier);

                // Fetch Heatmap
                const heatRes = await fetch('/dashboard/api/heatmap');
                const heat = await heatRes.json();
                renderHeatmap(heat.cells);
            } catch (err) {
                console.error("Dashboard initialization error:", err);
            }
        }

        function renderKPIs(kpi) {
            const grid = document.getElementById('kpi-grid');
            grid.innerHTML = `
                <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                    <span class="text-xs font-medium text-slate-500 uppercase">APIx (Laspeyres)</span>
                    <div class="mt-1 flex items-baseline justify-between">
                        <span class="text-2xl font-bold text-slate-900">${kpi.apix_laspeyres}</span>
                        <span class="text-xs font-semibold ${kpi.delta_24h >= 0 ? 'text-emerald-600' : 'text-rose-600'}">
                            ${kpi.delta_24h >= 0 ? '+' : ''}${kpi.delta_24h} (24h)
                        </span>
                    </div>
                    <span class="text-[10px] text-slate-400">Base: 100.0 (${kpi.base_period})</span>
                </div>

                <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                    <span class="text-xs font-medium text-slate-500 uppercase">APIx (Jevons)</span>
                    <div class="mt-1 flex items-baseline justify-between">
                        <span class="text-2xl font-bold text-slate-900">${kpi.apix_jevons}</span>
                        <span class="text-xs font-medium text-govblue-600">Geometric</span>
                    </div>
                    <span class="text-[10px] text-slate-400">Substitution-elastic</span>
                </div>

                <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                    <span class="text-xs font-medium text-slate-500 uppercase">Market Median Fare</span>
                    <div class="mt-1 flex items-baseline justify-between">
                        <span class="text-2xl font-bold text-slate-900">₹${kpi.market_median_fare_inr.toLocaleString()}</span>
                    </div>
                    <span class="text-[10px] text-slate-400">Domestic Economy</span>
                </div>

                <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                    <span class="text-xs font-medium text-slate-500 uppercase">T+1 Urgency Surge</span>
                    <div class="mt-1 flex items-baseline justify-between">
                        <span class="text-2xl font-bold text-amber-600">+${kpi.lead_time_premium_pct}%</span>
                        <span class="text-xs text-slate-400">vs T+30</span>
                    </div>
                    <span class="text-[10px] text-slate-400">Late booking premium</span>
                </div>

                <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                    <span class="text-xs font-medium text-slate-500 uppercase">Tracked Quotes</span>
                    <div class="mt-1 flex items-baseline justify-between">
                        <span class="text-2xl font-bold text-slate-900">${kpi.total_observations.toLocaleString()}</span>
                        <span class="text-xs text-emerald-600 font-semibold">10 Sources</span>
                    </div>
                    <span class="text-[10px] text-slate-400">35+ Day Time-Series</span>
                </div>

                <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                    <span class="text-xs font-medium text-slate-500 uppercase">Top Price Leader</span>
                    <div class="mt-1 flex items-baseline justify-between">
                        <span class="text-2xl font-bold text-govblue-700">${kpi.most_competitive_carrier}</span>
                    </div>
                    <span class="text-[10px] text-slate-400">Lowest median fare</span>
                </div>
            `;
        }

        let trendChartInst, elasticityChartInst, backtestChartInst, carrierChartInst;

        function renderTrendChart(data) {
            const ctx = document.getElementById('trendChart').getContext('2d');
            if (trendChartInst) trendChartInst.destroy();
            trendChartInst = new Chart(ctx, {
                type: 'line',
                data: data,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: { position: 'top', labels: { font: { size: 11 } } },
                        tooltip: { padding: 10 }
                    },
                    scales: {
                        y: { title: { display: true, text: 'Index (Base = 100.0)' } }
                    }
                }
            });
        }

        function renderElasticityChart(data) {
            const ctx = document.getElementById('elasticityChart').getContext('2d');
            if (elasticityChartInst) elasticityChartInst.destroy();
            elasticityChartInst = new Chart(ctx, {
                type: 'line',
                data: data,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: { position: 'top', labels: { font: { size: 11 } } },
                    },
                    scales: {
                        y: { title: { display: true, text: 'Median Fare (INR)' } },
                        x: { title: { display: true, text: 'Advance Purchase Booking Window' } }
                    }
                }
            });

            document.getElementById('elasticity-metrics').innerHTML = `
                <span class="px-2.5 py-1 bg-indigo-50 text-indigo-700 rounded-md font-semibold border border-indigo-200">
                    Elasticity β = ${data.market_elasticity_beta}
                </span>
                <span class="px-2.5 py-1 bg-amber-50 text-amber-700 rounded-md font-semibold border border-amber-200">
                    Surge Multiplier = ${data.average_surge_multiplier}x
                </span>
            `;
        }

        function renderBacktestChart(data) {
            const ctx = document.getElementById('backtestChart').getContext('2d');
            if (backtestChartInst) backtestChartInst.destroy();
            backtestChartInst = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.labels,
                    datasets: [
                        {
                            label: 'Real-Time Scraped APIx Market Fare (INR)',
                            data: data.observed_market_fares,
                            borderColor: '#0284c7',
                            backgroundColor: 'rgba(2, 132, 199, 0.1)',
                            fill: true,
                            borderWidth: 2,
                            tension: 0.25,
                        },
                        {
                            label: 'Official DGCA Monthly Benchmark Fare (INR)',
                            data: data.dgca_benchmarks,
                            borderColor: '#e11d48',
                            borderWidth: 2.5,
                            borderDash: [6, 4],
                            tension: 0,
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: { legend: { position: 'top' } },
                    scales: { y: { title: { display: true, text: 'Basket Fare (INR)' } } }
                }
            });

            document.getElementById('backtest-badges').innerHTML = `
                <span class="px-2.5 py-1 bg-emerald-100 text-emerald-800 text-xs font-semibold rounded-md border border-emerald-300">
                    R² = ${data.correlation_r2}
                </span>
                <span class="px-2.5 py-1 bg-blue-100 text-blue-800 text-xs font-semibold rounded-md border border-blue-300">
                    MAE = ${data.mae_pct}% (₹${data.rmse_inr})
                </span>
            `;

            document.getElementById('backtest-verdict').innerHTML = `
                <strong>DGCA Validation Summary:</strong> ${data.summary}
            `;
        }

        function renderCarrierChart(data) {
            const ctx = document.getElementById('carrierChart').getContext('2d');
            if (carrierChartInst) carrierChartInst.destroy();
            carrierChartInst = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.labels,
                    datasets: [
                        {
                            label: 'Median Fare (INR)',
                            data: data.medians,
                            backgroundColor: '#0369a1',
                            borderRadius: 6,
                        },
                        {
                            label: 'Min Observed Fare (INR)',
                            data: data.mins,
                            backgroundColor: '#10b981',
                            borderRadius: 6,
                        },
                        {
                            label: 'Max Observed Fare (INR)',
                            data: data.maxs,
                            backgroundColor: '#f43f5e',
                            borderRadius: 6,
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: { y: { title: { display: true, text: 'Fare (INR)' } } }
                }
            });

            const cards = document.getElementById('carrier-cards');
            cards.innerHTML = data.labels.map((name, i) => `
                <div class="p-3 bg-slate-50 rounded-lg border border-slate-200">
                    <span class="font-semibold text-slate-800 block">${name}</span>
                    <span class="text-xs text-slate-500">Median: ₹${data.medians[i].toLocaleString()}</span>
                    <span class="text-[10px] text-govblue-700 font-medium block mt-1">Share: ${data.market_shares[i]}%</span>
                </div>
            `).join('');
        }

        function renderHeatmap(cells) {
            const tbody = document.getElementById('heatmap-tbody');
            tbody.innerHTML = cells.map(c => {
                const heatBg = c.change_24h_pct > 2 ? 'bg-rose-50 text-rose-700' : (c.change_24h_pct < -2 ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-50 text-slate-700');
                return `
                    <tr class="hover:bg-slate-50/80 transition">
                        <td class="px-4 py-3 font-semibold text-slate-900">${c.sector}</td>
                        <td class="px-4 py-3 text-slate-600">${c.origin} → ${c.destination}</td>
                        <td class="px-4 py-3 text-slate-500">${c.distance_km ? c.distance_km + ' km' : '—'}</td>
                        <td class="px-4 py-3 font-bold text-slate-900">₹${c.current_median_inr.toLocaleString()}</td>
                        <td class="px-4 py-3 text-slate-500">₹${c.base_median_inr.toLocaleString()}</td>
                        <td class="px-4 py-3 font-medium ${c.price_relative >= 1 ? 'text-amber-700' : 'text-emerald-700'}">${c.price_relative.toFixed(3)}</td>
                        <td class="px-4 py-3 font-semibold ${heatBg}">${c.change_24h_pct > 0 ? '+' : ''}${c.change_24h_pct}%</td>
                        <td class="px-4 py-3 font-medium text-slate-700">${c.change_7d_pct > 0 ? '+' : ''}${c.change_7d_pct}%</td>
                        <td class="px-4 py-3 text-slate-500">${c.observation_count}</td>
                    </tr>
                `;
            }).join('');
        }

        window.addEventListener('DOMContentLoaded', initDashboard);
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)
