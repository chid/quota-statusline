#!/bin/bash
# Quota-aware fallback routing across claude / codex / opencode. No model tokens spent on the decision.
#   route.sh [opts] "prompt"        run prompt on the first backend with headroom
#   echo "prompt" | route.sh [opts] read prompt from stdin
# Opts:
#   --order claude,codex,opencode   preference order (default; env ROUTE_ORDER)
#   --threshold N                   gate % (default 80; env ROUTE_THRESHOLD)
#   --dry-run                       print the chosen backend name only, run nothing
#   --pace                          also treat "on pace to run out before reset" as tight (default off for routing; env ROUTE_PACE=1)
#   --wait                          if none has headroom, sleep (no tokens) until the first metered backend in --order resets, then retry once (exit 3 if too long)
# Env: OPENCODE_MODEL (default opencode/big-pickle, a free model), CLAUDE_BIN, CODEX_BIN,
#      ROUTE_CLAUDE_ARGS / ROUTE_CODEX_ARGS / ROUTE_OPENCODE_ARGS (extra flags, e.g. permission mode)
# opencode has no quota feed in CodexBar here, so it is treated as always available: keep it last.
DIR="$(cd "$(dirname "$0")" && pwd)"
ORDER="${ROUTE_ORDER:-claude,codex,opencode}"; TH="${ROUTE_THRESHOLD:-80}"; DRY=0; WAIT=0; export QUOTA_GATE_PACE="$([ "${ROUTE_PACE:-0}" = 1 ] && echo 1 || echo 0)"
while [ $# -gt 0 ]; do
  case "$1" in
    --order) ORDER="$2"; shift 2 ;;
    --threshold) TH="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    --pace) export QUOTA_GATE_PACE=1; shift ;;
    --wait) WAIT=1; shift ;;
    --) shift; break ;;
    *) break ;;
  esac
done
PROMPT="$*"; [ -z "$PROMPT" ] && [ ! -t 0 ] && PROMPT="$(cat)"
[ -z "$PROMPT" ] && [ "$DRY" = 0 ] && { echo "route.sh: no prompt" >&2; exit 64; }

pick() {
  local b msg
  for b in ${ORDER//,/ }; do
    case "$b" in
      claude|codex)
        msg=$("$DIR/quota.sh" --gate "$b" "$TH") && { echo "$b"; return 0; }
        echo "route: skip $b: ${msg//$'\n'/; }" >&2 ;;
      opencode) command -v opencode >/dev/null && { echo opencode; return 0; } ;;
      *) echo "route: unknown backend $b" >&2 ;;
    esac
  done
  return 1
}

B=$(pick)
if [ -z "$B" ] && [ "$WAIT" = 1 ]; then
  for first in ${ORDER//,/ }; do [ "$first" != opencode ] && break; done
  "$DIR/quota.sh" --wait "$first" >&2 || exit $?
  B=$(pick)
fi
[ -z "$B" ] && { echo "route: no backend with headroom (order: $ORDER)" >&2; exit 2; }
echo "route: using $B" >&2
[ "$DRY" = 1 ] && { echo "$B"; exit 0; }
case "$B" in
  claude)   exec "${CLAUDE_BIN:-$HOME/.local/bin/claude}" -p $ROUTE_CLAUDE_ARGS "$PROMPT" </dev/null ;;
  codex)    exec "${CODEX_BIN:-codex}" exec $ROUTE_CODEX_ARGS "$PROMPT" </dev/null ;;
  opencode) exec opencode run -m "${OPENCODE_MODEL:-opencode/big-pickle}" $ROUTE_OPENCODE_ARGS "$PROMPT" </dev/null ;;
esac
