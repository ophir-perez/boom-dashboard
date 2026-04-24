#!/usr/bin/env python3
"""Build the final dashboard HTML from template + data files."""
import json, os, re
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def js_monthly_array(data):
    """Convert [{s,e,t},...] to compact JS array string."""
    entries = [f'{{"s":"{d["s"]}","e":"{d["e"]}","t":{d["t"]}}}' for d in data]
    return "[" + ",".join(entries) + "]"


def js_meetings_array(data):
    """Convert meetings list to compact JS array string."""
    entries = []
    for m in data:
        title = json.dumps(m.get("title", ""))
        entries.append(
            f'{{"id":"{m["id"]}","title":{title},"date":"{m["date"]}","outcome":"{m["outcome"]}"}}'
        )
    return "[" + ",".join(entries) + "]"


def main():
    print("Building dashboard...")

    with open(os.path.join(ROOT, "src", "template.html")) as f:
        html = f.read()

    # Load required data
    with open(os.path.join(ROOT, "data", "deals.json")) as f:
        deals = json.load(f)
    with open(os.path.join(ROOT, "data", "leads.json")) as f:
        leads = json.load(f)

    # Replace deal + lead placeholders
    html = html.replace("__DEALS_DATA__", json.dumps(deals))
    html = html.replace("__LEADS_DATA__", json.dumps(leads))

    # SQLs
    sqls = load_json(os.path.join(ROOT, "data", "sqls.json"), [])
    if sqls:
        html = re.sub(r'var SQ=\[.*?\];', f'var SQ={js_monthly_array(sqls)};', html, flags=re.DOTALL)

    # Webinar leads
    wl = load_json(os.path.join(ROOT, "data", "webinar_leads.json"), [])
    if wl:
        html = re.sub(r'var WL=\[.*?\];', f'var WL={js_monthly_array(wl)};', html, flags=re.DOTALL)

    # Conference leads
    cl = load_json(os.path.join(ROOT, "data", "conf_leads.json"), [])
    if cl:
        html = re.sub(r'var CL=\[.*?\];', f'var CL={js_monthly_array(cl)};', html, flags=re.DOTALL)

    # Meetings — inject as JS variable for modal use
    meetings = load_json(os.path.join(ROOT, "data", "meetings.json"), [])
    mtg_js = f"var MEETINGS={js_meetings_array(meetings)};"
    html = html.replace("var MEETINGS=[];", mtg_js)

    # Ads summary
    ads = load_json(os.path.join(ROOT, "data", "ads_summary.json"), None)
    if ads:
        html = html.replace("var ADS_SPEND={};", f"var ADS_SPEND={json.dumps(ads)};")

    # Date stamp + subtitle counts
    today = datetime.now().strftime("%b %d, %Y")
    total_leads = sum(l["t"] for l in leads)
    won = [d for d in deals if d.get("w")]
    lost = [d for d in deals if d.get("l")]
    opn = [d for d in deals if not d.get("w") and not d.get("l")]
    total_sqls = sum(s["t"] for s in sqls)
    total_wl = sum(m["t"] for m in wl)
    total_cl = sum(m["t"] for m in cl)

    html = html.replace("__DATE__", today)
    html = html.replace("__TOTAL_LEADS__", f"{total_leads:,}")
    html = html.replace("__TOTAL_DEALS__", str(len(deals)))
    html = html.replace("__TOTAL_SQLS__", f"{total_sqls:,}")

    # Write output
    os.makedirs(os.path.join(ROOT, "output"), exist_ok=True)
    for fname in ("boom-dashboard.html", "index.html"):
        with open(os.path.join(ROOT, "output", fname), "w") as f:
            f.write(html)

    print(f"\n  Built: output/index.html ({len(html):,} bytes)")
    print(f"  Deals: {len(deals)} (Won:{len(won)} Lost:{len(lost)} Open:{len(opn)})")
    print(f"  Leads: {total_leads:,} | SQLs: {total_sqls:,}")
    print(f"  Webinar leads: {total_wl:,} | Conference leads: {total_cl:,}")
    print(f"  Meetings: {len(meetings)}")
    print(f"  Won MRR: ${sum(d.get('mrr', 0) for d in won):,.2f}")


if __name__ == "__main__":
    main()
