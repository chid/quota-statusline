---
name: codexbar-quota
description: Check Codex, Claude, and Antigravity (Gemini and Claude/GPT) usage quotas (session/5h and weekly windows, pace, reset times, Codex reset credits) via CodexBar, and gate runs on remaining quota. Use when asked about remaining quota/rate limits/usage, or before launching long, batch, looped or subagent-heavy work.
---

# CodexBar quota (cached, token-cheap)

All calls share one cache (`~/.cache/codexbar-quota/both.json`, TTL 300s, `QUOTA_TTL` to change). A cold fetch takes ~13s; cached calls are ~0.04s.

```bash
# Using quota-line (installed on PATH) or direct script:
S="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$0")")}/scripts/quota.sh"
[ -f "$S" ] || S="quota-line"

# Quick commands:
quota.sh --brief                                   # one line: "quota: codex 5h/wk 2%/25%! claude 5h/wk 32%/37% agy:gemini 5h/wk ... agy:gpt 5h/wk ..."
quota.sh --gate <claude|codex|agy|gemini|gpt> [N] # exit 0 OK, 1 TIGHT (>=N% default 80, or pace ahead), 2 STOP (>=95%); fails open if no data
quota.sh [codex|claude|agy|gemini|gpt]            # full detail incl. pace and Codex reset credits (use only when asked)
quota.sh --line                                    # status-line text (non-blocking)
quota.sh --wait <provider>                         # sleep in shell until a >=95% window resets (+60s), re-check; exit 3 if wait > QUOTA_MAX_WAIT (6h)
quota.sh --refresh                                 # force refresh
```

Source is `cli` by default (`QUOTA_SOURCE`), which avoids Keychain/cookie prompts in cron and `-p` runs; falls back to `auto`. If the cache is >2x TTL old and refresh fails, output is tagged `(STALE Nm)` (status line shows trailing `~`): treat stale numbers as unreliable.

## Fallback routing (claude → codex → opencode)

```bash
R="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$0")")}/scripts/route.sh"
$R "prompt"                                  # runs on first backend under the threshold (default 80% used)
$R --dry-run "x"                             # just print the chosen backend
$R --order gemini,claude,codex --threshold 70 "prompt"
$R --pace "prompt"                           # also skip a backend that is on pace to run out before reset
$R --wait "prompt"                           # nothing free: sleep in shell until the first metered backend resets, retry once
echo "prompt" | $R
```

Backends: `claude -p`, `codex exec`, `agy`, `opencode run -m $OPENCODE_MODEL` (default free `opencode/big-pickle`). Exit 2 = no backend had headroom. Extra flags via `ROUTE_CLAUDE_ARGS` / `ROUTE_CODEX_ARGS` / `ROUTE_AGY_ARGS` / `ROUTE_OPENCODE_ARGS`.

## Token discipline
- Default to `--brief`. Never dump the raw JSON from `codexbar` into context.
- Check once before a long job and at major checkpoints, not per step.
- In scripts/loops/cron, gate in shell so the model never sees it:
  `quota.sh --gate claude 80 && claude -p "..."`
  or to ride out a limit: `quota.sh --wait claude && claude -p "..."`
- On TIGHT: prefer a smaller model, fewer subagents, or defer. On STOP: defer until the reset time in the gate message.
- Codex reset credits (free full resets) are in the full output; mention them if Codex is tight.

The status line (`settings.json` → `statusLine`) shows `X:<5h>/<wk>% C:<5h>/<wk>% Ag:<5h>/<wk>% Ac:<5h>/<wk>%` (X=Codex, C=Claude, Ag=Antigravity Gemini, Ac=Antigravity Claude/GPT, `!` = tight) at zero token cost.

## Troubleshooting
`codexbar usage --help` for providers, `--all-accounts`, `--source oauth|web|cli`. "Code review remaining" only appears with `--source web`. Never print tokens/cookies from the CodexBar config.
