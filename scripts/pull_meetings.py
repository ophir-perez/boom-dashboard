#!/usr/bin/env python3
"""Pull discovery meeting data from HubSpot."""
import json, requests, os, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOKEN = os.environ.get("HUBSPOT_TOKEN")
if not TOKEN:
    with open(os.path.join(ROOT, "config.json")) as f:
        TOKEN = json.load(f)["hubspot"]["token"]

BASE = "https://api.hubapi.com"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def pull_meetings(start_date="2025-07-01"):
    """Pull all meetings from start_date — no activity_type filter (too restrictive)."""
    all_meetings = []
    after = 0
    while True:
        body = {
            "filterGroups": [{"filters": [
                {"propertyName": "hs_meeting_start_time", "operator": "GTE", "value": start_date}
            ]}],
            "properties": [
                "hs_meeting_title",
                "hs_meeting_start_time",
                "hs_meeting_outcome",
                "hs_activity_type",
                "hs_internal_meeting_notes",
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
        print(f"  Fetched {len(all_meetings)} meetings so far...")

        paging = data.get("paging", {}).get("next", {})
        if paging.get("after"):
            after = int(paging["after"])
            time.sleep(0.3)
        else:
            break
    return all_meetings


def main():
    print("Pulling meetings from HubSpot...")
    raw = pull_meetings()

    # Filter to Discovery meetings only (check activity_type field)
    discovery = []
    for m in raw:
        p = m["properties"]
        atype = (p.get("hs_activity_type") or "").lower()
        title = (p.get("hs_meeting_title") or "").lower()
        # Include if activity type is Discovery, or title contains discovery/demo
        if "discovery" in atype or "discovery" in title or "demo" in title or atype == "":
            discovery.append(m)

    print(f"\n  Total meetings fetched: {len(raw)}")
    print(f"  Discovery/Demo meetings: {len(discovery)}")

    # Summarize by month + outcome
    monthly = {}
    for m in discovery:
        p = m["properties"]
        dt = (p.get("hs_meeting_start_time") or "")[:7]  # YYYY-MM
        outcome = (p.get("hs_meeting_outcome") or "UNKNOWN").upper()
        if dt not in monthly:
            monthly[dt] = {"COMPLETED": 0, "SCHEDULED": 0, "NO_SHOW": 0, "RESCHEDULED": 0, "CANCELED": 0, "UNKNOWN": 0}
        monthly[dt][outcome] = monthly[dt].get(outcome, 0) + 1

    for ym in sorted(monthly.keys()):
        m = monthly[ym]
        total = sum(m.values())
        print(f"  {ym}: total={total} C={m['COMPLETED']} S={m['SCHEDULED']} NS={m['NO_SHOW']} R={m['RESCHEDULED']} X={m['CANCELED']}")

    # Save as list of individual meeting records
    meetings = []
    for m in discovery:
        p = m["properties"]
        meetings.append({
            "id": m["id"],
            "title": (p.get("hs_meeting_title") or "Discovery Meeting"),
            "date": (p.get("hs_meeting_start_time") or "")[:10],
            "outcome": (p.get("hs_meeting_outcome") or "UNKNOWN").upper(),
            "type": (p.get("hs_activity_type") or ""),
        })

    outdir = os.path.join(ROOT, "data")
    os.makedirs(outdir, exist_ok=True)
    outpath = os.path.join(outdir, "meetings.json")
    with open(outpath, "w") as f:
        json.dump(meetings, f)
    print(f"  Saved {len(meetings)} meetings to {outpath}")


if __name__ == "__main__":
    main()
