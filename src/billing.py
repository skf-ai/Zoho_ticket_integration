"""Real month-to-date spend, pulled from each provider's own billing API.

Three sources, each independent and each allowed to fail without breaking the
dashboard -- a failed source reports WHY and the page falls back to the
usage-based estimate, clearly badged:

  aws     Cost Explorer (needs ce:GetCostAndUsage on the Lambda role;
          each API call costs $0.01, so results are cached for an hour)
  openai  /v1/organization/costs (needs an ORG ADMIN key -- the normal
          project key cannot read billing; store as `openai_admin_key`)
  meta    Graph API conversation analytics on the WABA (uses the existing
          whatsapp_token; needs `whatsapp_waba_id` in the secret)

Every fetch returns {"source": "live"|"unavailable", "amount": float|None,
"currency": "...", "detail": "..."} so the renderer can be honest.
"""

import time
from datetime import timedelta, timezone

import requests

from . import config, workdays

CACHE_TTL_SECONDS = 3600
_cache = {"at": 0.0, "data": None}


def _month_start(now):
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0,
                       tzinfo=timezone.utc)


def _window(now):
    """Billing window: month-to-date normally; on the 1st (when month-to-date
    is empty by definition) fall back to the full previous month."""
    this_start = _month_start(now)
    if now.day > 1:
        return this_start, now, "month to date"
    prev_start = _month_start((this_start - timedelta(days=1)))
    return prev_start, this_start, "last month (new month just started)"


def _unavailable(detail):
    return {"source": "unavailable", "amount": None, "currency": "", "detail": detail}


def fetch_aws(now):
    """Month-to-date AWS spend via Cost Explorer, with a top-service breakdown."""
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        return _unavailable("boto3 not installed")
    window_start, window_end, label = _window(now)
    start = window_start.strftime("%Y-%m-%d")
    end = window_end.strftime("%Y-%m-%d")
    try:
        ce = boto3.client("ce", region_name="us-east-1")
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": start, "End": end},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
        groups = resp["ResultsByTime"][0].get("Groups", [])
        by_service = sorted(
            ((g["Keys"][0], float(g["Metrics"]["UnblendedCost"]["Amount"]))
             for g in groups),
            key=lambda kv: -kv[1],
        )
        total = sum(v for _, v in by_service)
        top = " · ".join(f"{k.replace('Amazon ', '').replace('AWS ', '')} ${v:.2f}"
                         for k, v in by_service[:4] if v >= 0.005)
        return {"source": "live", "amount": total, "currency": "USD",
                "detail": f"{label}: " + (top or "all services under $0.01")}
    except (ClientError, BotoCoreError, KeyError, IndexError) as e:
        return _unavailable(f"Cost Explorer: {type(e).__name__}")


def fetch_openai(now):
    """Month-to-date OpenAI spend. Requires an organization ADMIN key."""
    admin_key = config.get("openai_admin_key")
    if not admin_key:
        return _unavailable("no openai_admin_key configured (project keys "
                            "cannot read billing)")
    window_start, window_end, label = _window(now)
    try:
        resp = requests.get(
            "https://api.openai.com/v1/organization/costs",
            headers={"Authorization": f"Bearer {admin_key}"},
            params={"start_time": int(window_start.timestamp()),
                    "end_time": int(window_end.timestamp()), "limit": 31},
            timeout=10,
        )
        if resp.status_code in (401, 403):
            return _unavailable("key rejected -- an org ADMIN key is required")
        resp.raise_for_status()
        total = 0.0
        for bucket in resp.json().get("data", []):
            for result in bucket.get("results", []):
                total += float((result.get("amount") or {}).get("value") or 0.0)
        return {"source": "live", "amount": total, "currency": "USD",
                "detail": f"{label}, all projects (reporting can lag ~24h)"}
    except requests.RequestException as e:
        return _unavailable(f"OpenAI costs API: {type(e).__name__}")


def fetch_meta(now):
    """Month-to-date WhatsApp conversation charges from the WABA analytics."""
    token = config.get("whatsapp_token")
    waba_id = config.get("whatsapp_waba_id")
    if not token or not waba_id:
        return _unavailable("needs whatsapp_token and whatsapp_waba_id")
    window_start, window_end, _label = _window(now)
    start = int(window_start.timestamp())
    end = int(window_end.timestamp())
    fields = (f"conversation_analytics.start({start}).end({end})"
              f".granularity(MONTHLY).phone_numbers([])"
              f".dimensions([\"CONVERSATION_CATEGORY\"])")
    try:
        resp = requests.get(
            f"https://graph.facebook.com/{config.GRAPH_API_VERSION}/{waba_id}",
            params={"fields": fields, "access_token": token},
            timeout=10,
        )
        if resp.status_code != 200:
            err = resp.json().get("error", {}).get("message", resp.status_code)
            return _unavailable(f"Graph API: {str(err)[:80]}")
        points = []
        for chunk in (resp.json().get("conversation_analytics", {})
                      .get("data", [])):
            points.extend(chunk.get("data_points", []))
        total_cost = sum(float(p.get("cost") or 0.0) for p in points)
        conversations = sum(int(p.get("conversation") or 0) for p in points)
        return {"source": "live", "amount": total_cost, "currency": "INR",
                "detail": f"{conversations} paid/free conversations this month"}
    except requests.RequestException as e:
        return _unavailable(f"Graph API: {type(e).__name__}")


def fetch_all(now=None, force=False):
    """All three sources, cached for an hour (Cost Explorer calls cost $0.01)."""
    if not force and _cache["data"] and time.time() - _cache["at"] < CACHE_TTL_SECONDS:
        return _cache["data"]
    now = now or workdays.now_utc()
    data = {"aws": fetch_aws(now), "openai": fetch_openai(now),
            "meta": fetch_meta(now)}
    _cache["at"] = time.time()
    _cache["data"] = data
    return data
