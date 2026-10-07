#!/bin/bash
# Quota helper over CodexBar, cached so repeat calls are instant and token-free.
#   quota.sh [codex|claude|agy|gemini|gpt|both] full summary
#   quota.sh --brief                    one line, flags only tight windows
#   quota.sh --gate <provider> [N]      exit 0 ok, 1 tight (>=N% or pace-ahead), 2 stop (>=95%); default N=80
#                                       provider: codex | claude | agy | gemini | gpt
#   quota.sh --line [--remaining]       compact status-line text; never blocks (refreshes cache in background)
#                                       X=codex C=claude Ag=agy:gemini Ac=agy:gpt; --remaining (or QUOTA_SHOW=remaining) shows % left instead of % used
#   quota.sh --wait <provider>          sleep (no tokens) until any >=95% window resets, then re-check; exit 3 if wait > QUOTA_MAX_WAIT
#   quota.sh --refresh                  force refresh (single-flight: exits 1 if another refresh holds the lock)
# Line extras: color by % used (green <QUOTA_WARN=60, yellow <QUOTA_CRIT=80, red above; QUOTA_COLOR=0 off) and a
#   'Model ctx N%' prefix from Claude Code's stdin JSON (QUOTA_SESSION=0 off; QUOTA_STDIN_DUMP=/path saves the raw JSON to inspect fields).
#   Flags (--line): per window, ! = >=80% used, pace balance + / ++ = behind / far behind (headroom), - / -- = ahead / far ahead (overspending). QUOTA_FLAGS=combined restores one ! per provider; QUOTA_GATE_PACE=0 hides the pace flags.
# Expiry notice (--line): a window resetting soon gets a suffix like 41%@1h20 (or @45m); QUOTA_EXPIRY_MARK changes the '@'.
#   QUOTA_EXPIRY_SHORT minutes for the 5h window (default 120); QUOTA_EXPIRY_LONG for weekly (default 1440); 0 disables a class; QUOTA_EXPIRY=0 disables all.
# Env: QUOTA_LOCK_TTL seconds before a refresh lock counts as stuck and is reclaimed (default 120); QUOTA_SHOW (used|remaining, default used); QUOTA_TTL seconds (default 300); QUOTA_SOURCE (default cli: avoids Keychain/cookie prompts in cron/-p runs, falls back to auto);
#      QUOTA_MAX_WAIT seconds (default 21600); QUOTA_BUFFER seconds after reset (default 60)
DIR="$(cd "$(dirname "$0")" && pwd)"
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/codexbar-quota/both.json"
TTL="${QUOTA_TTL:-300}"
mkdir -p "$(dirname "$CACHE")"

age() { [ -f "$CACHE" ] && echo $(( $(date +%s) - $(stat -f %m "$CACHE") )) || echo 999999; }
# Single-flight lock (mkdir is atomic; macOS has no flock). Holder pid is stored inside.
# A lock is reclaimed when its holder is dead or it is older than QUOTA_LOCK_TTL (default 120s);
# a stuck holder is killed (with its codexbar children) before the lock is taken over.
LOCK="${CACHE%/*}/refresh.lock"
# Attempt stamp: touched on every refresh attempt so a failing codexbar is retried at most once per TTL (cache mtime only moves on success).
ATTEMPT="${CACHE%/*}/last_attempt"
attempt_age() { [ -f "$ATTEMPT" ] && echo $(( $(date +%s) - $(stat -f %m "$ATTEMPT") )) || echo 999999; }
due() { [ "$(age)" -gt "$TTL" ] && [ "$(attempt_age)" -gt "$TTL" ]; }
LOCK_TTL="${QUOTA_LOCK_TTL:-120}"
lock_age() { echo $(( $(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || date +%s) )); }
acquire() {
  mkdir "$LOCK" 2>/dev/null && { echo $$ > "$LOCK/pid"; return 0; }
  local pid; pid=$(cat "$LOCK/pid" 2>/dev/null)
  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    [ "$(lock_age)" -gt 5 ] || return 1   # grace: holder may not have written its pid yet
  elif [ "$(lock_age)" -gt "$LOCK_TTL" ]; then
    pkill -P "$pid" 2>/dev/null; kill "$pid" 2>/dev/null
  else
    return 1
  fi
  rm -rf "$LOCK"
  mkdir "$LOCK" 2>/dev/null && { echo $$ > "$LOCK/pid"; return 0; }
  return 1
}
refresh() {
  acquire || return 1
  trap 'rm -rf "$LOCK" "$CACHE.$$" "$CACHE.agy.$$"' EXIT
  touch "$ATTEMPT"
  _refresh
}
_refresh() {
  local tmp="$CACHE.$$" agy="$CACHE.agy.$$"
  for src in "${QUOTA_SOURCE:-cli}" auto; do
    if codexbar usage --provider both --source "$src" --format json 2>/dev/null > "$tmp" && [ -s "$tmp" ]; then
      # antigravity (agy) is best-effort: merge it in if available, otherwise keep claude/codex only
      if codexbar usage --provider antigravity --source "$src" --format json 2>/dev/null > "$agy" && [ -s "$agy" ]; then
        /usr/bin/python3 -c 'import json,sys; a=json.load(open(sys.argv[1])); b=json.load(open(sys.argv[2])); json.dump(a+b,open(sys.argv[1],"w"))' "$tmp" "$agy" 2>/dev/null
      fi
      rm -f "$agy"; mv "$tmp" "$CACHE"; return 0
    fi
  done
  rm -f "$tmp" "$agy"; return 1
}
ensure() { due && refresh; [ -s "$CACHE" ]; }
# stale = cache older than 2x TTL even after trying to refresh
py() { QUOTA_STALE_MIN=$(( $(age) / 60 )) QUOTA_STALE=$([ "$(age)" -gt $(( TTL * 2 )) ] && echo 1 || echo 0) /usr/bin/python3 "$DIR/summarize.py" "$@" < "$CACHE"; }

case "$1" in
  --refresh) refresh; exit $? ;;
  --line)
    if due; then ( "$0" --refresh >/dev/null 2>&1 & ); fi
    [ "$2" = "--remaining" ] && export QUOTA_SHOW=remaining
    # Claude Code pipes session JSON (model, context window, ...) on stdin; never block waiting for it.
    if [ ! -t 0 ]; then QUOTA_STDIN="$(cat)"; export QUOTA_STDIN; fi
    [ -n "$QUOTA_STDIN_DUMP" ] && printf '%s\n' "$QUOTA_STDIN" > "$QUOTA_STDIN_DUMP"
    [ -s "$CACHE" ] && py line || echo "quota:?"
    ;;
  --brief) ensure || { echo "quota: unavailable"; exit 0; }; py brief ;;
  --gate)
    ensure || exit 0   # fail open: no data should not block work
    py gate "${2:?provider}" "${3:-80}"
    ;;
  --wait)
    P="${2:?provider}"
    ensure || exit 0
    SECS=$(py wait "$P" "${QUOTA_BUFFER:-60}")
    [ "${SECS:-0}" -le 0 ] && { echo "OK $P"; exit 0; }
    if [ "$SECS" -gt "${QUOTA_MAX_WAIT:-21600}" ]; then
      echo "WAIT too long: $P resets in $((SECS/60))m (max $(( ${QUOTA_MAX_WAIT:-21600}/60 ))m)"; exit 3
    fi
    echo "sleeping ${SECS}s until $P resets" >&2
    sleep "$SECS"; refresh
    py gate "$P" 95
    ;;
  *)
    ensure || { echo "codexbar returned no data (is CodexBar signed in?)" >&2; exit 1; }
    py full "${1:-both}"
    ;;
esac
