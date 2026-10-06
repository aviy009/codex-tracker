"""End-to-end tests against a synthetic Codex home. Stdlib only.

    python tests/run_tests.py            # API + summary tests (+ UI tests if Chrome/Chromium/Edge is found)

Starts server.py on a free port with a temp CODEX_HOME / TRACKER_DATA_DIR and a fake `codex` CLI.
"""
import glob
import hashlib
import html as H
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import fixture  # noqa: E402

RESULTS = []


def chk(cond, msg):
    RESULTS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + msg)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def tree_hash(d):
    h = hashlib.md5()
    for f in sorted(glob.glob(os.path.join(d, "**", "*"), recursive=True)):
        if os.path.isfile(f) and not f.endswith(("-wal", "-shm")):
            with open(f, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def find_browser():
    for c in ("google-chrome", "chromium", "chromium-browser", "chrome", "msedge"):
        p = shutil.which(c)
        if p:
            return p
    for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        if os.path.exists(c):
            return c
    return None


def main():
    tmp = tempfile.mkdtemp(prefix="codex-tracker-test-")
    home, data = os.path.join(tmp, "codex"), os.path.join(tmp, "data")
    os.makedirs(data)
    ids = fixture.build(home)
    port = free_port()
    B = f"http://127.0.0.1:{port}"
    mode_file, log_file = os.path.join(tmp, "mode"), os.path.join(tmp, "fakecodex.json")
    env = dict(os.environ, TRACKER_DATA_DIR=data, TRACKER_CODEX=os.path.join(HERE, "fakecodex.py"),
               TRACKER_SUMMARY_TIMEOUT="3", FAKE_CODEX_MODE_FILE=mode_file, FAKE_CODEX_LOG=log_file)
    env.pop("TRACKER_SUMMARY_ARGS", None)
    env.pop("TRACKER_SUMMARY_MODEL", None)
    srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "server.py"), "--port", str(port), "--codex-home", home, "--no-browser"],
                           env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(B + "/api/health")
                break
            except Exception:
                time.sleep(0.1)
        run_api(B, ids, home)
        run_summary(B, ids, home, data, mode_file, log_file)
        br = find_browser()
        if br:
            run_ui(B, ids, br, tmp)
        else:
            print("SKIP UI tests (no Chrome/Chromium/Edge found)")
    finally:
        srv.terminate()
        try:
            srv.wait(5)
        except Exception:
            srv.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    ok = sum(RESULTS)
    print(f"\n{ok}/{len(RESULTS)} passed")
    return 0 if ok == len(RESULTS) else 1


def get(B, p, headers=None):
    return json.load(urllib.request.urlopen(urllib.request.Request(B + p, headers=headers or {})))


def post(B, p, body=None, ct="application/json", headers=None):
    req = urllib.request.Request(B + p, data=json.dumps(body or {}).encode(), method="POST", headers={"Content-Type": ct, **(headers or {})})
    try:
        r = urllib.request.urlopen(req)
        return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {}


def run_api(B, ids, home):
    h0 = tree_hash(home)
    d = get(B, "/api/sessions")
    S = {s["id"]: s for s in d["sessions"]}
    chk(S[ids["f1"]]["parent"] == ids["a"] and S[ids["f1"]]["rel"] == "fork", "user fork detected from rollout forked_from_id")
    chk(S[ids["f2"]]["parent"] == ids["f1"], "fork of fork (paged segment file)")
    chk(S[ids["u"]]["parent"] is None, "<id>_<segment> rollout is not treated as a fork")
    chk(S[ids["pf"]]["parent"] == ids["a"], "fork found in base file when latest segment lacks forked_from_id")
    chk(S[ids["s1"]]["rel"] == "spawn" and S[ids["s1"]]["edge_status"] == "open" and S[ids["s2"]]["edge_status"] == "closed", "spawn edges + status")
    chk(S[ids["g"]]["kind"] == "guardian" and S[ids["r"]]["kind"] == "review", "guardian / review kinds")
    chk(S[ids["a"]]["status"] == "active" and S[ids["f1"]]["status"] == "recent" and S[ids["f2"]]["status"] == "idle" and S[ids["u"]]["status"] == "archived", "status from recency")
    chk(S[ids["a"]]["suggested_issue"] == 42 and S[ids["u"]]["suggested_issue"] == 7 and S[ids["o"]]["suggested_issue"] is None, "issue suggested from branch")
    chk(S[ids["a"]]["repo"] == "example-org/example-app" and S[ids["o"]]["group"] == "other-org/other-thing", "repo from origin + repo grouping")
    chk(S[ids["no"]]["repo"] == "example-org/example-app" and S[ids["no"]]["repo_inferred"], "repo inferred from folder name")
    chk(S[ids["orph"]]["parent"] is None and S[ids["orph"]]["parent_missing"], "fork with unknown parent")
    chk(S[ids["a"]]["prs"][0]["url"].endswith("/pull/1") and S[ids["a"]]["worktrees"], "PR + worktree attachments")
    chk(S[ids["s1"]]["title"].startswith("Ada:"), "subagent nickname in title")
    chk(S[ids["a"]]["title"] == "Commit naming (indexed)" and S[ids["xfork"]]["title"] == "Language & Diagram Sync", "title: name > session_index thread_name > first prompt")
    chk(S[ids["cfg_fork"]]["section"] == "Settings work" and S[ids["cfg_fork"]]["section_pos"] == 3, "section membership + position from sidebar state")
    chk(d["sections"][:2] == ["Alpha project", "Settings work"] and "Side projects" in d["sections"], "sidebar section order (+ DB-only sections)")
    chk(d["kinds"].get("cloud") == 2 and S["task_e_aaaabbbbccccdddd0000111122223333"]["open_url"].startswith("https://chatgpt.com/codex/tasks/"), "cloud tasks from sidebar")
    chk(S[ids["a"]]["open_url"] == "codex://threads/" + ids["a"], "codex:// deep link")
    det = get(B, "/api/session/" + ids["f2"])
    chk([x["id"] for x in det["ancestors"]] == [ids["f1"], ids["a"]], "ancestor chain")
    st, _ = post(B, "/api/notes/" + ids["a"], {"goal": "ship 42", "next": "wait for CI", "issue": "#42"})
    chk(st == 200, "save note")
    S = {s["id"]: s for s in get(B, "/api/sessions?refresh=1")["sessions"]}
    chk(S[ids["a"]]["note_next"] == "wait for CI" and S[ids["a"]]["has_notes"], "note shows in list")
    chk(get(B, "/api/session/" + ids["f1"])["parent_notes"]["goal"] == "ship 42", "parent notes shown on fork")
    chk(post(B, "/api/notes/" + ids["a"], {"next": "x"}, ct="text/plain")[0] == 415, "non-JSON POST rejected")
    chk(post(B, "/api/notes/" + ids["a"], {"next": "x"}, headers={"Origin": "http://evil.example"})[0] == 403, "foreign Origin rejected")
    try:
        get(B, "/api/sessions", headers={"Host": "evil.example"})
        chk(False, "bad Host rejected")
    except urllib.error.HTTPError as e:
        chk(e.code == 403, "bad Host rejected (DNS rebinding)")
    chk(get(B, "/api/issue?ref=nonsense")["ok"] is False, "bad issue ref handled")
    lk = sqlite3.connect(os.path.join(home, "state_5.sqlite"))
    lk.execute("begin immediate")
    lk.execute("update threads set title=title")
    t0 = time.time()
    n = get(B, "/api/sessions?refresh=1")["total"]
    lk.rollback()
    lk.close()
    chk(n == len(ids) + 2, f"reads while a writer holds the lock ({time.time() - t0:.2f}s)")
    chk(tree_hash(home) == h0, "nothing written under CODEX_HOME")


def run_summary(B, ids, home, data, mode_file, log_file):
    def wait(tid, t=20):
        s = {}
        for _ in range(int(t / 0.25)):
            s = get(B, "/api/summary/" + tid)
            if s["state"] != "running":
                return s
            time.sleep(0.25)
        return s
    h0 = tree_hash(home)
    tid = ids["cfg"]
    chk(get(B, "/api/summary/" + tid)["state"] == "idle", "no summary until requested")
    chk(post(B, "/api/summarize/" + tid)[1].get("state") == "running", "summarize runs async")
    s = wait(tid)
    chk(s["state"] == "done" and "## Suggested next step" in s["summary"]["text"] and not s["summary"]["outdated"], "summary stored, fresh")
    L = json.load(open(log_file, encoding="utf-8"))
    p, a = L["prompt"], L["argv"]
    chk(os.path.basename(L["cwd"]) == ".summarize" and os.path.basename(a[a.index("-C") + 1]) == ".summarize", "runs in scratch .summarize dir")
    chk("--ephemeral" in a and a[a.index("-s") + 1] == "read-only" and "--ignore-user-config" in a and "--ignore-rules" in a, "ephemeral, read-only, no user config/hooks/MCP")
    chk(a[a.index("-m") + 1] == "test-model-1", "model from top-level config.toml")
    chk(all(m in p for m in ("GOAL-MARKER", "FINAL-1", "FINAL-2", "SEGMENT-USER-MSG")), "transcript spans all history files")
    chk(not any(m in p for m in ("REASONING-LEAK", "HUGE-TOOL-OUTPUT", "AGENTS-MD-TEXT", "ENVCTX", "x" * 1000)), "drops reasoning, tool output, injected context, base instructions")
    chk(p.count("REPEATED-HANDOFF-CONTEXT") == 20 and p.count("GOAL-MARKER") == 1, "re-sent context and compacted history deduped")
    chk("TOOL shell: bash -lc rg ConfigLoader" in p and "TOOL apply_patch:" in p and len(p) < 20000, "tool calls listed briefly")
    chk("[turn aborted by user]" in p and "assistant (progress)" in p, "aborted turns + progress notes")
    chk("Open a PR" in {x["id"]: x for x in get(B, "/api/sessions?refresh=1")["sessions"]}[tid]["summary"], "summary searchable in list")
    time.sleep(1.1)
    seg = glob.glob(os.path.join(home, "sessions", "**", f"*{tid}_*.jsonl"), recursive=True)[0]
    with open(seg, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "event_msg", "payload": {"type": "token_count"}}) + "\n")
    chk(get(B, "/api/summary/" + tid)["summary"]["outdated"] is True, "outdated after the session changes")
    h0 = tree_hash(home)
    post(B, "/api/summarize/" + ids["cfg_fork"])
    s2 = wait(ids["cfg_fork"])
    p2 = json.load(open(log_file, encoding="utf-8"))["prompt"]
    chk(s2["state"] == "done" and "INHERITED-PARENT-GOAL" in p2 and "FINAL-FORK" in p2, "fork includes inherited (compacted) history")
    open(mode_file, "w").write("fail")
    post(B, "/api/summarize/" + ids["plan"])
    s3 = wait(ids["plan"])
    chk(s3["state"] == "error" and "not logged in" in s3["error"], "CLI failure surfaced")
    open(mode_file, "w").write("slow")
    post(B, "/api/summarize/" + ids["cfg_fork_a"])
    time.sleep(0.5)
    chk(post(B, "/api/summarize/" + ids["cfg_fork_a"])[1].get("state") == "running", "no duplicate job while running")
    s4 = wait(ids["cfg_fork_a"], 15)
    chk(s4["state"] == "error" and "timed out" in s4["error"], "timeout surfaced")
    os.remove(mode_file)
    chk(post(B, "/api/summarize/task_e_aaaabbbbccccdddd0000111122223333")[0] == 400, "cloud tasks can't be summarized")
    chk(tree_hash(home) == h0, "nothing written under CODEX_HOME by summaries")
    chk(not [f for f in os.listdir(os.path.join(data, ".summarize")) if f.startswith("out-")], "scratch files cleaned up")


ROW = re.compile(r'<tr class="(grp|row[^"]*)"[^>]*?(?:data-g="([^"]*)" data-count="(\d+)"|data-id="([^"]+)")[^>]*>'
                 r'(?:<td class="t" title="([^"]*)" style="padding-left:(\d+)px">(.*?)</td>)?', re.S)


def run_ui(B, ids, browser, tmp):
    name = {v: k for k, v in ids.items()}

    def dump(qs, prof=None):
        cmd = [browser, "--headless=new", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=5000", "--dump-dom"]
        if prof:
            cmd.append("--user-data-dir=" + prof)
        return subprocess.run(cmd + [B + "/" + qs], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout

    def groups(out):
        tb = out[out.index('id="tb"'):out.index("</tbody>")]
        cur, d = None, {}
        for m in ROW.finditer(tb):
            if m.group(1) == "grp":
                cur = H.unescape(m.group(2))
                d[cur] = {"count": int(m.group(3)), "rows": []}
            else:
                d[cur]["rows"].append((name.get(m.group(4), m.group(4)), (int(m.group(6)) - 8) // 18, H.unescape(m.group(5)), m.group(7)))
        return d
    out = dump("?group=sections#" + ids["cfg"])
    if 'id="tb"' not in out or "</tbody>" not in out:
        print(f"SKIP UI tests ({os.path.basename(browser)} produced no --dump-dom output)")
        return
    G = groups(out)
    chk(list(G) == ["Alpha project", "Settings work", "Side projects", "No section"], f"sections mode: sidebar order, 'No section' last {list(G)}")
    st = G["Settings work"]
    chk(st["count"] == 5 and [(r[0], r[1]) for r in st["rows"]] == [("plan", 0), ("cfg", 0), ("cfg_fork", 1), ("cfg_fork_a", 2), ("cfg_fork_b", 2)],
        "in-section fork chain counted and visible")
    al = G["Alpha project"]
    rows = [(r[0], r[1]) for r in al["rows"]]
    chk(al["count"] == 5 and ("f1", 1) in rows and ("xfork", 0) in rows and sum(r[0].startswith("task_e_") for r in rows) == 2, "cloud tasks + cross-section fork as own row")
    xf = next(r for r in al["rows"] if r[0] == "xfork")
    chk('data-open="%s"' % ids["noparent"] in xf[3], "cross-section fork links to its parent")
    chk(not any(r[0] in ("s1", "s2") for r in al["rows"]), "subagents collapsed under parent")
    chk([r[0] for r in G["Side projects"]["rows"]] == ["p_old", "p_new", "p_mid"], "pinned first, then recency")
    chk({"noparent", "f2", "pf", "o", "no", "orph"} <= {r[0] for r in G["No section"]["rows"] if r[1] == 0}, "unsectioned sessions under 'No section'")
    chk('href="codex://threads/%s"' % ids["cfg"] in out and "Open in Codex" in out and "codex resume" not in out, "side panel Open in Codex link")
    chk(out.count('class="oc" href="codex://threads/') >= 5, "row open-in-Codex icons")
    g3 = list(groups(dump("")))
    chk("other-org/other-thing" in g3 and "No section" not in g3, "default grouping: sections + repo + folder")
    prof = os.path.join(tmp, "browser-profile")
    dump("?group=sections", prof)
    chk("No section" in groups(dump("", prof)), "grouping choice persisted in localStorage")


if __name__ == "__main__":
    sys.exit(main())
