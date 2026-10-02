# quota-statusline

A one-line, color-coded quota readout for Codex, Claude and Antigravity, built on
[CodexBar](https://github.com/steipete/CodexBar). Use it as a Claude Code status line or run it from a terminal.

```
Opus ctx 34% | X:100%!@27m/40%-- C:57%-/47%++ Ag:57%@1h09/21% Ac:88%!@1h11/43%
```

## Reading it

| Piece | Meaning |
| --- | --- |
| `X` `C` `Ag` `Ac` | Codex / Claude / Antigravity Gemini / Antigravity Claude & GPT |
| `57%/47%` | Percent used: 5-hour window, then weekly |
| color | green < 60% used, yellow < 80%, red above |
| `!` | that window is at 80%+ used |
| `-` / `--` | ahead / far ahead of pace (overspending) |
| `+` / `++` | behind / far behind pace (headroom) |
| `@38m` `@1h29` | window resets soon (< 2h for 5h windows, < 24h for weekly) |
| `~` | cache is stale |
| `Opus ctx 34% \|` | model and context use, from Claude Code's stdin JSON (status line only) |

## Install

### Option 1: Claude Code Plugin Marketplace (Recommended for Claude Code)

```bash
claude plugin marketplace add chid/quota-statusline
claude plugin install quota-statusline
```

### Option 2: One-line Shell Installer (Auto-configures ~/.claude/settings.json)

```bash
curl -fsSL https://raw.githubusercontent.com/chid/quota-statusline/main/install.sh | bash -s -- --configure
```

### Option 3: Agent Skill (skills.sh / Claude / Cursor / Codex / OpenCode)

```bash
npx skills add chid/quota-statusline
```

### Option 4: Homebrew Tap

```bash
brew tap chid/quota-statusline https://github.com/chid/quota-statusline
brew install quota-statusline
```

### Option 5: Manual Clone

```bash
git clone https://github.com/chid/quota-statusline.git ~/.local/share/quota-statusline
~/.local/share/quota-statusline/install.sh --configure
```

### Usage

```bash
quota-line            # print once
quota-line --remaining
quota-line --watch 30
```

Requires `codexbar` on `PATH` ([CodexBar](https://github.com/steipete/CodexBar) or `brew install --cask codexbar`), `python3` (`/usr/bin/python3`), and macOS (`stat -f`).

## How it works

`quota.sh --line` reads a cache (`~/.cache/codexbar-quota/both.json`) and never blocks. If the cache is older than
`QUOTA_TTL` it starts `quota.sh --refresh` in the background, which calls `codexbar usage` for Claude/Codex and
Antigravity and merges the results. A `refresh.lock` directory keeps it to one refresh; a lock is reclaimed when its
holder is dead or older than `QUOTA_LOCK_TTL`, and a stuck holder is killed. `summarize.py` renders the line.

## Settings (environment variables)

| Variable | Default | Effect |
| --- | --- | --- |
| `--remaining` / `QUOTA_SHOW=remaining` | used | show percent left |
| `QUOTA_EXPIRY_SHORT` / `QUOTA_EXPIRY_LONG` | 120 / 1440 | minutes before reset to flag 5h / weekly windows; 0 disables |
| `QUOTA_EXPIRY=0` | on | disable expiry markers |
| `QUOTA_EXPIRY_MARK` | `@` | marker character |
| `QUOTA_WARN` / `QUOTA_CRIT` | 60 / 80 | color thresholds (% used) |
| `QUOTA_COLOR=0` | on | disable color |
| `QUOTA_FLAGS=combined` | split | one `!` per provider (80% used or ahead of pace) |
| `QUOTA_GATE_PACE=0` | on | hide pace markers (also affects `--gate` and `route.sh`) |
| `QUOTA_SESSION=0` | on | drop the model / context prefix |
| `QUOTA_STDIN_DUMP=/path` | off | save the stdin JSON Claude Code sends, to inspect fields |
| `QUOTA_TTL` | 300 | seconds before the cache counts as old |
| `QUOTA_LOCK_TTL` | 120 | seconds before a refresh lock counts as stuck |

Other modes of `scripts/quota.sh`: `--brief`, `--gate <provider> [N]`, `--wait <provider>`, `--refresh`; see the
header of the script. `scripts/route.sh` runs a prompt on the first backend with headroom.

## Caveats

- The stdin field names (`model.display_name`, `context_window.used_percentage`) are untested against the real payload; use `QUOTA_STDIN_DUMP` to check.

## License

MIT, see [LICENSE](LICENSE).
