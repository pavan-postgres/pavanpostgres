# PG Log Analyzer

A local PostgreSQL log analysis tool for **Amazon RDS and Aurora PostgreSQL** logs exported from CloudWatch. Upload a log file through the web UI (or point the CLI at a file) and get a self-contained HTML report with charts, slow query analysis, error breakdowns, and a full-file boolean search explorer.

---

## Features

| Section | What it shows |
|---|---|
| **Summary** | Total events, errors/fatals, slow query counts, p50/p95/p99 durations, connection counts, autovacuum runs |
| **Activity Over Time** | Hourly event volume (spikes highlighted), severity distribution donut, events by node, slow query duration buckets |
| **Slowest Queries** | Top 100 individual queries by duration — full SQL captured from multi-line continuation lines, sortable, filterable by db/user |
| **Grouped Queries** | All slow queries normalised (literals → `?`, numbers → `N`) and grouped by pattern — sorted by total time or call count |
| **Errors & Fatals** | Error type frequency chart, filterable table with severity, user, database, node, PID |
| **Connections** | Received / authenticated / authorized / disconnections / auth failures — broken down by database and user |
| **Autovacuum** | All autovacuum and auto-analyze runs with timing |
| **Temp Files** | Spill-to-disk events (queries that exceeded `work_mem`) |
| **Lock Waits** | Sessions that waited longer than `deadlock_timeout` |
| **Log Explorer** | Full-file boolean search + PID session tracer (see below) |

### Log Explorer

- **Boolean query syntax** — `ERROR OR FATAL`, `duration AND NOT pgwatch`, `(ERROR OR FATAL) AND data_prep`, `/data.+/ OR /pgwatch.+/`
- **Operators** — `AND`, `OR`, `NOT`, parentheses `( )`, implicit AND between adjacent terms, `/regex/flags`
- **Exclude filter** — hide noise (e.g. `pgwatch connection received`) while the include query runs
- **Filter by** severity, database, user, node — all combined with the boolean query
- **Live query preview** — shows parsed AST as colour-coded badges as you type (`AND` in amber, `OR` in green, `NOT` in red)
- **PID Session Tracer** — enter any PID and get every log message for that session in chronological order with full SQL expanded inline
- All searches scan the **entire log file** on the server in real time — no sampling, no pre-indexing

---

## Log Format

Designed for the **CloudWatch-exported tab-separated format** produced by RDS/Aurora PostgreSQL:

```
EVENTS\t{event_id}\t{epoch_ms}\t{node_name}\t{pg_log_line}\t{epoch_ms2}
```

Where `{pg_log_line}` follows the standard RDS `log_line_prefix`:

```
%t:%r:%u@%d:[%p]: SEVERITY: message
```

Multi-line SQL (continuation lines starting with `\t`) is automatically collected and attached to the parent slow query entry.

---

## Requirements

```
Python  >= 3.9
Flask   >= 2.0
```

No other dependencies. Charts are rendered with vanilla Canvas 2D — no Chart.js, no CDN calls, no internet required.

```bash
pip install flask
```

---

## Project Structure

```
pg_log_analyzer/
├── app.py       # Flask web server + CLI entry point
├── parser.py    # Two-pass log parser + server-side boolean search engine
└── report.py    # Self-contained HTML report generator
```

---

## Usage

### Web UI

```bash
python3 app.py
```

Open [http://localhost:5050](http://localhost:5050), upload your `.log` file, set a slow query threshold, and click **Analyze**. The report opens automatically when parsing completes. Log Explorer searches run against the server in real time — keep the server running while using the report.

### CLI

```bash
# Generate a report directly from a log file
python3 app.py path/to/your.log

# With a slow query threshold (only log queries >= 500ms)
python3 app.py path/to/your.log 500
```

Output is written to `<logfile>_report.html` in the same directory.

---

## Configuration

Edit the top of `app.py` to change defaults:

```python
UPLOAD_DIR  = Path('/tmp/pg_analyzer/uploads')   # where uploads are stored
REPORT_DIR  = Path('/tmp/pg_analyzer/reports')   # where reports are stored
MAX_MB      = 2048                               # max upload size (2 GB)
ALLOWED_EXT = {'.log', '.csv', '.txt', '.gz'}    # accepted extensions
```

The server keeps uploaded files on disk for the lifetime of the process so the Log Explorer can re-scan on demand. Files are removed when the server restarts.

---

## Boolean Query Syntax Reference

| Expression | Meaning |
|---|---|
| `ERROR` | Lines containing the word "error" (case-insensitive) |
| `ERROR FATAL` | Lines containing both "error" AND "fatal" (implicit AND) |
| `ERROR OR FATAL` | Lines containing either |
| `duration AND NOT pgwatch` | Has "duration" but not "pgwatch" |
| `(ERROR OR FATAL) AND data_prep` | Either error severity AND contains "data_prep" |
| `/data.+/` | Regex — matches "data_worker", "data_prep_600326", etc. |
| `/data.+/ OR /pgwatch.+/` | Two regex patterns joined with OR |
| `ERROR AND NOT /pgwatch\|rdsadmin/` | ERROR but not from pgwatch or rdsadmin |

## How It Works

### Parsing pipeline

```
Log file
  │
  ├─ Pass 1 ──► PG_PREFIX regex match per line
  │              ├─ Severity counters (by hour / db / user / node)
  │              ├─ Connection event counting
  │              ├─ Error / Fatal collection
  │              ├─ Autovacuum / checkpoint / temp file / lock wait collection
  │              └─ Slow query state machine
  │                   └─ Multi-line SQL continuation collector
  │
  ├─ Post-process ──► Sort slow queries by duration
  │                   Group by normalised SQL pattern
  │                   Compute p50 / p95 / p99 percentiles
  │
  └─ Pass 2 ──► Re-scan for interesting PIDs (errors + top slow queries)
                Collect full session timeline per PID
```

### Report generation

`report.py` builds a single self-contained `.html` file:

- All chart data (hourly volumes, severity counts, etc.) is embedded as JSON constants
- Charts are drawn with **vanilla Canvas 2D** — no Chart.js, no external dependencies
- All JS lives either in the Python f-string (simple logic, no regex) or injected as a raw string via `str.replace()` after f-string evaluation (complex regex-heavy code), avoiding Python escape sequence conflicts
- Log Explorer calls back to the Flask server (`/search/<job_id>`) at query time — the full log file is never embedded in the HTML

---

## Tested With

- Amazon Aurora PostgreSQL 14 / 15 / 16
- Amazon RDS for PostgreSQL 14 / 15 / 16
- Log files up to ~400 MB (1M+ events), parsing in ~12 seconds on a MacBook M-series

---

## Known Limitations

- Log Explorer requires the Flask server to be running (it makes live HTTP requests back to `/search/` and `/pid/`). The static HTML report works fully for all other sections.
- Uploaded log files are stored in `/tmp/pg_analyzer/` and cleaned up on server restart — not suitable for multi-user production deployments without adding auth and persistent storage.
- Only the CloudWatch tab-separated export format is supported. Standard `stderr` format files (from `postgresql.log` directly) require a small parser tweak to the `EVENTS\t` prefix check.

