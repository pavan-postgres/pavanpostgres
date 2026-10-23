#!/usr/bin/env bash
# tests/test.sh - run: bash tests/test.sh     (SH=/bin/bash bash tests/test.sh to pick the shell under test)
# Uses a private tmux socket and a temp folder; touches nothing else.
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd); SH="${SH:-bash}"; T="$ROOT/tlogs"
W=$(mktemp -d "${TMPDIR:-/tmp}/tlogs-test.XXXXXX"); cd "$W" || exit 1
export TL_NO_ATTACH=1 TMUX_TMPDIR="$W" XDG_CONFIG_HOME="$W/cfg" HOME="$W"; unset TMUX
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "ok   $1"; }
bad() { fail=$((fail+1)); echo "FAIL $1"; [ -n "${2:-}" ] && printf '     %s\n' "$2"; }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1" "expected [$3] got [$2]"; fi; }
ESC=$(printf '\033')
echo "shell: $("$SH" -c 'echo $BASH_VERSION')   tmux: $(tmux -V 2>/dev/null || echo none)"

# --- colours (postgres levels)
c() { printf '%s\n' "$1" | "$SH" "$T" color; }
check "ERROR red"       "$(c '2026-10-12 10:00:03 UTC [1]: ERROR:  boom')"      "${ESC}[1;31m2026-10-12 10:00:03 UTC [1]: ERROR:  boom${ESC}[0m"
check "FATAL red"       "$(c 'x FATAL:  y' | cut -c1-8)"                       "${ESC}[1;31mx"
check "WARNING amber"   "$(c 'x WARNING:  y')"                                 "${ESC}[38;5;214mx WARNING:  y${ESC}[0m"
check "NOTICE yellow"   "$(c 'x NOTICE:  y')"                                  "${ESC}[33mx NOTICE:  y${ESC}[0m"
check "LOG plain"       "$(c 'x LOG:  checkpoint starting')"                   "x LOG:  checkpoint starting"
check "pg_upgrade ok"   "$(c 'Upgrade Complete')"                              "${ESC}[32mUpgrade Complete${ESC}[0m"
check "word highlight"  "$(printf 'a ERROR: b\n' | TL_HIGHLIGHT=word "$SH" "$T" color)" "a ${ESC}[1;31mERROR:${ESC}[0m b"
check "user rule"       "$(printf 'disk 91%%\n' | TL_RED_RE='disk 9[0-9]%' "$SH" "$T" color)" "${ESC}[1;31mdisk 91%${ESC}[0m"
check "rule off"        "$(printf 'x ERROR: y\n' | TL_RED_RE='' "$SH" "$T" color)" "x ERROR: y"
check "icase"           "$(printf 'oops error\n' | TL_ICASE=1 TL_RED_RE='ERROR' "$SH" "$T" color)" "${ESC}[1;31moops error${ESC}[0m"
check "NO_COLOR"        "$(printf 'x ERROR: y\n' | NO_COLOR=1 "$SH" "$T" color)" "x ERROR: y"
printf 'TL_RED_RE=BOOM\n' > p.conf
check "color -c FILE"   "$(printf 'x BOOM y\n' | "$SH" "$T" color -c p.conf)" "${ESC}[1;31mx BOOM y${ESC}[0m"
check "-c FILE color"   "$(printf 'x BOOM y\n' | "$SH" "$T" -c p.conf color)" "${ESC}[1;31mx BOOM y${ESC}[0m"
check "color bad config" "$(printf 'x\n' | "$SH" "$T" color -c nope.conf 2>&1)" "tlogs: no such config: nope.conf"
rm -f p.conf
check "special chars"   "$(printf 'a & b \\ c ERROR: d\n' | TL_HIGHLIGHT=word "$SH" "$T" color)" "a & b \\ c ${ESC}[1;31mERROR:${ESC}[0m d"

# --- states
printf 'Checking ok\nUpgrade Complete\n'            > a-ok.log
printf 'WARNING: x\nUpgrade Complete\n'             > b-warn.log
printf 'check fatal\nFailure, exiting\n'            > c-fail.log
printf 'Copying files\n'                            > d-run.log
printf 'name with space\n'                          > 'e run.log'
out=$("$SH" "$T" -l | sed "s/${ESC}\[[0-9;]*m//g")
check "list"   "$(printf '%s\n' "$out" | awk '{print $1}' | tr '\n' ' ')" "DONE WARN FAILED RUNNING RUNNING running: "
check "counts" "$(printf '%s\n' "$out" | tail -1)" "running: 2  done: 1  warn: 1  failed: 1  (of 5)"

# --- config file: parsed, never executed; env wins over file
printf "TL_GLOB='*.txt'\nTL_RED_RE=\$(touch PWNED)\nEVIL=\$(touch PWNED2)\nexport TL_DONE_GRACE=7\n" > .tlogs.conf
cfg=$("$SH" "$T" config 2>/dev/null)
check "no exec"      "$(ls PWNED PWNED2 2>/dev/null | wc -l | tr -d ' ')" "0"
check "file value"   "$(printf '%s\n' "$cfg" | grep '^TL_GLOB=')" "TL_GLOB=*.txt"
check "export form"  "$(printf '%s\n' "$cfg" | grep '^TL_DONE_GRACE=')" "TL_DONE_GRACE=7"
check "env wins"     "$(TL_GLOB='*.log' "$SH" "$T" config 2>/dev/null | grep '^TL_GLOB=')" "TL_GLOB=*.log"
rm -f .tlogs.conf
"$SH" "$T" init >/dev/null; [ -s "$W/cfg/tlogs/config" ] && ok "init writes config" || bad "init writes config"
cp "$W/cfg/tlogs/config" k; "$SH" "$T" init >/dev/null; cmp -s k "$W/cfg/tlogs/config" && ok "init never overwrites" || bad "init never overwrites"
a=$("$SH" "$T" config); rm -rf "$W/cfg"; check "init config round-trips" "$a" "$("$SH" "$T" config)"

# --- tmux
if command -v tmux >/dev/null 2>&1; then
  tmux new-session -d -s other 'sleep 120'          # an unrelated session, started first
  g0=$(tmux show -g -v mouse)                       # global value before tlogs (may be on via a system tmux.conf)
  "$SH" "$T" -n s1 >/dev/null 2>&1
  check "one pane per log" "$(tmux list-panes -t s1:logs | wc -l | tr -d ' ')" "5"
  check "pane state marks" "$(tmux list-panes -t s1:logs -F '#{@st}' | sort | tr '\n' ' ')" "DONE FAILED RUNNING RUNNING WARN "
  check "mouse on in tlogs session" "$(tmux show -t s1 -v mouse)" "on"
  check "other sessions untouched" "$(tmux show -t other mouse)" ""
  check "global mouse unchanged" "$(tmux show -g -v mouse)" "$g0"
  TL_MOUSE=0 "$SH" "$T" -n s4 >/dev/null 2>&1
  check "TL_MOUSE=0 keeps it off" "$(tmux show -t s4 -v mouse)" "off"
  "$SH" "$T" -e -n s2 >/dev/null 2>&1
  check "-e issues only" "$(tmux list-panes -t s2:logs -F '#{@tl_file}' | sort | tr '\n' ' ')" "b-warn.log c-fail.log "
  TL_WATCH_SEC=1 TL_DONE_GRACE=1 "$SH" "$T" -rw -n s3 >/dev/null 2>&1; s3name=s3
  check "watch pane titled" "$(tmux list-panes -t s3:tl-watch -F '#{pane_title}')" "tl-watch"
  check "full session name in status" "$(tmux show -t s3 -v status-left-length)" "$(( ${#s3name} + 4 ))"
  check "-r running only" "$(tmux list-panes -t s3:logs | wc -l | tr -d ' ')" "2"
  printf 'started\n' > f-new.log; sleep 3
  check "-w adds new log" "$(tmux list-panes -t s3:logs -F '#{@tl_file}' | grep -c f-new.log)" "1"
  printf 'Upgrade Complete\n' >> d-run.log; sleep 5
  check "-w closes DONE" "$(tmux list-panes -t s3:logs -F '#{@tl_file}' | grep -c d-run.log)" "0"
  check "-w keeps others" "$(tmux list-panes -t s3:logs | wc -l | tr -d ' ')" "2"
  sleep 1; fp=$(tmux list-panes -t s1:logs -F '#{pane_id} #{@tl_file}' | awk '$2=="c-fail.log"{print $1}')
  tmux capture-pane -p -e -t "$fp" | grep -q "31mFailure, exiting" && ok "pane lines coloured" || bad "pane lines coloured"
  printf 'n\n' | "$SH" "$T" kill s1 >/dev/null 2>&1; tmux has-session -t s1 2>/dev/null && ok "kill asks first" || bad "kill asks first"
  printf 'y\ns1\n' | "$SH" "$T" kill s1 >/dev/null 2>&1; tmux has-session -t s1 2>/dev/null && bad "kill after 2 confirmations" || ok "kill after 2 confirmations"
  [ -f a-ok.log ] && ok "logs untouched" || bad "logs untouched"
  tmux kill-server 2>/dev/null
else echo "skip tmux tests (tmux not installed)"; fi

cd / && rm -rf "$W"
echo "passed: $pass  failed: $fail"; [ "$fail" = 0 ]
