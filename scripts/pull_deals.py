#!/usr/bin/env python3
"""Pull all deals from HubSpot Sales 2.0 pipeline, enrich with contact attribution."""
import json, requests, os, sys, time

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

DEAL_PROPERTIES = [
    "dealname", "dealstage", "hs_mrr", "hs_arr", "amount",
    "closedate", "createdate", "commitment_listings",
    "how_did_you_hear_about_us_", "pipeline"
]

CONTACT_PROPERTIES = [
    "hs_analytics_source",           # First touch source (PAID_SEARCH, PAID_SOCIAL, etc.)
    "hs_analytics_source_data_1",    # First touch detail 1 (campaign/ad name)
    "hs_analytics_source_data_2",    # First touch detail 2
    "hs_latest_source",              # Last touch source
    "hs_latest_source_data_1",       # Last touch detail 1
    "hs_latest_source_data_2",       # Last touch detail 2
    "contact_origins",               # Webinar / Conference / Ads / etc.
    "contact_sources",               # LinkedIn Ads / Meta Ads / Google Ads / etc.
    "how_did_you_hear_about_us_",    # Self-reported source
    "webinars_name",                 # Which webinar attended
    "source_of_lead",                # Which conference attended
    "hs_v2_date_entered_opportunity",# SQL date
]


def pull_all_deals():
    all_deals = []
    after = 0
    while True:
        body = {
            "filterGroups": [{"filters": [
                {"propertyName": "pipeline", "operator": "EQ", "value": PIPELINE}
            ]}],
            "properties": DEAL_PROPERTIES,
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
            time.sleep(0.2)
        else:
            break
    return all_deals


def get_deal_contact_ids(deal_ids):
    """Batch fetch associated contact IDs for a list of deal IDs."""
    contact_map = {}  # deal_id -> first contact_id
    # Process in batches of 100
    for i in range(0, len(deal_ids), 100):
        batch = deal_ids[i:i+100]
        body = {"inputs": [{"id": str(did)} for did in batch]}
        r = requests.post(
            f"{BASE}/crm/v3/associations/deals/contacts/batch/read",
            headers=HEADERS, json=body
        )
        if r.status_code != 200:
            print(f"  Warning: associations batch failed ({r.status_code})")
            time.sleep(1)
            continue
        data = r.json()
        for result in data.get("results", []):
            deal_id = str(result.get("from", {}).get("id", ""))
            tos = result.get("to", [])
            if tos and deal_id:
                contact_map[deal_id] = str(tos[0]["id"])
        time.sleep(0.2)
    return contact_map


def get_contacts_batch(contact_ids):
    """Batch fetch contact properties for a list of contact IDs."""
    contacts = {}
    unique_ids = list(set(contact_ids))
    for i in range(0, len(unique_ids), 100):
        batch = unique_ids[i:i+100]
        body = {
            "inputs": [{"id": cid} for cid in batch],
            "properties": CONTACT_PROPERTIES
        }
        r = requests.post(
            f"{BASE}/crm/v3/objects/contacts/batch/read",
            headers=HEADERS, json=body
        )
        if r.status_code != 200:
            print(f"  Warning: contacts batch failed ({r.status_code})")
            time.sleep(1)
            continue
        data = r.json()
        for contact in data.get("results", []):
            contacts[str(contact["id"])] = contact.get("properties", {})
        time.sleep(0.2)
    return contacts


def enrich_deal(raw, contact_props=None):
    """Convert raw HubSpot deal to dashboard format, enriched with contact attribution."""
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

    c = contact_props or {}

    # Attribution from contact
    ft = c.get("hs_analytics_source", "") or ""
    ftd1 = c.get("hs_analytics_source_data_1", "") or ""
    ftd2 = c.get("hs_analytics_source_data_2", "") or ""
    lt = c.get("hs_latest_source", "") or ""
    ltd1 = c.get("hs_latest_source_data_1", "") or ""
    ltd2 = c.get("hs_latest_source_data_2", "") or ""
    ls = c.get("contact_origins", "") or ""       # Webinar / Conference / Ads / etc.
    sol = c.get("source_of_lead", "") or ""       # Which conference
    wn = c.get("webinars_name", "") or ""         # Which webinar
    cs = c.get("contact_sources", "") or ""       # LinkedIn Ads / Meta Ads / Google Ads

    # Use contact's how_did_you_hear if deal doesn't have it
    if not sr:
        sr = c.get("how_did_you_hear_about_us_", "") or ""

    # Channel flags (mirrors the JS logic in template)
    ch_google = 1 if (ft == "PAID_SEARCH" or lt == "PAID_SEARCH") else 0
    ch_meta = 1 if (ft == "PAID_SOCIAL" or lt == "PAID_SOCIAL" or
                    "Facebook" in ftd1 or "Facebook" in ltd1 or
                    cs in ("Meta Ads",) or "Meta" in ls) else 0
    ch_linkedin = 1 if ("LinkedIn" in cs or "LinkedIn" in ls or
                        "linkedin" in ftd1.lower() or "linkedin" in ltd1.lower()) else 0
    ch_organic = 1 if (ft == "ORGANIC_SEARCH" or lt == "ORGANIC_SEARCH") else 0
    ch_email = 1 if (ft == "EMAIL_MARKETING" or lt == "EMAIL_MARKETING" or
                     "hs_email" in ltd1 or "webinar" in (ftd1 + ltd1).lower()) else 0
    ch_ref = 1 if (ft == "REFERRALS" or lt == "REFERRALS") else 0
    ch_webinar = 1 if ("webinar" in (ftd1 + ltd1).lower() or
                       ls == "Webinar" or bool(wn)) else 0
    ch_conf = 1 if (ls in ("Conference", "VRMA 25", "FAVR 2025") or
                    any(x in (sol or "").lower() for x in
                        ["convention", "scale", "porto", "munich", "barcelona"])) else 0

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
        # Contact attribution
        "ft": ft, "ftd1": ftd1, "ftd2": ftd2,
        "lt": lt, "ltd1": ltd1, "ltd2": ltd2,
        "ls": ls, "sol": sol, "wn": wn, "cs": cs,
        # Channel flags
        "ch_google": ch_google, "ch_meta": ch_meta, "ch_linkedin": ch_linkedin,
        "ch_organic": ch_organic, "ch_email": ch_email,
        "ch_ref": ch_ref, "ch_webinar": ch_webinar, "ch_conf": ch_conf,
    }


def main():
    print("Pulling deals from HubSpot...")
    raw_deals = pull_all_deals()
    deal_ids = [d["id"] for d in raw_deals]

    print(f"\nFetching associated contacts for {len(deal_ids)} deals...")
    contact_map = get_deal_contact_ids(deal_ids)
    print(f"  Found contacts for {len(contact_map)} deals")

    contact_ids = list(set(contact_map.values()))
    print(f"\nFetching attribution for {len(contact_ids)} contacts...")
    contacts = get_contacts_batch(contact_ids)
    print(f"  Fetched {len(contacts)} contact records")

    # Enrich deals with contact attribution
    deals = []
    for raw in raw_deals:
        cid = contact_map.get(str(raw["id"]))
        contact_props = contacts.get(cid, {}) if cid else {}
        deals.append(enrich_deal(raw, contact_props))

    # Stats
    won = [d for d in deals if d["w"]]
    lost = [d for d in deals if d["l"]]
    opn = [d for d in deals if not d["w"] and not d["l"]]
    ch_web = [d for d in deals if d["ch_webinar"]]
    ch_conf = [d for d in deals if d["ch_conf"]]
    ch_google = [d for d in deals if d["ch_google"]]
    ch_meta = [d for d in deals if d["ch_meta"]]

    print(f"\n  Total: {len(deals)} | Won: {len(won)} | Lost: {len(lost)} | Open: {len(opn)}")
    print(f"  Won MRR: ${sum(d['mrr'] for d in won):,.2f}")
    print(f"  Pipeline MRR: ${sum(d['mrr'] for d in opn):,.2f}")
    print(f"  Attribution: Google={len(ch_google)} Meta={len(ch_meta)} Webinar={len(ch_web)} Conf={len(ch_conf)}")

    outpath = os.path.join(ROOT, "data", "deals.json")
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, "w") as f:
        json.dump(deals, f)
    print(f"  Saved to {outpath}")


if __name__ == "__main__":
    main()
