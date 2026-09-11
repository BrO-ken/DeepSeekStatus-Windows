# 🐳 DeepSeek Status for Windows 11

Windows adaptation of [DeepSeekStatus](https://github.com/owenzhao/DeepSeekStatus) (macOS, MIT © Zhao Xin):
a whale living in your **system tray** that tells you at a glance whether DeepSeek API is in
**peak** (awake blue whale) or **off-peak** (sleepy gray whale) pricing, with a dark Fluent-style
details panel.

## Pricing rule — verified against the official docs

Source: [api-docs.deepseek.com/quick_start/pricing](https://api-docs.deepseek.com/quick_start/pricing)
(checked on 2026-09-11) — *“Off-peak rates are half of the peak rates. Peak hours are
01:00 - 04:00 and 06:00 - 10:00 UTC, Monday through Friday”*.

| Beijing time (UTC+8) | UTC | Period | Price |
|---|---|---|---|
| Mon–Fri 09:00–12:00 | 01:00–04:00 | Peak | 100 % |
| Mon–Fri 12:00–14:00 | 04:00–06:00 | Off-peak | 50 % |
| Mon–Fri 14:00–18:00 | 06:00–10:00 | Peak | 100 % |
| Evenings, nights, weekends | — | Off-peak | 50 % |

- **Half-open ranges**: at 12:00 and 18:00 sharp you are already off-peak; at 09:00 sharp
  you are already peak.
- The decision is **always made in Beijing time** (no daylight saving), whatever your PC's
  timezone is. Public holidays are not part of the rule (same as DeepSeek's own rule).

## Features

- 🐳 Tray icon: blue during peak hours, gray during off-peak hours.
- Persistent tooltip: period + countdown (“… · 02:31:05 until 12:00”).
- Panel (left-click the whale): animated aquarium (swimming / sleeping whale), giant countdown,
  progress through the current block, ×1.0 / ×0.5 price bars, **7×24 weekly heat map**,
  timezone note.
- **Resizable panel**: drag the bottom-right grip; the size is clamped to the screen,
  the panel stays anchored bottom-right, and the size is remembered across sessions.
- **Preview mode**: force the peak / off-peak display (never affects the real computation).
- **Start with Windows** (opt-in, `HKCU\...\Run`).
- The panel hides itself when it loses focus — the tray whale keeps running in the background.
- Single instance, no network access, no account, no data collection.

## Usage

- **Left-click** the whale: show the panel.
- **Right-click**: preview, start with Windows, quit.
- **Esc**, ✕, or clicking outside: hide the panel.
- **Bottom-right grip**: drag to resize the panel.

## Run

- From sources: `venv\Scripts\python app.py` (or `DeepSeek Status.cmd`).
- Flags: `--show` (open the panel at start), `--preview peak|offPeak` (temporary preview),
  `--selftest` (run the built-in UI diagnostics).

## Verify the pricing rule

```
venv\Scripts\python tests\test_schedule.py
```

42 checks: boundaries 08:59/09:00/11:59/12:00/13:59/14:00/17:59/18:00, weekends,
the Friday-evening-to-Monday-morning span, timezone independence (UTC/New York/Tokyo),
hour-by-hour conformance with the official UTC rule, progress through the block.

## Build the executable

```
Tools\build_exe.cmd        → dist\DeepSeekStatus.exe
```

## Credits

- Original macOS project: [owenzhao/DeepSeekStatus](https://github.com/owenzhao/DeepSeekStatus) (MIT).
- The whale is DeepSeek's official mark, drawn from the
  [Simple Icons](https://simpleicons.org/) vector (CC0). Unofficial project, not affiliated
  with or endorsed by DeepSeek.
- MIT license (see `LICENSE`).
