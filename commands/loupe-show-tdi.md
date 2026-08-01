---
description: Show the Technical Debt Index trend - findings per turn, direction against the previous turn, and lifetime total
user_invocable: true
---

# Loupe Show TDI

Run the TDI report from the current project directory:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/show_tdi.py"
```

Relay the output as-is. It shows:

- **latest turn**: findings produced by the most recent turn that produced any, and whether that is `worse`, `better`, or `unchanged` against the turn before it.
- **lifetime**: total findings across every recorded turn.
- **last N turns**: one line per turn with its timestamp, total, and per-category breakdown.

How to read it honestly:

- Entries are appended at `Stop`, and **only for turns that produced findings**. A clean turn records nothing, so the history is a log of debt events, not a time series with zeros.
- An empty history therefore means either "nothing found yet" or "loupe never ran here". The output says so rather than implying zero debt. `/loupe-check-health` distinguishes the two.
- Counts are **unweighted** on purpose: a weighting formula would need tuning nobody has data for yet, and raw counts trend honestly from the first entry. Do not present a category total as a severity score.
