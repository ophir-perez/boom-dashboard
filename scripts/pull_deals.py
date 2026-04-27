#!/usr/bin/env python3
"""Pull all deals from HubSpot Sales 2.0 pipeline with full attribution."""
import json, requests, os, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOKEN = os.environ.get("HUBSPOT_TOKEN")
if not TOKEN:
    with open(os.path.join(ROOT, "config.json")) as f:
        TOKEN = json.load(f)["hubspot"]["token"]

PIPELINE   = "93413737"
ACCOUNT_ID = "24030694"
STAGES = {
    "171811493":  {"name": "Attack List",   "code": "atk",  "order": 1},
    "1075455291": {"name": "Discovery",     "code": "disc", "order": 3},
    "1075460493": {"name": "Negotiation",   "code": "neg",  "order": 4},
    "1275009440": {"name": "Contract Sent", "code": "cs",   "order": 5},
    "1108564665": {"name": "Closed Won",    "code": "won",  "order": 6},
    "216501682":  {"name": "Closed Lost",   "code": "lost", "order": 7},
}
BASE    = "https://api.hubapi.com"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# Properties stored directly on the deal object
DEAL_PROPERTIES = [
    "dealname", "dealstage", "hs_mrr", "hs_arr", "amount",
    "closedate", "createdate", "num_of_properties",
    "how_did_you_hear_about_us_", "pipeline",
    # Analytics source lives on deals too
    "hs_analytics_source",
    "hs_analytics_source_data_1",
    "hs_analytics_source_data_2",
    "hs_analytics_latest_source",
    "hs_analytics_latest_source_data_1",
    "hs_analytics_latest_source_data_2",
]

# Properties we still need from the associated contact
CONTACT_PROPERTIES = [
    "contact_origins",    # Boom enum: Webinar / Conference / Ads / etc.
    "contact_sources",    # Boom enum: LinkedIn Ads / Meta Ads / Google Ads
    "webinars_name",      # Which webinar attended
    "conference_name",    # Which conference attended
    "source_of_lead",     # Free-text conference source
    "how_did_you_hear_about_us_",
]


# ── helpers ──────────────────────────────────────────────────────────────────

def hs_post(url, body, retries=3):
    for attempt in range(retries):
        r = requests.post(url, headers=HEADERS, json=body)
        if r.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    raise Exception(f"Failed after {retries} retries: {url}")


def hs_get(url, retries=3):
    for attempt in range(retries):
        r = requests.get(url, headers=HEADERS)
        if r.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    raise Exception(f"Failed after {retries} retries: {url}")


# ── data fetching ─────────────────────────────────────────────────────────────

def pull_all_deals():
    all_deals, after = [], 0
    while True:
        body = {
            "filterGroups": [{"filters": [
                {"propertyName": "pipeline", "operator": "EQ", "value": PIPELINE}
            ]}],
            "properties": DEAL_PROPERTIES,
            "limit": 100, "after": after,
            "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}]
        }
        data = hs_post(f"{BASE}/crm/v3/objects/deals/search", body)
        all_deals.extend(data.get("results", []))
        print(f"  Pulled {len(all_deals)}/{data.get('total', '?')} deals...")
        after_cursor = data.get("paging", {}).get("next", {}).get("after")
        if after_cursor:
            after = int(after_cursor)
            time.sleep(0.3)
        else:
            break
    return all_deals


def get_contact_ids(deal_ids):
    """Return {deal_id: [contact_id, ...]} for all deals."""
    contact_map = {}
    for i in range(0, len(deal_ids), 100):
        batch = deal_ids[i:i+100]
        body = {"inputs": [{"id": str(d)} for d in batch]}
        r = requests.post(
            f"{BASE}/crm/v3/associations/deals/contacts/batch/read",
            headers=HEADERS, json=body
        )
        # 207 = partial success — still has results
        if r.status_code not in (200, 207):
            print(f"  Warning: association batch returned {r.status_code}")
            time.sleep(1)
            continue
        for res in r.json().get("results", []):
            did  = str(res.get("from", {}).get("id", ""))
            cids = [str(t["id"]) for t in res.get("to", [])]
            if did and cids:
                contact_map[did] = cids
        time.sleep(0.2)
    return contact_map


def get_contacts(contact_ids):
    """Batch-fetch contact properties. Returns {contact_id: props}."""
    contacts = {}
    unique = list(set(contact_ids))
    for i in range(0, len(unique), 100):
        batch = unique[i:i+100]
        body = {
            "inputs": [{"id": cid} for cid in batch],
            "properties": CONTACT_PROPERTIES,
        }
        r = requests.post(
            f"{BASE}/crm/v3/objects/contacts/batch/read",
            headers=HEADERS, json=body
        )
        if r.status_code not in (200, 207):
            print(f"  Warning: contacts batch returned {r.status_code}")
            time.sleep(1)
            continue
        for c in r.json().get("results", []):
            contacts[str(c["id"])] = c.get("properties", {})
        time.sleep(0.2)
    return contacts


def get_deal_meetings(deal_ids):
    """Return {deal_id: {outcome: count}} for meetings associated with each deal."""
    mtg_map = {}
    # Fetch meeting associations in batches
    for i in range(0, len(deal_ids), 100):
        batch = deal_ids[i:i+100]
        body = {"inputs": [{"id": str(d)} for d in batch]}
        r = requests.post(
            f"{BASE}/crm/v3/associations/deals/meetings/batch/read",
            headers=HEADERS, json=body
        )
        if r.status_code not in (200, 207):
            time.sleep(1)
            continue
        for res in r.json().get("results", []):
            did  = str(res.get("from", {}).get("id", ""))
            mids = [str(t["id"]) for t in res.get("to", [])]
            if did and mids:
                mtg_map[did] = mids
        time.sleep(0.2)

    if not mtg_map:
        return {}

    # Fetch meeting outcomes
    all_mtg_ids = list(set(mid for mids in mtg_map.values() for mid in mids))
    outcomes = {}
    for i in range(0, len(all_mtg_ids), 100):
        batch = all_mtg_ids[i:i+100]
        body = {
            "inputs": [{"id": mid} for mid in batch],
            "properties": ["hs_meeting_outcome", "hs_activity_type", "hs_meeting_start_time"],
        }
        r = requests.post(
            f"{BASE}/crm/v3/objects/meetings/batch/read",
            headers=HEADERS, json=body
        )
        if r.status_code not in (200, 207):
            time.sleep(1)
            continue
        for m in r.json().get("results", []):
            p = m.get("properties", {})
            outcomes[str(m["id"])] = {
                "outcome": (p.get("hs_meeting_outcome") or "UNKNOWN").upper(),
                "type":    (p.get("hs_activity_type") or "").lower(),
            }
        time.sleep(0.2)

    # Map deal_id -> best meeting outcome
    # Priority: COMPLETED > SCHEDULED > NO_SHOW > RESCHEDULED
    # Include all meeting types (don't filter by type — many have no type set)
    EXCLUDE_TYPES = {"internal", "team meeting", "check-in", "onboarding"}
    PRIORITY = {"COMPLETED": 4, "SCHEDULED": 3, "NO_SHOW": 2, "RESCHEDULED": 1, "NONE": 0}
    deal_mtg = {}
    for did, mids in mtg_map.items():
        best = "NONE"
        for mid in mids:
            o = outcomes.get(mid, {})
            otype = o.get("type", "").lower()
            outcome = o.get("outcome", "NONE")
            # Skip clearly internal meetings
            if any(x in otype for x in EXCLUDE_TYPES):
                continue
            if PRIORITY.get(outcome, 0) > PRIORITY.get(best, 0):
                best = outcome
        deal_mtg[did] = best
    return deal_mtg


# ── enrichment ────────────────────────────────────────────────────────────────

SOURCE_DISPLAY = {
    "PAID_SEARCH":    ("Google Ads",      "t-ps"),
    "PAID_SOCIAL":    ("Meta Ads",        "t-meta"),
    "ORGANIC_SEARCH": ("Organic Search",  "t-org"),
    "EMAIL_MARKETING":("Email",           "t-em"),
    "REFERRALS":      ("Referral",        "t-ref"),
    "DIRECT_TRAFFIC": ("Direct",          "t-dir"),
    "SOCIAL_MEDIA":   ("LinkedIn Org",    "t-lin"),
    "AI_REFERRALS":   ("ChatGPT",         "t-ai"),
    "OFFLINE":        ("Offline/Import",  "t-ft"),
}


def is_sdr(ft, ftd1):
    return ft == "OFFLINE" and ftd1 in ("CRM_UI", "INTEGRATION", "EXTENSION", "")


def build_tps(ft, ftd1, ftd2, lt, ltd1, contact_origins, contact_sources, wn, conf_name, sol, sr):
    seen, tps = set(), []

    def add(label, cls):
        key = f"{cls}:{label}"
        if key not in seen:
            seen.add(key)
            tps.append({"l": label, "c": cls})

    sdr = is_sdr(ft, ftd1)

    # ── First touch ──
    if ft:
        if sdr:
            add("Outbound/SDR", "t-sdr")
        elif ft in SOURCE_DISPLAY:
            lbl, cls = SOURCE_DISPLAY[ft]
            add(f"FT: {lbl}", "t-ft")
            if ft == "PAID_SEARCH":
                add(f"Google: {(ftd2 or ftd1 or 'Brand')[:22]}", "t-ps")
            elif ft == "PAID_SOCIAL":
                add("Meta Ads", "t-meta")
            elif ft == "ORGANIC_SEARCH":
                add("SEO", "t-org")
            elif ft == "AI_REFERRALS":
                add("ChatGPT", "t-ai")
            elif ft == "REFERRALS":
                add("Referral", "t-ref")
            elif ft == "DIRECT_TRAFFIC":
                add("Direct", "t-dir")
        else:
            add(f"FT: {ft}", "t-ft")

    # ── Last touch (if different) ──
    if lt and lt != ft:
        if lt in SOURCE_DISPLAY:
            lbl, cls = SOURCE_DISPLAY[lt]
            add(f"LT: {lbl}", "t-lt")
            if lt == "PAID_SOCIAL":
                add("Meta (LT)", "t-meta")
            elif lt == "PAID_SEARCH":
                add("Google (LT)", "t-ps")
            elif lt == "EMAIL_MARKETING":
                if "webinar" in (ltd1 or "").lower():
                    add("Webinar (LT)", "t-web")
                else:
                    add("Email (LT)", "t-em")
            elif lt == "REFERRALS":
                add("Referral (LT)", "t-ref")
            elif lt == "ORGANIC_SEARCH":
                add("SEO (LT)", "t-org")
        elif lt:
            add(f"LT: {lt}", "t-lt")
    elif lt == "EMAIL_MARKETING" and "webinar" in (ltd1 or "").lower():
        add("Webinar (LT)", "t-web")

    # Detect webinar via last-touch data_1
    if "webinar" in (ltd1 or "").lower():
        # Extract webinar name from HubSpot's format
        # "40639543-webinar: built to scale..." → "Built to Scale..."
        wname = ltd1.split("webinar:")[-1].strip()[:40] if "webinar:" in ltd1.lower() else ""
        if wname:
            add(f"Webinar: {wname}", "t-web")
    if "meeting" in (ltd1 or "").lower() or "meeting" in (ftd1 or "").lower():
        add("Meeting Link", "t-web")

    # ── Webinar name from contact ──
    if wn:
        for w in wn.split(";"):
            w = w.strip()
            if w:
                add(f"Webinar: {w[:38]}", "t-web")

    # ── Contact origins ──
    if contact_origins:
        for o in contact_origins.split(";"):
            o = o.strip()
            if not o:
                continue
            if o == "Webinar":
                add("Origin: Webinar", "t-web")
            elif o in ("Conference", "VRMA 25", "FAVR 2025"):
                add(f"Conf: {o}", "t-conf")
            elif o == "Ads":
                add("Origin: Ads", "t-ps")
            elif o in ("LinkedIn", "LinkedIn Ads"):
                add("LinkedIn Ads", "t-lin")
            elif o in ("Meta", "Meta Ads"):
                add("Meta Ads", "t-meta")
            elif o not in ("", "Website Form", "Direct"):
                add(f"Origin: {o[:20]}", "t-ls")

    # ── Contact sources (custom Boom field) ──
    if contact_sources:
        for cs in contact_sources.split(";"):
            cs = cs.strip()
            if cs == "LinkedIn Ads":
                add("LinkedIn Ads", "t-lin")
            elif cs == "Meta Ads":
                add("Meta Ads", "t-meta")
            elif cs == "Google Ads":
                add("Google Ads", "t-ps")
            elif cs and cs not in ("Organic", "Direct", "Outbound"):
                add(cs[:22], "t-ls")

    # ── Conference name ──
    if conf_name:
        add(f"Conf: {conf_name[:30]}", "t-conf")
    if sol and "other" not in sol.lower() and sol:
        add(f"Event: {sol[:28]}", "t-conf")

    # ── Self-reported ──
    if sr and sr.lower() not in ("other", ""):
        add(f"Says: {sr[:28]}", "t-sr")

    return tps


def enrich_deal(raw, contact_props, mtg_outcome):
    p   = raw["properties"]
    sid = p.get("dealstage", "")
    stg = STAGES.get(sid, {"name": "Unknown", "code": "unk", "order": 0})
    hid = raw["id"]

    mrr = float(p.get("hs_mrr")  or 0)
    arr = float(p.get("hs_arr")  or 0)
    amt = float(p.get("amount")  or 0)
    cd  = (p.get("closedate")    or "")[:10]
    cr  = (p.get("createdate")   or "")[:10]
    lst = int(float(p.get("num_of_properties") or 0))
    sr  = p.get("how_did_you_hear_about_us_", "") or ""

    # Analytics source from deal properties directly
    ft   = p.get("hs_analytics_source",               "") or ""
    ftd1 = p.get("hs_analytics_source_data_1",        "") or ""
    ftd2 = p.get("hs_analytics_source_data_2",        "") or ""
    lt   = p.get("hs_analytics_latest_source",        "") or ""
    ltd1 = p.get("hs_analytics_latest_source_data_1", "") or ""
    ltd2 = p.get("hs_analytics_latest_source_data_2", "") or ""

    # Contact-level fields
    c = contact_props or {}
    contact_origins  = c.get("contact_origins",  "") or ""
    contact_sources  = c.get("contact_sources",  "") or ""
    wn               = c.get("webinars_name",    "") or ""
    conf_name        = c.get("conference_name",  "") or ""
    sol              = c.get("source_of_lead",   "") or ""
    if not sr:
        sr = c.get("how_did_you_hear_about_us_", "") or ""

    # Build touchpoints
    tps = build_tps(ft, ftd1, ftd2, lt, ltd1, contact_origins, contact_sources, wn, conf_name, sol, sr)

    # Channel flags (for tab filtering)
    webinar_in_ltd1 = "webinar" in (ltd1 or "").lower()
    ch_google  = 1 if ft == "PAID_SEARCH"    or lt == "PAID_SEARCH"    else 0
    ch_meta    = 1 if ft == "PAID_SOCIAL"    or lt == "PAID_SOCIAL"    or "Facebook" in ftd1 else 0
    ch_linkedin= 1 if "LinkedIn Ads" in contact_sources or "linkedin" in (ftd1+ltd1).lower() else 0
    ch_organic = 1 if ft == "ORGANIC_SEARCH" or lt == "ORGANIC_SEARCH" else 0
    ch_email   = 1 if ft == "EMAIL_MARKETING"or lt == "EMAIL_MARKETING" else 0
    ch_ref     = 1 if ft == "REFERRALS"      or lt == "REFERRALS"      else 0
    ch_webinar = 1 if (webinar_in_ltd1 or "Webinar" in contact_origins or bool(wn) or
                       "meeting" in (ltd1+ftd1).lower()) else 0
    ch_conf    = 1 if (any(o in contact_origins for o in ("Conference","VRMA 25","FAVR 2025"))
                       or bool(conf_name)
                       or any(x in (sol or "").lower() for x in ["convention","scale","porto","munich","barcelona","vrma","favr"])
                      ) else 0
    ch_sdr     = 1 if is_sdr(ft, ftd1) else 0
    ch_ai      = 1 if ft == "AI_REFERRALS" or lt == "AI_REFERRALS" else 0
    ch_direct  = 1 if ft == "DIRECT_TRAFFIC" and not ch_webinar else 0

    # Meeting outcome
    ms2 = ""
    if mtg_outcome == "COMPLETED":    ms2 = "show"
    elif mtg_outcome == "SCHEDULED":  ms2 = "sched"
    elif mtg_outcome == "NO_SHOW":    ms2 = "noshow"
    elif mtg_outcome == "RESCHEDULED":ms2 = "sched"
    mb = 1 if ms2 else 0

    return {
        "n": (p.get("dealname") or "").strip(),
        "hid": hid,
        "url": f"https://app.hubspot.com/contacts/{ACCOUNT_ID}/record/0-3/{hid}",
        "sn": stg["name"], "so": stg["order"], "sc": stg["code"],
        "w": 1 if sid == "1108564665" else 0,
        "l": 1 if sid == "216501682"  else 0,
        "mrr": mrr, "arr": arr, "a": amt,
        "cd": cd, "cr": cr,
        "list": lst, "sr": sr, "neg": 1 if sid == "1075460493" else 0,
        "mb": mb, "ms2": ms2,
        # Attribution
        "ft": ft, "ftd1": ftd1, "ftd2": ftd2,
        "lt": lt, "ltd1": ltd1, "ltd2": ltd2,
        "ls": contact_origins, "wn": wn, "sol": sol,
        # Channel flags
        "ch_google": ch_google, "ch_meta": ch_meta, "ch_linkedin": ch_linkedin,
        "ch_organic": ch_organic, "ch_email": ch_email, "ch_ref": ch_ref,
        "ch_webinar": ch_webinar, "ch_conf": ch_conf, "ch_sdr": ch_sdr,
        "ch_ai": ch_ai, "ch_direct": ch_direct,
        # Pre-built tags
        "tps": tps,
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("Pulling deals from HubSpot...")
    raw_deals = pull_all_deals()
    deal_ids  = [d["id"] for d in raw_deals]

    print(f"\nFetching contact associations for {len(deal_ids)} deals...")
    contact_map = get_contact_ids(deal_ids)
    print(f"  Found contacts for {len(contact_map)}/{len(deal_ids)} deals")

    all_contact_ids = list(set(cid for cids in contact_map.values() for cid in cids))
    print(f"\nFetching {len(all_contact_ids)} contact records...")
    contacts = get_contacts(all_contact_ids)
    print(f"  Fetched {len(contacts)} contacts")

    print(f"\nFetching meeting associations...")
    deal_mtg = get_deal_meetings(deal_ids)
    print(f"  Found meetings for {len(deal_mtg)} deals")

    print("\nEnriching deals...")
    deals = []
    for raw in raw_deals:
        did  = str(raw["id"])
        # Pick the contact with webinar/conf origin first, else first contact
        cids = contact_map.get(did, [])
        best_c = {}
        for cid in cids:
            cp = contacts.get(cid, {})
            if cp.get("contact_origins") or cp.get("webinars_name") or cp.get("conference_name"):
                best_c = cp
                break
        if not best_c and cids:
            best_c = contacts.get(cids[0], {})

        mtg_outcome = deal_mtg.get(did, "NONE")
        deals.append(enrich_deal(raw, best_c, mtg_outcome))

    # Stats
    won  = [d for d in deals if d["w"]]
    lost = [d for d in deals if d["l"]]
    opn  = [d for d in deals if not d["w"] and not d["l"]]
    has_tps = sum(1 for d in deals if d["tps"])
    print(f"\n  Total: {len(deals)} | Won: {len(won)} | Lost: {len(lost)} | Open: {len(opn)}")
    print(f"  Won MRR:   ${sum(d['mrr'] for d in won):,.2f}")
    print(f"  Pipeline:  ${sum(d['mrr'] for d in opn):,.2f}")
    print(f"  With attribution: {has_tps}/{len(deals)}")
    print(f"  Google:{sum(d['ch_google'] for d in deals)}  Meta:{sum(d['ch_meta'] for d in deals)}  "
          f"Webinar:{sum(d['ch_webinar'] for d in deals)}  Conf:{sum(d['ch_conf'] for d in deals)}  "
          f"SDR:{sum(d['ch_sdr'] for d in deals)}")

    outpath = os.path.join(ROOT, "data", "deals.json")
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, "w") as f:
        json.dump(deals, f)
    print(f"\n  Saved to {outpath}")


if __name__ == "__main__":
    main()
