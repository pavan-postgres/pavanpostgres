"""
HTML Report Generator — pgbadger-style, self-contained.
Generates a single HTML file with:
  - All existing sections (summary, slow queries, errors, connections …)
  - Log Explorer: include/exclude keyword filters, regex, PID session tracer
"""

import json, html as _html, os
from collections import Counter


def _j(o):  return json.dumps(o, default=str)
def _e(s):  return _html.escape(str(s))

def _ms(ms):
    if ms >= 3_600_000: return f"{ms/3_600_000:.2f}h"
    if ms >= 60_000:    return f"{ms/60_000:.2f}m"
    if ms >= 1_000:     return f"{ms/1_000:.2f}s"
    return f"{ms:.1f}ms"

def _sql(sql, max_len=2000):
    if not sql: return '<em class="muted">— no statement captured —</em>'
    s = _e(sql[:max_len])
    sfx = '<span class="muted"> … (truncated)</span>' if len(sql) > max_len else ''
    return f'<pre class="sql-block">{s}{sfx}</pre>'


def generate(result, output_path: str, job_id: str = "") -> None:

    # ── chart data ─────────────────────────────────────────────────────────
    hours     = sorted(result.by_hour.items())
    h_labels  = [h[0][5:] for h in hours]
    h_vals    = [h[1]     for h in hours]

    sev_items  = list(result.by_severity.most_common())
    sev_labels = [s[0] for s in sev_items]
    sev_vals   = [s[1] for s in sev_items]

    db_items  = [(k,v) for k,v in result.by_database.most_common(8) if k != '[unknown]']
    db_labels = [d[0] for d in db_items]
    db_vals   = [d[1] for d in db_items]

    node_items  = list(result.by_node.most_common())
    node_labels = [n[0].split('.')[-1] for n in node_items]
    node_vals   = [n[1] for n in node_items]

    err_items  = list(result.error_types.most_common(12))
    err_labels = [e[0][:55] + ('…' if len(e[0])>55 else '') for e in err_items]
    err_vals   = [e[1] for e in err_items]

    bucket_order = ['<100ms','100ms-1s','1s-10s','10s-1min','>1min']
    bkts = Counter()
    for sq in result.slow_queries:
        d = sq['duration_ms']
        if   d < 100:   bkts['<100ms']   += 1
        elif d < 1000:  bkts['100ms-1s'] += 1
        elif d < 10000: bkts['1s-10s']   += 1
        elif d < 60000: bkts['10s-1min'] += 1
        else:           bkts['>1min']    += 1
    b_vals = [bkts.get(b,0) for b in bucket_order]

    top_by_time  = sorted(result.slow_by_normalized.items(), key=lambda x: -x[1]['total_ms'])[:20]
    top_by_count = sorted(result.slow_by_normalized.items(), key=lambda x: -x[1]['count'])[:20]

    all_errors = result.errors + result.fatals
    all_errors.sort(key=lambda x: x['ts'])

    # ── Explorer data (embedded as JSON) ────────────────────────────────────
    log_sample_json   = _j(getattr(result, 'log_sample', []))
    pid_groups_json   = _j(getattr(result, 'pid_groups', {}))
    ex_databases_json = _j([k for k in result.by_database if k != '[unknown]'])
    ex_users_json     = _j([k for k in result.by_user    if k not in ('[unknown]',)])
    ex_nodes_json     = _j(list(result.by_node.keys()))

    # ── row helpers ─────────────────────────────────────────────────────────
    def slow_row(i, sq):
        dur = sq['duration_ms']
        dc  = 'dur-crit' if dur>60000 else ('dur-warn' if dur>5000 else 'dur-ok')
        sid = f"sql_{i}"
        return f"""<tr>
          <td class="num">{i+1}</td>
          <td class="{dc} num">{_ms(dur)}</td>
          <td class="mono xs">{_e(sq['ts'])}</td>
          <td class="mono xs">{_e(sq['user'])}</td>
          <td><span class="db-pill">{_e(sq['db'][:30])}</span></td>
          <td class="mono xs">{_e(sq['node'].split('.')[-1])}</td>
          <td class="mono xs pid-cell" data-pid="{_e(sq['pid'])}">{_e(sq['pid'])}</td>
          <td>
            <button class="toggle-btn" onclick="toggleSQL('{sid}')">Show SQL ▾</button>
            <div id="{sid}" style="display:none;margin-top:8px">{_sql(sq['sql'])}</div>
          </td>
        </tr>"""

    def grouped_row(rank, key, grp):
        gid  = f"gq_{rank}"
        samp = grp['samples'][0] if grp['samples'] else {}
        avg  = grp['total_ms'] / grp['count']
        return f"""<tr>
          <td class="num">{rank}</td>
          <td class="num">×{grp['count']}</td>
          <td class="num dur-crit">{_ms(grp['total_ms'])}</td>
          <td class="num dur-warn">{_ms(avg)}</td>
          <td class="num dur-ok">{_ms(grp['min_ms'])}</td>
          <td class="num">{_ms(grp['max_ms'])}</td>
          <td>
            <button class="toggle-btn" onclick="toggleSQL('{gid}')">Show SQL ▾</button>
            <div id="{gid}" style="display:none;margin-top:8px">{_sql(samp.get('sql',''))}</div>
          </td>
        </tr>"""

    def err_row(e):
        sc = 'sev-fatal' if e['severity']=='FATAL' else 'sev-error'
        return f"""<tr data-sev="{_e(e['severity'])}">
          <td class="{sc}">{_e(e['severity'])}</td>
          <td class="mono xs">{_e(e['ts'])}</td>
          <td class="mono xs">{_e(e['user'])}@<span class="db-pill">{_e(e['db'][:22])}</span></td>
          <td class="mono xs">{_e(e['node'].split('.')[-1])}</td>
          <td class="mono xs pid-cell" data-pid="{_e(e['pid'])}">{_e(e['pid'])}</td>
          <td class="msg">{_e(e['msg'][:300])}</td>
        </tr>"""

    def av_row(av):
        return f"""<tr>
          <td class="mono xs">{_e(av['ts'])}</td>
          <td class="mono xs">{_e(av['user'])}</td>
          <td><span class="db-pill">{_e(av['db'][:25])}</span></td>
          <td class="mono xs">{_e(av['node'].split('.')[-1])}</td>
          <td class="msg">{_e(av['msg'][:250])}</td>
        </tr>"""

    def bar_rows(items, max_val, color):
        return ''.join(f"""<div class="stat-bar-row">
          <span class="label">{_e(k)}</span>
          <div class="stat-bar"><div class="stat-bar-fill" style="width:{round(v/max_val*100) if max_val else 0}%;background:{color}"></div></div>
          <span class="val">{v:,}</span>
        </div>""" for k,v in items)

    # ── full HTML ────────────────────────────────────────────────────────────
    report = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PG Log Report — {_e(result.filename)}</title>
<style>
:root{{
  --bg:#0d1117;--bg2:#161b22;--bg3:#21262d;--border:#30363d;
  --text:#e6edf3;--text2:#8b949e;--text3:#484f58;
  --green:#3fb950;--amber:#d29922;--red:#f85149;--blue:#58a6ff;
  --purple:#bc8cff;--teal:#39d353;
  --font:'JetBrains Mono',monospace;--sans:'Segoe UI',system-ui,sans-serif;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14px;line-height:1.6}}
.header{{background:linear-gradient(135deg,#161b22,#0d1117);border-bottom:1px solid var(--border);padding:28px 40px 24px}}
.header h1{{font-size:22px;font-weight:700;color:var(--blue);letter-spacing:-.5px}}
.header .sub{{font-size:13px;color:var(--text2);margin-top:6px;font-family:var(--font)}}
.header .badges{{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}}
.badge{{display:inline-flex;align-items:center;gap:5px;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600}}
.badge-red{{background:rgba(248,81,73,.15);color:#ffa198;border:1px solid rgba(248,81,73,.3)}}
.badge-amber{{background:rgba(210,153,34,.15);color:#e3b341;border:1px solid rgba(210,153,34,.3)}}
.badge-green{{background:rgba(63,185,80,.15);color:#56d364;border:1px solid rgba(63,185,80,.3)}}
.badge-blue{{background:rgba(88,166,255,.15);color:#79c0ff;border:1px solid rgba(88,166,255,.3)}}
.toc{{background:var(--bg2);border-bottom:1px solid var(--border);padding:12px 40px;display:flex;gap:20px;flex-wrap:wrap;overflow-x:auto;position:sticky;top:0;z-index:20}}
.toc a{{color:var(--text2);text-decoration:none;font-size:13px;font-weight:500;white-space:nowrap;padding:4px 0;border-bottom:2px solid transparent;transition:all .15s}}
.toc a:hover,.toc a.active{{color:var(--blue);border-bottom-color:var(--blue)}}
.toc a.explorer-link{{color:var(--green)}}
.toc a.explorer-link.active,.toc a.explorer-link:hover{{color:#56d364;border-bottom-color:var(--green)}}
.main{{max-width:1400px;margin:0 auto;padding:32px 40px}}
section{{margin-bottom:48px;scroll-margin-top:80px}}
.sec-title{{font-size:16px;font-weight:700;color:var(--text);padding-bottom:12px;border-bottom:1px solid var(--border);margin-bottom:20px;display:flex;align-items:center;gap:10px}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:14px;margin-bottom:24px}}
.metric{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:16px}}
.metric-label{{font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:.8px;font-weight:600;margin-bottom:8px}}
.metric-value{{font-size:26px;font-weight:700;font-family:var(--font);letter-spacing:-1px}}
.metric-sub{{font-size:11px;color:var(--text3);margin-top:4px}}
.mv-red{{color:var(--red)}}.mv-amber{{color:var(--amber)}}.mv-green{{color:var(--green)}}
.mv-blue{{color:var(--blue)}}.mv-purple{{color:var(--purple)}}
.charts{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px;margin-bottom:24px}}
.chart-card{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:16px}}
.chart-title{{font-size:12px;font-weight:600;color:var(--text2);text-transform:uppercase;letter-spacing:.7px;margin-bottom:12px}}
.chart-wrap{{position:relative;width:100%}}
.table-wrap{{overflow-x:auto;border:1px solid var(--border);border-radius:8px;background:var(--bg2)}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;padding:10px 14px;font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.8px;border-bottom:1px solid var(--border);background:var(--bg3);white-space:nowrap}}
td{{padding:10px 14px;border-bottom:1px solid rgba(48,54,61,.6);color:var(--text2);vertical-align:top}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:rgba(255,255,255,.02)}}
td.num{{text-align:right;font-family:var(--font);white-space:nowrap}}
td.mono{{font-family:var(--font)}}
td.xs{{font-size:12px}}
td.msg{{word-break:break-word;max-width:480px}}
.dur-crit{{color:var(--red);font-weight:700;font-family:var(--font)}}
.dur-warn{{color:var(--amber);font-weight:600;font-family:var(--font)}}
.dur-ok{{color:var(--green);font-family:var(--font)}}
.sev-fatal{{color:#ffa198;font-weight:700;font-family:var(--font);font-size:11px}}
.sev-error{{color:var(--red);font-weight:700;font-family:var(--font);font-size:11px}}
.muted{{color:var(--text3);font-style:italic}}
.db-pill{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-family:var(--font);background:rgba(188,140,255,.12);color:var(--purple);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:middle}}
.node-pill{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-family:var(--font);background:rgba(88,166,255,.12);color:var(--blue)}}
.sql-block{{background:#0a0f1a;border:1px solid #1c2333;border-radius:6px;padding:14px 16px;font-family:var(--font);font-size:12px;color:#cdd9e5;line-height:1.7;overflow-x:auto;white-space:pre-wrap;word-break:break-word;max-height:420px;overflow-y:auto}}
.toggle-btn{{background:transparent;border:1px solid var(--border);border-radius:5px;color:var(--text2);font-size:12px;padding:4px 10px;cursor:pointer;font-family:var(--sans);transition:all .15s}}
.toggle-btn:hover{{border-color:var(--blue);color:var(--blue)}}
.search-row{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}}
.search-row input,.search-row select{{background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:7px 12px;color:var(--text);font-size:13px;font-family:var(--sans);outline:none}}
.search-row input{{flex:1;min-width:180px}}
.search-row input:focus,.search-row select:focus{{border-color:var(--blue)}}
.stat-bar-row{{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid rgba(48,54,61,.4)}}
.stat-bar-row:last-child{{border-bottom:none}}
.stat-bar-row .label{{font-size:12px;color:var(--text2);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.stat-bar{{flex:2;height:5px;background:var(--border);border-radius:3px;overflow:hidden}}
.stat-bar-fill{{height:100%;border-radius:3px}}
.stat-bar-row .val{{font-size:12px;font-family:var(--font);color:var(--text);min-width:55px;text-align:right}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}}
/* ── Explorer styles ── */
.ex-filter-panel{{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:20px;margin-bottom:16px}}
.ex-label{{font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.7px;display:block;margin-bottom:6px}}
.ex-input{{width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:9px 12px;color:var(--text);font-size:13px;font-family:monospace;outline:none;transition:border-color .15s}}
.ex-input:focus{{border-color:var(--blue)}}
.ex-select{{background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:8px 10px;color:var(--text);font-size:13px;outline:none;cursor:pointer}}
.ex-btn{{padding:9px 18px;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;transition:all .15s}}
.ex-btn-primary{{background:var(--blue);color:#0d1117}}
.ex-btn-primary:hover{{background:#79c0ff}}
.ex-btn-ghost{{background:transparent;color:var(--text2);border:1px solid var(--border)}}
.ex-btn-ghost:hover{{border-color:var(--text2);color:var(--text)}}
.ex-btn-green{{background:var(--green);color:#0d1117}}
.ex-btn-green:hover{{background:#56d364}}
.pid-tracer-box{{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:14px;margin-bottom:14px}}
.pid-link{{color:var(--green);font-family:monospace;font-size:12px;cursor:pointer;text-decoration:underline dotted;text-underline-offset:3px}}
.pid-link:hover{{color:#56d364}}
mark.hit{{background:#d29922;color:#0d1117;border-radius:2px;padding:0 2px}}
.pid-info-card{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:14px;margin-top:10px}}
.ex-count{{font-size:13px;color:var(--text2);margin-left:6px}}
.pager{{display:flex;align-items:center;gap:8px;margin-top:14px;justify-content:flex-end;flex-wrap:wrap}}
.pager span{{font-size:12px;color:var(--text3)}}
footer{{text-align:center;padding:32px;color:var(--text3);font-size:12px;border-top:1px solid var(--border);margin-top:32px}}
.scroll-top{{position:fixed;bottom:24px;right:24px;background:var(--blue);color:#0d1117;border:none;border-radius:50%;width:40px;height:40px;font-size:20px;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.4);z-index:100}}
.pid-cell{{cursor:pointer;color:var(--green);font-family:monospace;font-size:12px}}
.pid-cell:hover{{text-decoration:underline}}
/* boolean query badges */
.qbadge{{display:inline-flex;align-items:center;padding:2px 8px;border-radius:4px;font-size:11px;font-family:monospace;line-height:1.5}}
.qbadge-txt{{background:rgba(255,255,255,.08);color:var(--text)}}
.qbadge-re{{background:rgba(88,166,255,.15);color:#79c0ff}}
.qbadge-err{{background:rgba(248,81,73,.2);color:#ffa198;cursor:help}}
.qop{{display:inline-flex;align-items:center;padding:2px 6px;border-radius:3px;font-size:11px;font-weight:700;font-family:var(--sans)}}
.qop-and{{background:rgba(210,153,34,.15);color:#e3b341}}
.qop-or{{background:rgba(63,185,80,.15);color:#56d364}}
.qop-not{{background:rgba(248,81,73,.15);color:#ffa198}}
.qop-paren{{color:var(--text3);font-family:monospace;font-size:13px;font-weight:700}}
@media(max-width:700px){{.grid2{{grid-template-columns:1fr}}.main{{padding:16px}}}}
</style>
</head>
<body>

<div class="header">
  <h1>&#9658; PostgreSQL Log Analysis Report</h1>
  <div class="sub">
    <b>File:</b> {_e(result.filename)} &nbsp;|&nbsp;
    <b>Size:</b> {result.file_size_mb} MB &nbsp;|&nbsp;
    <b>Period:</b> {_e(result.date_range[0])} → {_e(result.date_range[1])} &nbsp;|&nbsp;
    <b>Nodes:</b> {len(result.nodes)}
  </div>
  <div class="badges">
    <span class="badge badge-red">&#9679; {result.by_severity.get('FATAL',0)+result.by_severity.get('ERROR',0)} Errors/Fatals</span>
    <span class="badge badge-amber">&#9651; {result.slow_count:,} Slow Queries</span>
    <span class="badge badge-blue">&#10022; {result.conn_received:,} Connections</span>
    <span class="badge badge-green">&#10003; {result.parsed_entries:,} Events Parsed</span>
  </div>
</div>

<nav class="toc">
  <a href="#summary">Summary</a>
  <a href="#activity">Activity</a>
  <a href="#slowest">Slowest Queries</a>
  <a href="#grouped">Grouped Queries</a>
  <a href="#errors">Errors &amp; Fatals</a>
  <a href="#connections">Connections</a>
  <a href="#autovacuum">Autovacuum</a>
  <a href="#tempfiles">Temp Files</a>
  <a href="#locks">Lock Waits</a>
  <a href="#explorer" class="explorer-link">&#128269; Log Explorer</a>
</nav>

<div class="main">

<!-- ══ SUMMARY ══ -->
<section id="summary">
  <div class="sec-title"><span>&#9632;</span> Summary</div>
  <div class="metrics">
    <div class="metric"><div class="metric-label">Total Events</div><div class="metric-value mv-blue">{result.parsed_entries:,}</div><div class="metric-sub">{result.total_lines:,} raw lines</div></div>
    <div class="metric"><div class="metric-label">Errors + Fatals</div><div class="metric-value mv-red">{result.by_severity.get('ERROR',0)+result.by_severity.get('FATAL',0):,}</div><div class="metric-sub">{result.by_severity.get('ERROR',0)} errors · {result.by_severity.get('FATAL',0)} fatals</div></div>
    <div class="metric"><div class="metric-label">Slow Queries</div><div class="metric-value mv-amber">{result.slow_count:,}</div><div class="metric-sub">with logged duration</div></div>
    <div class="metric"><div class="metric-label">Max Duration</div><div class="metric-value mv-red">{_ms(result.slow_max_ms)}</div><div class="metric-sub">{result.slow_max_ms:,.0f} ms</div></div>
    <div class="metric"><div class="metric-label">Avg Duration</div><div class="metric-value mv-amber">{_ms(result.slow_avg_ms)}</div><div class="metric-sub">p95: {_ms(result.slow_p95_ms)}</div></div>
    <div class="metric"><div class="metric-label">p99 Duration</div><div class="metric-value mv-purple">{_ms(result.slow_p99_ms)}</div><div class="metric-sub">99th percentile</div></div>
    <div class="metric"><div class="metric-label">Connections</div><div class="metric-value mv-green">{result.conn_received:,}</div><div class="metric-sub">{result.conn_failed} auth failures</div></div>
    <div class="metric"><div class="metric-label">Autovacuum Runs</div><div class="metric-value mv-purple">{len(result.autovacuum_runs):,}</div><div class="metric-sub">background maintenance</div></div>
  </div>
  <div class="grid2">
    <div class="chart-card"><div class="chart-title">Events by Database</div>{bar_rows(db_items, max(db_vals) if db_vals else 1, 'var(--purple)')}</div>
    <div class="chart-card"><div class="chart-title">Events by User</div>{bar_rows(result.by_user.most_common(8), max(result.by_user.values()) if result.by_user else 1, 'var(--blue)')}</div>
  </div>
</section>

<!-- ══ ACTIVITY ══ -->
<section id="activity">
  <div class="sec-title"><span>&#9650;</span> Activity Over Time</div>
  <div class="chart-card" style="margin-bottom:16px"><div class="chart-title">Hourly Event Volume</div><div class="chart-wrap" style="height:220px"><canvas id="chartHour"></canvas></div></div>
  <div class="charts">
    <div class="chart-card"><div class="chart-title">Severity Distribution</div><div class="chart-wrap" style="height:200px"><canvas id="chartSev"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">Events by Node</div><div class="chart-wrap" style="height:200px"><canvas id="chartNode"></canvas></div></div>
    <div class="chart-card"><div class="chart-title">Slow Query Duration Buckets</div><div class="chart-wrap" style="height:200px"><canvas id="chartBuckets"></canvas></div></div>
  </div>
</section>

<!-- ══ SLOWEST QUERIES ══ -->
<section id="slowest">
  <div class="sec-title"><span>&#9201;</span> Slowest Individual Queries <span style="font-size:13px;font-weight:400;color:var(--text2)">— top {min(len(result.slow_queries),100)} by duration · click PID to trace session</span></div>
  <div class="search-row">
    <input type="text" id="slowSearch" placeholder="&#128269; Filter by user, db, node, SQL…" oninput="filterSlow()">
    <select id="slowDbF" onchange="filterSlow()"><option value="">All databases</option>{''.join(f'<option>{_e(k)}</option>' for k in result.databases[:10])}</select>
    <select id="slowUF"  onchange="filterSlow()"><option value="">All users</option>{''.join(f'<option>{_e(k)}</option>' for k in result.users[:10])}</select>
  </div>
  <div class="table-wrap">
    <table id="slowTable">
      <thead><tr><th>#</th><th>Duration</th><th>Timestamp</th><th>User</th><th>Database</th><th>Node</th><th>PID</th><th>Query</th></tr></thead>
      <tbody>{''.join(slow_row(i,sq) for i,sq in enumerate(result.slow_queries[:100]))}</tbody>
    </table>
  </div>
</section>

<!-- ══ GROUPED QUERIES ══ -->
<section id="grouped">
  <div class="sec-title"><span>&#9737;</span> Queries Grouped by Pattern</div>
  <p style="color:var(--text2);font-size:13px;margin-bottom:16px">Literals and bind params replaced with placeholders. Sorted by total cumulative time.</p>
  <div style="font-size:13px;font-weight:600;color:var(--text2);margin-bottom:8px">&#9201; Top 20 by Total Time</div>
  <div class="table-wrap" style="margin-bottom:24px">
    <table><thead><tr><th>#</th><th>Calls</th><th>Total</th><th>Avg</th><th>Min</th><th>Max</th><th>Query Pattern</th></tr></thead>
    <tbody>{''.join(grouped_row(i+1,k,v) for i,(k,v) in enumerate(top_by_time))}</tbody></table>
  </div>
  <div style="font-size:13px;font-weight:600;color:var(--text2);margin-bottom:8px">&#9670; Top 20 by Call Count</div>
  <div class="table-wrap">
    <table><thead><tr><th>#</th><th>Calls</th><th>Total</th><th>Avg</th><th>Min</th><th>Max</th><th>Query Pattern</th></tr></thead>
    <tbody>{''.join(grouped_row(i+1,k,v) for i,(k,v) in enumerate(top_by_count))}</tbody></table>
  </div>
</section>

<!-- ══ ERRORS ══ -->
<section id="errors">
  <div class="sec-title"><span>&#9747;</span> Errors &amp; Fatals</div>
  <div class="metrics" style="grid-template-columns:repeat(auto-fill,minmax(140px,1fr))">
    {''.join(f'<div class="metric"><div class="metric-label">{_e(k)}</div><div class="metric-value mv-red">{v:,}</div></div>' for k,v in sorted(result.by_severity.items()) if k in ('ERROR','FATAL','PANIC'))}
    <div class="metric"><div class="metric-label">Unique Types</div><div class="metric-value mv-amber">{len(result.error_types)}</div></div>
    <div class="metric"><div class="metric-label">Auth Failures</div><div class="metric-value mv-red">{result.conn_failed}</div></div>
  </div>
  <div class="chart-card" style="margin-bottom:16px"><div class="chart-title">Error Type Frequency</div><div class="chart-wrap" style="height:250px"><canvas id="chartErrors"></canvas></div></div>
  <div class="search-row">
    <input type="text" id="errSearch" placeholder="&#128269; Filter errors…" oninput="filterErr()">
    <select id="errSevF" onchange="filterErr()"><option value="">All severities</option><option>ERROR</option><option>FATAL</option><option>PANIC</option></select>
  </div>
  <div class="table-wrap">
    <table id="errTable">
      <thead><tr><th>Severity</th><th>Timestamp</th><th>User@DB</th><th>Node</th><th>PID</th><th>Message</th></tr></thead>
      <tbody>{''.join(err_row(e) for e in all_errors[:200])}</tbody>
    </table>
  </div>
</section>

<!-- ══ CONNECTIONS ══ -->
<section id="connections">
  <div class="sec-title"><span>&#9654;</span> Connection Activity</div>
  <div class="metrics">
    <div class="metric"><div class="metric-label">Received</div><div class="metric-value mv-blue">{result.conn_received:,}</div></div>
    <div class="metric"><div class="metric-label">Authenticated</div><div class="metric-value mv-green">{result.conn_authenticated:,}</div></div>
    <div class="metric"><div class="metric-label">Authorized</div><div class="metric-value mv-green">{result.conn_authorized:,}</div></div>
    <div class="metric"><div class="metric-label">Disconnections</div><div class="metric-value mv-amber">{result.disconnections:,}</div></div>
    <div class="metric"><div class="metric-label">Auth Failures</div><div class="metric-value mv-red">{result.conn_failed:,}</div></div>
  </div>
  <div class="grid2">
    <div class="chart-card"><div class="chart-title">Top Databases</div>{bar_rows(db_items, max(db_vals) if db_vals else 1, 'var(--purple)')}</div>
    <div class="chart-card"><div class="chart-title">Top Users</div>{bar_rows(result.by_user.most_common(8), max(result.by_user.values()) if result.by_user else 1, 'var(--blue)')}</div>
  </div>
</section>

<!-- ══ AUTOVACUUM ══ -->
<section id="autovacuum">
  <div class="sec-title"><span>&#9927;</span> Autovacuum / Auto-analyze</div>
  <div class="metrics"><div class="metric"><div class="metric-label">Total Runs</div><div class="metric-value mv-purple">{len(result.autovacuum_runs):,}</div></div></div>
  <div class="table-wrap"><table>
    <thead><tr><th>Timestamp</th><th>User</th><th>Database</th><th>Node</th><th>Message</th></tr></thead>
    <tbody>{''.join(av_row(a) for a in result.autovacuum_runs[:50])}</tbody>
  </table></div>
</section>

<!-- ══ TEMP FILES ══ -->
<section id="tempfiles">
  <div class="sec-title"><span>&#128196;</span> Temporary Files</div>
  <div class="metrics"><div class="metric"><div class="metric-label">Temp File Events</div><div class="metric-value mv-amber">{len(result.temp_files):,}</div><div class="metric-sub">Spill-to-disk ops</div></div></div>
  {'<div class="table-wrap"><table><thead><tr><th>Timestamp</th><th>User</th><th>Database</th><th>Message</th></tr></thead><tbody>' + ''.join(f'<tr><td class="mono xs">{_e(t["ts"])}</td><td class="mono xs">{_e(t["user"])}</td><td><span class="db-pill">{_e(t["db"][:22])}</span></td><td class="msg">{_e(t["msg"][:300])}</td></tr>' for t in result.temp_files[:50]) + '</tbody></table></div>' if result.temp_files else '<p class="muted">No temporary file events found.</p>'}
</section>

<!-- ══ LOCK WAITS ══ -->
<section id="locks">
  <div class="sec-title"><span>&#128274;</span> Lock Wait Events</div>
  <div class="metrics"><div class="metric"><div class="metric-label">Lock Wait Events</div><div class="metric-value mv-red">{len(result.lock_waits):,}</div></div></div>
  {'<div class="table-wrap"><table><thead><tr><th>Timestamp</th><th>User</th><th>Database</th><th>Message</th></tr></thead><tbody>' + ''.join(f'<tr><td class="mono xs">{_e(t["ts"])}</td><td class="mono xs">{_e(t["user"])}</td><td><span class="db-pill">{_e(t["db"][:22])}</span></td><td class="msg">{_e(t["msg"][:400])}</td></tr>' for t in result.lock_waits[:50]) + '</tbody></table></div>' if result.lock_waits else '<p class="muted">No lock wait events found.</p>'}
</section>

<!-- ══ LOG EXPLORER ══ -->
<section id="explorer">
  <div class="sec-title"><span>&#128269;</span> Log Explorer
    <span style="font-size:13px;font-weight:400;color:var(--text2)">— searches entire file ({result.parsed_entries:,} events) via server API · any PID traceable</span>
  </div>

  <div class="ex-filter-panel">

    <!-- Boolean query row -->
    <div style="margin-bottom:14px">
      <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:6px;flex-wrap:wrap">
        <label class="ex-label" style="margin:0">&#43; Query</label>
        <span style="font-size:11px;color:var(--text3)">supports <code style="color:var(--blue);background:rgba(88,166,255,.1);padding:1px 5px;border-radius:3px">AND</code> <code style="color:var(--green);background:rgba(63,185,80,.1);padding:1px 5px;border-radius:3px">OR</code> <code style="color:var(--red);background:rgba(248,81,73,.1);padding:1px 5px;border-radius:3px">NOT</code> <code style="color:var(--text2);background:rgba(255,255,255,.07);padding:1px 5px;border-radius:3px">(groups)</code> and <code style="color:var(--purple);background:rgba(188,140,255,.1);padding:1px 5px;border-radius:3px">/regex/</code></span>
      </div>
      <input class="ex-input" id="exInclude"
             placeholder="e.g.  ERROR OR FATAL    /data.*/ OR /pgwatch.*/    (ERROR OR FATAL) AND duration    ERROR AND NOT pgwatch"
             oninput="previewQuery()">
      <div id="incPreview" style="margin-top:7px;min-height:22px;display:flex;gap:6px;flex-wrap:wrap;align-items:center"></div>
    </div>

    <!-- Exclude row -->
    <div style="margin-bottom:14px">
      <label class="ex-label">&#8722; Exclude <span style="color:var(--text3);font-weight:400;text-transform:none;letter-spacing:0">— plain terms or /regex/ (space or comma separated, all excluded if ANY matches)</span></label>
      <input class="ex-input" id="exExclude"
             placeholder="e.g.  pgwatch  connection received  /autovacuum/"
             oninput="previewExclude()">
      <div id="excPreview" style="margin-top:7px;min-height:22px;display:flex;gap:6px;flex-wrap:wrap;align-items:center"></div>
    </div>

    <!-- Severity + dropdowns row -->
    <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:flex-end;margin-bottom:14px">
      <div>
        <label class="ex-label">Severity</label>
        <div style="display:flex;gap:6px;flex-wrap:wrap" id="exSevBoxes"></div>
      </div>
      <div>
        <label class="ex-label">Database</label>
        <select class="ex-select" id="exDb"><option value="">All</option></select>
      </div>
      <div>
        <label class="ex-label">User</label>
        <select class="ex-select" id="exUser"><option value="">All</option></select>
      </div>
      <div>
        <label class="ex-label">Node</label>
        <select class="ex-select" id="exNode"><option value="">All</option></select>
      </div>
    </div>

    <!-- PID tracer -->
    <div class="pid-tracer-box">
      <label class="ex-label" style="margin-bottom:8px">&#128203; PID Session Tracer — show every message for a PID in chronological order</label>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <input class="ex-input" id="exPid" placeholder="Enter PID  e.g. 17319" style="max-width:200px;font-family:monospace"
               onkeydown="if(event.key==='Enter') tracePid()">
        <button class="ex-btn ex-btn-green" onclick="tracePid()">Trace PID ▶</button>
        <button class="ex-btn ex-btn-ghost" onclick="clearPidTrace()">Clear</button>
        <span style="font-size:12px;color:var(--text3)" id="pidAvailHint">Any PID from the log can be traced — scans the full file on demand</span>
      </div>
      <div id="pidInfoCard" style="display:none;margin-top:12px"></div>
    </div>

    <!-- Action row -->
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <button class="ex-btn ex-btn-primary" onclick="applyExplorer()">Apply Filters</button>
      <button class="ex-btn ex-btn-ghost"   onclick="clearExplorer()">Clear All</button>
      <span class="ex-count" id="exCount"></span>
    </div>
  </div>

  <div id="exResults">
    <p class="muted">Set filters above and click <strong>Apply Filters</strong>, or enter a PID and click <strong>Trace PID</strong>.</p>
  </div>
</section>

</div><!-- .main -->

<footer>Generated by PG Log Analyzer &bull; {_e(result.filename)} &bull; {result.parsed_entries:,} events parsed</footer>
<button class="scroll-top" onclick="window.scrollTo({{top:0,behavior:'smooth'}})">&#8679;</button>

<script>
/* ── chart data ── */
const H_LABELS={_j(h_labels)};
const H_VALS={_j(h_vals)};
const SEV_LABELS={_j(sev_labels)};
const SEV_VALS={_j(sev_vals)};
const NODE_LABELS={_j(node_labels)};
const NODE_VALS={_j(node_vals)};
const B_VALS={_j(b_vals)};
const ERR_LABELS={_j(err_labels)};
const ERR_VALS={_j(err_vals)};
const BUCKET_ORDER={_j(bucket_order)};

/* ── explorer dropdown data (databases, users, nodes from parse) ── */
const EX_DBS={ex_databases_json};
const EX_USERS={ex_users_json};
const EX_NODES={ex_nodes_json};

const SEV_COLORS={{
  LOG:'rgba(88,166,255,.7)',DETAIL:'rgba(72,79,88,.7)',FATAL:'rgba(248,81,73,.9)',
  STATEMENT:'rgba(188,140,255,.7)',ERROR:'rgba(248,81,73,.8)',HINT:'rgba(210,153,34,.7)',
  WARNING:'rgba(210,153,34,.8)',NOTICE:'rgba(63,185,80,.6)'
}};
const SEV_TEXT={{LOG:'#58a6ff',ERROR:'#f85149',FATAL:'#ffa198',WARNING:'#d29922',
  PANIC:'#f85149',DETAIL:'#484f58',STATEMENT:'#bc8cff',HINT:'#d29922',NOTICE:'#3fb950'}};
const SEV_ORDER=['LOG','ERROR','FATAL','WARNING','PANIC','DETAIL','STATEMENT','HINT','NOTICE'];

/* ══ Charts ══ */
/* ── Vanilla canvas charts — zero dependencies ─────────────────────────────── */
function mkChart(id,type,labels,datasets,opts={{}}) {{
  const el=document.getElementById(id);
  if(!el) return;
  const wrap=el.parentElement||el.parentNode;
  // getBoundingClientRect() is reliable after layout; offsetWidth can be 0 if parent
  // uses grid/flex before paint. Fall back through multiple strategies.
  let W=0,H=0;
  if(wrap){{
    const r=wrap.getBoundingClientRect();
    W=Math.floor(r.width)||wrap.offsetWidth||wrap.clientWidth;
    H=Math.floor(r.height)||wrap.offsetHeight||wrap.clientHeight||
      parseInt(wrap.style.height||'0')||parseInt(getComputedStyle(wrap).height||'0');
  }}
  W=W>0?W:600; H=H>0?H:200;
  el.style.display='block';
  el.width=W; el.height=H;
  const ctx=el.getContext('2d');
  if(!ctx) return;
  // Dark background so chart is always visible regardless of page bg
  ctx.fillStyle='#161b22';
  ctx.fillRect(0,0,W,H);
  const ds=datasets[0]||{{}};
  const vals=ds.data||[];
  const isHoriz=ds.indexAxis==='y';
  try{{
    if(type==='doughnut') _drawDonut(ctx,W,H,labels,vals,ds.backgroundColor,opts);
    else if(isHoriz)      _drawHBar(ctx,W,H,labels,vals,ds.backgroundColor);
    else                  _drawVBar(ctx,W,H,labels,vals,ds.backgroundColor);
  }}catch(e){{console.error('chart error:',id,e);}}
}}
function _drawVBar(ctx,W,H,labels,vals,colors) {{
  const PL=52,PR=12,PT=12,PB=52;
  const cW=W-PL-PR,cH=H-PT-PB;
  const max=Math.max(...vals,1);
  const n=vals.length,gapW=cW/n;
  const barW=Math.max(gapW*0.75,1);
  ctx.font='10px sans-serif'; ctx.textAlign='right';
  for(let i=0;i<=4;i++){{
    const y=PT+cH*i/4;
    const v=Math.round(max*(4-i)/4);
    ctx.strokeStyle='rgba(48,54,61,.6)'; ctx.lineWidth=0.5;
    ctx.beginPath(); ctx.moveTo(PL,y); ctx.lineTo(W-PR,y); ctx.stroke();
    ctx.fillStyle='#484f58';
    ctx.fillText(v>9999?(v/1000).toFixed(0)+'k':v,PL-4,y+3);
  }}
  vals.forEach((v,i)=>{{
    const x=PL+i*gapW+(gapW-barW)/2;
    const bh=(v/max)*cH;
    ctx.fillStyle=Array.isArray(colors)?colors[i]||colors[0]:colors||'rgba(88,166,255,.7)';
    ctx.fillRect(x,PT+cH-bh,barW,Math.max(bh,0));
  }});
  const skip=Math.ceil(n/20);
  ctx.fillStyle='#484f58'; ctx.font='9px sans-serif'; ctx.textAlign='center';
  labels.forEach((lbl,i)=>{{
    if(i%skip!==0) return;
    const x=PL+i*gapW+gapW/2;
    ctx.save(); ctx.translate(x,H-PB+10);
    if(n>8) ctx.rotate(-0.6);
    ctx.fillText(String(lbl).slice(0,10),0,0);
    ctx.restore();
  }});
}}
function _drawHBar(ctx,W,H,labels,vals,bgColor) {{
  const n=vals.length||1;
  const max=Math.max(...vals,1);
  const PR=52,PT=4,PB=4;
  ctx.font='11px sans-serif';
  const lblW=Math.min(W*0.48,labels.reduce((m,l)=>Math.max(m,ctx.measureText(String(l)).width),0)+12);
  const cW=W-lblW-PR;
  const rowH=(H-PT-PB)/n,barH=rowH*0.55;
  vals.forEach((v,i)=>{{
    const y=PT+i*rowH;
    const bw=(v/max)*cW;
    ctx.fillStyle='#8b949e'; ctx.textAlign='right'; ctx.font='11px sans-serif';
    const lbl=String(labels[i]);
    ctx.fillText(lbl.length>42?lbl.slice(0,42)+'…':lbl,lblW-4,y+rowH/2+4);
    ctx.fillStyle=Array.isArray(bgColor)?bgColor[i]||bgColor[0]:bgColor||'rgba(248,81,73,.7)';
    ctx.fillRect(lblW,y+(rowH-barH)/2,Math.max(bw,1),barH);
    ctx.fillStyle='#8b949e'; ctx.textAlign='left'; ctx.font='10px sans-serif';
    ctx.fillText(v.toLocaleString(),lblW+bw+4,y+rowH/2+3);
  }});
}}
function _drawDonut(ctx,W,H,labels,vals,colors,opts) {{
  const total=vals.reduce((s,v)=>s+v,0)||1;
  const legRight=opts&&opts.plugins&&opts.plugins.legend&&opts.plugins.legend.display&&opts.plugins.legend.position==='right';
  const chartW=legRight?W*0.52:W;
  const cx=chartW/2,cy=H/2;
  const r=Math.min(cx,cy)-10,inner=r*0.58;
  let angle=-Math.PI/2;
  vals.forEach((v,i)=>{{
    const slice=(v/total)*Math.PI*2;
    ctx.beginPath(); ctx.moveTo(cx,cy);
    ctx.arc(cx,cy,r,angle,angle+slice); ctx.closePath();
    ctx.fillStyle=Array.isArray(colors)?colors[i]||'#444':'#58a6ff';
    ctx.fill(); angle+=slice;
  }});
  ctx.beginPath(); ctx.arc(cx,cy,inner,0,Math.PI*2);
  ctx.fillStyle='#161b22'; ctx.fill();
  if(legRight){{
    const lx=chartW+8;
    ctx.font='11px sans-serif'; ctx.textAlign='left';
    labels.forEach((lbl,i)=>{{
      const y=16+i*19;
      if(y+10>H) return;
      ctx.fillStyle=Array.isArray(colors)?colors[i]||'#444':'#58a6ff';
      ctx.fillRect(lx,y-8,11,11);
      ctx.fillStyle='#8b949e';
      ctx.fillText(String(lbl).slice(0,14),lx+15,y+2);
    }});
  }}
}}

function _renderAllCharts() {{
  mkChart('chartHour','bar',H_LABELS,[{{data:H_VALS,backgroundColor:H_VALS.map(v=>v>40000?'rgba(248,81,73,.7)':'rgba(88,166,255,.5)')}}]);
  mkChart('chartSev','doughnut',SEV_LABELS,[{{data:SEV_VALS,backgroundColor:SEV_LABELS.map(l=>SEV_COLORS[l]||'#444')}}],
    {{plugins:{{legend:{{display:true,position:'right'}}}}}});
  mkChart('chartNode','bar',NODE_LABELS,[{{data:NODE_VALS,backgroundColor:['rgba(88,166,255,.7)','rgba(63,185,80,.7)','rgba(188,140,255,.7)','rgba(210,153,34,.7)']}}]);
  mkChart('chartBuckets','bar',BUCKET_ORDER,[{{data:B_VALS,backgroundColor:['rgba(63,185,80,.7)','rgba(210,153,34,.5)','rgba(210,153,34,.7)','rgba(248,81,73,.6)','rgba(248,81,73,.9)']}}]);
  mkChart('chartErrors','bar',ERR_LABELS,[{{data:ERR_VALS,backgroundColor:'rgba(248,81,73,.7)',indexAxis:'y'}}]);
}}
// Double requestAnimationFrame guarantees layout is complete before measuring
window.addEventListener('load',()=>{{
  requestAnimationFrame(()=>requestAnimationFrame(_renderAllCharts));
}});
// Also re-render after 500ms in case rAF fires before layout on some browsers
window.addEventListener('load',()=>setTimeout(_renderAllCharts,500));

/* ══ Existing table filters ══ */
function toggleSQL(id){{
  const el=document.getElementById(id);
  if(!el) return;
  const open=el.style.display==='none'||el.style.display==='';
  el.style.display=open?'block':'none';
  const btn=el.previousElementSibling;
  if(btn&&btn.tagName==='BUTTON') btn.textContent=open?'Hide SQL ▴':'Show SQL ▾';
}}
function filterSlow(){{
  const qEl=document.getElementById('slowSearch');
  const dbEl=document.getElementById('slowDbF');
  const uEl=document.getElementById('slowUF');
  if(!qEl) return;
  const q=qEl.value.toLowerCase();
  const db=dbEl?dbEl.value.toLowerCase():'';
  const u=uEl?uEl.value.toLowerCase():'';
  document.querySelectorAll('#slowTable tbody tr').forEach(r=>{{
    // Include SQL divs in search (they may be hidden but still contain text)
    const allText=(r.textContent+' '+(r.querySelector('pre')||{{}}).textContent).toLowerCase();
    const dbCell=r.querySelector('.db-pill');
    const dbMatch=!db||allText.includes(db)||(dbCell&&dbCell.title.toLowerCase().includes(db));
    const uCell=r.querySelector('td:nth-child(4)');
    const uMatch=!u||allText.includes(u);
    const qMatch=!q||allText.includes(q);
    r.style.display=(qMatch&&dbMatch&&uMatch)?'':'none';
  }});
}}
function filterErr(){{
  const qEl=document.getElementById('errSearch');
  const sEl=document.getElementById('errSevF');
  if(!qEl) return;
  const q=qEl.value.toLowerCase();
  const s=sEl?sEl.value:'';
  document.querySelectorAll('#errTable tbody tr').forEach(r=>{{
    const t=r.textContent.toLowerCase();
    // data-sev is set on <tr data-sev="ERROR"> in err_row()
    const sev=(r.dataset&&r.dataset.sev)||r.getAttribute('data-sev')||'';
    const qMatch=!q||t.includes(q);
    const sMatch=!s||sev===s||t.toLowerCase().startsWith(s.toLowerCase());
    r.style.display=(qMatch&&sMatch)?'':'none';
  }});
}}

/* ══ PID click-through from tables ══ */
document.addEventListener('click',e=>{{
  const cell=e.target.closest('.pid-cell');
  if(!cell) return;
  const pid=cell.dataset.pid;
  if(!pid) return;
  document.getElementById('exPid').value=pid;
  document.getElementById('explorer').scrollIntoView({{behavior:'smooth'}});
  setTimeout(()=>tracePid(),400);
}});

/* ══ LOG EXPLORER ══ */
(function initExplorer(){{
  // Severity checkboxes
  const box=document.getElementById('exSevBoxes');
  SEV_ORDER.forEach(s=>{{
    const lbl=document.createElement('label');
    lbl.style.cssText='display:flex;align-items:center;gap:4px;font-size:12px;color:var(--text2);cursor:pointer;white-space:nowrap';
    lbl.innerHTML=`<input type="checkbox" value="${{s}}" checked style="accent-color:${{SEV_TEXT[s]||'var(--blue)'}};cursor:pointer"> ${{s}}`;
    box.appendChild(lbl);
  }});
  // Dropdowns
  const add=(id,arr)=>arr.forEach(v=>{{const o=document.createElement('option');o.value=o.textContent=v;document.getElementById(id).appendChild(o);}});
  add('exDb',EX_DBS); add('exUser',EX_USERS); add('exNode',EX_NODES);
  // PID hint — server-side, any PID is traceable
  document.getElementById('pidAvailHint').textContent='Any PID from the log can be traced — scans the full file on demand';
}})();

const JOB_ID = "{job_id}";

// ═══════════════════════════════════════════════════════════════════════════
// BOOLEAN QUERY ENGINE
// Supports: AND  OR  NOT  (groups)  /regex/  implicit AND between adjacent terms
// Examples: ERROR OR FATAL
//           /data.+/ OR /pgwatch.+/   (use .+ not .* to avoid */closing comments)
//           (ERROR OR FATAL) AND NOT pgwatch
//           ERROR OR FATAL AND duration AND NOT pgwatch
// ═══════════════════════════════════════════════════════════════════════════

__INJECT_ESCFNS__

const PAGE=100;
let exData=[];
let exPage=0;
let exLeaves=[];   // leaf terms for highlighting

let _searchController=null;

async function applyExplorer(){{
  document.getElementById('pidInfoCard').style.display='none';
  if(!JOB_ID){{
    document.getElementById('exCount').innerHTML='<span style="color:var(--amber)">&#9888; Log Explorer requires the Flask server. Open this report via localhost:5050.</span>';
    return;
  }}

  const qRaw =document.getElementById('exInclude').value.trim();
  const excRaw=document.getElementById('exExclude').value.trim();
  const sevs  =Array.from(document.querySelectorAll('#exSevBoxes input:checked')).map(x=>x.value);
  const db    =document.getElementById('exDb').value;
  const user  =document.getElementById('exUser').value;
  const node  =document.getElementById('exNode').value;

  // Parse AST just for highlighting
  const qAst=qRaw?parse(lex(qRaw)):null;
  exLeaves=qAst?collectLeaves(qAst):[];

  // Build URL
  const params=new URLSearchParams();
  if(qRaw)  params.set('q',qRaw);
  if(excRaw) params.set('exc',excRaw);
  if(sevs.length<9) params.set('sev',sevs.join(','));
  if(db)   params.set('db',db);
  if(user) params.set('user',user);
  if(node) params.set('node',node);
  params.set('limit','500');

  // Cancel previous request
  if(_searchController) _searchController.abort();
  _searchController=new AbortController();

  document.getElementById('exCount').innerHTML=
    '<span style="color:var(--text3)">&#9203; Searching entire file…</span>';
  document.getElementById('exResults').innerHTML=
    '<p class="muted" style="padding:20px 0">&#9203; Scanning log file on server…</p>';

  try{{
    const resp=await fetch(`/search/${{JOB_ID}}?${{params}}`,{{signal:_searchController.signal}});
    if(!resp.ok){{
      const err=await resp.json().catch(()=>({{error:resp.statusText}}));
      throw new Error(err.error||resp.statusText);
    }}
    const data=await resp.json();

    exData=data.results; exPage=0;

    let qlabel='';
    if(qAst) qlabel=` &nbsp;·&nbsp; ${{printAST(qAst)}}`;
    const limited=data.limited?` <span style="color:var(--amber)">(showing first 500 — refine your query)</span>`:'';
    document.getElementById('exCount').innerHTML=
      `<strong>${{data.total_matched.toLocaleString()}}</strong> match${{data.total_matched!==1?'es':''}} in `+
      `${{data.total_scanned.toLocaleString()}} scanned${{qlabel}}${{limited}}`;
    renderExTable();
  }}catch(e){{
    if(e.name==='AbortError') return;
    document.getElementById('exCount').innerHTML=
      `<span style="color:var(--red)">&#9747; Error: ${{escH(e.message)}}</span>`;
    document.getElementById('exResults').innerHTML='';
  }}
}}

function renderExTable(){{
  if(!exData.length){{
    document.getElementById('exResults').innerHTML='<p class="muted">No matching log entries found.</p>';
    return;
  }}
  const start=exPage*PAGE;
  const page =exData.slice(start,start+PAGE);
  const rows =page.map(e=>{{
    const sc=SEV_TEXT[e.severity]||'var(--text2)';
    const nd=e.node?e.node.split('.').pop():'?';
    // All PIDs are traceable via server API
    const pidCell=e.pid
      ?`<span class="pid-link" onclick="tracePidDirect('${{escH(e.pid)}}')" title="Click to trace full session">${{escH(e.pid)}}</span>`
      :'—';
    const msgHtml=e.sql&&e.sql.trim()
      ?`${{highlight(e.msg.slice(0,300),exLeaves)}}<div style="margin-top:6px"><button class="toggle-btn" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none';this.textContent=this.nextElementSibling.style.display==='block'?'Hide SQL ▴':'Show SQL ▾'">Show SQL ▾</button><div style="display:none;margin-top:6px"><pre class="sql-block">${{escH(e.sql.slice(0,2000))}}</pre></div></div>`
      :highlight(e.msg.slice(0,400),exLeaves);
    return `<tr>
      <td class="mono xs" style="white-space:nowrap">${{escH(e.ts)}}</td>
      <td style="white-space:nowrap"><span style="font-family:monospace;font-size:11px;font-weight:700;color:${{sc}}">${{escH(e.severity)}}</span></td>
      <td style="font-family:monospace;font-size:12px">${{pidCell}}</td>
      <td class="mono xs">${{escH(e.user)}}</td>
      <td><span class="db-pill" title="${{escH(e.db)}}">${{escH(e.db.slice(0,22))}}</span></td>
      <td><span class="node-pill">.${{escH(nd)}}</span></td>
      <td class="msg">${{msgHtml}}</td>
    </tr>`;
  }}).join('');

  const total=exData.length, pages=Math.ceil(total/PAGE);
  const pager=pages>1?`<div class="pager">
    <span>${{start+1}}–${{Math.min(start+PAGE,total)}} of ${{total.toLocaleString()}}</span>
    ${{exPage>0?'<button class="toggle-btn" onclick="exPage--;renderExTable()">&#8592; Prev</button>':''}}
    ${{exPage<pages-1?'<button class="toggle-btn" onclick="exPage++;renderExTable()">Next &#8594;</button>':''}}
  </div>`:'';

  document.getElementById('exResults').innerHTML=`
    <div class="table-wrap"><table>
      <thead><tr><th>Timestamp</th><th>Severity</th><th title="Green PIDs are fully traceable — click to trace">PID</th><th>User</th><th>Database</th><th>Node</th><th>Message</th></tr></thead>
      <tbody>${{rows}}</tbody>
    </table></div>${{pager}}`;
}}

function tracePid(){{
  const pid=document.getElementById('exPid').value.trim();
  if(!pid){{alert('Enter a PID number first.');return;}}
  tracePidDirect(pid);
}}

function tracePidDirect(pid){{
  document.getElementById('exPid').value=pid;
  if(!JOB_ID){{
    document.getElementById('exCount').textContent='';
    document.getElementById('exResults').innerHTML='<div style="color:var(--amber);padding:16px">&#9888; PID trace requires the Flask server (localhost:5050).</div>';
    return;
  }}
  document.getElementById('exCount').innerHTML='<span style="color:var(--text3)">&#9203; Scanning file for PID '+escH(pid)+'…</span>';
  document.getElementById('exResults').innerHTML='<p class="muted" style="padding:20px 0">&#9203; Tracing PID on server…</p>';
  fetch(`/pid/${{JOB_ID}}/${{encodeURIComponent(pid)}}`)
    .then(r=>r.ok?r.json():r.json().then(e=>Promise.reject(new Error(e.error||r.statusText))))
    .then(data=>_renderPidTrace(pid, data.entries))
    .catch(e=>{{
      document.getElementById('exCount').textContent='';
      document.getElementById('exResults').innerHTML=`<div style="background:rgba(248,81,73,.1);border:1px solid rgba(248,81,73,.3);border-radius:8px;padding:16px;color:#ffa198;font-size:13px">&#9747; ${{escH(e.message)}}</div>`;
    }});
}}

function _renderPidTrace(pid, entries){{
  const dummy_entries=entries;  // alias for compatibility
  if(!entries||!entries.length){{
    document.getElementById('exCount').textContent='';
    document.getElementById('exResults').innerHTML=`
      <div style="background:rgba(248,81,73,.1);border:1px solid rgba(248,81,73,.3);border-radius:8px;padding:16px;color:#ffa198;font-size:13px">
        No log entries found for PID <strong>${{escH(pid)}}</strong>.<br>
        The PID may not exist in this log file, or the log file is no longer available on the server.
      </div>`;
    return;
  }}

  // Session summary card
  const first=entries[0], last=entries[entries.length-1];
  const sevCounts={{}};
  entries.forEach(e=>{{sevCounts[e.severity]=(sevCounts[e.severity]||0)+1;}});
  const sevSummary=Object.entries(sevCounts).sort((a,b)=>b[1]-a[1])
    .map(([s,c])=>`<span style="font-family:monospace;font-size:11px;font-weight:700;color:${{SEV_TEXT[s]||'var(--text2)'}}">${{s}}</span>&thinsp;<span style="color:var(--text2)">${{c}}</span>`)
    .join(' &nbsp;');

  const card=document.getElementById('pidInfoCard');
  card.className='pid-info-card';
  card.style.display='block';
  card.innerHTML=`
    <div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:10px">
      <div><div class="ex-label">PID</div><div style="font-family:monospace;font-size:20px;font-weight:700;color:var(--green)">${{escH(pid)}}</div></div>
      <div><div class="ex-label">User</div><div style="font-size:14px">${{escH(first.user)}}</div></div>
      <div><div class="ex-label">Database</div><span class="db-pill">${{escH(first.db)}}</span></div>
      <div><div class="ex-label">Node</div><span class="node-pill">.${{escH(first.node.split('.').pop())}}</span></div>
      <div><div class="ex-label">First seen</div><div style="font-family:monospace;font-size:12px;color:var(--text2)">${{escH(first.ts)}}</div></div>
      <div><div class="ex-label">Last seen</div><div style="font-family:monospace;font-size:12px;color:var(--text2)">${{escH(last.ts)}}</div></div>
      <div><div class="ex-label">Messages</div><div style="font-size:16px;font-weight:700">${{entries.length}}${{entries.length>=200?' <span style="font-size:11px;color:var(--text3)">(capped at 200)</span>':''}}</div></div>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      <span class="ex-label" style="margin:0">Severity breakdown:</span> ${{sevSummary}}
    </div>`;

  // Timeline rows
  const trows=entries.map((e,i)=>{{
    const sc=SEV_TEXT[e.severity]||'var(--text2)';
    const isErr=['ERROR','FATAL','PANIC'].includes(e.severity);
    const bg=isErr?'background:rgba(248,81,73,.04)':'';
    const hasSql=e.sql&&e.sql.trim();
    const msgHtml=hasSql
      ?`${{escH(e.msg.slice(0,300))}}<div style="margin-top:6px"><button class="toggle-btn" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none';this.textContent=this.nextElementSibling.style.display==='block'?'Hide SQL ▴':'Show SQL ▾'">Show SQL ▾</button><div style="display:none;margin-top:6px"><pre class="sql-block">${{escH((e.sql||'').slice(0,2000))}}</pre></div></div>`
      :escH(e.msg.slice(0,500));
    return `<tr style="${{bg}}">
      <td class="num xs" style="color:var(--text3)">${{i+1}}</td>
      <td class="mono xs" style="white-space:nowrap">${{escH(e.ts)}}</td>
      <td style="white-space:nowrap"><span style="font-family:monospace;font-size:11px;font-weight:700;color:${{sc}}">${{escH(e.severity)}}</span></td>
      <td class="msg">${{msgHtml}}</td>
    </tr>`;
  }}).join('');

  document.getElementById('exCount').textContent=`PID ${{pid}} — ${{entries.length}} messages in chronological order`;
  document.getElementById('exResults').innerHTML=`
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>Timestamp</th><th>Severity</th><th>Message</th></tr></thead>
      <tbody>${{trows}}</tbody>
    </table></div>`;

  document.getElementById('explorer').scrollIntoView({{behavior:'smooth',block:'start'}});
}}

function clearPidTrace(){{
  document.getElementById('exPid').value='';
  document.getElementById('pidInfoCard').style.display='none';
  document.getElementById('exCount').textContent='';
  document.getElementById('exResults').innerHTML='<p class="muted">Set filters above and click <strong>Apply Filters</strong>, or enter a PID and click <strong>Trace PID</strong>.</p>';
}}

function clearExplorer(){{
  ['exInclude','exExclude','exPid'].forEach(id=>document.getElementById(id).value='');
  ['exDb','exUser','exNode'].forEach(id=>document.getElementById(id).value='');
  ['incPreview','excPreview'].forEach(id=>document.getElementById(id).innerHTML='');
  document.querySelectorAll('#exSevBoxes input').forEach(x=>x.checked=true);
  clearPidTrace();
}}

/* ══ Scroll-spy ══ */
const sections=document.querySelectorAll('section[id]');
const navLinks=document.querySelectorAll('.toc a');
window.addEventListener('scroll',()=>{{
  let cur='';
  sections.forEach(s=>{{if(window.scrollY>=s.offsetTop-100) cur=s.id;}});
  navLinks.forEach(a=>a.classList.toggle('active',a.getAttribute('href')==='#'+cur));
}},{{passive:true}});
</script>
</body>
</html>"""

    # Inject JS that cannot live inside f-string (has regex with backslashes)
    _js_inject = r'''
function escH(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

function _escRegex(s){
  return s.replace(/[\\^$.|?*+()[\]{}]/g,'\\$&');
}

// ── Lexer: tokenise a boolean query string ─────────────────────────────────
function lex(raw){
  const toks=[];
  let s=raw.trim();
  while(s){
    s=s.trimStart();
    if(!s) break;
    // Regex literal /pattern/flags
    if(s[0]==='/'){
      let end=-1;
      for(let i=1;i<s.length;i++) if(s[i]==='/'&&s.charCodeAt(i-1)!==92){end=i;break;}
      if(end===-1){toks.push({t:'TERM',term:{type:'txt',v:s.slice(1).toLowerCase(),raw:s}});break;}
      const pat=s.slice(1,end);
      const fm=s.slice(end+1).match(/^([gimsuy]*)/);
      const fl=fm?fm[1]:'';
      try{toks.push({t:'TERM',term:{type:'re',re:new RegExp(pat,fl||'i'),raw:'/'+pat+'/'+fl}});}
      catch(e){toks.push({t:'TERM',term:{type:'err',raw:'/'+pat+'/',msg:e.message}});}
      s=s.slice(end+1+fl.length).replace(/^[,\s]*/,'');
      continue;
    }
    // Keywords
    const kw=s.match(/^(OR|AND|NOT|or|and|not)(?=[\s(),/]|$)/);
    if(kw){toks.push({t:kw[1].toUpperCase()});s=s.slice(kw[0].length).replace(/^[,\s]*/,'');continue;}
    // Parens
    if(s[0]==='('||s[0]===')'){toks.push({t:s[0]});s=s.slice(1).replace(/^[,\s]*/,'');continue;}
    // Quoted string
    if(s[0]==='"'||s[0]==="'"){
      const q=s[0],end=s.indexOf(q,1);
      const v=end===-1?s.slice(1):s.slice(1,end);
      toks.push({t:'TERM',term:{type:'txt',v:v.toLowerCase(),raw:q+v+q}});
      s=end===-1?'':s.slice(end+1).replace(/^[,\s]*/,'');
      continue;
    }
    // Plain word
    const wm=s.match(/^([^\s,/()"']+)/);
    if(wm){
      const w=wm[1].trim().replace(/,$/,'');
      if(w) toks.push({t:'TERM',term:{type:'txt',v:w.toLowerCase(),raw:w}});
      s=s.slice(wm[0].length).replace(/^[,\s]*/,'');
    }else{s=s.slice(1);}
  }
  return toks;
}

// ── Recursive-descent parser ─────────────────────────────────────────────────
function parse(toks){
  let pos=0;
  function peek(){return pos<toks.length?toks[pos]:null;}
  function consume(){return toks[pos++];}
  function parseExpr(){return parseOr();}
  function parseOr(){
    let left=parseAnd();
    while(peek()&&peek().t==='OR'){consume();const r=parseAnd();left={op:'OR',l:left,r};}
    return left;
  }
  function parseAnd(){
    let left=parseNot();
    while(peek()){
      const p=peek();
      if(p.t==='AND'){consume();const r=parseNot();left={op:'AND',l:left,r};continue;}
      if(p.t==='TERM'||p.t==='NOT'||p.t==='('){const r=parseNot();left={op:'AND',l:left,r};continue;}
      break;
    }
    return left;
  }
  function parseNot(){
    if(peek()&&peek().t==='NOT'){consume();const o=parseNot();return {op:'NOT',o};}
    return parsePrimary();
  }
  function parsePrimary(){
    const p=peek();
    if(!p) return null;
    if(p.t==='('){
      consume();const e=parseExpr();
      if(peek()&&peek().t===')') consume();
      return {op:'GROUP',e};
    }
    if(p.t==='TERM'){consume();return {op:'TERM',term:p.term};}
    return null;
  }
  return parseExpr();
}

// ── Evaluate AST ──────────────────────────────────────────────────────────────
function evalAST(node,txt){
  if(!node) return true;
  if(node.op==='TERM') return matchLeaf(txt,node.term);
  if(node.op==='NOT')  return !evalAST(node.o,txt);
  if(node.op==='AND')  return evalAST(node.l,txt)&&evalAST(node.r,txt);
  if(node.op==='OR')   return evalAST(node.l,txt)||evalAST(node.r,txt);
  if(node.op==='GROUP')return evalAST(node.e,txt);
  return false;
}

function matchLeaf(txt,term){
  if(!term||term.type==='err') return false;
  if(term.type==='txt') return txt.includes(term.v);
  if(term.type==='re')  return term.re.test(txt);
  return false;
}

function collectLeaves(node,acc){
  acc=acc||[];
  if(!node) return acc;
  if(node.op==='TERM'&&node.term) acc.push(node.term);
  if(node.op==='NOT')  collectLeaves(node.o,acc);
  if(node.op==='AND'||node.op==='OR'){collectLeaves(node.l,acc);collectLeaves(node.r,acc);}
  if(node.op==='GROUP')collectLeaves(node.e,acc);
  return acc;
}

// ── Exclude terms parser (simple OR list) ─────────────────────────────────────
function parseExclude(raw){
  if(!raw.trim()) return [];
  const terms=[];
  let s=raw.trim();
  while(s){
    s=s.trimStart();if(!s) break;
    if(s[0]==='/'){
      let end=-1;
      for(let i=1;i<s.length;i++) if(s[i]==='/'&&s.charCodeAt(i-1)!==92){end=i;break;}
      if(end===-1){terms.push({type:'txt',v:s.slice(1).toLowerCase(),raw:s});break;}
      const pat=s.slice(1,end);
      const fm=s.slice(end+1).match(/^([gimsuy]*)/);const fl=fm?fm[1]:'';
      try{terms.push({type:'re',re:new RegExp(pat,fl||'i'),raw:'/'+pat+'/'});}
      catch(e){terms.push({type:'err',raw:'/'+pat+'/',msg:e.message});}
      s=s.slice(end+1+fl.length).replace(/^[,\s]*/,'');continue;
    }
    const m=s.match(/^([^,/]+)/);
    if(!m){s=s.slice(1);continue;}
    m[1].split(/\s+/).map(t=>t.replace(/,/g,'').trim()).filter(Boolean)
        .forEach(t=>terms.push({type:'txt',v:t.toLowerCase(),raw:t}));
    s=s.slice(m[0].length).replace(/^[,\s]*/,'');
  }
  return terms;
}

// ── AST pretty-print as colour-coded HTML badges ──────────────────────────────
function termBadge(t){
  if(!t) return '';
  if(t.type==='err') return '<span class="qbadge qbadge-err" title="'+escH(t.msg||'')+'">&#9747; '+escH(t.raw)+'</span>';
  if(t.type==='re')  return '<span class="qbadge qbadge-re">/re/ '+escH(t.raw)+'</span>';
  return '<span class="qbadge qbadge-txt">'+escH(t.raw||t.v)+'</span>';
}

function printAST(node){
  if(!node) return '';
  if(node.op==='TERM')  return termBadge(node.term);
  if(node.op==='NOT')   return '<span class="qop qop-not">NOT</span> '+printAST(node.o);
  if(node.op==='AND')   return printAST(node.l)+' <span class="qop qop-and">AND</span> '+printAST(node.r);
  if(node.op==='OR')    return printAST(node.l)+' <span class="qop qop-or">OR</span> '+printAST(node.r);
  if(node.op==='GROUP') return '<span class="qop-paren">(</span>'+printAST(node.e)+'<span class="qop-paren">)</span>';
  return '';
}

// ── Live query preview ─────────────────────────────────────────────────────────
let _qAst=null;
let _qExc=[];

function previewQuery(){
  const raw=document.getElementById('exInclude').value;
  const el=document.getElementById('incPreview');
  if(!el) return;
  if(!raw.trim()){el.innerHTML='';_qAst=null;return;}
  const ast=parse(lex(raw));
  _qAst=ast;
  const hasErr=collectLeaves(ast).some(t=>t.type==='err');
  el.innerHTML='<span style="font-size:11px;color:var(--text3)">Parsed:</span> '
    +printAST(ast)
    +(hasErr?' <span style="font-size:11px;color:#ffa198"> — fix regex errors</span>':'');
}

function previewExclude(){
  const raw=document.getElementById('exExclude').value;
  const el=document.getElementById('excPreview');
  if(!el) return;
  const terms=parseExclude(raw);
  _qExc=terms;
  if(!terms.length){el.innerHTML='';return;}
  el.innerHTML='<span style="font-size:11px;color:var(--text3)">Exclude any of:</span> '
    +terms.map(t=>termBadge(t)).join(' ');
}

function highlight(txt,leaves){
  let r=escH(txt);
  leaves.forEach(t=>{
    if(!t||t.type==='err') return;
    const p=t.type==='re'?t.re.source:_escRegex(t.v);
    try{r=r.replace(new RegExp('('+p+')','gi'),'<mark class="hit">$1</mark>');}catch(e){}
  });
  return r;
}
'''
    report = report.replace('__INJECT_ESCFNS__', _js_inject)

    with open(output_path, 'w', encoding='utf-8') as fh:
        fh.write(report)
