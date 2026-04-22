// Boom Dashboard — HubSpot Ads API Proxy
// Deploy this as a Cloudflare Worker (free tier)
// 
// SETUP:
// 1. Go to https://dash.cloudflare.com → Workers & Pages → Create Worker
// 2. Paste this entire file → Save and Deploy
// 3. Copy the worker URL (looks like: https://boom-ads.YOUR_SUBDOMAIN.workers.dev)
// 4. Paste that URL into the dashboard's "Ads Proxy URL" field

// Set this as an Environment Variable in the Cloudflare Worker dashboard (not hardcoded here).
// Workers & Pages → your worker → Settings → Variables → add HUBSPOT_TOKEN
const HUBSPOT_TOKEN = typeof HUBSPOT_TOKEN_ENV !== "undefined" ? HUBSPOT_TOKEN_ENV : "";
const HUBSPOT_BASE = "https://api.hubapi.com";

export default {
  async fetch(request) {
    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
          "Access-Control-Max-Age": "86400",
        },
      });
    }

    const url = new URL(request.url);
    const action = url.searchParams.get("action");

    let hsUrl;
    if (action === "accounts") {
      hsUrl = `${HUBSPOT_BASE}/marketing/v3/ads/ad-accounts?limit=100`;
    } else if (action === "campaigns") {
      const accountId = url.searchParams.get("accountId") || "";
      const after = url.searchParams.get("after") || "";
      hsUrl = `${HUBSPOT_BASE}/marketing/v3/ads/campaigns?limit=100&adAccountId=${accountId}${after ? "&after=" + after : ""}`;
    } else if (action === "spend") {
      // Get campaign analytics with spend data
      const startDate = url.searchParams.get("start") || "2025-01-01";
      const endDate = url.searchParams.get("end") || "2026-12-31";
      const adAccountId = url.searchParams.get("accountId") || "";
      hsUrl = `${HUBSPOT_BASE}/marketing/v3/ads/ad-accounts/${adAccountId}/analytics?startDate=${startDate}&endDate=${endDate}&breakdownBy=MONTH`;
    } else if (action === "allspend") {
      // Aggregate: fetch all ad accounts, then get spend for each
      try {
        const accountsRes = await fetch(`${HUBSPOT_BASE}/marketing/v3/ads/ad-accounts?limit=100`, {
          headers: { Authorization: `Bearer ${HUBSPOT_TOKEN}` },
        });
        const accountsData = await accountsRes.json();
        const accounts = accountsData.results || [];
        
        const startDate = url.searchParams.get("start") || "2025-01-01";
        const endDate = url.searchParams.get("end") || "2026-12-31";
        
        const results = [];
        for (const acc of accounts) {
          try {
            const spendRes = await fetch(
              `${HUBSPOT_BASE}/marketing/v3/ads/ad-accounts/${acc.adAccountId}/analytics?startDate=${startDate}&endDate=${endDate}&breakdownBy=MONTH`,
              { headers: { Authorization: `Bearer ${HUBSPOT_TOKEN}` } }
            );
            const spendData = await spendRes.json();
            results.push({
              accountId: acc.adAccountId,
              name: acc.name || acc.adAccountId,
              network: acc.adNetwork || "UNKNOWN",
              currency: acc.currency || "USD",
              analytics: spendData.results || spendData || [],
            });
          } catch (e) {
            results.push({
              accountId: acc.adAccountId,
              name: acc.name || acc.adAccountId,
              network: acc.adNetwork || "UNKNOWN",
              error: e.message,
            });
          }
        }
        
        return new Response(JSON.stringify({ accounts, spend: results }), {
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
          },
        });
      } catch (e) {
        return new Response(JSON.stringify({ error: e.message }), {
          status: 500,
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
          },
        });
      }
    } else {
      return new Response(JSON.stringify({
        usage: "?action=accounts | ?action=campaigns&accountId=X | ?action=spend&accountId=X&start=2026-01-01&end=2026-03-31 | ?action=allspend&start=2026-01-01&end=2026-03-31"
      }), {
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*",
        },
      });
    }

    // Proxy the request to HubSpot
    try {
      const hsRes = await fetch(hsUrl, {
        headers: { Authorization: `Bearer ${HUBSPOT_TOKEN}` },
      });
      const data = await hsRes.json();
      return new Response(JSON.stringify(data), {
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*",
        },
      });
    } catch (e) {
      return new Response(JSON.stringify({ error: e.message }), {
        status: 500,
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*",
        },
      });
    }
  },
};
