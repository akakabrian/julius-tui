# DOGFOOD — julius

_Session: 2026-04-23T13:21:28, driver: pty, duration: 3.0 min_

**PASS** — ran for 1.9m, captured 11 snap(s), 1 milestone(s), 0 blocker(s), 0 major(s).

## Summary

Ran a rule-based exploratory session via `pty` driver. Found no findings worth flagging. Game reached 40 unique state snapshots. Captured 1 milestone shot(s); top candidates promoted to `screenshots/candidates/`. 1 coverage note(s) — see Coverage section.

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
- Keys pressed: 979 (unique: 50)
- State samples: 76 (unique: 40)
- Score samples: 0
- Milestones captured: 1
- Phase durations (s): A=81.3, B=17.4, C=18.0
- Snapshots: `/home/brian/AI/projects/tui-dogfood/reports/snaps/julius-20260423-131929`

Unique keys exercised: ,, -, /, 0, 2, 3, 4, 5, :, ;, ?, H, R, ], backspace, c, ctrl+l, delete, down, enter, escape, f, f1, f2, g, h, home, k, l, left, m, n, o, p, page_down, page_up, q, question_mark, r, right ...

### Coverage notes

- **[CN1] Phase B exited early due to saturation**
  - State hash unchanged for 10 consecutive samples during the stress probe; remaining keys skipped.

## Milestones

| Event | t (s) | Interest | File | Note |
|---|---|---|---|---|
| first_input | 0.4 | 0.0 | `julius-20260423-131929/milestones/first_input.txt` | key=up |
