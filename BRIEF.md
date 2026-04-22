# Boom Dashboard — Setup & Brief

## Quick Start

### 1. Prerequisites
```bash
# Install Claude Code (requires Node.js 18+)
npm install -g @anthropic-ai/claude-code

# Install Python requests library
pip install requests
```

### 2. Unzip & Configure
```bash
unzip boom-dashboard.zip
cd boom-dashboard

# Edit config.json with your ROTATED HubSpot token
# (The current token should be rotated for security)
```

### 3. First Run
```bash
# Full data refresh from HubSpot + build dashboard
chmod +x scripts/refresh.sh
./scripts/refresh.sh
```

### 4. Open Dashboard
```bash
open output/boom-dashboard.html
```

### 5. Using Claude Code
```bash
cd boom-dashboard
claude

# Then just ask:
# "Refresh the dashboard"
# "Pull latest deals and rebuild"
# "Show me this week's performance"
# "Add the Won Deals pipeline to the dashboard"
```

---

## Architecture

```
HubSpot CRM API
       │
       ▼
  Python Scripts ──→ data/*.json ──→ build.py ──→ output/boom-dashboard.html
       │                                              │
       │                                              ▼
       │                                    Open in browser
       ▼
  Cloudflare Worker (optional)
       │
       ▼
  Browser-side live ad spend
```

**The dashboard is a single HTML file** with embedded Chart.js, inline CSS, and all data baked in. No server needed — just open the HTML file.

**Data is pulled via Python scripts** that call HubSpot's REST API. These write JSON files that get injected into the HTML template at build time.

**For live ad spend in the browser**, a Cloudflare Worker acts as a CORS proxy. This is optional — the Python `pull_ads.py` script can also bake ad data in at build time.

---

## HubSpot Account Structure

### Pipelines
| Pipeline | ID | Deals | Purpose |
|----------|-----|-------|---------|
| **Sales 2.0** | 93413737 | 186 | Primary sales pipeline (dashboard source) |
| **Won Deals** | 116281938 | 52 | Post-close customer tracking ($114K MRR) |
| **Upsell** | 122477648 | 17 | Customer upsells |
| Cold Leads | 117323190 | — | Disqualified |
| Ambassador | 122481495 | — | Referral partners |
| Investors | 652029074 | — | Investor relations |
| BoomAir | 728550662 | — | Separate product |
| Business Dev | 806963594 | — | BD deals |
| Subscription Change | 834706586 | — | Plan changes |
| Meetings | 856543905 | — | Meeting tracking |

### Deal Stages (Sales 2.0)
| Stage | ID | Status |
|-------|----|--------|
| Attack List | 171811493 | Open |
| Discovery | 1075455291 | Open |
| Negotiation | 1075460493 | Open |
| Contract Sent | 1275009440 | Open |
| Closed Won | 1108564665 | Closed |
| Closed Lost | 216501682 | Closed |

### Key Contact Properties
| Property | Type | Purpose |
|----------|------|---------|
| `contact_origins` | Enum | Attribution source (Webinar, Conference, Ads, etc.) |
| `contact_sources` | Enum | Channel (LinkedIn Ads, Meta Ads, Google Ads, etc.) |
| `hs_v2_date_entered_opportunity` | Date | When contact became SQL (lifecycle stage) |
| `how_did_you_hear_about_us_` | Enum | Self-reported source |
| `webinars_name` | Enum | Which webinar attended |
| `source_of_lead` | Enum | Which conference attended |

### Ad Accounts (Connected in HubSpot)
- Meta Ads
- Google Ads
- LinkedIn Ads

---

## Current Numbers (as of Apr 14, 2026)

| Metric | Value |
|--------|-------|
| Total Contacts | 15,012 |
| Total SQLs (lifecycle) | 4,346 |
| Total Deals (Sales 2.0) | 186 |
| Won Deals | 81 |
| Lost Deals | 100 |
| Open Deals | 5 |
| All-time Won MRR | $109,191 |
| All-time Won ARR | $1,310,296 |
| Pipeline MRR | $7,714 |
| Win Rate | 44.8% |
| Won in 2026 | 12 deals / $11,038 MRR |

### Open Deals Right Now
1. Georgia - GK Properties (Attack List, $1,885 MRR)
2. Nick - Osa Property Management (Attack List, $2,175 MRR)
3. Janine - 5 Star Bali Villa (Attack List, $2,900 MRR)
4. Mary - Redtail Ridge Rentals (Discovery, $754 MRR)
5. Dominika - Aguesseau Capital (Negotiation, $69,600 amount)

---

## Pending Improvements

### High Priority
1. **Enable ads_read scope** on the HubSpot private app token to pull ad spend data
2. **Rotate the token** — current one was shared in chat
3. **Webinar/Conference tabs** — filter SQLs, meetings, and deals by `contact_origins` attribution
4. **Avg meetings per deal / per won deal** — new Sales Pipeline KPIs

### Medium Priority
5. **Won Deals pipeline integration** — 52 additional customers ($114K MRR) not in dashboard
6. **Deploy Cloudflare Worker** for live browser-side ad spend
7. **Fix 6 deals with $0 hs_mrr** — data entry gap in HubSpot (Air TLV, Homis, Atmabnb, Two Five Five, Dwell PM, Second Home Hosting)

### Lower Priority
8. **Multi-contact aggregation** — aggregate all contacts per deal for attribution
9. **GitHub Pages hosting** — deploy as a live URL for team access
10. **Automated daily refresh** — cron job or GitHub Action to rebuild nightly

---

## Token Security

**IMPORTANT:** The token in config.json was shared in a chat conversation and should be rotated immediately.

To rotate:
1. Go to `https://app.hubspot.com/developer/24030694/application/private`
2. Click "Legacy Apps"
3. Find your app → click it
4. Go to Auth tab → Rotate token
5. Update `config.json` with new token
6. While there, add `ads_read` scope under Scopes tab
