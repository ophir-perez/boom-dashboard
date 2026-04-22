#!/usr/bin/env python3
"""Pull advertising spend data from HubSpot Marketing API.

REQUIRES: ads_read scope on the private app token.
To add: HubSpot > Development > Legacy Apps > your app > Scopes > add ads_read

Connected ad accounts: Meta Ads, Google Ads, LinkedIn Ads
"""
import json, requests, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOKEN = os.environ.get("HUBSPOT_TOKEN")
if not TOKEN:
    with open(os.path.join(ROOT, "config.json")) as f:
        TOKEN = json.load(f)["hubspot"]["token"]

BASE = "https://api.hubapi.com"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

def get_ad_accounts():
    """List all connected ad accounts."""
    r = requests.get(f"{BASE}/marketing/v3/ads/ad-accounts?limit=100", headers=HEADERS)
    if r.status_code == 403:
        print("  ERROR: Token lacks ads_read scope. Add it in HubSpot Legacy Apps.")
        print("  Go to: https://app.hubspot.com/developer/24030694/application/private")
        print("  Edit your app > Scopes > check ads_read > Save")
        return None
    r.raise_for_status()
    return r.json().get("results", [])

def get_account_analytics(account_id, start="2025-01-01", end="2026-12-31"):
    """Get monthly spend breakdown for an ad account."""
    url = f"{BASE}/marketing/v3/ads/ad-accounts/{account_id}/analytics"
    params = {"startDate": start, "endDate": end, "breakdownBy": "MONTH"}
    r = requests.get(url, headers=HEADERS, params=params)
    if r.status_code != 200:
        print(f"  Warning: Could not pull analytics for {account_id}: {r.status_code}")
        return []
    data = r.json()
    return data.get("results", data if isinstance(data, list) else [])

def main():
    print("Pulling ad spend from HubSpot...")
    
    accounts = get_ad_accounts()
    if accounts is None:
        sys.exit(1)
    
    if not accounts:
        print("  No ad accounts found. Check HubSpot > Marketing > Ads to connect accounts.")
        sys.exit(1)
    
    print(f"\n  Found {len(accounts)} ad accounts:")
    
    all_spend = []
    for acc in accounts:
        aid = acc.get("adAccountId", acc.get("id", ""))
        name = acc.get("name", aid)
        network = acc.get("adNetwork", "UNKNOWN")
        currency = acc.get("currency", "USD")
        print(f"    {network}: {name} ({aid})")
        
        analytics = get_account_analytics(aid)
        
        account_data = {
            "accountId": aid,
            "name": name,
            "network": network,
            "currency": currency,
            "monthly": []
        }
        
        for period in analytics:
            # HubSpot returns spend in various formats depending on the endpoint
            spend = period.get("spend", period.get("cost", 0))
            impressions = period.get("impressions", 0)
            clicks = period.get("clicks", 0)
            date = period.get("date", period.get("startDate", ""))
            
            account_data["monthly"].append({
                "date": date,
                "spend": float(spend or 0),
                "impressions": int(impressions or 0),
                "clicks": int(clicks or 0),
            })
        
        total_spend = sum(m["spend"] for m in account_data["monthly"])
        print(f"      Total spend: ${total_spend:,.2f}")
        all_spend.append(account_data)
    
    outpath = os.path.join(ROOT, "data", "ads.json")
    with open(outpath, "w") as f:
        json.dump(all_spend, f, indent=2)
    
    # Also create a summary by network by month for the dashboard
    summary = {}  # {network: {YYYY-MM: spend}}
    for acc in all_spend:
        net = acc["network"]
        if net not in summary:
            summary[net] = {}
        for m in acc["monthly"]:
            ym = m["date"][:7] if m["date"] else "unknown"
            summary[net][ym] = summary[net].get(ym, 0) + m["spend"]
    
    summary_path = os.path.join(ROOT, "data", "ads_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n  Saved raw data to {outpath}")
    print(f"  Saved summary to {summary_path}")

if __name__ == "__main__":
    main()
