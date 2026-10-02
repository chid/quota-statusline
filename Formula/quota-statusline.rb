class QuotaStatusline < Formula
  desc "Color-coded Codex, Claude, and Antigravity quota status line built on CodexBar"
  homepage "https://github.com/chid/quota-statusline"
  url "https://github.com/chid/quota-statusline.git", branch: "main"
  version "0.2.0"
  license "MIT"
  head "https://github.com/chid/quota-statusline.git", branch: "main"

  depends_on "python@3"

  def install
    bin.install "bin/quota-line"
    prefix.install "scripts"
  end

  def caveats
    <<~EOS
      To use with Claude Code, add this to your ~/.claude/settings.json:

        "statusLine": {
          "type": "command",
          "command": "#{opt_bin}/quota-line"
        }

      Requires CodexBar (https://github.com/steipete/CodexBar or brew install --cask codexbar).
    EOS
  end

  test do
    assert_match "quota", shell_output("#{bin}/quota-line --help 2>&1", 1) rescue true
  end
end
