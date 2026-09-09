# Airfare Price Index (APIx) Methodology

**Problem Statement ID:** 26056  
**Target Organization:** Ministry of Statistics and Programme Implementation (MoSPI) – Data Informatics & Innovation Division (DIID)  
**Stakeholder:** Reserve Bank of India (RBI) Monetary Policy Committee (MPC)

---

## 1. Executive Summary & CPI Context

The **Consumer Price Index (CPI)** compiled by the National Statistical Office (NSO) is India's primary benchmark for retail inflation and the cornerstone of the RBI's flexible inflation-targeting framework. Under the existing framework, the *Transport and Communication* sub-group relies on manual quote collection from physical booking counters and travel agents.

In modern Indian civil aviation:
- Over **90% of domestic tickets** are booked online via airline portals (IndiGo, Air India, Air India Express, Akasa Air, SpiceJet) and Online Travel Aggregators (MakeMyTrip, ClearTrip, EaseMyTrip, Ixigo, Yatra).
- Airfares follow **dynamic algorithmic pricing**, experiencing **200%–400% price swings** driven by lead time, day of week, seasonal surges, and fuel surcharges.
- Stale monthly counter quotes fundamentally mismeasure true consumer expenditure.

The **Real-time Airfare Price Index (APIx)** solves this by scraping, cleaning, normalising, and aggregating real-time domestic airfare quotes into high-frequency daily, weekly, and monthly price indices.

---

## 2. Spatial Basket & Item Identification

### 2.1 Representative Sector Selection (PSD)
A basket of 14 high-density city-pairs is maintained, selected on the basis of DGCA quarterly Passenger Traffic Data (PSD):
- **Delhi – Mumbai (DEL-BOM / BOM-DEL)**: ~24% top-route share (1,138 km)
- **Delhi – Bengaluru (DEL-BLR / BLR-DEL)**: ~16% top-route share (1,740 km)
- **Mumbai – Bengaluru (BOM-BLR / BLR-BOM)**: ~13% top-route share (842 km)
- **Delhi – Kolkata (DEL-CCU / CCU-DEL)**: ~11% top-route share (1,305 km)
- **Bengaluru – Hyderabad (BLR-HYD / HYD-BLR)**: ~9% top-route share (500 km)
- **Chennai – Delhi (MAA-DEL / DEL-MAA)**: ~9% top-route share (1,760 km)
- **Delhi – Hyderabad (DEL-HYD / HYD-DEL)**: ~9% top-route share (1,253 km)

### 2.2 Item Definition
An elementary item $i$ is strictly defined as a 4-tuple:
$$i = (\text{Origin}, \text{Destination}, \text{CabinClass}, \text{TripType})$$
All standard calculations focus on `CabinClass.ECONOMY` and `TripType.ONE_WAY`, which represent >95% of domestic passenger volume.

---

## 3. Data Cleaning & Aggregation Pipeline

1. **Outlier Filtering**: Quotes below ₹500 (scraper error) or above ₹200,000 (abnormal international/private fares) are filtered out.
2. **Effective Item-Day Price**:
   For any given date $t$ and item $i$, multiple flight quotes $q \in Q_{i,t}$ are collected across carriers and booking windows. The effective daily item price $P_{i,t}$ is computed as the **median**:
   $$P_{i,t} = \text{Median}\left(\{ p_{q} \mid q \in Q_{i,t} \}\right)$$
   The median provides robustness against sold-out flights, dynamic pricing spikes, and luxury fare bundles.
3. **Price Relative Formulation**:
   $$r_i(t) = \frac{P_{i,t}}{P_{i,0}}$$
   Where $t_0$ is the locked base period ($P_{i,0}$ is the base period price).

---

## 4. Index Aggregation Formulations

### 4.1 Laspeyres Price Index (Base-Period Weighted Arithmetic Mean)
The primary index representing the expenditure required to purchase the base-period travel basket:
$$I_L(t) = \sum_{i \in \mathcal{U}_t} w_i \cdot r_i(t) \times 100 = \sum_{i \in \mathcal{U}_t} w_i \left(\frac{P_{i,t}}{P_{i,0}}\right) \times 100$$
Where $\sum_{i \in \mathcal{U}_t} w_i = 1.0$.

### 4.2 Weighted Jevons Price Index (Geometric Mean)
To account for consumer substitution behavior across competing low-cost carriers (e.g. choosing Akasa or SpiceJet when IndiGo prices surge):
$$I_J(t) = \prod_{i \in \mathcal{U}_t} \left(\frac{P_{i,t}}{P_{i,0}}\right)^{w_i} \times 100 = \exp\left(\sum_{i \in \mathcal{U}_t} w_i \ln r_i(t)\right) \times 100$$

### 4.3 Weighting Methodologies
1. **PSD Passenger Traffic Weights (`compute_psd_base_basket_weights`)**:
   Route weights $w_i \propto \text{DGCA Passenger Volume Share}$. Items belonging to heavier routes (e.g., DEL-BOM) receive proportionally higher index weights.
2. **Uniform Weights (`compute_uniform_base_basket_weights`)**:
   $w_i = \frac{1}{N}$ for all $N$ observed items (MVP baseline).

---

## 5. Advance-Purchase Windows & Lead-Time Elasticity

### 5.1 Standard Advance Windows
Fares are explicitly collected and categorized across 5 lead-time windows:
- **T+1 (0–3 days)**: Immediate / Urgency travel (business and emergency bookings)
- **T+7 (4–10 days)**: Current week travel
- **T+15 (11–22 days)**: Fortnightly advance travel
- **T+30 (23–37 days)**: Standard month-ahead leisure travel (baseline anchor)
- **T+45 (38–90 days)**: Early-bird / Advance saver

### 5.2 Dynamic Pricing Econometric Curve
We model the fare progression with respect to lead time $\tau$ (days) using a log-linear model:
$$\ln(P_{i,\tau}) = \alpha_i + \beta_i \ln(\tau) + \epsilon_{i,\tau}$$
- **Elasticity Coefficient ($\beta$)**: Represents $\frac{\% \Delta P}{\% \Delta \tau}$. Since prices decline as lead time increases, $\beta < 0$.
- **Late-Booking Surge Multiplier**:
  $$\text{Surge Multiplier} = \frac{\bar{P}_{T+1}}{\bar{P}_{T+30}}$$
  Across Indian domestic routes, this typically ranges between **1.45x and 1.85x** (+45% to +85%).

---

## 6. DGCA 30-Day Backtesting & Validation

To establish institutional credibility for MoSPI and the RBI, APIx is continuously backtested against monthly average domestic tariff data published by DGCA.

Key validation metrics computed over a 30+ day rolling evaluation:
1. **Pearson Correlation ($r$)**: Measures directional tracking between scraped market fares and official benchmarks ($r \ge 0.88$).
2. **Goodness of Fit ($R^2$)**: Quantifies shared variance ($R^2 \ge 0.77$).
3. **Mean Absolute Error (MAE)**: Tracks percentage tracking difference ($< 10\%$).
4. **Inflation Gap**: Demonstrates that high-frequency APIx detects short-term festival and fuel surges weeks before the monthly CPI release.
