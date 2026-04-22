#!/usr/bin/env python3
"""Pull monthly contact creation counts from HubSpot."""
import json, requests, os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOKEN = os.environ.get("HUBSPOT_TOKEN")
if not TOKEN:
    with open(os.path.join(ROOT, "config.json")) as f:
        TOKEN = json.load(f)["hubspot"]["token"]

BASE = "https://api.hubapi.com"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

def count_contacts_in_range(start, end):
    """Count contacts created between start and end dates."""
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "createdate", "operator": "GTE", "value": start},
            {"propertyName": "createdate", "operator": "LTE", "value": end}
        ]}],
        "properties": ["createdate"],
        "limit": 1
    }
    r = requests.post(f"{BASE}/crm/v3/objects/contacts/search", headers=HEADERS, json=body)
    r.raise_for_status()
    return r.json().get("total", 0)

def main():
    print("Pulling monthly contact counts...")
    
    # Define months to pull (pre-2025 as one bucket, then monthly)
    months = [
        ("2024-01-01", "2024-12-31", "Pre-2025"),
        ("2025-01-01", "2025-01-31", "Jan 25"), ("2025-02-01", "2025-02-28", "Feb 25"),
        ("2025-03-01", "2025-03-31", "Mar 25"), ("2025-04-01", "2025-04-30", "Apr 25"),
        ("2025-05-01", "2025-05-31", "May 25"), ("2025-06-01", "2025-06-30", "Jun 25"),
        ("2025-07-01", "2025-07-31", "Jul 25"), ("2025-08-01", "2025-08-31", "Aug 25"),
        ("2025-09-01", "2025-09-30", "Sep 25"), ("2025-10-01", "2025-10-31", "Oct 25"),
        ("2025-11-01", "2025-11-30", "Nov 25"), ("2025-12-01", "2025-12-31", "Dec 25"),
        ("2026-01-01", "2026-01-31", "Jan 26"), ("2026-02-01", "2026-02-28", "Feb 26"),
        ("2026-03-01", "2026-03-31", "Mar 26"), ("2026-04-01", "2026-04-30", "Apr 26"),
        ("2026-05-01", "2026-05-31", "May 26"), ("2026-06-01", "2026-06-30", "Jun 26"),
    ]
    
    leads = []
    total = 0
    for start, end, label in months:
        count = count_contacts_in_range(start, end)
        if count > 0:
            leads.append({"s": start, "e": end, "t": count})
            total += count
            print(f"  {label}: {count:,}")
    
    outpath = os.path.join(ROOT, "data", "leads.json")
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, "w") as f:
        json.dump(leads, f)
    print(f"\n  Total: {total:,} contacts")
    print(f"  Saved to {outpath}")

if __name__ == "__main__":
    main()
