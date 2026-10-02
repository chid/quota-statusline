import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(DIR)
QUOTA_SH = os.path.join(PROJECT_DIR, "scripts", "quota.sh")
ROUTE_SH = os.path.join(PROJECT_DIR, "scripts", "route.sh")
QUOTA_LINE = os.path.join(PROJECT_DIR, "bin", "quota-line")
FIXTURES_DIR = os.path.join(DIR, "fixtures")

class TestScriptsIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.cache_dir = os.path.join(self.tmp_dir, "codexbar-quota")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache_file = os.path.join(self.cache_dir, "both.json")
        with open(os.path.join(FIXTURES_DIR, "cache_full.json"), "r") as f:
            data = json.load(f)
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        def fix_dates(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == "resetsAt" and isinstance(v, str):
                        mins = obj.get("windowMinutes", 300)
                        delta = timedelta(minutes=70 if mins <= 360 else 7200)
                        obj[k] = (now + delta).strftime("%Y-%m-%dT%H:%M:%SZ")
                    else:
                        fix_dates(v)
            elif isinstance(obj, list):
                for item in obj:
                    fix_dates(item)
        fix_dates(data)
        with open(self.cache_file, "w") as f:
            json.dump(data, f)
        # Ensure cache timestamp is recent so TTL check passes
        os.utime(self.cache_file, None)

        self.env = os.environ.copy()
        self.env["XDG_CACHE_HOME"] = self.tmp_dir
        self.env["QUOTA_COLOR"] = "0"
        self.env["QUOTA_EXPIRY"] = "0"
        self.env["QUOTA_TTL"] = "3600"

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_quota_sh_line(self):
        """Tests scripts/quota.sh --line outputs X, C, Ag, Ac status line."""
        res = subprocess.run(
            [QUOTA_SH, "--line"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 0)
        out = res.stdout.strip()
        self.assertIn("X:", out)
        self.assertIn("C:", out)
        self.assertIn("Ag:57%/21%", out)
        self.assertIn("Ac:88%!/43%", out)

    def test_quota_sh_line_remaining(self):
        """Tests scripts/quota.sh --line --remaining shows inverted percentages."""
        res = subprocess.run(
            [QUOTA_SH, "--line", "--remaining"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 0)
        out = res.stdout.strip()
        self.assertTrue(out.startswith("left "))
        self.assertIn("Ag:43%/79%", out)
        self.assertIn("Ac:12%!/57%", out)

    def test_quota_sh_brief(self):
        """Tests scripts/quota.sh --brief formats all providers as 5h/wk."""
        res = subprocess.run(
            [QUOTA_SH, "--brief"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 0)
        out = res.stdout.strip()
        self.assertIn("agy:gemini 5h/wk 57%/21%", out)
        self.assertIn("agy:gpt 5h/wk 88%/43%!", out)

    def test_quota_sh_gate_gemini(self):
        """Tests scripts/quota.sh --gate gemini exits 0 when headroom is available."""
        res = subprocess.run(
            [QUOTA_SH, "--gate", "gemini", "80"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("OK gemini", res.stdout)

    def test_quota_sh_gate_gpt(self):
        """Tests scripts/quota.sh --gate gpt exits 1 when usage exceeds threshold."""
        res = subprocess.run(
            [QUOTA_SH, "--gate", "gpt", "80"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("TIGHT gpt", res.stdout)

    def test_quota_sh_gate_agy(self):
        """Tests scripts/quota.sh --gate agy exits 1 if either model family is tight."""
        res = subprocess.run(
            [QUOTA_SH, "--gate", "agy", "80"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("TIGHT agy", res.stdout)

    def test_quota_sh_subcommands(self):
        """Tests scripts/quota.sh agy, gemini, and gpt subcommands."""
        # agy
        res_agy = subprocess.run(
            [QUOTA_SH, "agy"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
        )
        self.assertEqual(res_agy.returncode, 0)
        self.assertIn("Gemini 5-hour", res_agy.stdout)
        self.assertIn("Claude/GPT 5-hour", res_agy.stdout)

        # gemini
        res_gem = subprocess.run(
            [QUOTA_SH, "gemini"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
        )
        self.assertEqual(res_gem.returncode, 0)
        self.assertIn("Gemini 5-hour", res_gem.stdout)
        self.assertNotIn("Claude/GPT", res_gem.stdout)

        # gpt
        res_gpt = subprocess.run(
            [QUOTA_SH, "gpt"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
        )
        self.assertEqual(res_gpt.returncode, 0)
        self.assertIn("Claude/GPT 5-hour", res_gpt.stdout)
        self.assertNotIn("Gemini 5-hour", res_gpt.stdout)

    def test_quota_line_bin(self):
        """Tests bin/quota-line wrapper works properly."""
        res = subprocess.run(
            [QUOTA_LINE],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 0)
        out = res.stdout.strip()
        self.assertIn("Ag:", out)
        self.assertIn("Ac:", out)

    def test_route_sh_picks_gemini(self):
        """Tests route.sh picks gemini when ordered first and within threshold."""
        res = subprocess.run(
            [ROUTE_SH, "--dry-run", "--order", "gemini,claude,codex", "hello world"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "gemini")

    def test_route_sh_skips_tight_gpt_and_picks_gemini(self):
        """Tests route.sh skips tight gpt (88% used) and routes to gemini (57% used)."""
        res = subprocess.run(
            [ROUTE_SH, "--dry-run", "--threshold", "80", "--order", "gpt,gemini", "hello world"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "gemini")
        self.assertIn("skip gpt", res.stderr)


if __name__ == "__main__":
    unittest.main()
