"""Fake `codex` CLI for tests: validates flags, records the prompt, writes a canned summary to -o.

Mode comes from the file named by $FAKE_CODEX_MODE_FILE (ok | fail | slow); the call is logged to $FAKE_CODEX_LOG.
"""
import json
import os
import sys
import time

a = sys.argv[1:]
prompt = sys.stdin.read()
mf = os.environ.get("FAKE_CODEX_MODE_FILE", "")
mode = open(mf).read().strip() if mf and os.path.exists(mf) else "ok"
with open(os.environ["FAKE_CODEX_LOG"], "w", encoding="utf-8") as fh:
    json.dump({"argv": a, "cwd": os.getcwd(), "prompt": prompt}, fh)
if mode == "fail":
    print("hook: SessionStart\nwarning: noise\nERROR: not logged in", file=sys.stderr)
    sys.exit(3)
if mode == "slow":
    time.sleep(10)
need = ["exec", "--ephemeral", "--skip-git-repo-check", "-s", "read-only", "-C", "-o"]
if [n for n in need if n not in a] or a[-1] != "-":
    print("bad args", file=sys.stderr)
    sys.exit(2)
with open(a[a.index("-o") + 1], "w", encoding="utf-8") as fh:
    fh.write("## Goal\n- Fix config loader 11-13\n\n## What was done\n- Fixed 11/12\n\n## Current state\n- 13 option B implemented\n\n"
             "## Open questions / blockers\n- None\n\n## Suggested next step\nOpen a PR for feat/13-config and request review.\n\n"
             "## Related issues / PRs / branches\n- #11 #12 #13, feat/13-config\n")
