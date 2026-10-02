import json
import os
import subprocess
import sys
import unittest

DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(DIR)
SUMMARIZE = os.path.join(PROJECT_DIR, "scripts", "summarize.py")
FIXTURES_DIR = os.path.join(DIR, "fixtures")

def load_fixture(name):
    with open(os.path.join(FIXTURES_DIR, name), "r") as f:
        return f.read()

def run_summarize(mode, args=None, stdin_data="", env_vars=None):
    cmd = [sys.executable, SUMMARIZE, mode]
    if args:
        cmd.extend(args)
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)
    res = subprocess.run(
        cmd,
        input=stdin_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    return res


class TestSummarizeLineMode(unittest.TestCase):
    def setUp(self):
        self.cache_full = load_fixture("cache_full.json")
        self.cache_legacy = load_fixture("cache_legacy.json")
        self.cache_single = load_fixture("cache_single_family.json")

    def test_line_default_output(self):
        """Verifies default statusline output with Codex, Claude, and Antigravity Ag & Ac."""
        res = run_summarize("line", stdin_data=self.cache_full, env_vars={"QUOTA_COLOR": "0"})
        self.assertEqual(res.returncode, 0)
        out = res.stdout.strip()
        # Verify provider labels exist in order
        self.assertIn("X:", out)
        self.assertIn("C:", out)
        self.assertIn("Ag:57%", out)
        self.assertIn("Ac:88%!", out)
        # Verify weekly windows for Ag and Ac
        self.assertIn("/21%", out)
        self.assertIn("/43%", out)

    def test_line_remaining(self):
        """Verifies --remaining / QUOTA_SHOW=remaining inverts the percentages."""
        res = run_summarize(
            "line",
            stdin_data=self.cache_full,
            env_vars={"QUOTA_SHOW": "remaining", "QUOTA_COLOR": "0"},
        )
        self.assertEqual(res.returncode, 0)
        out = res.stdout.strip()
        self.assertTrue(out.startswith("left "))
        # 100 - 96 = 4% for X primary, 100 - 55 = 45% for X secondary
        self.assertIn("X:4%", out)
        self.assertIn("/45%", out)
        # 100 - 57.3 = 43% for Ag primary, 100 - 21.0 = 79% for Ag secondary
        self.assertIn("Ag:43%", out)
        self.assertIn("/79%", out)
        # 100 - 87.8 = 12% for Ac primary, 100 - 43.4 = 57% for Ac secondary
        self.assertIn("Ac:12%!", out)
        self.assertIn("/57%", out)

    def test_line_colors_enabled_and_disabled(self):
        """Verifies ANSI colors are emitted by default and suppressed with QUOTA_COLOR=0."""
        res_color = run_summarize("line", stdin_data=self.cache_full, env_vars={"QUOTA_COLOR": "1"})
        self.assertIn("\033[", res_color.stdout)

        res_nocolor = run_summarize("line", stdin_data=self.cache_full, env_vars={"QUOTA_COLOR": "0"})
        self.assertNotIn("\033[", res_nocolor.stdout)

    def test_line_expiry_tags(self):
        """Verifies expiry tags show reset proximity and QUOTA_EXPIRY=0 disables them."""
        # In cache_full, primary windows reset within ~1h
        res_exp = run_summarize("line", stdin_data=self.cache_full, env_vars={"QUOTA_COLOR": "0"})
        # Should contain '@' markers
        self.assertIn("@", res_exp.stdout)

        # Disabled
        res_noexp = run_summarize(
            "line",
            stdin_data=self.cache_full,
            env_vars={"QUOTA_EXPIRY": "0", "QUOTA_COLOR": "0"},
        )
        self.assertNotIn("@", res_noexp.stdout)

    def test_line_pace_markers(self):
        """Verifies pace markers (+, ++, -, --) appear and QUOTA_GATE_PACE=0 suppresses them."""
        res_pace = run_summarize("line", stdin_data=self.cache_full, env_vars={"QUOTA_COLOR": "0"})
        self.assertTrue(any(sym in res_pace.stdout for sym in ("--", "++", "+", "-")))

        res_nopace = run_summarize(
            "line",
            stdin_data=self.cache_full,
            env_vars={"QUOTA_GATE_PACE": "0", "QUOTA_COLOR": "0"},
        )
        self.assertNotIn("--", res_nopace.stdout)
        self.assertNotIn("++", res_nopace.stdout)

    def test_line_combined_flags(self):
        """Verifies QUOTA_FLAGS=combined restores provider-level '!' flag."""
        res = run_summarize(
            "line",
            stdin_data=self.cache_full,
            env_vars={"QUOTA_FLAGS": "combined", "QUOTA_COLOR": "0", "QUOTA_EXPIRY": "0"},
        )
        self.assertEqual(res.returncode, 0)
        out = res.stdout.strip()
        # Codex (96% used) should end with !
        self.assertIn("X:96%/55%!", out)
        # Ag (57%/21%) has no tight window
        self.assertIn("Ag:57%", out)
        self.assertNotIn("Ag:57%!", out)
        # Ac (88%/43%) has tight window, so Ac gets !
        self.assertIn("Ac:88%/43%!", out)

    def test_line_session_stdin_prefix(self):
        """Verifies model and context window info from stdin JSON."""
        session_json = json.dumps({
            "model": {"display_name": "Opus 4.5"},
            "context_window": {"used_percentage": 34.0},
        })
        res = run_summarize(
            "line",
            stdin_data=self.cache_full,
            env_vars={"QUOTA_STDIN": session_json, "QUOTA_COLOR": "0"},
        )
        self.assertEqual(res.returncode, 0)
        self.assertTrue(res.stdout.startswith("Opus 4.5 ctx 34% | "))

    def test_line_session_disabled(self):
        """Verifies QUOTA_SESSION=0 disables model/context prefix."""
        session_json = json.dumps({
            "model": {"display_name": "Opus 4.5"},
            "context_window": {"used_percentage": 34.0},
        })
        res = run_summarize(
            "line",
            stdin_data=self.cache_full,
            env_vars={"QUOTA_STDIN": session_json, "QUOTA_SESSION": "0", "QUOTA_COLOR": "0"},
        )
        self.assertEqual(res.returncode, 0)
        self.assertNotIn("Opus", res.stdout)
        self.assertNotIn("ctx", res.stdout)

    def test_line_stale_cache_marker(self):
        """Verifies ~ is appended when cache is stale."""
        res = run_summarize(
            "line",
            stdin_data=self.cache_full,
            env_vars={"QUOTA_STALE": "1", "QUOTA_COLOR": "0"},
        )
        self.assertEqual(res.returncode, 0)
        self.assertTrue(res.stdout.strip().endswith("~"))

    def test_line_legacy_fallback(self):
        """Verifies that an older cache without extraRateWindows falls back to A: cleanly."""
        res = run_summarize("line", stdin_data=self.cache_legacy, env_vars={"QUOTA_COLOR": "0", "QUOTA_EXPIRY": "0"})
        self.assertEqual(res.returncode, 0)
        out = res.stdout.strip()
        self.assertIn("A:50%/80%!", out)

    def test_line_single_family(self):
        """Verifies that if only Gemini family is present, only Ag is shown."""
        res = run_summarize("line", stdin_data=self.cache_single, env_vars={"QUOTA_COLOR": "0", "QUOTA_EXPIRY": "0"})
        self.assertEqual(res.returncode, 0)
        out = res.stdout.strip()
        self.assertIn("Ag:30%/15%", out)
        self.assertNotIn("Ac:", out)


class TestSummarizeBriefMode(unittest.TestCase):
    def setUp(self):
        self.cache_full = load_fixture("cache_full.json")

    def test_brief_mode_labels(self):
        """Verifies brief mode formats codex, claude, agy:gemini, and agy:gpt accurately as 5h/wk."""
        res = run_summarize("brief", stdin_data=self.cache_full, env_vars={"QUOTA_COLOR": "0"})
        self.assertEqual(res.returncode, 0)
        out = res.stdout.strip()
        self.assertTrue(out.startswith("quota: "))
        self.assertIn("codex 5h/wk 96%/55%!", out)
        self.assertIn("claude 5h/wk 4%/52%", out)
        self.assertIn("agy:gemini 5h/wk 57%/21%", out)
        self.assertIn("agy:gpt 5h/wk 88%/43%!", out)


class TestSummarizeFullMode(unittest.TestCase):
    def setUp(self):
        self.cache_full = load_fixture("cache_full.json")

    def test_full_mode_both(self):
        """Verifies full mode prints all providers and all four Antigravity windows."""
        res = run_summarize("full", ["both"], stdin_data=self.cache_full)
        self.assertEqual(res.returncode, 0)
        out = res.stdout
        self.assertIn("== codex", out)
        self.assertIn("== claude", out)
        self.assertIn("== antigravity", out)
        self.assertIn("Gemini 5-hour", out)
        self.assertIn("Gemini weekly", out)
        self.assertIn("Claude/GPT 5-hour", out)
        self.assertIn("Claude/GPT weekly", out)
        self.assertIn("reset credits available:", out)

    def test_full_filter_gemini(self):
        """Verifies filtering by 'gemini' only displays Gemini windows."""
        res = run_summarize("full", ["gemini"], stdin_data=self.cache_full)
        self.assertEqual(res.returncode, 0)
        out = res.stdout
        self.assertIn("Gemini 5-hour", out)
        self.assertIn("Gemini weekly", out)
        self.assertNotIn("Claude/GPT", out)
        self.assertNotIn("== codex", out)

    def test_full_filter_gpt(self):
        """Verifies filtering by 'gpt' only displays Claude/GPT windows."""
        res = run_summarize("full", ["gpt"], stdin_data=self.cache_full)
        self.assertEqual(res.returncode, 0)
        out = res.stdout
        self.assertIn("Claude/GPT 5-hour", out)
        self.assertIn("Claude/GPT weekly", out)
        self.assertNotIn("Gemini 5-hour", out)
        self.assertNotIn("== codex", out)

    def test_full_filter_agy(self):
        """Verifies 'agy' displays antigravity with both Gemini and Claude/GPT."""
        res = run_summarize("full", ["agy"], stdin_data=self.cache_full)
        self.assertEqual(res.returncode, 0)
        out = res.stdout
        self.assertIn("Gemini 5-hour", out)
        self.assertIn("Claude/GPT 5-hour", out)
        self.assertNotIn("== codex", out)


class TestSummarizeGateMode(unittest.TestCase):
    def setUp(self):
        self.cache_full = load_fixture("cache_full.json")
        self.cache_stop = load_fixture("cache_stop.json")

    def test_gate_ok(self):
        """Gating gemini at 80% should exit 0 (OK) since gemini windows are 57% and 21%."""
        res = run_summarize("gate", ["gemini", "80"], stdin_data=self.cache_full)
        self.assertEqual(res.returncode, 0)
        self.assertIn("OK gemini", res.stdout)

    def test_gate_tight(self):
        """Gating gpt at 80% should exit 1 (TIGHT) since Claude/GPT 5h is 88%."""
        res = run_summarize("gate", ["gpt", "80"], stdin_data=self.cache_full)
        self.assertEqual(res.returncode, 1)
        self.assertIn("TIGHT gpt", res.stdout)
        self.assertIn("Claude/GPT 5-hour 88%", res.stdout)

    def test_gate_antigravity_combined(self):
        """Gating agy/antigravity should exit 1 because Claude/GPT is tight."""
        res = run_summarize("gate", ["agy", "80"], stdin_data=self.cache_full)
        self.assertEqual(res.returncode, 1)
        self.assertIn("TIGHT agy", res.stdout)

    def test_gate_stop(self):
        """Gating a provider with a >=95% window should exit 2 (STOP)."""
        res = run_summarize("gate", ["gemini", "80"], stdin_data=self.cache_stop)
        self.assertEqual(res.returncode, 2)
        self.assertIn("STOP gemini", res.stdout)
        self.assertIn("98%", res.stdout)


class TestSummarizeWaitMode(unittest.TestCase):
    def setUp(self):
        self.cache_full = load_fixture("cache_full.json")
        self.cache_stop = load_fixture("cache_stop.json")

    def test_wait_no_stop_windows(self):
        """When no windows are >=95%, wait prints 0."""
        res = run_summarize("wait", ["gemini", "60"], stdin_data=self.cache_full)
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "0")

    def test_wait_stop_window(self):
        """When a window is >=95%, wait prints seconds to reset + buffer."""
        res = run_summarize("wait", ["gemini", "60"], stdin_data=self.cache_stop)
        self.assertEqual(res.returncode, 0)
        secs = int(res.stdout.strip())
        self.assertGreater(secs, 0)


if __name__ == "__main__":
    unittest.main()
