# Changelog

## 2.1.2
- Pane labels always keep their state colour (a FAILED pane stays red when you select it); the active pane is marked with `>`.
- README: animated demo (`docs/demo.gif`), recorded from a real tlogs run.

## 2.1.1
- The watch window's pane is titled `tl-watch` (was the host name).
- Status bar shows the full session name instead of cutting it at 10 characters.

## 2.1.0
- Mouse support in tlogs sessions only (`TL_MOUSE=1`, default): click a pane, scroll back, drag borders, right-click menu with Zoom. Other tmux sessions and `~/.tmux.conf` are not changed. `TL_MOUSE=0` for keyboard only.
- CI workflow now lives at the repo root and tests the `tlogs/` folder on Ubuntu and macOS (system bash 3.2).
- 36 tests.

## 2.0.0
- Standalone public release: one script, user-defined colour rules (red / amber / yellow / green / blue / dim), log states (RUNNING / DONE / WARN / FAILED), presets for PostgreSQL, pg_upgrade, RDS/Aurora downloads and batch jobs.
- Config files are parsed as data, never executed.
