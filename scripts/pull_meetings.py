#!/usr/bin/env python3
"""Pull discovery meeting data from HubSpot."""
import json, requests, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOKEN = os.environ.get("HUBSPOT_TOKEN")
if not TOKEN:
    with open(os.path.join(ROOT, "config.json")) as f:
        TOKEN = json.load(f)["hubspot"]["token"]

BASE = "https://api.hubapi.com"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

def pull_meetings(start_date="2025-01-01"):
    """Pull all discovery meetings from start_date onward."""
    all_meetings = []
    after = 0
    while True:
        body = {
            "filterGroups": [{"filters": [
                {"propertyName": "hs_activity_type", "operator": "EQ", "value": "Discovery Meeting"},
                {"propertyName": "hs_meeting_start_time", "operator": "GTE", "value": start_date}
            ]}],
            "properties": [
                "hs_meeting_title", "hs_meeting_start_time", 
                "hs_meeting_outcome", "hs_activity_type"
            ],
            "limit": 100,
            "after": after,
            "sorts": [{"propertyName": "hs_meeting_start_time", "direction": "DESCENDING"}]
        }
        r = requests.post(f"{BASE}/crm/v3/objects/meetings/search", headers=HEADERS, json=body)
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])
        all_meetings.extend(results)
        
        paging = data.get("paging", {}).get("next", {})
        if paging.get("after"):
            after = int(paging["after"])
        else:
            break
    return all_meetings

def main():
    print("Pulling discovery meetings...")
    raw = pull_meetings()
    
    # Summarize by month
    monthly = {}
    for m in raw:
        p = m["properties"]
        dt = (p.get("hs_meeting_start_time") or "")[:7]  # YYYY-MM
        outcome = p.get("hs_meeting_outcome", "UNKNOWN")
        if dt not in monthly:
            monthly[dt] = {"COMPLETED": 0, "SCHEDULED": 0, "NO_SHOW": 0, "RESCHEDULED": 0, "CANCELED": 0}
        monthly[dt][outcome] = monthly[dt].get(outcome, 0) + 1
    
    print(f"\n  Total meetings: {len(raw)}")
    for ym in sorted(monthly.keys()):
        m = monthly[ym]
        print(f"  {ym}: C={m['COMPLETED']} S={m['SCHEDULED']} NS={m['NO_SHOW']} R={m['RESCHEDULED']} X={m['CANCELED']}")
    
    # Save raw meetings
    meetings = []
    for m in raw:
        p = m["properties"]
        meetings.append({
            "id": m["id"],
            "title": p.get("hs_meeting_title", ""),
            "date": (p.get("hs_meeting_start_time") or "")[:10],
            "outcome": p.get("hs_meeting_outcome", ""),
            "type": p.get("hs_activity_type", ""),
        })
    
    outpath = os.path.join(ROOT, "data", "meetings.json")
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, "w") as f:
        json.dump(meetings, f)
    print(f"  Saved to {outpath}")

if __name__ == "__main__":
    main()
