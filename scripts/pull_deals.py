#!/usr/bin/env python3
"""Pull all deals from HubSpot Sales 2.0 pipeline and save as enriched JSON."""
import json, requests, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Support HUBSPOT_TOKEN env var (used in CI/CD — token stored as GitHub Secret)
TOKEN = os.environ.get("HUBSPOT_TOKEN")
if not TOKEN:
    with open(os.path.join(ROOT, "config.json")) as f:
        TOKEN = json.load(f)["hubspot"]["token"]

PIPELINE = "93413737"
ACCOUNT_ID = "24030694"
STAGES = {
    "171811493": {"name": "Attack List", "code": "atk", "order": 1},
    "1075455291": {"name": "Discovery", "code": "disc", "order": 3},
    "1075460493": {"name": "Negotiation", "code": "neg", "order": 4},
    "1275009440": {"name": "Contract Sent", "code": "cs", "order": 5},
    "1108564665": {"name": "Closed Won", "code": "won", "order": 6},
    "216501682": {"name": "Closed Lost", "code": "lost", "order": 7},
}
BASE = "https://api.hubapi.com"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

PROPERTIES = [
    "dealname", "dealstage", "hs_mrr", "hs_arr", "amount",
    "closedate", "createdate", "commitment_listings",
    "how_did_you_hear_about_us_", "pipeline"
]

def pull_all_deals():
    """Pull all deals from Sales 2.0 pipeline using search API with pagination."""
    all_deals = []
    after = 0
    while True:
        body = {
            "filterGroups": [{"filters": [
                {"propertyName": "pipeline", "operator": "EQ", "value": PIPELINE}
            ]}],
            "properties": PROPERTIES,
            "limit": 100,
            "after": after,
            "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}]
        }
        r = requests.post(f"{BASE}/crm/v3/objects/deals/search", headers=HEADERS, json=body)
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])
        all_deals.extend(results)
        print(f"  Pulled {len(all_deals)}/{data.get('total', '?')} deals...")
        
        paging = data.get("paging", {}).get("next", {})
        if paging.get("after"):
            after = int(paging["after"])
        else:
            break
    return all_deals

def enrich_deal(raw):
    """Convert raw HubSpot deal to dashboard format."""
    p = raw["properties"]
    sid = p.get("dealstage", "")
    stage = STAGES.get(sid, {"name": "Unknown", "code": "unk", "order": 0})
    
    mrr = float(p.get("hs_mrr") or 0)
    arr = float(p.get("hs_arr") or 0)
    amt = float(p.get("amount") or 0)
    cd = (p.get("closedate") or "")[:10]
    cr = (p.get("createdate") or "")[:10]
    lst = int(float(p.get("commitment_listings") or 0))
    sr = p.get("how_did_you_hear_about_us_", "") or ""
    hid = raw["id"]
    
    return {
        "n": (p.get("dealname") or "").strip(),
        "hid": hid,
        "url": f"https://app.hubspot.com/contacts/{ACCOUNT_ID}/record/0-3/{hid}",
        "sn": stage["name"], "so": stage["order"], "sc": stage["code"],
        "w": 1 if sid == "1108564665" else 0,
        "l": 1 if sid == "216501682" else 0,
        "mrr": mrr, "arr": arr, "a": amt,
        "cd": cd, "cr": cr,
        "list": lst, "sr": sr,
        "neg": 1 if sid == "1075460493" else 0,
        "ms1": "", "ms2": "",
    }

def main():
    print("Pulling deals from HubSpot...")
    raw_deals = pull_all_deals()
    deals = [enrich_deal(d) for d in raw_deals]
    
    # Stats
    won = [d for d in deals if d["w"]]
    lost = [d for d in deals if d["l"]]
    opn = [d for d in deals if not d["w"] and not d["l"]]
    
    print(f"\n  Total: {len(deals)} | Won: {len(won)} | Lost: {len(lost)} | Open: {len(opn)}")
    print(f"  Won MRR: ${sum(d['mrr'] for d in won):,.2f}")
    print(f"  Pipeline MRR: ${sum(d['mrr'] for d in opn):,.2f}")
    
    outpath = os.path.join(ROOT, "data", "deals.json")
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, "w") as f:
        json.dump(deals, f)
    print(f"  Saved to {outpath}")

if __name__ == "__main__":
    main()
