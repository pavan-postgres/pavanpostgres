"""
RDS / Aurora PostgreSQL Log Parser — two-pass with PID group collection.
"""

import re, os
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

PG_PREFIX = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC'
    r':([\d\.]+(?:\(\d+\))?|\[local\])'
    r':([\w\[\]]+)'
    r'@([^:]+)'
    r':\[(\d+)\]'
    r':(LOG|ERROR|FATAL|WARNING|DETAIL|STATEMENT|HINT|NOTICE|PANIC|DEBUG\d?):'
    r'\s*(.*)'
)
DURATION_RE = re.compile(
    r'duration:\s*([\d\.]+)\s*ms'
    r'(?:\s+(?:statement|execute|parse)\s*(?:<[^>]*>)?:?\s*(.*))?',
    re.DOTALL
)
NORM_RE  = re.compile(r'\s+')
PARAM_RE = re.compile(r'\$\d+')
LIT_STR  = re.compile(r"'[^']*'")
LIT_NUM  = re.compile(r'\b\d+\b')


def normalize_query(sql):
    sql = NORM_RE.sub(' ', sql).strip()
    sql = PARAM_RE.sub('?', sql)
    sql = LIT_STR.sub("'?'", sql)
    sql = LIT_NUM.sub('N', sql)
    return sql[:500]


@dataclass
class SlowQuery:
    ts: str; duration_ms: float; user: str; db: str
    node: str; pid: str; sql: str; normalized: str


@dataclass
class ParseResult:
    filename: str; file_size_mb: float; total_lines: int; parsed_entries: int
    date_range: tuple; nodes: list; databases: list; users: list
    by_severity: Counter; by_hour: Counter; by_database: Counter
    by_user: Counter; by_node: Counter
    conn_received: int; conn_authenticated: int; conn_authorized: int
    conn_failed: int; disconnections: int
    errors: list; fatals: list; error_types: Counter
    slow_queries: list; slow_by_normalized: dict
    autovacuum_runs: list; checkpoints: list; temp_files: list; lock_waits: list
    slow_count: int; slow_max_ms: float; slow_avg_ms: float
    slow_p95_ms: float; slow_p99_ms: float
    log_sample: list = field(default_factory=list)
    pid_groups: dict = field(default_factory=dict)


def _edict(ts, host, user, db, pid, severity, message, node, sql=''):
    return {'ts': ts, 'host': host, 'user': user, 'db': db,
            'pid': pid, 'severity': severity, 'msg': message[:500], 'node': node, 'sql': sql}


def _pass1(filepath, min_slow_ms):
    total_lines = parsed_entries = 0
    by_severity, by_hour, by_database = Counter(), Counter(), Counter()
    by_user, by_node = Counter(), Counter()
    conn_received = conn_authenticated = conn_authorized = conn_failed = disconnections = 0
    errors, fatals, slow_queries = [], [], []
    autovacuum_runs, checkpoints, temp_files, lock_waits = [], [], [], []
    error_types = Counter()
    log_sample = []
    first_ts = last_ts = None
    collecting_sql = False
    sql_lines = []
    cur_entry = None
    cur_dur = 0.0

    def flush():
        nonlocal collecting_sql, sql_lines, cur_entry, cur_dur
        if cur_entry and collecting_sql:
            full_sql = '\n'.join(sql_lines).strip() or cur_entry.sql.strip()
            slow_queries.append(SlowQuery(
                ts=cur_entry.ts, duration_ms=cur_dur,
                user=cur_entry.user, db=cur_entry.db,
                node=cur_entry.node, pid=cur_entry.pid,
                sql=full_sql, normalized=normalize_query(full_sql),
            ))
        collecting_sql = False; sql_lines = []; cur_entry = None; cur_dur = 0.0

    with open(filepath, 'r', errors='replace', buffering=1 << 20) as fh:
        for raw in fh:
            total_lines += 1
            line = raw.rstrip('\n')
            if collecting_sql and (line.startswith('\t') or
                    (line.startswith('  ') and not line.startswith('  EVENTS'))):
                sql_lines.append(line.strip()); continue
            if collecting_sql: flush()
            if not line.startswith('EVENTS\t'): continue
            parts = line.split('\t', 5)
            if len(parts) < 5: continue
            node, pg_line = parts[3], parts[4]
            m = PG_PREFIX.match(pg_line)
            if not m: continue
            ts, host, user, db, pid, severity, message = m.groups()
            parsed_entries += 1
            if first_ts is None: first_ts = ts
            last_ts = ts
            by_severity[severity] += 1; by_hour[ts[:13]] += 1
            by_database[db] += 1; by_user[user] += 1; by_node[node] += 1
            if len(log_sample) < 3000:
                log_sample.append(_edict(ts, host, user, db, pid, severity, message, node))
            if severity == 'LOG':
                ml = message.lower()
                if   'connection received'      in ml: conn_received      += 1
                elif 'connection authenticated' in ml: conn_authenticated += 1
                elif 'connection authorized'    in ml: conn_authorized    += 1
                elif 'disconnection'            in ml: disconnections     += 1
                elif 'autovacuum' in ml or 'autoanalyze' in ml:
                    autovacuum_runs.append(_edict(ts, host, user, db, pid, severity, message, node))
                elif 'checkpoint' in ml:
                    checkpoints.append({'ts': ts, 'msg': message[:400], 'node': node})
                elif 'temporary file' in ml:
                    temp_files.append(_edict(ts, host, user, db, pid, severity, message, node))
                elif 'still waiting' in ml:
                    lock_waits.append(_edict(ts, host, user, db, pid, severity, message, node))
                dm = DURATION_RE.search(message)
                if dm:
                    dur = float(dm.group(1))
                    inline = (dm.group(2) or '').strip()
                    if dur >= min_slow_ms:
                        from dataclasses import dataclass as _dc
                        class _E:
                            pass
                        e = _E()
                        e.ts=ts; e.host=host; e.user=user; e.db=db; e.pid=pid
                        e.severity=severity; e.message=message; e.node=node; e.sql=inline
                        cur_entry=e; cur_dur=dur
                        sql_lines=[inline] if inline else []; collecting_sql=True
            elif severity in ('ERROR', 'PANIC'):
                error_types[message.strip()[:120]] += 1
                if len(errors) < 200:
                    errors.append(_edict(ts, host, user, db, pid, severity, message, node))
            elif severity == 'FATAL':
                error_types[message.strip()[:120]] += 1
                if len(fatals) < 200:
                    fatals.append(_edict(ts, host, user, db, pid, severity, message, node))
                if 'authentication failed' in message.lower(): conn_failed += 1

    if collecting_sql: flush()
    return dict(total_lines=total_lines, parsed_entries=parsed_entries,
                first_ts=first_ts, last_ts=last_ts,
                by_severity=by_severity, by_hour=by_hour,
                by_database=by_database, by_user=by_user, by_node=by_node,
                conn_received=conn_received, conn_authenticated=conn_authenticated,
                conn_authorized=conn_authorized, conn_failed=conn_failed,
                disconnections=disconnections, errors=errors, fatals=fatals,
                error_types=error_types, slow_queries=slow_queries,
                autovacuum_runs=autovacuum_runs, checkpoints=checkpoints,
                temp_files=temp_files, lock_waits=lock_waits, log_sample=log_sample)


def _pass2(filepath, interesting_pids):
    MAX_PER_PID = 200
    groups = {pid: [] for pid in interesting_pids}
    with open(filepath, 'r', errors='replace', buffering=1 << 20) as fh:
        for raw in fh:
            if not raw.startswith('EVENTS\t'): continue
            parts = raw.split('\t', 5)
            if len(parts) < 5: continue
            node, pg_line = parts[3], parts[4]
            m = PG_PREFIX.match(pg_line)
            if not m: continue
            ts, host, user, db, pid, severity, message = m.groups()
            if pid not in groups: continue
            lst = groups[pid]
            if len(lst) < MAX_PER_PID:
                lst.append(_edict(ts, host, user, db, pid, severity, message, node))
    for pid in groups:
        groups[pid].sort(key=lambda e: e['ts'])
    return groups


def parse(filepath: str, min_slow_ms: float = 0) -> ParseResult:
    filename     = os.path.basename(filepath)
    file_size_mb = round(os.path.getsize(filepath) / 1024 / 1024, 1)

    p1 = _pass1(filepath, min_slow_ms)
    slow_queries = sorted(p1['slow_queries'], key=lambda x: -x.duration_ms)

    durations  = sorted(sq.duration_ms for sq in slow_queries)
    slow_count = len(durations)
    slow_max   = durations[-1] if durations else 0
    slow_avg   = sum(durations) / slow_count if slow_count else 0
    slow_p95   = durations[int(slow_count * 0.95)] if slow_count else 0
    slow_p99   = durations[int(slow_count * 0.99)] if slow_count else 0

    slow_by_norm = {}
    for sq in slow_queries:
        g = slow_by_norm.setdefault(sq.normalized, {
            'count': 0, 'total_ms': 0.0, 'max_ms': 0.0, 'min_ms': float('inf'), 'samples': []
        })
        g['count'] += 1; g['total_ms'] += sq.duration_ms
        g['max_ms'] = max(g['max_ms'], sq.duration_ms)
        g['min_ms'] = min(g['min_ms'], sq.duration_ms)
        if len(g['samples']) < 2:
            g['samples'].append({'ts': sq.ts, 'duration_ms': sq.duration_ms,
                                 'user': sq.user, 'db': sq.db, 'node': sq.node, 'sql': sq.sql})

    interesting_pids = set()
    for e in p1['errors']:   interesting_pids.add(e['pid'])
    for e in p1['fatals']:   interesting_pids.add(e['pid'])
    for sq in slow_queries[:100]: interesting_pids.add(sq.pid)
    for e in p1['lock_waits'][:50]: interesting_pids.add(e['pid'])

    pid_groups = _pass2(filepath, interesting_pids) if interesting_pids else {}

    slow_list = [{'ts': sq.ts, 'duration_ms': sq.duration_ms, 'user': sq.user,
                  'db': sq.db, 'node': sq.node, 'pid': sq.pid,
                  'sql': sq.sql, 'normalized': sq.normalized}
                 for sq in slow_queries[:300]]

    return ParseResult(
        filename=filename, file_size_mb=file_size_mb,
        total_lines=p1['total_lines'], parsed_entries=p1['parsed_entries'],
        date_range=(p1['first_ts'] or '', p1['last_ts'] or ''),
        nodes=list(p1['by_node'].keys()),
        databases=[k for k in p1['by_database'] if k != '[unknown]'],
        users=[k for k in p1['by_user'] if k not in ('[unknown]',)],
        by_severity=p1['by_severity'], by_hour=p1['by_hour'],
        by_database=p1['by_database'], by_user=p1['by_user'], by_node=p1['by_node'],
        conn_received=p1['conn_received'], conn_authenticated=p1['conn_authenticated'],
        conn_authorized=p1['conn_authorized'], conn_failed=p1['conn_failed'],
        disconnections=p1['disconnections'],
        errors=p1['errors'], fatals=p1['fatals'], error_types=p1['error_types'],
        slow_queries=slow_list, slow_by_normalized=slow_by_norm,
        autovacuum_runs=p1['autovacuum_runs'][:100], checkpoints=p1['checkpoints'][:100],
        temp_files=p1['temp_files'][:100], lock_waits=p1['lock_waits'][:100],
        slow_count=slow_count, slow_max_ms=slow_max, slow_avg_ms=slow_avg,
        slow_p95_ms=slow_p95, slow_p99_ms=slow_p99,
        log_sample=p1['log_sample'], pid_groups=pid_groups,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SERVER-SIDE BOOLEAN SEARCH ENGINE
# Mirrors the JS boolean engine in the browser.
# Called by Flask endpoints — scans the full file on demand.
# ═══════════════════════════════════════════════════════════════════════════════

import re as _re

# ── Python boolean query parser (mirrors JS lex/parse/evalAST) ───────────────

class _Term:
    __slots__ = ('kind', 'v', 're', 'raw')
    def __init__(self, kind, v=None, pattern=None, raw=''):
        self.kind = kind   # 'txt' | 're' | 'err'
        self.v    = v
        self.re   = pattern
        self.raw  = raw

class _Node:
    __slots__ = ('op', 'l', 'r', 'o', 'e', 'term')
    def __init__(self, op, **kw):
        self.op   = op        # AND | OR | NOT | GROUP | TERM
        self.l    = kw.get('l')
        self.r    = kw.get('r')
        self.o    = kw.get('o')    # NOT operand
        self.e    = kw.get('e')    # GROUP inner
        self.term = kw.get('term') # TERM leaf


def _lex_py(raw: str):
    """Tokenise a boolean query string into (type, payload?) tuples."""
    tokens = []
    s = raw.strip()
    while s:
        s = s.lstrip()
        if not s:
            break
        # regex literal
        if s[0] == '/':
            end = -1
            for i in range(1, len(s)):
                if s[i] == '/' and s[i-1] != '\\':
                    end = i; break
            if end == -1:
                tokens.append(('TERM', _Term('txt', v=s[1:].lower(), raw=s)))
                break
            pat = s[1:end]
            flags_m = _re.match(r'^([gimsuy]*)', s[end+1:])
            flags_s = flags_m.group(1) if flags_m else ''
            skip = end + 1 + len(flags_s)
            re_flags = _re.IGNORECASE
            try:
                tokens.append(('TERM', _Term('re', pattern=_re.compile(pat, re_flags), raw=f'/{pat}/')))
            except _re.error:
                tokens.append(('TERM', _Term('err', raw=f'/{pat}/')))
            s = s[skip:].lstrip(', ')
            continue
        # keywords
        kw_m = _re.match(r'^(OR|AND|NOT|or|and|not)(?=[\s(),/]|$)', s)
        if kw_m:
            tokens.append((kw_m.group(1).upper(),))
            s = s[kw_m.end():].lstrip(', ')
            continue
        # parens
        if s[0] in '()':
            tokens.append((s[0],))
            s = s[1:].lstrip(', ')
            continue
        # quoted string
        if s[0] in ('"', "'"):
            q = s[0]
            end = s.find(q, 1)
            v = s[1:end] if end != -1 else s[1:]
            tokens.append(('TERM', _Term('txt', v=v.lower(), raw=s[:end+1] if end!=-1 else s)))
            s = s[end+1:] if end != -1 else ''
            continue
        # plain word
        wm = _re.match(r'^([^\s,/()"\']+)', s)
        if wm:
            w = wm.group(1).strip(',')
            if w:
                tokens.append(('TERM', _Term('txt', v=w.lower(), raw=w)))
            s = s[wm.end():].lstrip(', ')
        else:
            s = s[1:]
    return tokens


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def consume(self):
        t = self.tokens[self.pos]; self.pos += 1; return t

    def parse(self):
        return self._or()

    def _or(self):
        left = self._and()
        while self.peek() and self.peek()[0] == 'OR':
            self.consume()
            right = self._and()
            left = _Node('OR', l=left, r=right)
        return left

    def _and(self):
        left = self._not()
        while self.peek():
            t = self.peek()
            if t[0] == 'AND':
                self.consume(); right = self._not(); left = _Node('AND', l=left, r=right); continue
            if t[0] in ('TERM', 'NOT', '('):
                right = self._not(); left = _Node('AND', l=left, r=right); continue
            break
        return left

    def _not(self):
        if self.peek() and self.peek()[0] == 'NOT':
            self.consume(); return _Node('NOT', o=self._not())
        return self._primary()

    def _primary(self):
        t = self.peek()
        if not t: return None
        if t[0] == '(':
            self.consume(); e = self.parse()
            if self.peek() and self.peek()[0] == ')': self.consume()
            return _Node('GROUP', e=e)
        if t[0] == 'TERM':
            self.consume(); return _Node('TERM', term=t[1])
        return None


def _parse_query(raw: str) -> '_Node | None':
    if not raw.strip():
        return None
    return _Parser(_lex_py(raw)).parse()


def _eval_node(node, txt: str) -> bool:
    if node is None: return True
    if node.op == 'TERM':
        t = node.term
        if t.kind == 'err': return False
        if t.kind == 'txt': return t.v in txt
        if t.kind == 're':  return bool(t.re.search(txt))
    if node.op == 'NOT':   return not _eval_node(node.o, txt)
    if node.op == 'AND':   return _eval_node(node.l, txt) and _eval_node(node.r, txt)
    if node.op == 'OR':    return _eval_node(node.l, txt) or _eval_node(node.r, txt)
    if node.op == 'GROUP': return _eval_node(node.e, txt)
    return False


def _parse_exclude(raw: str):
    """Parse exclude field: simple OR list of terms."""
    terms = []
    s = raw.strip()
    while s:
        s = s.lstrip()
        if not s: break
        if s[0] == '/':
            end = -1
            for i in range(1, len(s)):
                if s[i] == '/' and s[i-1] != '\\':
                    end = i; break
            if end == -1: terms.append(_Term('txt', v=s[1:].lower())); break
            pat = s[1:end]
            try: terms.append(_Term('re', pattern=_re.compile(pat, _re.I), raw=f'/{pat}/'))
            except: terms.append(_Term('err', raw=f'/{pat}/'))
            s = s[end+1:].lstrip(', ')
            continue
        m = _re.match(r'^([^,/]+)', s)
        if not m: s = s[1:]; continue
        for t in _re.split(r'\s+', m.group(1)):
            t = t.strip(',').strip()
            if t: terms.append(_Term('txt', v=t.lower(), raw=t))
        s = s[m.end():].lstrip(', ')
    return terms


def _match_term(txt: str, term: _Term) -> bool:
    if term.kind == 'err': return False
    if term.kind == 'txt': return term.v in txt
    if term.kind == 're':  return bool(term.re.search(txt))
    return False


# ── Public search API ─────────────────────────────────────────────────────────

def search_file(filepath: str, *,
                query: str = '',
                exclude: str = '',
                severities=None,      # list of severity strings, None = all
                db: str = '',
                user: str = '',
                node: str = '',
                limit: int = 500) -> dict:
    """
    Full-file boolean search.  Returns:
      {'results': [entry_dict, ...], 'total_matched': int, 'total_scanned': int}
    """
    q_ast    = _parse_query(query)
    exc_terms = _parse_exclude(exclude)
    sev_set  = set(severities) if severities else None

    results = []
    total_scanned = 0
    total_matched = 0

    collecting_sql = False
    sql_lines = []
    cur_entry = None

    def flush():
        nonlocal collecting_sql, sql_lines, cur_entry
        if cur_entry and collecting_sql:
            cur_entry['sql'] = '\n'.join(sql_lines).strip()
        collecting_sql = False
        sql_lines = []
        cur_entry = None

    with open(filepath, 'r', errors='replace', buffering=1 << 20) as fh:
        for raw in fh:
            line = raw.rstrip('\n')

            # Collect multi-line SQL for current duration entry
            if collecting_sql and (line.startswith('\t') or
                    (line.startswith('  ') and not line.startswith('  EVENTS'))):
                sql_lines.append(line.strip())
                continue
            if collecting_sql:
                flush()

            if not line.startswith('EVENTS\t'):
                continue

            parts = line.split('\t', 5)
            if len(parts) < 5:
                continue

            nd  = parts[3]
            pg  = parts[4]
            m   = PG_PREFIX.match(pg)
            if not m:
                continue

            ts, host, usr, db_name, pid, sev, message = m.groups()
            total_scanned += 1

            # Hard filters first (cheap)
            if sev_set and sev not in sev_set:
                continue
            if db   and db_name != db:
                continue
            if user and usr != user:
                continue
            if node and nd != node:
                continue

            txt = (message + ' ' + usr + ' ' + db_name + ' ' + nd + ' ' + sev + ' ' + pid).lower()

            if exc_terms and any(_match_term(txt, t) for t in exc_terms):
                continue
            if q_ast and not _eval_node(q_ast, txt):
                continue

            total_matched += 1
            entry = {'ts': ts, 'host': host, 'user': usr, 'db': db_name,
                     'pid': pid, 'severity': sev, 'msg': message[:500], 'node': nd, 'sql': ''}

            # Capture SQL for duration lines
            dm = DURATION_RE.search(message)
            if dm:
                inline = (dm.group(2) or '').strip()
                entry['sql'] = inline
                cur_entry = entry
                sql_lines = [inline] if inline else []
                collecting_sql = True

            if total_matched <= limit:
                results.append(entry)

    if collecting_sql:
        flush()

    return {
        'results':       results,
        'total_matched': total_matched,
        'total_scanned': total_scanned,
        'limited':       total_matched > limit,
    }


def search_pid(filepath: str, pid: str, limit: int = 500) -> list:
    """Return all log entries for a given PID in chronological order."""
    entries = []
    collecting_sql = False
    sql_lines = []
    cur_entry = None

    def flush():
        nonlocal collecting_sql, sql_lines, cur_entry
        if cur_entry and collecting_sql:
            cur_entry['sql'] = '\n'.join(sql_lines).strip()
        collecting_sql = False; sql_lines = []; cur_entry = None

    with open(filepath, 'r', errors='replace', buffering=1 << 20) as fh:
        for raw in fh:
            line = raw.rstrip('\n')
            if collecting_sql and (line.startswith('\t') or
                    (line.startswith('  ') and not line.startswith('  EVENTS'))):
                sql_lines.append(line.strip()); continue
            if collecting_sql: flush()
            if not line.startswith('EVENTS\t'): continue
            parts = line.split('\t', 5)
            if len(parts) < 5: continue
            nd, pg = parts[3], parts[4]
            m = PG_PREFIX.match(pg)
            if not m: continue
            ts, host, usr, db_name, p, sev, message = m.groups()
            if p != pid: continue
            entry = {'ts': ts, 'host': host, 'user': usr, 'db': db_name,
                     'pid': p, 'severity': sev, 'msg': message[:500], 'node': nd, 'sql': ''}
            dm = DURATION_RE.search(message)
            if dm:
                inline = (dm.group(2) or '').strip()
                entry['sql'] = inline
                cur_entry = entry
                sql_lines = [inline] if inline else []
                collecting_sql = True
            if len(entries) < limit:
                entries.append(entry)
    if collecting_sql: flush()
    entries.sort(key=lambda e: e['ts'])
    return entries
