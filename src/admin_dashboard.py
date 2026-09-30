"""Admin dashboard: one protected HTML app summarising spend, tickets and
how quickly the admin side acted.

Two views served as a single page: OVERVIEW (fits one screen; the numbers that
matter now, with hover popovers for detail) and REPORTS (the full ticket
timeline and breakdowns), switched client-side via the left menu.

Everything is computed from the conversation items the system already stores in
DynamoDB -- no new write paths, no extra services. Spend cards show the real
provider bill where `billing.fetch_all()` could reach it (badged LIVE) and a
usage-based estimate otherwise (badged ESTIMATE, with the reason).

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
            f"<div class='bar-row' title='{count} ticket(s) in {html.escape(name)}'>"
            f"<span class='bar-label'>{html.escape(name)}</span>"
            f"<span class='bar-track'><span class='bar' style='width:{width}%'></span></span>"
            f"<span class='bar-num'>{count}</span></div>"
        )
    return "".join(rows)


def render_overdue_only(metrics):
    """Archana's view: one number, one instruction, nothing else.

    Her job is a daily glance, not operating the dashboard -- no billing, no
    tickets, no jargon. If the number is 0 there is nothing to do; if not,
    the page tells her the one message to send and to whom.
    """
    overdue = metrics["overdue"]
    ok = overdue == 0
    color = "#1B8A50" if ok else "#B4442C"
    bg = "#EAF5EE" if ok else "#FBEBE7"
    big = "0" if ok else str(overdue)
    headline = "All clear" if ok else "Something needs attention"
    instruction = (
        "Nothing to do today."
        if ok else
        "Please send this message to Naidu ji or Kalyani madam:<br>"
        "<i>“Admin panel shows an overdue ticket, please check.”</i>"
    )
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Support Line — Daily Check</title>
<style>
  body {{ margin:0; background:#F7F6F2; color:#26221C; font-family:"Segoe UI",system-ui,sans-serif;
         display:flex; align-items:center; justify-content:center; min-height:100vh; padding:24px; }}
  .card {{ background:#fff; border:1.5px solid #E3E0D9; border-radius:20px; padding:40px 32px;
          max-width:480px; width:100%; text-align:center; box-shadow:0 10px 30px rgba(38,34,28,.10); }}
  .num {{ font-size:6rem; font-weight:700; color:{color}; background:{bg}; border-radius:20px;
         padding:24px; margin-bottom:20px; font-variant-numeric:tabular-nums; }}
  h1 {{ font-size:1.3rem; margin:0 0 14px; color:{color}; }}
  p {{ font-size:1.05rem; line-height:1.6; color:#4B4438; margin:0; }}
  .label {{ font-size:.8rem; color:#6B6459; margin-top:-14px; margin-bottom:24px; }}
  .refresh {{ margin-top:26px; padding:12px 20px; background:#26221C; color:#fff; border:none;
             border-radius:10px; font-size:1rem; cursor:pointer; }}
</style></head><body>
  <div class="card">
    <div class="num">{big}</div>
    <div class="label">tickets overdue right now</div>
    <h1>{headline}</h1>
    <p>{instruction}</p>
    <button class="refresh" onclick="location.reload()">Check again</button>
  </div>
</body></html>"""


def render(metrics, billing=None, zoho_tickets=None):
    """Return the full dashboard HTML (overview + reports views).

    `billing` is the optional result of billing.fetch_all(): real provider
    spend where reachable. Cards fall back to usage-based estimates and every
    figure is badged LIVE or ESTIMATE so the reader always knows which.

    `zoho_tickets` is the optional Zoho Desk archive (zoho_client.list_tickets):
    the Reports view shows every individual ticket from it, since the local
    store keeps only one live record per student. None = archive unreachable.
    """
    m = metrics
    b = billing or {}

    zoho_status_colors = {"open": "#C0670F", "on hold": "#6B6459",
                          "escalated": "#B4442C", "resolved": "#2F5FBE",
                          "closed": "#1B8A50"}
    if zoho_tickets is None:
        zoho_section = ("<p class='muted'>Zoho Desk archive unreachable right now "
                        "— showing only the live student records below.</p>")
        zoho_cats = None
    elif not zoho_tickets:
        zoho_section = "<p class='muted'>No tickets in Zoho Desk yet.</p>"
        zoho_cats = None
    else:
        zrows = []
        zoho_cats = {}
        for t in zoho_tickets:
            cat = (t.get("category") or "-").strip() or "-"
            if cat != "-":
                zoho_cats[cat] = zoho_cats.get(cat, 0) + 1
            color = zoho_status_colors.get(str(t.get("status", "")).lower(), "#6B6459")
            zrows.append(
                "<tr>"
                f"<td class='num'>#{html.escape(t.get('number', '-'))}</td>"
                f"<td>{html.escape(t.get('subject', ''))}</td>"
                f"<td>{html.escape(cat)}</td>"
                f"<td><span class='pill' style='color:{color};border-color:{color}'>"
                f"{html.escape(t.get('status', '-'))}</span></td>"
                f"<td>{html.escape(t.get('created', ''))}</td>"
                "</tr>"
            )
        zoho_section = (
            "<table><tr><th>#</th><th>Subject</th><th>Category</th>"
            "<th>Status</th><th>Created</th></tr>" + "".join(zrows) + "</table>"
        )

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

    overdue_alert = " alert" if m["overdue"] else ""
    gen_short = html.escape(m["generated_at"].replace("T", " ").replace("Z", " UTC"))

    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Support Line Admin</title>
<style>
  :root {{ --ink:#26221C; --muted:#6B6459; --line:#E3E0D9; --green:#1B8A50;
           --orange:#C0670F; --blue:#2F5FBE; --red:#B4442C; --paper:#F7F6F2;
           --side:#26221C; --card:#FFFFFF; }}
  * {{ box-sizing:border-box; }}
  /* rem units below all scale off THIS root size, not body's -- raising it
     is what actually makes every number/label on the page bigger, not just
     plain body text. */
  html {{ height:100%; font-size:18px; }}
  body {{ height:100%; margin:0; background:var(--paper); color:var(--ink);
         font-family:"Segoe UI",system-ui,sans-serif; font-size:1rem; display:flex; }}
  [hidden] {{ display:none !important; }}

  aside {{ flex:0 0 190px; background:var(--side); color:#EDEAE4; display:flex;
          flex-direction:column; padding:22px 0; }}
  .brand {{ padding:0 22px 18px; font-weight:600; font-size:1.02rem; letter-spacing:.02em; }}
  .brand small {{ display:block; color:#A79F92; font-weight:400; font-size:.72rem; margin-top:2px; }}
  nav a {{ display:block; padding:11px 22px; color:#C9C3B8; text-decoration:none;
          font-size:.9rem; border-left:3px solid transparent; cursor:pointer; }}
  nav a:hover {{ color:#fff; background:#332E27; }}
  nav a.on {{ color:#fff; border-left-color:var(--orange); background:#332E27; font-weight:600; }}
  .side-foot {{ margin-top:auto; padding:14px 22px 0; font-size:.68rem; color:#A79F92; line-height:1.5; }}
  .refresh {{ display:block; width:100%; margin-bottom:10px; padding:8px 10px;
             background:#332E27; color:#EDEAE4; border:1.5px solid #4A443B;
             border-radius:8px; font-size:.78rem; font-weight:600; cursor:pointer; }}
  .refresh:hover {{ background:#3E382F; border-color:var(--orange); }}
  .dot {{ display:inline-block; width:7px; height:7px; border-radius:50%; background:var(--green);
         margin-right:6px; animation:pulse 2s infinite; }}
  @keyframes pulse {{ 50% {{ opacity:.35; }} }}

  main {{ flex:1; min-width:0; overflow:auto; padding:22px 28px; }}
  .view {{ max-width:1220px; }}
  .topline {{ display:flex; align-items:baseline; justify-content:space-between; margin-bottom:16px; }}
  h1 {{ font-size:1.25rem; margin:0; }}
  .when {{ color:var(--muted); font-size:.78rem; }}
  h2 {{ font-size:.8rem; text-transform:uppercase; letter-spacing:.12em; color:var(--muted);
       margin:20px 0 10px; }}

  .tiles {{ display:grid; grid-template-columns:repeat(6,1fr); gap:12px; }}
  .tile {{ background:var(--card); border:1.5px solid var(--line); border-radius:12px;
          padding:12px 14px; transition:transform .12s, box-shadow .12s; cursor:default; }}
  .tile:hover {{ transform:translateY(-2px); box-shadow:0 4px 14px rgba(38,34,28,.1); }}
  .tile .v {{ font-size:1.65rem; font-weight:650; font-variant-numeric:tabular-nums; line-height:1.1; }}
  .tile .l {{ font-size:.74rem; color:var(--muted); margin-top:2px; }}
  .tile.alert {{ border-color:var(--red); }}
  .tile.alert .v {{ color:var(--red); }}

  .costs {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }}
  .cost {{ position:relative; background:var(--card); border:1.5px solid var(--line);
          border-top:4px solid var(--red); border-radius:12px; padding:12px 14px;
          transition:transform .12s, box-shadow .12s; cursor:default; }}
  .cost.freebie {{ border-top-color:var(--green); }}
  .cost:hover {{ transform:translateY(-2px); box-shadow:0 6px 18px rgba(38,34,28,.12); z-index:5; }}
  .cost .s {{ font-size:.7rem; font-weight:600; text-transform:uppercase; letter-spacing:.07em;
             color:var(--muted); display:flex; justify-content:space-between; align-items:center; }}
  .cost .v {{ font-size:1.5rem; font-weight:650; margin:4px 0 2px; font-variant-numeric:tabular-nums; }}
  .cost .u {{ font-size:.74rem; color:var(--muted); }}
  .badge {{ border-radius:4px; padding:1px 6px; font-size:.58rem; font-weight:700; letter-spacing:.06em; }}
  .badge.live {{ background:var(--green); color:#fff; }}
  .badge.est {{ background:#E5E2DB; color:var(--muted); }}
  .pop {{ display:none; position:absolute; left:0; right:-40px; top:calc(100% + 6px);
         background:#fff; border:1.5px solid var(--line); border-radius:10px;
         box-shadow:0 10px 26px rgba(38,34,28,.18); padding:11px 13px;
         font-size:.78rem; line-height:1.5; color:var(--ink); }}
  .cost:hover .pop {{ display:block; }}
  .pop a {{ color:var(--blue); }}
  .hint {{ font-size:.72rem; color:var(--muted); margin-top:8px; }}

  .duo {{ display:grid; grid-template-columns:3fr 2fr; gap:12px; }}
  .panel {{ background:var(--card); border:1.5px solid var(--line); border-radius:12px; padding:14px 16px; }}
  .panel h2 {{ margin-top:0; }}
  .bar-row {{ display:flex; align-items:center; gap:10px; margin-bottom:7px; }}
  .bar-label {{ flex:0 0 120px; font-size:.82rem; }}
  .bar-track {{ flex:1; background:#EBE9E3; border-radius:6px; height:14px; overflow:hidden; }}
  .bar {{ display:block; height:100%; background:var(--orange); border-radius:6px;
         transition:width .4s; }}
  .bar-num {{ flex:0 0 30px; text-align:right; font-variant-numeric:tabular-nums; font-weight:600; }}
  .mini {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }}
  .mini .tile .v {{ font-size:1.3rem; }}

  table {{ width:100%; border-collapse:collapse; background:var(--card);
           border:1.5px solid var(--line); border-radius:12px; overflow:hidden; font-size:.84rem; }}
  th {{ text-align:left; font-size:.66rem; text-transform:uppercase; letter-spacing:.08em;
       color:var(--muted); padding:9px 11px; border-bottom:1.5px solid var(--line); }}
  td {{ padding:8px 11px; border-bottom:1px solid #EFEDE8; }}
  tr:hover td {{ background:#FBFAF7; }}
  tr:last-child td {{ border-bottom:none; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .pill {{ border:1.5px solid; border-radius:999px; padding:1px 9px; font-size:.7rem; font-weight:600; }}
  .good {{ color:var(--green); font-weight:700; }}
  .warn {{ color:var(--orange); font-weight:700; }}
  .bad {{ color:var(--red); font-weight:700; }}
  .muted {{ color:var(--muted); }}
  .note {{ font-size:.76rem; color:var(--muted); margin-top:10px; line-height:1.5; }}
</style></head><body>

<aside>
  <div class="brand">Support Line<small>Siddhanta Knowledge Foundation</small></div>
  <nav>
    <a data-v="overview" onclick="show('overview')">Overview</a>
    <a data-v="reports" onclick="show('reports')">Reports</a>
  </nav>
  <div class="side-foot">
    <button class="refresh" onclick="location.reload()">⟳ Refresh data</button>
    <span class="dot"></span>live data · refresh manually<br>{gen_short}
  </div>
</aside>

<main>
  <section id="overview" class="view">
    <div class="topline"><h1>Admin Panel — Overview</h1>
      <span class="when">hover any card for detail</span></div>

    <div class="tiles">
      <div class="tile" title="Every student who has ever messaged the bot"><div class="v">{m["conversations"]}</div><div class="l">conversations</div></div>
      <div class="tile" title="One live record per student; a student's newer ticket replaces their older one here. Zoho Desk keeps the full history of every individual ticket."><div class="v">{m["tickets_total"]}</div><div class="l">students with tickets</div></div>
      <div class="tile" title="Waiting on the LMS admin right now"><div class="v">{m["open"]}</div><div class="l">open now</div></div>
      <div class="tile" title="Resolved; waiting for the student's Yes/No"><div class="v">{m["waiting"]}</div><div class="l">awaiting student</div></div>
      <div class="tile" title="Confirmed fixed by the student, or auto-closed"><div class="v">{m["closed"]}</div><div class="l">closed</div></div>
      <div class="tile{overdue_alert}" title="Past the SLA clock and being chased by the sweeper"><div class="v">{m["overdue"]}</div><div class="l">overdue right now</div></div>
    </div>

    <h2>Spend</h2>
    <div class="costs">
      <div class="cost">
        <div class="s"><span>OpenAI · AI brain</span>{ai_badge}</div>
        <div class="v">{ai_v}</div>
        <div class="u">{m["ai_turns"]} answered turns</div>
        <div class="pop">Reads each student message and chooses: answer or ticket.
          Unit ≈ ₹{AI_TURN_INR:.2f}/conversation.<br>{ai_note}<br>
          Bill: <a href="https://platform.openai.com/usage">platform.openai.com/usage</a></div>
      </div>
      <div class="cost">
        <div class="s"><span>Meta · WhatsApp</span>{meta_badge}</div>
        <div class="v">{meta_v}</div>
        <div class="u">{m["template_sends"]} template sends</div>
        <div class="pop">Chat replies are free; only scheduled templates are paid
          (admin nudges, "resolved?" checks, close notices) at ₹{TEMPLATE_INR:.3f} incl. GST.<br>
          {meta_note}<br>Bill: WhatsApp Manager → Insights</div>
      </div>
      <div class="cost">
        <div class="s"><span>AWS · hosting</span>{aws_badge}</div>
        <div class="v">{aws_v}</div>
        <div class="u">Lambda · DynamoDB · API GW</div>
        <div class="pop">Serverless hosting: runs only when messages arrive.<br>
          {aws_note}<br>Bill: AWS Console → Billing</div>
      </div>
      <div class="cost freebie">
        <div class="s"><span>Zoho Desk · tickets</span></div>
        <div class="v">₹0 extra</div>
        <div class="u">inside Zoho One</div>
        <div class="pop">Ticket board, audit trail and admin email notifications —
          covered by the existing Zoho One subscription.</div>
      </div>
    </div>
    <div class="hint"><span class="badge live">LIVE</span> figure fetched from that provider's own
      billing API (cached 1h) · <span class="badge est">ESTIMATE</span> computed from usage counters;
      the reason is shown in the card's hover.</div>

    <div class="duo" style="margin-top:20px">
      <div class="panel"><h2>Tickets by category</h2>{_bars(m["by_category"])}</div>
      <div class="panel"><h2>Admin response</h2>
        <div class="mini">
          <div class="tile" title="From ticket creation to confirmed closure"><div class="v">{avg_close}</div><div class="l">avg time to close</div></div>
          <div class="tile" title="Closed before any automatic reminder was needed"><div class="v">{pct_clean}</div><div class="l">zero-reminder closes</div></div>
          <div class="tile" title="Automatic WhatsApp reminders sent per ticket"><div class="v">{m["avg_nudges_per_ticket"]:.1f}</div><div class="l">nudges per ticket</div></div>
        </div>
        <div class="note">Full per-ticket timeline is under <b>Reports</b>.</div>
      </div>
    </div>
  </section>

  <section id="reports" class="view" hidden>
    <div class="topline"><h1>Admin Panel — Reports</h1>
      <span class="when">archive from Zoho Desk · live records from the system</span></div>

    <h2>All tickets — full Zoho Desk archive (newest first)</h2>
    {zoho_section}

    <h2 style="margin-top:24px">Live student records — how fast we acted</h2>
    <table>
      <tr><th>Student</th><th>Ticket</th><th>Category</th><th>Status</th>
          <th>Created</th><th>Age / time to close</th><th>Admin nudges</th><th>Student reminders</th></tr>
      {table_rows}
    </table>
    <div class="note">Nudges: <span class="good">0</span> = admin acted before any reminder ·
      <span class="warn">1</span> = one reminder needed · <span class="bad">2+</span> = repeated chasing.
      Closed tickets no longer show their ticket number (cleared on closure by design).
      One row per student (their newest ticket); the complete per-ticket archive lives in
      Zoho Desk. Student numbers are masked to the last 4 digits everywhere.</div>

    <h2 style="margin-top:24px">Categories</h2>
    <div class="panel">{_bars(zoho_cats if zoho_cats else m["by_category"])}</div>
  </section>
</main>

<script>
function show(v) {{
  document.querySelectorAll('.view').forEach(function (el) {{ el.hidden = true; }});
  document.getElementById(v).hidden = false;
  document.querySelectorAll('nav a').forEach(function (a) {{
    a.classList.toggle('on', a.dataset.v === v);
  }});
  location.hash = v;
}}
show(location.hash === '#reports' ? 'reports' : 'overview');
</script>
</body></html>"""
