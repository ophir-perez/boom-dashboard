#!/usr/bin/env python3
"""Pull monthly contact counts: total leads, webinar leads, conference leads."""
import json, requests, os, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOKEN = os.environ.get("HUBSPOT_TOKEN")
if not TOKEN:
    with open(os.path.join(ROOT, "config.json")) as f:
        TOKEN = json.load(f)["hubspot"]["token"]

BASE = "https://api.hubapi.com"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

MONTHS = [
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


def count_contacts(start, end, extra_filters=None):
    filters = [
        {"propertyName": "createdate", "operator": "GTE", "value": start},
        {"propertyName": "createdate", "operator": "LTE", "value": end},
    ]
    if extra_filters:
        filters.extend(extra_filters)
    body = {
        "filterGroups": [{"filters": filters}],
        "properties": ["createdate"],
        "limit": 1
    }
    r = requests.post(f"{BASE}/crm/v3/objects/contacts/search", headers=HEADERS, json=body)
    r.raise_for_status()
    return r.json().get("total", 0)


def pull_series(label, extra_filters=None):
    results = []
    total = 0
    for start, end, lbl in MONTHS:
        count = count_contacts(start, end, extra_filters)
        time.sleep(0.3)
        results.append({"s": start, "e": end, "t": count})
        if count > 0:
            total += count
            print(f"    {lbl}: {count:,}")
    return results, total


def main():
    outdir = os.path.join(ROOT, "data")
    os.makedirs(outdir, exist_ok=True)

    # --- Total leads ---
    print("Pulling total monthly lead counts...")
    leads, total = pull_series("leads")
    with open(os.path.join(outdir, "leads.json"), "w") as f:
        json.dump([m for m in leads if m["t"] > 0], f)
    print(f"  Total: {total:,} contacts\n")

    # --- Webinar leads (contact_origins = Webinar) ---
    print("Pulling webinar lead counts...")
    wl, wl_total = pull_series("webinar", [
        {"propertyName": "contact_origins", "operator": "EQ", "value": "Webinar"}
    ])
    with open(os.path.join(outdir, "webinar_leads.json"), "w") as f:
        json.dump(wl, f)
    print(f"  Webinar total: {wl_total:,}\n")

    # --- Conference leads (contact_origins = Conference / VRMA 25 / FAVR 2025) ---
    print("Pulling conference lead counts...")
    # HubSpot IN operator for enum
    cl_conf, _ = pull_series("conf", [
        {"propertyName": "contact_origins", "operator": "EQ", "value": "Conference"}
    ])
    cl_vrma, _ = pull_series("vrma", [
        {"propertyName": "contact_origins", "operator": "EQ", "value": "VRMA 25"}
    ])
    cl_favr, _ = pull_series("favr", [
        {"propertyName": "contact_origins", "operator": "EQ", "value": "FAVR 2025"}
    ])
    # Merge the three conference series
    cl = []
    cl_total = 0
    for i, (start, end, lbl) in enumerate(MONTHS):
        t = cl_conf[i]["t"] + cl_vrma[i]["t"] + cl_favr[i]["t"]
        cl.append({"s": start, "e": end, "t": t})
        cl_total += t
    with open(os.path.join(outdir, "conf_leads.json"), "w") as f:
        json.dump(cl, f)
    print(f"  Conference total: {cl_total:,}")


if __name__ == "__main__":
    main()
