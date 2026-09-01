"""Admin dashboard: one protected HTML page summarising spend, tickets and
how quickly the admin side acted.

Everything is computed from the conversation items the system already stores in
DynamoDB -- no new write paths, no extra services. Costs shown are ESTIMATES
derived from usage counters (nudges, reminders, message history); the exact
bills stay in each provider's console, which the page links to.

`aggregate()` and `render()` are pure functions so tests need no AWS.
"""

import html

from . import workdays

# Per-unit price assumptions, kept in one place so a price change is one edit.
# Sources: COSTS.md (utility template ₹0.115 + 18% GST; GPT-5 mini ~₹0.17 per
# answered conversation; AWS ~₹250-350/month flat at this volume).
TEMPLATE_INR = 0.115 * 1.18
AI_TURN_INR = 0.17
AWS_FLAT_INR = "250-350"

OPEN_STATUSES = ("open", "creating", "verification_prompting")
WAITING_STATUSES = ("verification_prompting", "awaiting_verification")


def _n(value):
    """DynamoDB numbers arrive as Decimal; missing as None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _days_between(start_iso, end_iso):
    try:
        delta = workdays.parse(end_iso) - workdays.parse(start_iso)
        return max(delta.total_seconds() / 86400.0, 0.0)
    except (TypeError, ValueError):
        return None


def aggregate(items, now=None):
    """Reduce raw conversation items to the numbers the dashboard shows."""
    now = now or workdays.now_utc()
    now_iso = workdays.iso(now)

    by_category = {}
    tickets = []
    open_count = waiting_count = closed_count = overdue_count = 0
    total_messages = 0
    verifications = 0

    for item in items:
        total_messages += len(item.get("history") or [])
        status = item.get("ticket_status", "none")
        has_ticket = bool(item.get("ticket_id")) or bool(item.get("closed_at"))
        if not has_ticket:
            continue

        category = str(item.get("category") or "other")
        by_category[category] = by_category.get(category, 0) + 1

        closed_at = item.get("closed_at")
        created_at = item.get("ticket_created_at")
        nudges = _n(item.get("admin_nudges"))
        reminders = _n(item.get("student_reminders"))
        if item.get("verification_prompted_at") or status == "awaiting_verification":
            verifications += 1

        if closed_at:
            closed_count += 1
            state = "closed"
            days = _days_between(created_at, closed_at)
        else:
            if status in WAITING_STATUSES:
                waiting_count += 1
                state = "awaiting student"
            else:
                open_count += 1
                state = "open"
            days = _days_between(created_at, now_iso)
            if (item.get("due_bucket")
                    and str(item.get("next_action_at") or "9999") <= now_iso):
                overdue_count += 1

        tickets.append({
            "student": f"*{str(item.get('wa_id', ''))[-4:]}",
            "ticket_id": str(item.get("ticket_id") or "-"),
            "category": category,
            "state": state,
            "created_at": created_at or "",
            "closed_at": closed_at or "",
            "closed_reason": str(item.get("closed_reason") or ""),
            "nudges": nudges,
            "reminders": reminders,
            "days": days,
        })

    tickets.sort(key=lambda t: t["created_at"], reverse=True)

    closed = [t for t in tickets if t["state"] == "closed"]
    closed_days = [t["days"] for t in closed if t["days"] is not None]
    total_nudges = sum(t["nudges"] for t in tickets)
    total_reminders = sum(t["reminders"] for t in tickets)
    template_sends = total_nudges + total_reminders + verifications + closed_count
    ai_turns = total_messages // 2

    return {
        "generated_at": now_iso,
        "conversations": len(items),
        "tickets_total": len(tickets),
        "open": open_count,
        "waiting": waiting_count,
        "closed": closed_count,
        "overdue": overdue_count,
        "by_category": dict(sorted(by_category.items(), key=lambda kv: -kv[1])),
        "avg_days_to_close": (sum(closed_days) / len(closed_days)) if closed_days else None,
        "pct_closed_without_nudge": (
            100.0 * sum(1 for t in closed if t["nudges"] == 0) / len(closed)
        ) if closed else None,
        "avg_nudges_per_ticket": (total_nudges / len(tickets)) if tickets else 0.0,
        "template_sends": template_sends,
        "ai_turns": ai_turns,
        "meta_cost_inr": template_sends * TEMPLATE_INR,
        "ai_cost_inr": ai_turns * AI_TURN_INR,
        "tickets": tickets[:60],
    }


# --- rendering -----------------------------------------------------------------

_STATE_COLORS = {"open": "#C0670F", "awaiting student": "#2F5FBE", "closed": "#1B8A50"}


def _fmt_days(days):
    if days is None:
        return "-"
    return f"{days:.1f}d"


def _bars(counts):
    """Horizontal bar list for the category report."""
    if not counts:
        return "<p class='muted'>No tickets yet.</p>"
    peak = max(counts.values())
    rows = []
    for name, count in counts.items():
        width = max(int(100 * count / peak), 4)
        rows.append(
            f"<div class='bar-row'><span class='bar-label'>{html.escape(name)}</span>"
            f"<span class='bar-track'><span class='bar' style='width:{width}%'></span></span>"
            f"<span class='bar-num'>{count}</span></div>"
        )
    return "".join(rows)


def render(metrics, billing=None):
    """Return the full dashboard HTML.

    `billing` is the optional result of billing.fetch_all(): real provider
    spend where reachable. Cards fall back to usage-based estimates and every
    figure is badged LIVE or ESTIMATE so the reader always knows which.
    """
    m = metrics
    b = billing or {}

    def _money(source_key, estimate_html):
        src = b.get(source_key) or {}
        if src.get("source") == "live" and src.get("amount") is not None:
            symbol = "₹" if src.get("currency") == "INR" else "$"
            return (f"{symbol}{src['amount']:.2f}",
                    "<span class='badge live'>LIVE</span>",
                    html.escape(src.get("detail") or ""))
        reason = html.escape(src.get("detail") or "billing API not configured")
        return (estimate_html, "<span class='badge est'>ESTIMATE</span>", reason)

    ai_v, ai_badge, ai_note = _money("openai", f"₹{m['ai_cost_inr']:.0f}")
    meta_v, meta_badge, meta_note = _money("meta", f"₹{m['meta_cost_inr']:.0f}")
    aws_v, aws_badge, aws_note = _money("aws", f"₹{AWS_FLAT_INR}/mo")
    avg_close = _fmt_days(m["avg_days_to_close"])
    pct_clean = ("-" if m["pct_closed_without_nudge"] is None
                 else f"{m['pct_closed_without_nudge']:.0f}%")

    rows = []
    for t in m["tickets"]:
        color = _STATE_COLORS.get(t["state"], "#6B6459")
        nudge_class = "good" if t["nudges"] == 0 else ("warn" if t["nudges"] == 1 else "bad")
        reason = f" · {html.escape(t['closed_reason'])}" if t["closed_reason"] else ""
        rows.append(
            "<tr>"
            f"<td>{html.escape(t['student'])}</td>"
            f"<td>{html.escape(t['ticket_id'])}</td>"
            f"<td>{html.escape(t['category'])}</td>"
            f"<td><span class='pill' style='color:{color};border-color:{color}'>"
            f"{html.escape(t['state'])}</span>{reason}</td>"
            f"<td>{html.escape((t['created_at'] or '')[:10])}</td>"
            f"<td class='num'>{_fmt_days(t['days'])}</td>"
            f"<td class='num {nudge_class}'>{t['nudges']}</td>"
            f"<td class='num'>{t['reminders']}</td>"
            "</tr>"
        )
    table_rows = "".join(rows) or "<tr><td colspan='8' class='muted'>No tickets yet.</td></tr>"

    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<meta http-equiv="refresh" content="60">
<title>Support Line Admin</title>
<style>
  :root {{ --ink:#26221C; --muted:#6B6459; --line:#DDD9D1; --green:#1B8A50;
           --orange:#C0670F; --blue:#2F5FBE; --red:#B4442C; --paper:#F7F6F2; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--paper); color:var(--ink);
         font-family:"Segoe UI",system-ui,sans-serif; font-size:15px; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:26px 20px 40px; }}
  h1 {{ font-size:1.5rem; margin:0 0 2px; }}
  .sub {{ color:var(--muted); font-size:.85rem; margin-bottom:22px; }}
  h2 {{ font-size:1.05rem; margin:26px 0 10px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; }}
  .card {{ background:#fff; border:1.5px solid var(--line); border-radius:10px; padding:12px 14px; }}
  .card .v {{ font-size:1.6rem; font-weight:600; font-variant-numeric:tabular-nums; }}
  .card .l {{ font-size:.78rem; color:var(--muted); }}
  .card.alert .v {{ color:var(--red); }}
  .cost-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }}
  .cost {{ background:#fff; border:1.5px solid var(--line); border-left-width:5px; border-radius:10px; padding:12px 14px; }}
  .cost .s {{ font-size:.72rem; font-weight:600; text-transform:uppercase; letter-spacing:.07em; color:var(--muted); margin-bottom:2px; }}
  .badge {{ border-radius:4px; padding:1px 6px; font-size:.6rem; font-weight:700; letter-spacing:.06em; vertical-align:1px; }}
  .badge.live {{ background:var(--green); color:#fff; }}
  .badge.est {{ background:#E5E2DB; color:var(--muted); }}
  .cost .v {{ font-size:1.25rem; font-weight:600; }}
  .cost .l {{ font-size:.78rem; color:var(--muted); line-height:1.4; }}
  .cost a {{ color:inherit; }}
  .bar-row {{ display:flex; align-items:center; gap:10px; margin-bottom:7px; }}
  .bar-label {{ flex:0 0 130px; font-size:.85rem; }}
  .bar-track {{ flex:1; background:#EBE9E3; border-radius:6px; height:16px; overflow:hidden; }}
  .bar {{ display:block; height:100%; background:var(--orange); border-radius:6px; }}
  .bar-num {{ flex:0 0 34px; text-align:right; font-variant-numeric:tabular-nums; font-weight:600; }}
  table {{ width:100%; border-collapse:collapse; background:#fff; border:1.5px solid var(--line);
           border-radius:10px; overflow:hidden; font-size:.85rem; }}
  th {{ text-align:left; font-size:.68rem; text-transform:uppercase; letter-spacing:.08em;
       color:var(--muted); padding:8px 10px; border-bottom:1.5px solid var(--line); }}
  td {{ padding:7px 10px; border-bottom:1px solid #EEECE7; }}
  tr:last-child td {{ border-bottom:none; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .pill {{ border:1.5px solid; border-radius:999px; padding:1px 9px; font-size:.72rem; font-weight:600; }}
  .good {{ color:var(--green); font-weight:700; }}
  .warn {{ color:var(--orange); font-weight:700; }}
  .bad {{ color:var(--red); font-weight:700; }}
  .muted {{ color:var(--muted); }}
  .note {{ font-size:.78rem; color:var(--muted); margin-top:8px; }}
</style></head><body><div class="wrap">
  <h1>Support Line — Admin Panel</h1>
  <div class="sub">Live from system records · generated {html.escape(m["generated_at"])} UTC ·
    auto-refreshes every 60s · student numbers masked</div>

  <div class="cards">
    <div class="card"><div class="v">{m["conversations"]}</div><div class="l">conversations stored</div></div>
    <div class="card"><div class="v">{m["tickets_total"]}</div><div class="l">tickets, all time</div></div>
    <div class="card"><div class="v">{m["open"]}</div><div class="l">open now</div></div>
    <div class="card"><div class="v">{m["waiting"]}</div><div class="l">awaiting student</div></div>
    <div class="card"><div class="v">{m["closed"]}</div><div class="l">closed</div></div>
    <div class="card{' alert' if m["overdue"] else ''}"><div class="v">{m["overdue"]}</div><div class="l">overdue right now</div></div>
  </div>

  <h2>Realtime spend — what we use and what it costs</h2>
  <div class="cost-grid">
    <div class="cost" style="border-left-color:var(--red)">
      <div class="s">OpenAI · the AI brain {ai_badge}</div>
      <div class="v">{ai_v}</div>
      <div class="l"><b>{m["ai_turns"]}</b> answered turns recorded ·
        used for: reading each message, choosing answer/ticket<br>
        {ai_note}<br>
        console: <a href="https://platform.openai.com/usage">platform.openai.com/usage</a></div>
    </div>
    <div class="cost" style="border-left-color:var(--red)">
      <div class="s">Meta WhatsApp · reminders {meta_badge}</div>
      <div class="v">{meta_v}</div>
      <div class="l"><b>{m["template_sends"]}</b> template sends recorded ·
        used for: admin nudges, "resolved?" checks, close notices<br>
        {meta_note}<br>
        chat replies: ₹0 · console: WhatsApp Manager → Insights</div>
    </div>
    <div class="cost" style="border-left-color:var(--red)">
      <div class="s">AWS · hosting {aws_badge}</div>
      <div class="v">{aws_v}</div>
      <div class="l">used for: Lambda (bot + sweeper), DynamoDB memory, API Gateway, logs, secrets vault<br>
        {aws_note}<br>
        console: AWS Console → Billing</div>
    </div>
    <div class="cost" style="border-left-color:var(--green)">
      <div class="s">Zoho Desk · tickets</div>
      <div class="v">₹0 extra</div>
      <div class="l">included in the existing Zoho One subscription<br>
        used for: the ticket board, audit trail, admin emails</div>
    </div>
  </div>
  <div class="note"><span class="badge live">LIVE</span> = month-to-date figure fetched from that
    provider's own billing API (refreshed hourly). <span class="badge est">ESTIMATE</span> = computed
    from this system's usage counters because the billing API is not configured/reachable — the
    reason is shown on the card. Page reloads every 60s.</div>

  <h2>Tickets by category</h2>
  {_bars(m["by_category"])}

  <h2>Admin response — did tickets need chasing?</h2>
  <div class="cards">
    <div class="card"><div class="v">{avg_close}</div><div class="l">average time to close</div></div>
    <div class="card"><div class="v">{pct_clean}</div><div class="l">closed with zero reminders</div></div>
    <div class="card"><div class="v">{m["avg_nudges_per_ticket"]:.1f}</div><div class="l">admin nudges per ticket</div></div>
  </div>

  <h2>Ticket timeline (latest {len(m["tickets"])})</h2>
  <table>
    <tr><th>Student</th><th>Ticket</th><th>Category</th><th>Status</th>
        <th>Created</th><th>Age / time to close</th><th>Admin nudges</th><th>Student reminders</th></tr>
    {table_rows}
  </table>
  <div class="note">Nudges column: <span class="good">0</span> = admin acted before any reminder ·
    <span class="warn">1</span> = one reminder needed · <span class="bad">2+</span> = repeated chasing.
    Closed tickets no longer show their ticket number (it is cleared on closure by design).</div>
</div></body></html>"""
