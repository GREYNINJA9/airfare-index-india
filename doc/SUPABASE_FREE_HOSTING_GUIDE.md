# 🌐 100% Free Cloud Hosting Guide: Supabase + Render

This guide explains how to host the **Real-time Airfare Price Index (APIx)** platform **completely free ($0/month)** using:
- **[Supabase](https://supabase.com)**: Free-tier Managed PostgreSQL Database (500 MB storage).
- **[Render](https://render.com)**: Free-tier Docker Web Service (serves FastAPI + Patchright Chromium + Interactive Dashboard).

---

## 🏗️ Architecture Overview

```
┌────────────────────────────────────────────────────────┐
│                   Render.com (Free)                    │
│   FastAPI Web Service + Patchright + HTML5 Dashboard    │
│            Port 8000 (HTTPS Public URL)                │
└──────────────────────────┬─────────────────────────────┘
                           │
                           │ SSL / IPv4 Connection Pooler
                           ▼
┌────────────────────────────────────────────────────────┐
│                  Supabase (Free Tier)                  │
│       Managed PostgreSQL 15/16 (500 MB Storage)        │
│          • fares table (13,650+ quotes)                │
│          • index_results table (39 daily APIx indices) │
└────────────────────────────────────────────────────────┘
```

---

## 📋 Step-by-Step Instructions

### Step 1: Create Your Free Supabase Database
1. Go to **[supabase.com](https://supabase.com)** and sign in with GitHub.
2. Click **New Project**:
   - **Name**: `airfare-index`
   - **Database Password**: Set a strong password and **keep note of it**.
   - **Region**: Choose the closest region (e.g. `South Asia (Mumbai)` or `ap-south-1`).
   - **Pricing Plan**: Free Tier ($0/mo).
3. Click **Create new project** and wait ~1–2 minutes for provisioning to complete.

---

### Step 2: Copy the IPv4 Connection Pooler URI

> [!IMPORTANT]
> Render's free tier connects over **IPv4**. Direct Supabase connections use IPv6. Therefore, you **must** use Supabase's **Connection Pooler** URI.

1. In your Supabase project dashboard, click the **Settings (gear icon)** at the bottom left $\to$ **Database**.
2. Scroll down to the **Connection string** panel.
3. Click the **URI** tab.
4. Set:
   - **Type**: `Connection pooler`
   - **Mode**: `Session` (Port `5432`)
5. Copy the URI. It will look like this:
   ```text
   postgresql://postgres.[PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres
   ```
6. Replace `[YOUR-PASSWORD]` with the password you created in Step 1.

> [!TIP]
> **Password URL Encoding**: If your password contains special symbols (like `@`, `#`, `:`, `?`, `%`, `/`), URL-encode them. For example, `@` becomes `%40`, `#` becomes `%23`.

---

### Step 3: Seed 13,650 Historical Quotes into Supabase

You can seed your historical 35+ days of airfare quotes and computed APIx indices into Supabase from your local terminal with this single command:

```bash
# 1. Set your Supabase connection string
export DATABASE_URL="postgresql://postgres.[PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres"

# 2. Run the seeder
python database/seed_data.py
```

You will see:
```text
Generating 35+ days of rich, multi-sector, multi-window fare observations...
Inserting 13650 fare observations into PostgreSQL...
Successfully inserted 13650 fare observations.
Computing daily Airfare Price Index (APIx) time-series...
Computed and persisted 39 daily index results.
```

#### Verify in Supabase Web UI:
Open the **Table Editor** icon in the Supabase sidebar. You will see two populated tables:
- `fares`: 13,650 rows
- `index_results`: 39 rows

---

### Step 4: Deploy the Web Application for Free on Render

1. Make sure your local changes are pushed to GitHub:
   ```bash
   git push origin main
   ```
2. Log into **[render.com](https://render.com)** (sign in with GitHub).
3. Click **New +** (top right) $\to$ **Web Service**.
4. Select **Build and deploy from a Git repository** $\to$ choose `GREYNINJA9/airfare-index-india`.
5. Configure the deployment settings:
   - **Name**: `airfare-index-india` (or any name you prefer)
   - **Region**: Choose closest to your Supabase region (e.g. `Singapore` or `Frankfurt`)
   - **Branch**: `main`
   - **Runtime**: Select **Docker** (Render will use your existing `Dockerfile`)
   - **Instance Type**: Select **Free**
6. Scroll down to **Environment Variables** and add:
   | Key | Value |
   | :--- | :--- |
   | `DATABASE_URL` | Your Supabase connection string from Step 2 |
   | `ENVIRONMENT` | `production` |
   | `AUTO_SEED` | `true` *(Optional: guarantees auto-seeding if DB was not pre-seeded)* |
7. Click **Deploy Web Service**.

Render will build the Docker container and output a public HTTPS URL (e.g. `https://airfare-index-india.onrender.com`).

---

### Step 5: Verify Your Live Platform

Visit your live URL:
- **Executive Dashboard:** `https://<your-subdomain>.onrender.com/dashboard`
- **Swagger Documentation:** `https://<your-subdomain>.onrender.com/docs`
- **Health Check:** `https://<your-subdomain>.onrender.com/health`
- **NSO / RBI Export Feed:** `https://<your-subdomain>.onrender.com/api/analytics/rbi-nso-feed?format=csv`

---

## ⚡ Eliminating Render Cold Starts (Keep-Alive Setup)

Render's free tier automatically suspends web services after **15 minutes of inactivity**, causing a **50–90 second delay** when the next person visits the dashboard.

To keep your service **awake 24/7 with zero spin-down lag**:
1. Go to **[cron-job.org](https://cron-job.org)** or **[UptimeRobot](https://uptimerobot.com)** (both 100% free).
2. Create a new HTTP monitor / cron job:
   - **URL:** `https://<your-subdomain>.onrender.com/health`
   - **Interval:** Every **10 minutes** (Render's inactivity timer is 15 min)
   - **HTTP Method:** `GET`
3. Save the job. Your container will remain permanently warm and respond in **under 50 milliseconds**!

---

## 🛠️ Alternative Free App Hosts (If Render Has Resource Limits)

1. **[Koyeb](https://www.koyeb.com)** (Free Eco container tier):
   - Fast SSD, zero cold starts, deploys directly from GitHub Dockerfile.
   - Set `DATABASE_URL` under Environment Variables.

2. **[Hugging Face Spaces](https://huggingface.co/spaces)** (Free Docker Space - **16 GB RAM**):
   - Create Space $\to$ Docker.
   - Add Secret: `DATABASE_URL`.
   - Outstanding option if you want to run high-frequency Playwright / Patchright browser scraping without memory pressure.
