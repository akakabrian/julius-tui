# DOGFOOD — julius

_Session: 2026-04-23T14:40:37, driver: pty, duration: 1.5 min_

**PASS** — ran for 1.2m, captured 8 snap(s), 1 milestone(s), 0 blocker(s), 0 major(s).

## Summary

Ran a rule-based exploratory session via `pty` driver. Found no findings worth flagging. Game reached 30 unique state snapshots. Captured 1 milestone shot(s); top candidates promoted to `screenshots/candidates/`.

## Findings

### Blockers

_None._

### Majors

_None._

### Minors

_None._

### Nits

_None._

### UX (feel-better-ifs)

_None._

## Coverage

- Driver backend: `pty`
- Keys pressed: 662 (unique: 63)
- State samples: 77 (unique: 30)
- Score samples: 0
- Milestones captured: 1
- Phase durations (s): A=42.0, B=22.3, C=9.0
- Snapshots: `/home/brian/AI/projects/tui-dogfood/reports/snaps/julius-20260423-143922`

Unique keys exercised: +, ,, -, ., /, 0, 1, 2, 3, 4, 5, :, ;, =, ?, H, R, [, ], a, b, backspace, c, ctrl+l, d, delete, down, end, enter, escape, f, f1, f2, g, h, home, j, k, l, left ...

## Milestones

| Event | t (s) | Interest | File | Note |
|---|---|---|---|---|
| first_input | 0.4 | 0.0 | `julius-20260423-143922/milestones/first_input.txt` | key=up |
