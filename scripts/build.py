#!/usr/bin/env python3
"""Build the final dashboard HTML from template + data files."""
import json, os, re
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    print("Building dashboard...")
    
    # Load template
    with open(os.path.join(ROOT, "src", "template.html")) as f:
        html = f.read()
    
    # Load data
    with open(os.path.join(ROOT, "data", "deals.json")) as f:
        deals = json.load(f)
    with open(os.path.join(ROOT, "data", "leads.json")) as f:
        leads = json.load(f)
    
    # Load SQLs if available
    sqls_path = os.path.join(ROOT, "data", "sqls.json")
    if os.path.exists(sqls_path):
        with open(sqls_path) as f:
            sqls = json.load(f)
        # Build SQ array JS
        sq_entries = []
        for s in sqls:
            sq_entries.append(f'{{"s":"{s["s"]}","e":"{s["e"]}","t":{s["t"]}}}')
        sq_js = "[" + ",\n".join(sq_entries) + "]"
        # Replace the SQ array in the template
        html = re.sub(r'var SQ=\[.*?\];', f'var SQ={sq_js};', html, flags=re.DOTALL)
    
    # Load ads summary if available
    ads_path = os.path.join(ROOT, "data", "ads_summary.json")
    if os.path.exists(ads_path):
        with open(ads_path) as f:
            ads = json.load(f)
        # Inject ads data as JS variable
        ads_js = f"var ADS_SPEND={json.dumps(ads)};"
        html = html.replace("</script>", f"\n{ads_js}\n</script>", 1)
    
    # Replace placeholders
    today = datetime.now().strftime("%b %d, %Y")
    deals_json = json.dumps(deals)
    leads_json = json.dumps(leads)
    
    html = html.replace("__DEALS_DATA__", deals_json)
    html = html.replace("__LEADS_DATA__", leads_json)
    html = html.replace("Data as of __DATE__", f"Data as of {today}")
    
    # Update subtitle counts
    total_leads = sum(l["t"] for l in leads)
    total_deals = len(deals)
    won = [d for d in deals if d.get("w")]
    lost = [d for d in deals if d.get("l")]
    opn = [d for d in deals if not d.get("w") and not d.get("l")]
    
    # Write output — boom-dashboard.html for local use, index.html for GitHub Pages
    os.makedirs(os.path.join(ROOT, "output"), exist_ok=True)
    outpath = os.path.join(ROOT, "output", "boom-dashboard.html")
    index_path = os.path.join(ROOT, "output", "index.html")
    with open(outpath, "w") as f:
        f.write(html)
    with open(index_path, "w") as f:
        f.write(html)

    print(f"\n  Dashboard built: {outpath}")
    print(f"  Size: {len(html):,} bytes")
    print(f"  Deals: {total_deals} (Won:{len(won)} Lost:{len(lost)} Open:{len(opn)})")
    print(f"  Leads: {total_leads:,}")
    print(f"  Won MRR: ${sum(d.get('mrr',0) for d in won):,.2f}")
    print(f"\n  Local: file://{os.path.abspath(outpath)}")
    print(f"  Pages: output/index.html → published to gh-pages branch")

if __name__ == "__main__":
    main()
