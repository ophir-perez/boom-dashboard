#!/usr/bin/env python3
"""Pull all deals from HubSpot Sales 2.0 pipeline, enrich with ALL contact attribution."""
import json, requests, os, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
    "hs_analytics_source",
    "hs_analytics_source_data_1",
    "hs_analytics_source_data_2",
    "hs_latest_source",
    "hs_latest_source_data_1",
    "hs_latest_source_data_2",
    "hs_analytics_source_history",   # Full session history (semicolon-separated)
    "contact_origins",               # Boom custom: Webinar / Conference / Ads / etc.
    "contact_sources",               # Boom custom: LinkedIn Ads / Meta Ads / Google Ads
    "how_did_you_hear_about_us_",
    "webinars_name",
    "source_of_lead",
    "hs_v2_date_entered_opportunity",
]

# Map HubSpot source keys to display labels and tag CSS classes
SOURCE_MAP = {
    "PAID_SEARCH":      ("Google Ads",     "t-ps"),
    "PAID_SOCIAL":      ("Meta Ads",       "t-meta"),
    "ORGANIC_SEARCH":   ("Organic Search", "t-org"),
    "EMAIL_MARKETING":  ("Email",          "t-em"),
    "REFERRALS":        ("Referral",       "t-ref"),
    "DIRECT_TRAFFIC":   ("Direct",         "t-dir"),
    "SOCIAL_MEDIA":     ("Social",         "t-lin"),
    "AI_REFERRALS":     ("ChatGPT",        "t-ai"),
    "OFFLINE":          ("Offline/Import", "t-ft"),
}


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
    """Batch fetch ALL associated contact IDs for each deal (not just first)."""
    contact_map = {}  # deal_id -> [contact_id, ...]
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
        for result in r.json().get("results", []):
            deal_id = str(result.get("from", {}).get("id", ""))
            tos = [str(t["id"]) for t in result.get("to", [])]
            if tos and deal_id:
                contact_map[deal_id] = tos
        time.sleep(0.2)
    return contact_map


def get_contacts_batch(contact_ids):
    """Batch fetch contact properties."""
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
        for contact in r.json().get("results", []):
            contacts[str(contact["id"])] = contact.get("properties", {})
        time.sleep(0.2)
    return contacts


def merge_contact_props(contact_props_list):
    """
    Merge attribution from ALL contacts on a deal.
    Priority: pick the contact with the richest attribution data.
    For webinar/conference/ads flags, any contact matching counts.
    """
    if not contact_props_list:
        return {}

    # Start with the first contact's core analytics
    best = {}
    best_score = -1

    all_origins = []
    all_sources = []
    all_wn = []
    all_sol = []
    all_sr = []
    all_history = []

    for c in contact_props_list:
        ft = c.get("hs_analytics_source", "") or ""
        lt = c.get("hs_latest_source", "") or ""
        wn = c.get("webinars_name", "") or ""
        origins = c.get("contact_origins", "") or ""
        history = c.get("hs_analytics_source_history", "") or ""

        # Score this contact by richness of data
        score = (1 if ft else 0) + (1 if lt else 0) + (2 if wn else 0) + \
                (2 if origins else 0) + (1 if history else 0)

        if score > best_score:
            best_score = score
            best = c

        if origins:
            all_origins.append(origins)
        if c.get("contact_sources"):
            all_sources.append(c["contact_sources"])
        if wn:
            all_wn.append(wn)
        if c.get("source_of_lead"):
            all_sol.append(c["source_of_lead"])
        if c.get("how_did_you_hear_about_us_"):
            all_sr.append(c["how_did_you_hear_about_us_"])
        if history:
            all_history.extend(history.split(";"))

    # Build merged result from best contact + union of special fields
    merged = dict(best)
    merged["_all_origins"] = list(set(all_origins))
    merged["_all_sources"] = list(set(all_sources))
    merged["_all_wn"] = list(set(all_wn))
    merged["_all_sol"] = list(set(all_sol))
    merged["_all_sr"] = list(set(all_sr))
    merged["_all_history"] = list(set(h.strip() for h in all_history if h.strip()))
    return merged


def is_webinar(c):
    """True if any contact on this deal has webinar attribution."""
    if "Webinar" in c.get("_all_origins", []):
        return True
    if any(c.get("_all_wn", [])):
        return True
    # "Meeting Links" in HubSpot source data = webinar booking
    for field in ["hs_latest_source_data_1", "hs_analytics_source_data_1"]:
        val = (c.get(field) or "").lower()
        if "webinar" in val or "meeting_link" in val or "meeting link" in val:
            return True
    # Check full session history
    for h in c.get("_all_history", []):
        if "webinar" in h.lower() or "meeting_link" in h.lower():
            return True
    return False


def is_conference(c):
    """True if any contact on this deal has conference attribution."""
    conf_origins = {"Conference", "VRMA 25", "FAVR 2025"}
    if any(o in conf_origins for o in c.get("_all_origins", [])):
        return True
    for sol in c.get("_all_sol", []):
        if any(x in sol.lower() for x in ["convention", "scale", "porto", "munich", "barcelona", "vrma", "favr"]):
            return True
    return False


def build_touchpoints(c):
    """
    Build a list of all distinct touchpoint tags from all sources:
    first touch, last touch, full history, custom fields.
    Returns list of {l: label, c: css_class}
    """
    seen = set()
    tags = []

    def add(label, cls):
        key = label + cls
        if key not in seen:
            seen.add(key)
            tags.append({"l": label, "c": cls})

    ft = c.get("hs_analytics_source", "") or ""
    ftd1 = c.get("hs_analytics_source_data_1", "") or ""
    ftd2 = c.get("hs_analytics_source_data_2", "") or ""
    lt = c.get("hs_latest_source", "") or ""
    ltd1 = c.get("hs_latest_source_data_1", "") or ""
    ltd2 = c.get("hs_latest_source_data_2", "") or ""

    # First touch
    if ft and ft in SOURCE_MAP:
        lbl, cls = SOURCE_MAP[ft]
        add(f"FT: {lbl}", "t-ft")
        # Extra detail for paid channels
        if ft == "PAID_SEARCH":
            detail = (ftd2 or ftd1 or "Brand")[:22]
            add(f"Google: {detail}", "t-ps")
        elif ft == "PAID_SOCIAL":
            detail = (f" · {ftd2[:18]}" if ftd2 else "")
            add(f"Meta{detail}", "t-meta")
        elif ft == "ORGANIC_SEARCH":
            add("SEO" + (" (G)" if ftd2 == "GOOGLE" else ""), "t-org")
        elif ft == "AI_REFERRALS":
            add("ChatGPT", "t-ai")
        elif ft == "REFERRALS":
            add("Referral", "t-ref")
        elif ft == "DIRECT_TRAFFIC":
            add("Direct", "t-dir")
    elif ft:
        add(f"FT: {ft}", "t-ft")

    # Last touch (only if different from first)
    if lt and lt != ft:
        if lt in SOURCE_MAP:
            lbl, cls = SOURCE_MAP[lt]
            add(f"LT: {lbl}", "t-lt")
            if lt == "PAID_SOCIAL":
                add("Meta (LT)", "t-meta")
            elif lt == "PAID_SEARCH":
                add("Google (LT)", "t-ps")
            elif lt == "EMAIL_MARKETING":
                if "hs_email" in ltd1.lower():
                    add("HS Email (LT)", "t-em")
                else:
                    add("Email (LT)", "t-em")
            elif lt == "ORGANIC_SEARCH":
                add("SEO (LT)", "t-org")
            elif lt == "AI_REFERRALS":
                add("ChatGPT (LT)", "t-ai")
            elif lt == "REFERRALS":
                add("Referral (LT)", "t-ref")
        elif lt:
            add(f"LT: {lt}", "t-lt")

    # Last touch detail — Meeting Links = webinar
    if ltd1 and "meeting" in ltd1.lower():
        add("LT: Meeting Link", "t-web")

    # Full session history — all unique sources
    history_seen = set()
    for src in c.get("_all_history", []):
        src_clean = src.strip().upper()
        if src_clean in history_seen:
            continue
        history_seen.add(src_clean)
        if src_clean in SOURCE_MAP and src_clean not in {ft.upper(), lt.upper()}:
            lbl, cls = SOURCE_MAP[src_clean]
            add(f"Also: {lbl}", cls)

    # Webinar tags
    for wn in c.get("_all_wn", []):
        add(f"Webinar: {wn[:32]}", "t-web")
    if "Webinar" in c.get("_all_origins", []):
        add("Origin: Webinar", "t-web")

    # Conference tags
    conf_origins = {"Conference", "VRMA 25", "FAVR 2025"}
    for o in c.get("_all_origins", []):
        if o in conf_origins:
            add(f"Conf: {o}", "t-conf")
    for sol in c.get("_all_sol", []):
        if sol and "other" not in sol.lower():
            add(f"Event: {sol[:28]}", "t-conf")

    # contact_sources (custom Boom field: LinkedIn Ads / Meta Ads / Google Ads)
    for cs in c.get("_all_sources", []):
        if cs == "LinkedIn Ads":
            add("LinkedIn Ads", "t-lin")
        elif cs == "Meta Ads":
            add("Meta Ads", "t-meta")
        elif cs == "Google Ads":
            add("Google Ads", "t-ps")
        elif cs and cs not in ("Organic", "Direct", "Outbound"):
            add(cs[:22], "t-ls")

    # Self-reported
    for sr in c.get("_all_sr", []):
        if sr and sr.lower() not in ("other", ""):
            add(f"Says: {sr[:28]}", "t-sr")

    # Outbound/SDR detection
    if ft in ("OFFLINE", "INTEGRATION", "CRM_UI", "EXTENSION") and \
       ftd1 in ("CRM_UI", "INTEGRATION", "EXTENSION", ""):
        add("Outbound/SDR", "t-sdr")

    return tags


def enrich_deal(raw, merged_contact=None):
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

    c = merged_contact or {}

    ft = c.get("hs_analytics_source", "") or ""
    ftd1 = c.get("hs_analytics_source_data_1", "") or ""
    ftd2 = c.get("hs_analytics_source_data_2", "") or ""
    lt = c.get("hs_latest_source", "") or ""
    ltd1 = c.get("hs_latest_source_data_1", "") or ""
    ltd2 = c.get("hs_latest_source_data_2", "") or ""

    if not sr:
        sr = (c.get("_all_sr") or [""])[0]

    wn = (c.get("_all_wn") or [""])[0]
    sol = (c.get("_all_sol") or [""])[0]
    ls = (c.get("_all_origins") or [""])[0]

    # Channel flags
    all_sources_str = " ".join(c.get("_all_sources", [])).lower()
    all_history_str = " ".join(c.get("_all_history", [])).lower()
    all_origins = c.get("_all_origins", [])

    ch_google = 1 if (ft == "PAID_SEARCH" or lt == "PAID_SEARCH" or
                      "google ads" in all_sources_str or "PAID_SEARCH" in all_history_str) else 0
    ch_meta = 1 if (ft == "PAID_SOCIAL" or lt == "PAID_SOCIAL" or
                    "Facebook" in ftd1 or "Facebook" in ltd1 or
                    "meta ads" in all_sources_str or "PAID_SOCIAL" in all_history_str) else 0
    ch_linkedin = 1 if ("linkedin ads" in all_sources_str or
                        "linkedin" in ftd1.lower() or "linkedin" in ltd1.lower()) else 0
    ch_organic = 1 if (ft == "ORGANIC_SEARCH" or lt == "ORGANIC_SEARCH" or
                       "ORGANIC_SEARCH" in all_history_str) else 0
    ch_email = 1 if (ft == "EMAIL_MARKETING" or lt == "EMAIL_MARKETING" or
                     "hs_email" in ltd1.lower() or "EMAIL_MARKETING" in all_history_str) else 0
    ch_ref = 1 if (ft == "REFERRALS" or lt == "REFERRALS" or
                   "REFERRALS" in all_history_str) else 0
    ch_webinar = 1 if is_webinar(c) else 0
    ch_conf = 1 if is_conference(c) else 0
    ch_sdr = 1 if (ft in ("OFFLINE", "CRM_UI", "INTEGRATION", "EXTENSION") and
                   ftd1 in ("CRM_UI", "INTEGRATION", "EXTENSION", "")) else 0

    # Build all touchpoint tags
    touchpoints = build_touchpoints(c) if c else []

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
        # Attribution
        "ft": ft, "ftd1": ftd1, "ftd2": ftd2,
        "lt": lt, "ltd1": ltd1, "ltd2": ltd2,
        "ls": ls, "sol": sol, "wn": wn,
        # Channel flags
        "ch_google": ch_google, "ch_meta": ch_meta, "ch_linkedin": ch_linkedin,
        "ch_organic": ch_organic, "ch_email": ch_email,
        "ch_ref": ch_ref, "ch_webinar": ch_webinar, "ch_conf": ch_conf, "ch_sdr": ch_sdr,
        # Pre-built touchpoint tags for display
        "tps": touchpoints,
    }


def main():
    print("Pulling deals from HubSpot...")
    raw_deals = pull_all_deals()
    deal_ids = [d["id"] for d in raw_deals]

    print(f"\nFetching ALL associated contacts for {len(deal_ids)} deals...")
    contact_map = get_deal_contact_ids(deal_ids)
    print(f"  Found contacts for {len(contact_map)} deals")

    all_contact_ids = []
    for cids in contact_map.values():
        all_contact_ids.extend(cids)

    print(f"\nFetching attribution for {len(set(all_contact_ids))} unique contacts...")
    contacts = get_contacts_batch(all_contact_ids)
    print(f"  Fetched {len(contacts)} contact records")

    deals = []
    for raw in raw_deals:
        cids = contact_map.get(str(raw["id"]), [])
        contact_props_list = [contacts[cid] for cid in cids if cid in contacts]
        merged = merge_contact_props(contact_props_list)
        deals.append(enrich_deal(raw, merged))

    won = [d for d in deals if d["w"]]
    lost = [d for d in deals if d["l"]]
    opn = [d for d in deals if not d["w"] and not d["l"]]
    print(f"\n  Total: {len(deals)} | Won: {len(won)} | Lost: {len(lost)} | Open: {len(opn)}")
    print(f"  Won MRR: ${sum(d['mrr'] for d in won):,.2f}")
    print(f"  Attribution breakdown:")
    print(f"    Google: {sum(d['ch_google'] for d in deals)}")
    print(f"    Meta:   {sum(d['ch_meta'] for d in deals)}")
    print(f"    LinkedIn: {sum(d['ch_linkedin'] for d in deals)}")
    print(f"    Webinar: {sum(d['ch_webinar'] for d in deals)}")
    print(f"    Conference: {sum(d['ch_conf'] for d in deals)}")
    print(f"    Organic: {sum(d['ch_organic'] for d in deals)}")

    outpath = os.path.join(ROOT, "data", "deals.json")
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, "w") as f:
        json.dump(deals, f)
    print(f"  Saved to {outpath}")


if __name__ == "__main__":
    main()
