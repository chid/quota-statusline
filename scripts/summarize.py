import json, os, sys
import time
from datetime import datetime

mode = sys.argv[1]
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0 if mode in ("gate", "line", "brief") else "bad cache")

def loc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone().strftime("%a %b %d %H:%M")

STALE = os.environ.get("QUOTA_STALE") == "1"
STALE_MIN = os.environ.get("QUOTA_STALE_MIN", "?")
STALE_TAG = f" (STALE {STALE_MIN}m)" if STALE else ""

SHORT = {"codex": "X", "claude": "C", "antigravity": "A"}
REMAINING = os.environ.get("QUOTA_SHOW") == "remaining"

# Expiry notice: flag a window whose reset is near. Thresholds in minutes; 0 disables that class.
#   QUOTA_EXPIRY_SHORT  windows <= 6h (the "5h" session window)  default 120 (2h)
#   QUOTA_EXPIRY_LONG   longer windows (weekly)                  default 1440 (24h)
#   QUOTA_EXPIRY=0      disable entirely
def _num(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)

EXPIRY_MARK = os.environ.get("QUOTA_EXPIRY_MARK", "@")  # ASCII default: ⏱ renders double-width/overlapping in many terminal fonts

def expiry_tag(w):
    if os.environ.get("QUOTA_EXPIRY", "1") == "0" or not w.get("resetsAt"):
        return ""
    limit = _num("QUOTA_EXPIRY_SHORT", 120) if (w.get("windowMinutes") or 0) <= 360 else _num("QUOTA_EXPIRY_LONG", 1440)
    mins = (datetime.fromisoformat(w["resetsAt"].replace("Z", "+00:00")).timestamp() - time.time()) / 60
    if limit <= 0 or mins <= 0 or mins >= limit:
        return ""
    return f"{EXPIRY_MARK}{int(mins // 60)}h{int(mins % 60):02d}" if mins >= 60 else f"{EXPIRY_MARK}{int(mins)}m"
def windows(p):
    u = p.get("usage") or {}
    pace = p.get("pace") or {}
    for k in ("primary", "secondary"):
        w = u.get(k)
        if w:
            yield k, w, pace.get(k) or {}

USE_PACE = os.environ.get("QUOTA_GATE_PACE", "1") != "0"

def tight(w, pace, n=80):
    return w["usedPercent"] >= n or (USE_PACE and pace.get("stage") in ("ahead", "farAhead"))

if mode == "full":
    want = sys.argv[2]
    for p in data:
        name = p.get("provider")
        if want != "both" and name != want:
            continue
        if p.get("error"):
            print(f"== {name}: ERROR {p['error']}")
            continue
        u = p.get("usage", {})
        labels = p.get("rateWindowLabels", {})
        print(f"== {name} ({u.get('loginMethod', '?')}) {u.get('accountEmail', '')} [source={p.get('source')}]")
        for k, w, pace in windows(p):
            flag = " !!" if tight(w, pace) else ""
            print(f"  {labels.get(k, k):8} {w['usedPercent']:3.0f}% used, resets {loc(w['resetsAt'])}{flag}")
            if pace.get("summary"):
                print(f"           pace: {pace['summary']}")
        rc = u.get("codexResetCredits")
        if rc:
            print(f"  reset credits available: {rc.get('availableCount')}")
            for c in rc.get("credits", []):
                if c.get("status") == "available":
                    print(f"    - {c['title']} (expires {loc(c['expires_at'])})")
        cr = p.get("credits")
        if cr and cr.get("balanceReadSucceeded"):
            print(f"  credits remaining: {cr.get('remaining')}")

elif mode in ("brief", "line"):
    LINE = mode == "line"
    SPLIT = LINE and os.environ.get("QUOTA_FLAGS", "split") != "combined"  # QUOTA_FLAGS=combined restores the single per-provider "!"
    # Color by % used: green < WARN, yellow < CRIT, red >= CRIT. QUOTA_COLOR=0 disables.
    COLOR = LINE and os.environ.get("QUOTA_COLOR", "1") != "0"
    WARN, CRIT = _num("QUOTA_WARN", 60), _num("QUOTA_CRIT", 80)
    def paint(text, used):
        if not COLOR:
            return text
        code = 31 if used >= CRIT else 33 if used >= WARN else 32
        return f"\033[{code}m{text}\033[0m"

    parts = []
    for p in data:
        name = p.get("provider")
        ws = list(windows(p))
        if not ws:
            continue
        def flags(w, pc):
            # split: "!" = >=80% used. Pace is a budget balance: "+"/"++" = behind / far behind pace (headroom),
            # "-"/"--" = ahead / far ahead (overspending). Marked per window; QUOTA_GATE_PACE=0 hides pace.
            f = paint("!", 100) if w["usedPercent"] >= 80 else ""
            if USE_PACE:
                mark, code = {"farBehind": ("++", 32), "behind": ("+", 32), "ahead": ("-", 33), "farAhead": ("--", 31)}.get(pc.get("stage"), ("", 0))
                f += f"\033[{code}m{mark}\033[0m" if mark and COLOR else mark
            return f
        def cell(w, pc):
            shown = 100 - w["usedPercent"] if REMAINING else w["usedPercent"]
            return paint(f"{shown:.0f}%", w["usedPercent"]) + (flags(w, pc) if SPLIT else "") + (expiry_tag(w) if LINE else "")
        s = "/".join(cell(w, pc) for _, w, pc in ws)
        bang = "" if SPLIT else "!" if any(tight(w, pc) for _, w, pc in ws) else ""
        parts.append(f"{SHORT.get(name, name)}:{s}{bang}" if LINE else f"{name} 5h/wk {s}{bang}")
    out = ("" if LINE else "quota: ") + ("left " if REMAINING else "") + " ".join(parts) + ("~" if LINE and STALE else STALE_TAG)

    # Session info from the JSON Claude Code feeds the status line on stdin (passed in via QUOTA_STDIN).
    # Optional and defensive: any missing field is just omitted. QUOTA_SESSION=0 disables.
    if LINE and os.environ.get("QUOTA_SESSION", "1") != "0":
        try:
            sess = json.loads(os.environ.get("QUOTA_STDIN") or "{}")
        except Exception:
            sess = {}
        bits = []
        model = (sess.get("model") or {}).get("display_name")
        if model:
            bits.append(model)
        cw = sess.get("context_window") or {}
        ctx = cw.get("used_percentage")
        if ctx is None and cw.get("remaining_percentage") is not None:
            ctx = 100 - cw["remaining_percentage"]
        if ctx is not None:
            shown = 100 - ctx if REMAINING else ctx
            bits.append("ctx " + paint(f"{shown:.0f}%", ctx))
        if bits:
            out = " ".join(bits) + " | " + out
    print(out)

elif mode == "gate":
    want, n = sys.argv[2], float(sys.argv[3])
    code = 0
    for p in data:
        if p.get("provider") != want:
            continue
        for k, w, pace in windows(p):
            if w["usedPercent"] >= 95:
                print(f"STOP {want} {k} {w['usedPercent']:.0f}% resets {loc(w['resetsAt'])}{STALE_TAG}")
                sys.exit(2)
            if tight(w, pace, n):
                print(f"TIGHT {want} {k} {w['usedPercent']:.0f}% ({pace.get('stage', '-')}) resets {loc(w['resetsAt'])}{STALE_TAG}")
                code = 1
    if code == 0:
        print(f"OK {want}{STALE_TAG}")
    sys.exit(code)

elif mode == "wait":
    want, buf = sys.argv[2], int(sys.argv[3])
    now = time.time()
    secs = 0
    for p in data:
        if p.get("provider") != want:
            continue
        for k, w, pace in windows(p):
            if w["usedPercent"] >= 95:
                r = datetime.fromisoformat(w["resetsAt"].replace("Z", "+00:00")).timestamp()
                secs = max(secs, int(r - now) + buf)
    print(max(secs, 0))
