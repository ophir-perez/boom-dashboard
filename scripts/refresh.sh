#!/bin/bash
# Boom Dashboard — Full Data Refresh
# Pulls all data from HubSpot and rebuilds the dashboard
#
# Usage: ./scripts/refresh.sh
# Or:    ./scripts/refresh.sh --deals-only
# Or:    ./scripts/refresh.sh --build-only

set -e
cd "$(dirname "$0")/.."

echo "================================================"
echo "  Boom Dashboard — Full Refresh"
echo "  $(date)"
echo "================================================"
echo ""

if [ "$1" = "--build-only" ]; then
    echo "Skipping data pull, building from existing data..."
    python3 scripts/build.py
    exit 0
fi

if [ "$1" = "--deals-only" ]; then
    echo "Pulling deals only..."
    python3 scripts/pull_deals.py
    python3 scripts/build.py
    exit 0
fi

# Full refresh
echo "Step 1/5: Pulling deals..."
python3 scripts/pull_deals.py
echo ""

echo "Step 2/5: Pulling lead counts..."
python3 scripts/pull_leads.py
echo ""

echo "Step 3/5: Pulling SQL counts..."
python3 scripts/pull_sqls.py
echo ""

echo "Step 4/5: Pulling meetings..."
python3 scripts/pull_meetings.py
echo ""

echo "Step 5/5: Pulling ad spend..."
python3 scripts/pull_ads.py 2>/dev/null || echo "  (Skipped — ads_read scope not yet enabled)"
echo ""

echo "Building dashboard..."
python3 scripts/build.py
echo ""

echo "================================================"
echo "  Refresh complete!"
echo "  Open: output/boom-dashboard.html"
echo "================================================"
