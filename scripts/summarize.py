import json, os, sys
import time
from datetime import datetime

mode = sys.argv[1]
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0 if mode in ("gate", "line", "brief") else "bad cache")

def loc(s):
    if not s:
        return "unknown"
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone().strftime("%a %b %d %H:%M")
    except Exception:
        return str(s)

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
    try:
        mins = (datetime.fromisoformat(w["resetsAt"].replace("Z", "+00:00")).timestamp() - time.time()) / 60
    except Exception:
        return ""
    if limit <= 0 or mins <= 0 or mins >= limit:
        return ""
    return f"{EXPIRY_MARK}{int(mins // 60)}h{int(mins % 60):02d}" if mins >= 60 else f"{EXPIRY_MARK}{int(mins)}m"

def classify_antigravity_family(item):
    wid = str(item.get("id", "")).lower()
    title = str(item.get("title", "")).lower()
    if "gemini" in wid or "gemini" in title:
        return "gemini"
    if any(k in wid or k in title for k in ("3p", "claude", "gpt", "third-party")):
        return "claude-gpt"
    return "other"

def get_groups(p):
    """
    Returns a list of display groups for a provider object.
    Each group dict has:
      'short': status line prefix ('X', 'C', 'Ag', 'Ac')
      'brief': label in brief mode ('codex', 'claude', 'agy:gemini', 'agy:gpt')
      'family': family key ('codex', 'claude', 'gemini', 'claude-gpt')
      'keys': set of match aliases for gate/full/wait
      'windows': list of (label, window_dict, pace_dict)
    """
    name = (p.get("provider") or "").lower()
    usage = p.get("usage") or {}
    pace = p.get("pace") or {}
    extra = usage.get("extraRateWindows") or []

    # Check if antigravity has split extraRateWindows
    if name in ("antigravity", "agy") and extra:
        gemini_windows = []
        claudegpt_windows = []
        for item in extra:
            w = item.get("window") or item
            if not isinstance(w, dict) or "usedPercent" not in w:
                continue
            fam = classify_antigravity_family(item)
            title = item.get("title") or item.get("id") or fam
            mins = w.get("windowMinutes") or (300 if any(k in (str(item.get("id", "")) + " " + title).lower() for k in ("5h", "5-hour", "session")) else 10080)
            entry = (title, w, {}, mins)
            if fam == "gemini":
                gemini_windows.append(entry)
            elif fam == "claude-gpt":
                claudegpt_windows.append(entry)

        groups = []
        if gemini_windows:
            gemini_windows.sort(key=lambda x: x[3])
            groups.append({
                "short": "Ag",
                "brief": "agy:gemini",
                "family": "gemini",
                "provider": name,
                "keys": {"antigravity", "agy", "gemini", "agy:gemini", "antigravity:gemini"},
                "windows": [(lbl, w, pc) for lbl, w, pc, _ in gemini_windows]
            })
        if claudegpt_windows:
            claudegpt_windows.sort(key=lambda x: x[3])
            groups.append({
                "short": "Ac",
                "brief": "agy:gpt",
                "family": "claude-gpt",
                "provider": name,
                "keys": {"antigravity", "agy", "gpt", "claude-gpt", "3p", "agy:gpt", "antigravity:gpt", "claude and gpt"},
                "windows": [(lbl, w, pc) for lbl, w, pc, _ in claudegpt_windows]
            })
        if groups:
            return groups

    # Standard fallback for codex, claude, or antigravity without extraRateWindows
    ws = []
    labels = p.get("rateWindowLabels") or {}
    for k in ("primary", "secondary"):
        w = usage.get(k)
        if w and isinstance(w, dict) and "usedPercent" in w:
            ws.append((labels.get(k, k), w, pace.get(k) or {}))

    short = SHORT.get(name, name[:1].upper() if name else "?")
    keys = {name}
    if name == "antigravity":
        keys.add("agy")
    elif name == "agy":
        keys.add("antigravity")

    return [{
        "short": short,
        "brief": name,
        "family": name,
        "provider": name,
        "keys": keys,
        "windows": ws
    }]

USE_PACE = os.environ.get("QUOTA_GATE_PACE", "1") != "0"

def tight(w, pace, n=80):
    return w.get("usedPercent", 0) >= n or (USE_PACE and pace.get("stage") in ("ahead", "farAhead"))

if mode == "full":
    want = sys.argv[2].lower() if len(sys.argv) > 2 else "both"
    for p in data:
        name = (p.get("provider") or "").lower()
        if p.get("error"):
            if want in ("both", "all", name, "agy" if name == "antigravity" else ""):
                print(f"== {name}: ERROR {p['error']}")
            continue

        groups = get_groups(p)
        matched_groups = [g for g in groups if want in ("both", "all") or want in g["keys"]]
        if not matched_groups:
            continue

        u = p.get("usage", {})
        login = u.get("loginMethod") or "?"
        email = u.get("accountEmail") or ""
        email_str = f" {email}" if email else ""
        print(f"== {name} ({login}){email_str} [source={p.get('source')}]")

        for g in matched_groups:
            for lbl, w, pc in g["windows"]:
                flag = " !!" if tight(w, pc) else ""
                print(f"  {lbl:18} {w['usedPercent']:3.0f}% used, resets {loc(w.get('resetsAt'))}{flag}")
                if pc.get("summary"):
                    print(f"           pace: {pc['summary']}")

        rc = u.get("codexResetCredits")
        if rc:
            print(f"  reset credits available: {rc.get('availableCount')}")
            for c in rc.get("credits", []):
                if c.get("status") == "available":
                    print(f"    - {c['title']} (expires {loc(c.get('expires_at'))})")
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
        groups = get_groups(p)
        for g in groups:
            ws = g["windows"]
            if not ws:
                continue
            def flags(w, pc):
                # split: "!" = >=80% used. Pace is a budget balance: "+"/"++" = behind / far behind pace (headroom),
                # "-"/"--" = ahead / far ahead (overspending). Marked per window; QUOTA_GATE_PACE=0 hides pace.
                f = paint("!", 100) if w.get("usedPercent", 0) >= 80 else ""
                if USE_PACE:
                    mark, code = {"farBehind": ("++", 32), "behind": ("+", 32), "ahead": ("-", 33), "farAhead": ("--", 31)}.get(pc.get("stage"), ("", 0))
                    f += f"\033[{code}m{mark}\033[0m" if mark and COLOR else mark
                return f
            def cell(w, pc):
                used_val = w.get("usedPercent", 0)
                shown = 100 - used_val if REMAINING else used_val
                return paint(f"{shown:.0f}%", used_val) + (flags(w, pc) if SPLIT else "") + (expiry_tag(w) if LINE else "")
            s = "/".join(cell(w, pc) for _, w, pc in ws)
            bang = "" if SPLIT else "!" if any(tight(w, pc) for _, w, pc in ws) else ""
            parts.append(f"{g['short']}:{s}{bang}" if LINE else f"{g['brief']} 5h/wk {s}{bang}")
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
    want = sys.argv[2].lower()
    n = float(sys.argv[3])
    code = 0
    matched = False
    for p in data:
        groups = get_groups(p)
        for g in groups:
            if want not in g["keys"]:
                continue
            matched = True
            for lbl, w, pace in g["windows"]:
                used_val = w.get("usedPercent", 0)
                if used_val >= 95:
                    print(f"STOP {want} {lbl} {used_val:.0f}% resets {loc(w.get('resetsAt'))}{STALE_TAG}")
                    sys.exit(2)
                if tight(w, pace, n):
                    stage = pace.get("stage", "-") if pace else "-"
                    print(f"TIGHT {want} {lbl} {used_val:.0f}% ({stage}) resets {loc(w.get('resetsAt'))}{STALE_TAG}")
                    code = 1
    if code == 0:
        print(f"OK {want}{STALE_TAG}")
    sys.exit(code)

elif mode == "wait":
    want = sys.argv[2].lower()
    buf = int(sys.argv[3])
    now = time.time()
    secs = 0
    for p in data:
        groups = get_groups(p)
        for g in groups:
            if want not in g["keys"]:
                continue
            for lbl, w, pace in g["windows"]:
                if w.get("usedPercent", 0) >= 95 and w.get("resetsAt"):
                    try:
                        r = datetime.fromisoformat(w["resetsAt"].replace("Z", "+00:00")).timestamp()
                        secs = max(secs, int(r - now) + buf)
                    except Exception:
                        pass
    print(max(secs, 0))
