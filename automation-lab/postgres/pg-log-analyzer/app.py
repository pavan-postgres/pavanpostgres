"""
PG Log Analyzer — Flask Web Application
Run:  python3 app.py
Then open:  http://localhost:5050
"""

import os
import time
import uuid
import threading
from pathlib import Path

from flask import (Flask, request, render_template_string,
                   redirect, url_for, send_file, jsonify)

import parser as log_parser
import report as log_report

# ── Config ────────────────────────────────────────────────────────────────────
UPLOAD_DIR  = Path('/tmp/pg_analyzer/uploads')
REPORT_DIR  = Path('/tmp/pg_analyzer/reports')
MAX_MB      = 2048          # 2 GB max upload
ALLOWED_EXT = {'.log', '.csv', '.txt', '.gz'}

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_MB * 1024 * 1024

# In-memory job tracker  {job_id: {status, progress, message, report_path}}
jobs: dict = {}
jobs_lock  = threading.Lock()

# ── Frontend HTML ─────────────────────────────────────────────────────────────
FRONTEND = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PG Log Analyzer</title>
<style>
:root {
  --bg: #0d1117; --bg2: #161b22; --bg3: #21262d; --border: #30363d;
  --text: #e6edf3; --text2: #8b949e; --text3: #484f58;
  --green: #3fb950; --amber: #d29922; --red: #f85149; --blue: #58a6ff;
  --purple: #bc8cff; --font: 'JetBrains Mono', monospace;
  --sans: 'Segoe UI', system-ui, sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: var(--sans);
       min-height: 100vh; display: flex; flex-direction: column; align-items: center; }

.hero { width: 100%; background: linear-gradient(135deg, #161b22 0%, #0d1117 100%);
        border-bottom: 1px solid var(--border); padding: 48px 24px 40px;
        text-align: center; }
.hero h1 { font-size: 32px; font-weight: 800; color: var(--blue);
            letter-spacing: -1px; margin-bottom: 10px; }
.hero p  { color: var(--text2); font-size: 15px; max-width: 520px; margin: 0 auto; line-height: 1.6; }
.hero .pills { display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; margin-top: 18px; }
.pill { padding: 5px 14px; border-radius: 20px; font-size: 12px; font-weight: 600;
        background: rgba(88,166,255,.12); color: var(--blue);
        border: 1px solid rgba(88,166,255,.25); }

.wrap { width: 100%; max-width: 760px; padding: 40px 24px; }

/* Upload card */
.card { background: var(--bg2); border: 1px solid var(--border); border-radius: 12px;
        padding: 32px; margin-bottom: 24px; }
.card h2 { font-size: 16px; font-weight: 700; margin-bottom: 6px; }
.card .sub { font-size: 13px; color: var(--text2); margin-bottom: 24px; }

.drop-zone { border: 2px dashed var(--border); border-radius: 10px;
             padding: 52px 32px; text-align: center; cursor: pointer;
             transition: all .2s; position: relative; }
.drop-zone.drag, .drop-zone:hover { border-color: var(--blue);
                                     background: rgba(88,166,255,.04); }
.drop-zone input[type=file] { position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; height: 100%; }
.drop-zone .icon { font-size: 40px; margin-bottom: 12px; }
.drop-zone h3 { font-size: 17px; color: var(--text); margin-bottom: 6px; }
.drop-zone p  { font-size: 13px; color: var(--text3); }
.drop-zone .selected { font-size: 13px; color: var(--green); margin-top: 12px;
                       font-family: var(--font); }

/* Options row */
.opts { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 20px; }
.opt-group label { display: block; font-size: 12px; font-weight: 600; color: var(--text3);
                   text-transform: uppercase; letter-spacing: .7px; margin-bottom: 6px; }
.opt-group input, .opt-group select {
  width: 100%; background: var(--bg3); border: 1px solid var(--border);
  border-radius: 6px; padding: 9px 12px; color: var(--text); font-size: 13px;
  font-family: var(--sans); outline: none; }
.opt-group input:focus, .opt-group select:focus { border-color: var(--blue); }

/* Submit button */
.btn-submit { width: 100%; margin-top: 20px; padding: 14px;
              background: var(--blue); color: #0d1117; border: none;
              border-radius: 8px; font-size: 15px; font-weight: 700;
              cursor: pointer; transition: all .15s; letter-spacing: -.2px; }
.btn-submit:hover { background: #79c0ff; }
.btn-submit:disabled { background: var(--bg3); color: var(--text3); cursor: not-allowed; }

/* Progress */
#progressCard { display: none; }
.prog-status  { font-size: 14px; color: var(--text2); margin-bottom: 10px; }
.prog-bar     { height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
.prog-fill    { height: 100%; background: var(--blue); border-radius: 3px;
                transition: width .4s ease; width: 0; }
.prog-pct     { font-size: 12px; color: var(--text3); margin-top: 6px; font-family: var(--font); }

/* Result card */
#resultCard { display: none; }
.result-icon { font-size: 48px; text-align: center; margin-bottom: 12px; }
.result-msg  { text-align: center; font-size: 15px; color: var(--text2); margin-bottom: 20px; }
.result-stats { display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; margin-bottom: 20px; }
.rstat { background: var(--bg3); border-radius: 8px; padding: 14px; text-align: center; }
.rstat .rv { font-size: 22px; font-weight: 700; font-family: var(--font); }
.rstat .rl { font-size: 11px; color: var(--text3); text-transform: uppercase;
             letter-spacing: .7px; margin-top: 4px; }
.rv-red { color: var(--red); } .rv-amber { color: var(--amber); }
.rv-green { color: var(--green); } .rv-blue { color: var(--blue); }
.btn-report { display: block; text-align: center; background: var(--green); color: #0d1117;
              padding: 13px; border-radius: 8px; font-size: 15px; font-weight: 700;
              text-decoration: none; letter-spacing: -.2px; margin-bottom: 12px; }
.btn-report:hover { background: #56d364; }
.btn-new { display: block; text-align: center; background: transparent; color: var(--text2);
           padding: 10px; border-radius: 8px; font-size: 13px; border: 1px solid var(--border);
           cursor: pointer; text-decoration: none; }
.btn-new:hover { border-color: var(--text2); color: var(--text); }

/* Error */
.err-box { background: rgba(248,81,73,.1); border: 1px solid rgba(248,81,73,.3);
           border-radius: 8px; padding: 16px; color: #ffa198; font-size: 13px; }

/* History */
.history-item { display: flex; align-items: center; gap: 12px; padding: 12px 0;
                border-bottom: 1px solid var(--border); }
.history-item:last-child { border-bottom: none; }
.hi-name { flex: 1; font-size: 13px; color: var(--text2); font-family: var(--font);
           overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hi-time { font-size: 11px; color: var(--text3); white-space: nowrap; }
.hi-btn  { padding: 5px 12px; border-radius: 5px; background: var(--bg3);
           border: 1px solid var(--border); color: var(--text2); font-size: 12px;
           text-decoration: none; white-space: nowrap; }
.hi-btn:hover { border-color: var(--blue); color: var(--blue); }

@media (max-width: 500px) { .opts { grid-template-columns: 1fr; }
  .result-stats { grid-template-columns: 1fr 1fr; } }
</style>
</head>
<body>

<div class="hero">
  <h1>&#9658; PG Log Analyzer</h1>
  <p>Upload your RDS / Aurora PostgreSQL log file and get a pgbadger-style report with
     slow queries, error breakdown, connection activity, and more — in seconds.</p>
  <div class="pills">
    <span class="pill">CloudWatch export format</span>
    <span class="pill">Multi-line SQL captured</span>
    <span class="pill">Grouped query patterns</span>
    <span class="pill">Self-contained HTML report</span>
  </div>
</div>

<div class="wrap">

  <!-- Upload form -->
  <div class="card" id="uploadCard">
    <h2>Analyze a Log File</h2>
    <div class="sub">Supports CloudWatch-exported tab-separated .log files up to 2 GB.</div>

    <div class="drop-zone" id="dropZone">
      <input type="file" id="fileInput" accept=".log,.csv,.txt,.gz"
             onchange="onFileSelected(this)">
      <div class="icon">&#128196;</div>
      <h3>Drop your log file here</h3>
      <p>or click to browse</p>
      <div class="selected" id="selectedName" style="display:none"></div>
    </div>

    <div class="opts">
      <div class="opt-group">
        <label>Min slow query threshold</label>
        <select id="minSlow">
          <option value="0">All queries (0 ms)</option>
          <option value="100">100 ms</option>
          <option value="500" selected>500 ms</option>
          <option value="1000">1 s</option>
          <option value="5000">5 s</option>
          <option value="10000">10 s</option>
        </select>
      </div>
      <div class="opt-group">
        <label>Report title (optional)</label>
        <input type="text" id="reportTitle" placeholder="e.g. prod-db Apr 2026">
      </div>
    </div>

    <div id="errBox" class="err-box" style="display:none;margin-top:16px"></div>

    <button class="btn-submit" id="submitBtn" onclick="startUpload()" disabled>
      Analyze Log File &#8594;
    </button>
  </div>

  <!-- Progress card -->
  <div class="card" id="progressCard">
    <h2 style="margin-bottom:16px">&#8987; Analyzing…</h2>
    <div class="prog-status" id="progStatus">Uploading file…</div>
    <div class="prog-bar"><div class="prog-fill" id="progFill"></div></div>
    <div class="prog-pct" id="progPct">0%</div>
  </div>

  <!-- Result card -->
  <div class="card" id="resultCard">
    <div class="result-icon">&#9989;</div>
    <div class="result-msg" id="resultMsg">Analysis complete!</div>
    <div class="result-stats" id="resultStats"></div>
    <a class="btn-report" id="reportLink" href="#" target="_blank">
      &#128196; Open Full Report
    </a>
    <a class="btn-new" href="/" onclick="location.reload();return false">
      &#8617; Analyze another file
    </a>
  </div>

  <!-- Recent reports -->
  {% if history %}
  <div class="card">
    <h2 style="margin-bottom:16px">Recent Reports</h2>
    {% for h in history %}
    <div class="history-item">
      <span class="hi-name">{{ h.filename }}</span>
      <span class="hi-time">{{ h.created }}</span>
      <a class="hi-btn" href="/report/{{ h.job_id }}" target="_blank">Open &#8599;</a>
    </div>
    {% endfor %}
  </div>
  {% endif %}

</div><!-- wrap -->

<script>
let selectedFile = null;

function onFileSelected(input) {
  selectedFile = input.files[0];
  if (!selectedFile) return;
  document.getElementById('selectedName').textContent = '&#10003; ' + selectedFile.name +
    ' (' + (selectedFile.size / 1024 / 1024).toFixed(1) + ' MB)';
  document.getElementById('selectedName').style.display = 'block';
  document.getElementById('submitBtn').disabled = false;
  document.getElementById('errBox').style.display = 'none';
}

const dropZone = document.getElementById('dropZone');
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag'));
dropZone.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('drag');
  const file = e.dataTransfer.files[0];
  if (file) {
    document.getElementById('fileInput').files;  // can't set programmatically
    selectedFile = file;
    document.getElementById('selectedName').textContent = '&#10003; ' + file.name +
      ' (' + (file.size/1024/1024).toFixed(1) + ' MB)';
    document.getElementById('selectedName').style.display = 'block';
    document.getElementById('submitBtn').disabled = false;
  }
});

async function startUpload() {
  if (!selectedFile) return;
  const minSlow = document.getElementById('minSlow').value;

  document.getElementById('uploadCard').style.display = 'none';
  document.getElementById('progressCard').style.display = 'block';
  setProgress(5, 'Uploading file…');

  const fd = new FormData();
  fd.append('logfile', selectedFile);
  fd.append('min_slow_ms', minSlow);

  let jobId;
  try {
    const res = await fetch('/upload', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Upload failed');
    jobId = data.job_id;
  } catch (e) {
    showError(e.message);
    return;
  }

  // Poll for completion
  pollJob(jobId);
}

function setProgress(pct, msg) {
  document.getElementById('progFill').style.width = pct + '%';
  document.getElementById('progPct').textContent = pct + '%';
  if (msg) document.getElementById('progStatus').textContent = msg;
}

async function pollJob(jobId) {
  while (true) {
    await new Promise(r => setTimeout(r, 1200));
    try {
      const res = await fetch('/status/' + jobId);
      const data = await res.json();
      setProgress(data.progress, data.message);
      if (data.status === 'done') {
        showResult(data, jobId);
        return;
      }
      if (data.status === 'error') {
        showError(data.message);
        return;
      }
    } catch (e) { /* network blip, keep polling */ }
  }
}

function showResult(data, jobId) {
  document.getElementById('progressCard').style.display = 'none';
  document.getElementById('resultCard').style.display = 'block';
  document.getElementById('resultMsg').textContent =
    `Analysis complete for ${data.filename}`;
  document.getElementById('resultStats').innerHTML = `
    <div class="rstat"><div class="rv rv-blue">${fmtNum(data.total_events)}</div><div class="rl">Events</div></div>
    <div class="rstat"><div class="rv rv-red">${fmtNum(data.errors)}</div><div class="rl">Errors/Fatals</div></div>
    <div class="rstat"><div class="rv rv-amber">${fmtNum(data.slow_queries)}</div><div class="rl">Slow Queries</div></div>
    <div class="rstat"><div class="rv rv-amber">${data.slow_max}</div><div class="rl">Slowest Query</div></div>
    <div class="rstat"><div class="rv rv-green">${fmtNum(data.connections)}</div><div class="rl">Connections</div></div>
    <div class="rstat"><div class="rv rv-blue">${data.elapsed}s</div><div class="rl">Parse Time</div></div>`;
  document.getElementById('reportLink').href = '/report/' + jobId;
}

function showError(msg) {
  document.getElementById('progressCard').style.display = 'none';
  document.getElementById('uploadCard').style.display = 'block';
  const eb = document.getElementById('errBox');
  eb.textContent = '&#9747; Error: ' + msg;
  eb.style.display = 'block';
}

function fmtNum(n) {
  if (n === undefined || n === null) return '—';
  return Number(n).toLocaleString();
}
</script>
</body>
</html>"""

# ── Routes ────────────────────────────────────────────────────────────────────

def _history():
    """Return list of completed jobs, newest first."""
    items = []
    for jid, j in jobs.items():
        if j['status'] == 'done':
            items.append({'job_id': jid, 'filename': j.get('filename','?'), 'created': j.get('created','')})
    return sorted(items, key=lambda x: x['created'], reverse=True)[:10]


@app.route('/')
def index():
    return render_template_string(FRONTEND, history=_history())


@app.route('/upload', methods=['POST'])
def upload():
    if 'logfile' not in request.files:
        return jsonify(error='No file uploaded'), 400

    f = request.files['logfile']
    if not f.filename:
        return jsonify(error='Empty filename'), 400

    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        return jsonify(error=f'Unsupported extension {ext}. Use .log .csv .txt .gz'), 400

    min_slow = float(request.form.get('min_slow_ms', 0))
    job_id = str(uuid.uuid4())[:8]
    save_path = UPLOAD_DIR / f'{job_id}{ext}'

    f.save(str(save_path))

    with jobs_lock:
        jobs[job_id] = {
            'status': 'queued', 'progress': 5, 'message': 'File received, queued for parsing…',
            'filename': f.filename, 'created': time.strftime('%Y-%m-%d %H:%M'),
            'upload_path': str(save_path), 'min_slow': min_slow
        }

    t = threading.Thread(target=_run_analysis, args=(job_id,), daemon=True)
    t.start()

    return jsonify(job_id=job_id)


@app.route('/status/<job_id>')
def status(job_id):
    with jobs_lock:
        j = jobs.get(job_id)
    if not j:
        return jsonify(error='Unknown job'), 404

    resp = {k: j[k] for k in ('status', 'progress', 'message', 'filename')}
    resp['job_id'] = job_id

    if j['status'] == 'done':
        r = j.get('result_summary', {})
        resp.update({
            'total_events': r.get('total_events', 0),
            'errors':       r.get('errors', 0),
            'slow_queries': r.get('slow_queries', 0),
            'slow_max':     r.get('slow_max', '—'),
            'connections':  r.get('connections', 0),
            'elapsed':      r.get('elapsed', 0),
        })
    return jsonify(resp)


@app.route('/report/<job_id>')
def view_report(job_id):
    with jobs_lock:
        j = jobs.get(job_id)
    if not j or j['status'] != 'done':
        return 'Report not ready or not found', 404
    return send_file(j['report_path'], mimetype='text/html')



@app.route('/search/<job_id>')
def search_log(job_id):
    """Full-file boolean search endpoint for Log Explorer."""
    with jobs_lock:
        j = jobs.get(job_id)
    if not j or j['status'] != 'done':
        return jsonify(error='Job not ready'), 404
    log_path = j.get('log_file_path', '')
    if not log_path or not os.path.exists(log_path):
        return jsonify(error='Log file no longer available on server'), 410
    query    = request.args.get('q', '')
    exclude  = request.args.get('exc', '')
    sev_raw  = request.args.get('sev', '')
    db_f     = request.args.get('db', '')
    user_f   = request.args.get('user', '')
    node_f   = request.args.get('node', '')
    limit    = min(int(request.args.get('limit', 500)), 2000)
    severities = [s for s in sev_raw.split(',') if s] if sev_raw else None
    result = log_parser.search_file(
        log_path, query=query, exclude=exclude,
        severities=severities, db=db_f, user=user_f, node=node_f, limit=limit,
    )
    return jsonify(result)


@app.route('/pid/<job_id>/<pid_val>')
def trace_pid(job_id, pid_val):
    """Return ALL log entries for a specific PID in chronological order."""
    with jobs_lock:
        j = jobs.get(job_id)
    if not j or j['status'] != 'done':
        return jsonify(error='Job not ready'), 404
    log_path = j.get('log_file_path', '')
    if not log_path or not os.path.exists(log_path):
        return jsonify(error='Log file no longer available on server'), 410
    limit   = min(int(request.args.get('limit', 1000)), 5000)
    entries = log_parser.search_pid(log_path, pid_val, limit=limit)
    return jsonify({'entries': entries, 'pid': pid_val, 'count': len(entries)})


# ── Background worker ─────────────────────────────────────────────────────────

def _fmt_ms(ms: float) -> str:
    if ms >= 3_600_000: return f"{ms/3_600_000:.2f}h"
    if ms >= 60_000:    return f"{ms/60_000:.2f}m"
    if ms >= 1_000:     return f"{ms/1_000:.2f}s"
    return f"{ms:.0f}ms"


def _run_analysis(job_id: str):
    def update(pct, msg):
        with jobs_lock:
            jobs[job_id]['progress'] = pct
            jobs[job_id]['message']  = msg

    try:
        with jobs_lock:
            j = dict(jobs[job_id])

        update(10, 'Parsing log entries…')
        t0 = time.time()

        result = log_parser.parse(j['upload_path'], min_slow_ms=j['min_slow'])

        update(80, 'Generating HTML report…')
        report_path = str(REPORT_DIR / f'{job_id}_report.html')
        log_report.generate(result, report_path, job_id=job_id)

        elapsed = round(time.time() - t0, 1)
        update(100, 'Done!')

        with jobs_lock:
            jobs[job_id]['status']       = 'done'
            jobs[job_id]['report_path']  = report_path
            jobs[job_id]['log_file_path'] = j['upload_path']
            jobs[job_id]['min_slow']      = j['min_slow']
            jobs[job_id]['result_summary'] = {
                'total_events': result.parsed_entries,
                'errors':       result.by_severity.get('ERROR', 0) + result.by_severity.get('FATAL', 0),
                'slow_queries': result.slow_count,
                'slow_max':     _fmt_ms(result.slow_max_ms),
                'connections':  result.conn_received,
                'elapsed':      elapsed,
            }

        # Keep upload file for server-side search queries
        # (will be cleaned up when server restarts)

    except Exception as exc:
        import traceback
        with jobs_lock:
            jobs[job_id]['status']   = 'error'
            jobs[job_id]['message']  = str(exc)
            jobs[job_id]['progress'] = 0
        print(f'[ERROR] job {job_id}: {exc}')
        traceback.print_exc()


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        # CLI mode: python3 app.py <logfile> [min_slow_ms]
        filepath  = sys.argv[1]
        min_slow  = float(sys.argv[2]) if len(sys.argv) > 2 else 0
        out_path  = Path(filepath).stem + '_report.html'

        print(f'[PG Log Analyzer] Parsing {filepath}…')
        t0 = time.time()
        result = log_parser.parse(filepath, min_slow_ms=min_slow)
        print(f'  Events  : {result.parsed_entries:,}')
        print(f'  Errors  : {result.by_severity.get("ERROR",0) + result.by_severity.get("FATAL",0)}')
        print(f'  Slow Qs : {result.slow_count:,}  (max {_fmt_ms(result.slow_max_ms)})')
        print(f'  Parsed  : {round(time.time()-t0,1)}s')
        log_report.generate(result, out_path)
        print(f'  Report  : {out_path}')
    else:
        print('[PG Log Analyzer] Starting web server at http://localhost:5050')
        print('  Upload a log file at the web interface.')
        print('  CLI usage:  python3 app.py <logfile.log> [min_slow_ms]')
        app.run(host='0.0.0.0', port=5050, debug=False, threaded=True)
