# Ethical Web Scraping & Regulatory Compliance Charter

**Platform:** Real-time Airfare Price Index for India (APIx)  
**Regulatory Context:** Ministry of Statistics and Programme Implementation (MoSPI) & Reserve Bank of India (RBI)  
**Legal Framework:** Indian Information Technology Act, 2000 (as amended) & Digital Personal Data Protection (DPDP) Act, 2023

---

## 1. Principles of Ethical Data Collection

The APIx extraction engine adheres to strict ethical scraping principles designed to collect publicly accessible tariff data without causing infrastructure degradation or legal infringement on source airline and OTA portals.

### 1.1 The Five Tenets of APIx Scraping
1. **Public Tariff Exclusivity**: We collect *only* publicly advertised scheduled flight fares that any anonymous browser can view.
2. **Zero PII Collection**: No personal information (passenger names, contact details, payment info, account credentials) is ever requested, stored, or processed.
3. **Polite Rate Limiting & Concurrency Throttling**: Requests are paced with exponential jitter and delayed between consecutive route queries (minimum 2.5–5.0 seconds).
4. **Transparent Attribution**: Requests carry an identifiable `User-Agent` string identifying the platform as a public statistical research project with contact details.
5. **Caching & Deduplication**: Avoid redundant duplicate requests by caching results and strictly following minimum collection intervals.

---

## 2. Robots.txt Compliance & Anti-Bot Strategy

### 2.1 Robots.txt Adherence
- The scraper checks `robots.txt` disallow paths on targeted domains.
- Search queries target standardized flight search results endpoints, respecting crawler delays where declared.

### 2.2 Anti-Bot & Fingerprinting Safeguards
- **Browser Automation via Patchright / Playwright**: Uses stealth browser contexts that accurately mimic standard consumer desktop browsers (Chromium with human-like viewport and WebGL parameters).
- **No CAPTCHA Breaking**: If a portal challenges a session with a hard CAPTCHA, the scraper **backs off immediately** and logs a temporary rate-limit cooldown rather than attempting to circumvent security mechanisms.
- **Header Standardization**:
  ```http
  User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 (MoSPI APIx Research Crawler)
  Accept-Language: en-IN,en-GB;q=0.9,en;q=0.8
  Accept: text/html,application/xhtml+xml,application/xml;q=0.9
  ```

---

## 3. Legal and Regulatory Positioning in India

### 3.1 Indian Information Technology Act, 2000
- **Section 43 & Section 66**: Unauthorized access to computer systems.
  *Compliance Note:* APIx interacts strictly with public-facing web servers without bypassing access control gates, authentication firewalls, or paywalls. Public fare quotes are intended by airlines for unrestricted public broadcast.

### 3.2 Digital Personal Data Protection (DPDP) Act, 2023
- APIx collects **no personal data**. Flight numbers, IATA route codes, departure timestamps, and rupee prices constitute public commercial price listings, not personal data under Section 2(t) of the DPDP Act.

### 3.3 Public Purpose Defense
- Collection is conducted for national statistical augmentation of retail inflation indicators for MoSPI (Government of India) and monetary policy evaluation by the Reserve Bank of India (RBI).
