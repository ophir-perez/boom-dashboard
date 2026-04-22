# Boom Dashboard — Claude Code Instructions

## PROJECT OVERVIEW
This is a marketing & sales attribution dashboard for Boom (vacation rental SaaS), built as a single self-contained HTML file. It pulls data from HubSpot CRM (account ID: 24030694) and displays deal pipeline, KPIs, funnel metrics, meetings, webinar/conference attribution, and ad spend.

## CRITICAL CONTEXT
- **Company:** EasyAir Technologies Inc. dba Boom (part of The Furlough Group)
- **HubSpot Account ID:** 24030694
- **HubSpot Private App Token:** See `config.json` — has `marketing.campaigns.read` and `marketing.campaigns.revenue.read` scopes. NEEDS `ads_read` scope added.
- **Primary Pipeline:** Sales 2.0 (`93413737`)
- **Won Deals Pipeline:** `116281938` (52 additional customers moved post-close — NOT yet integrated into dashboard)
- **Dashboard URL template for deals:** `https://app.hubspot.com/contacts/24030694/record/0-3/{id}`

## FILE STRUCTURE
```
boom-dashboard/
├── CLAUDE.md              ← This file (Claude Code reads this)
├── BRIEF.md               ← Full project brief with data definitions
├── config.json            ← API tokens and account IDs (GITIGNORE THIS)
├── src/
│   └── template.html      ← Dashboard HTML template with __DEALS_DATA__ and __LEADS_DATA__ placeholders
├── data/
│   ├── deals.json         ← Enriched deal data (186 deals from Sales 2.0)
│   └── leads.json         ← Monthly contact counts and SQL counts
├── scripts/
│   ├── refresh.sh         ← One-command full data refresh from HubSpot
│   ├── pull_deals.py      ← Pull all deals from Sales 2.0 pipeline
│   ├── pull_leads.py      ← Pull monthly contact creation counts
│   ├── pull_sqls.py       ← Pull monthly SQL counts (hs_v2_date_entered_opportunity)
│   ├── pull_meetings.py   ← Pull discovery meeting data
│   ├── pull_ads.py        ← Pull ad spend from HubSpot Marketing API
│   └── build.py           ← Combine template + data → output dashboard HTML
├── worker/
│   └── cloudflare-worker.js ← Proxy for browser-side HubSpot API calls (ads)
└── output/
    └── boom-dashboard.html  ← Final built dashboard (open in browser)
```

## KEY COMMANDS

### Full refresh (pull all data + rebuild dashboard):
```bash
./scripts/refresh.sh
```

### Pull only deals:
```bash
python3 scripts/pull_deals.py
```

### Build dashboard from current data:
```bash
python3 scripts/build.py
```

### Open dashboard:
```bash
open output/boom-dashboard.html  # macOS
xdg-open output/boom-dashboard.html  # Linux
```

## HUBSPOT API REFERENCE

### Authentication
All API calls use Bearer token authentication:
```
Authorization: Bearer {token from config.json}
```

### Base URL
```
https://api.hubapi.com
```

### Key Endpoints

**Deals (CRM):**
```
POST /crm/v3/objects/deals/search
```

**Contacts (CRM):**
```
POST /crm/v3/objects/contacts/search
```

**Meetings (CRM):**
```
POST /crm/v3/objects/meetings/search
```

**Ad Accounts:**
```
GET /marketing/v3/ads/ad-accounts
```

**Ad Account Analytics (spend by month):**
```
GET /marketing/v3/ads/ad-accounts/{accountId}/analytics?startDate=2025-01-01&endDate=2026-12-31&breakdownBy=MONTH
```

**Ad Campaigns:**
```
GET /marketing/v3/ads/campaigns?adAccountId={accountId}
```

## DEAL STAGE MAPPING (Sales 2.0 Pipeline: 93413737)
| Stage ID | Name | Dashboard Code |
|----------|------|---------------|
| 171811493 | Attack List | atk |
| 1075455291 | Discovery | disc |
| 1075460493 | Negotiation | neg |
| 1275009440 | Contract Sent | cs |
| 1108564665 | Closed Won | won |
| 216501682 | Closed Lost | lost |

## DEAL PROPERTIES TO PULL
```
dealname, dealstage, hs_mrr, hs_arr, amount, closedate, createdate,
commitment_listings, how_did_you_hear_about_us_, pipeline
```

## CONTACT PROPERTIES
- `contact_origins` — enum: Conference, Import, Ads, Meeting Links, Website Form, Newsletter, Webinar, SDR Operation, Email Outbound, Meta, LinkedIn, Google
- `contact_sources` — enum: LinkedIn Ads, Meta Ads, Google Ads, Organic, Direct, Outbound, SDR Operation
- `hs_v2_date_entered_opportunity` — Date contact entered SQL lifecycle stage (THIS IS THE SQL METRIC)
- `lifecyclestage` — includes custom stages

## MEETING PROPERTIES
- `hs_activity_type` — filter for "Discovery Meeting"
- `hs_meeting_outcome` — SCHEDULED, COMPLETED, RESCHEDULED, NO_SHOW, CANCELED
- `hs_meeting_start_time` — meeting date

## KPI DEFINITIONS (From HubSpot Team)

### Sales Pipeline Tab:
- **Open Deals** = deals in Discovery, Negotiation, Attack List, Contract Sent (NOT won/lost)
- **Won MRR** = sum `hs_mrr` of Closed Won deals in selected timeframe
- **Won ARR** = sum `hs_arr` of Closed Won deals in selected timeframe
- **Pipeline MRR** = sum `hs_mrr` of open deals
- **Win Rate** = won deals / total deals
- **SQL Rate** = SQLs (contacts entering SQL stage) / Leads In (contacts created)
- **Demo Booked** = Discovery Meetings with outcome SCHEDULED
- **Demo Completed** = Discovery Meetings with outcome COMPLETED
- **Avg meetings per deal** = total discovery meetings / total deals (PENDING)
- **Avg meetings per won deal** = meetings for won deals / won deals (PENDING)

### Webinar Tab:
All metrics filtered to contacts with `contact_origins = Webinar`:
- Won MRR, Won ARR, Pipeline MRR, Win Rate (webinar-attributed deals only)
- SQLs = contacts with `contact_origins=Webinar` AND `hs_v2_date_entered_opportunity` in period
- Demo Booked/Completed = meetings of webinar-attributed contacts

### Conference Tab:
Same as Webinar but filtered to `contact_origins = Conference`

## LEADS DATA FORMAT
Monthly contact creation counts. Format: `[{s:"YYYY-MM-DD", e:"YYYY-MM-DD", t:count}, ...]`
- Pull from HubSpot by searching contacts with `createdate` GTE/LTE for each month
- Use the `total` field from search results (set limit=1, just need the count)

## SQL DATA FORMAT
Monthly counts of contacts entering SQL stage. Stored in SQ array in template.
- Pull from HubSpot by searching contacts with `hs_v2_date_entered_opportunity` GTE/LTE for each month

## AD SPEND INTEGRATION
HubSpot has Meta, Google, and LinkedIn ad accounts connected. The Marketing API can pull spend data:
1. GET `/marketing/v3/ads/ad-accounts` → list all connected ad accounts with network type
2. GET `/marketing/v3/ads/ad-accounts/{id}/analytics?startDate=X&endDate=Y&breakdownBy=MONTH` → monthly spend

The dashboard needs spend per channel per month to calculate:
- **CPL** = Spend / Leads from that channel
- **CPA** = Spend / Customers Won from that channel
- **ROAS** = Revenue / Spend

**NOTE:** The private app token needs `ads_read` scope added for this to work. Current scopes: `marketing.campaigns.read`, `marketing.campaigns.revenue.read`.

## KNOWN DATA GAPS
1. **6 won deals have $0 hs_mrr** — Air TLV, Homis, Atmabnb, Two Five Five, Dwell PM, Second Home Hosting (dup). They have deal `amount` but no MRR filled in.
2. **Won Deals pipeline (116281938)** has 52 additional customers ($114K MRR) not in the dashboard. Future integration needed.
3. **Upsell pipeline (122477648)** has 17 deals not counted.

## STYLE
- Dark theme: `--bg:#0B0E11; --s:#141820; --s2:#1A2030`
- Fonts: DM Sans + Playfair Display
- Charts: Chart.js 4.4.1
- All deal names link to HubSpot record
- KPI boxes are clickable → modal preview with deal list
- Date filter with preset buttons (All, Q1 26, Q4 25, YTD)
