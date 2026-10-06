"""Builds a synthetic, fake Codex home (state_5.sqlite + rollouts + sidebar state) for tests.

All names, ids, paths and repos here are made up.
"""
import json
import os
import sqlite3
import time
import uuid

SCHEMA = """
create table threads(id text primary key, rollout_path text, created_at integer, updated_at integer, source text, model_provider text,
 cwd text, title text, sandbox_policy text, approval_mode text, tokens_used integer, has_user_event int, archived int, archived_at int,
 git_sha text, git_branch text, git_origin_url text, cli_version text, first_user_message text, agent_nickname text, agent_role text,
 memory_mode text, model text, reasoning_effort text, agent_path text, created_at_ms int, updated_at_ms int, thread_source text,
 preview text, recency_at int, recency_at_ms int, history_mode text, name text, is_pinned int, thread_section_id text,
 section_position int, section_entered_at_ms int, project_id text, originator text);
create table thread_spawn_edges(parent_thread_id text, child_thread_id text, status text);
create table thread_sections(id text, name text, appearance text);
create table thread_attachments(id text, thread_id text, attachment_type text, identity_key text, payload text, created_at int);
"""
REPO = "https://github.com/example-org/example-app.git"
M = 60000


def build(home):
    os.makedirs(os.path.join(home, "sessions", "2026", "01", "02"), exist_ok=True)
    day = os.path.join(home, "sessions", "2026", "01", "02")
    db = sqlite3.connect(os.path.join(home, "state_5.sqlite"))
    db.execute("pragma journal_mode=wal")
    db.executescript(SCHEMA)
    now = int(time.time() * 1000)
    ids, rollouts = {}, {}

    def meta_line(tid, fork=None, extra=None):
        m = {"session_id": tid, "id": tid}
        if fork:
            m["forked_from_id"] = fork
        m.update({"timestamp": "x", "cwd": "/home/dev/example-app", "base_instructions": {"text": "x" * 6000}})
        m.update(extra or {})
        return json.dumps({"type": "session_meta", "payload": m}) + "\n"

    def mk(key, title, ago, src="vscode", branch=None, archived=0, section=None, pos=None, fork=None, ts="user",
           segment=False, name=None, nick=None, role=None, cwd="/home/dev/example-app", origin=REPO, pinned=0, rollout=True):
        tid = str(uuid.uuid4())
        path = None
        if rollout:
            fn = f"rollout-2026-01-02T10-00-00-{tid}" + (f"_{uuid.uuid4()}" if segment else "") + ".jsonl"
            path = os.path.join(day, fn)
            extra = {"history_base": {"thread_id": tid, "end_ordinal_exclusive": 5}} if segment else None
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(meta_line(tid, fork, extra))
        db.execute("""insert into threads(id,rollout_path,created_at_ms,updated_at_ms,recency_at_ms,source,cwd,title,name,preview,
            first_user_message,archived,git_branch,git_origin_url,agent_nickname,agent_role,thread_source,is_pinned,thread_section_id,
            section_position,model,tokens_used) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (tid, path, now - ago - 60 * M, now - ago, now - ago, src, cwd, title, name, "last msg of " + title,
                    "please " + title, archived, branch, origin, nick, role, ts, pinned, section, pos, "test-model", 1234))
        ids[key], rollouts[key] = tid, path
        return tid

    db.execute("insert into thread_sections values('s1','Alpha project',null)")
    db.execute("insert into thread_sections values('s2','Side projects',null)")
    db.execute("insert into thread_sections values('s3','Settings work',null)")
    a = mk("a", "Commit naming", 5 * M, branch="feat/42-commit-names", section="s1")
    f1 = mk("f1", "fork of commit naming", 2 * 60 * M, branch="feat/42-commit-names", fork=a, section="s1")
    mk("f2", "fork of fork", 3 * 24 * 60 * M, fork=f1, segment=True)
    s1 = mk("s1", "explorer", 3 * M, src=json.dumps({"subagent": {"thread_spawn": {"parent_thread_id": a, "agent_nickname": "Ada"}}}),
            fork=a, ts="subagent", nick="Ada", role="explorer")
    s2 = mk("s2", "worker", 30 * M, src=json.dumps({"subagent": {"thread_spawn": {"parent_thread_id": a, "agent_nickname": "Bob"}}}),
            ts="subagent", nick="Bob", role="worker")
    db.execute("insert into thread_spawn_edges values(?,?,?)", (a, s1, "open"))
    db.execute("insert into thread_spawn_edges values(?,?,?)", (a, s2, "closed"))
    mk("g", "guardian", 4 * M, src='{"subagent":{"other":"guardian"}}', ts="guardian_review")
    mk("r", "review", 4 * M, src='{"subagent":"review"}')
    mk("u", "Paged archived thread", 40 * 24 * 60 * M, src="cli", segment=True, branch="fix/7-bug", archived=1)
    mk("o", "Other repo", 10 * 24 * 60 * M, src="cli", branch="main", cwd="/home/dev/other-thing", origin="https://github.com/other-org/other-thing")
    mk("orph", "orphan fork", 50 * M, fork=str(uuid.uuid4()))
    mk("no", "no origin", 0, src="cli", cwd="D:\\work\\Example-App", origin=None, rollout=False)
    mk("p_old", "pinned old", 20 * 24 * 60 * M, section="s2", pinned=1, cwd="/home/dev/side", origin=None, rollout=False)
    mk("p_new", "side recent", 1 * M, section="s2", cwd="/home/dev/side", origin=None, rollout=False)
    mk("p_mid", "side mid", 2 * 60 * M, section="s2", cwd="/home/dev/other", origin="https://github.com/other-org/other-thing", rollout=False)
    # "Settings work": a fork chain inside one section (sidebar order differs from tree order)
    mk("plan", "Plan settings storage", 120 * M, section="s3", pos=62500, name="Plan settings storage")
    cfg = mk("cfg", "Config loader issues 11,12,13", 2 * M, section="s3", pos=125000, name="Config loader issues 11,12,13")
    cfgf = mk("cfg_fork", "Config loader issue 12", 30 * M, section="s3", pos=500000, fork=cfg, name="Config loader issue 12")
    mk("cfg_fork_a", "Persist per-user setting 14", 10 * M, section="s3", pos=250000, fork=cfgf, name="Persist per-user setting 14")
    mk("cfg_fork_b", "Persist per-user setting 15", 50 * M, section="s3", pos=1000000, fork=cfgf, name="Persist per-user setting 15")
    # a sectioned fork whose parent has no section; NULL name -> display title from session_index
    np_ = mk("noparent", "parent prompt in no section", 3 * 24 * 60 * M)
    mk("xfork", "first prompt text of the fork", 4 * 60 * M, section="s1", pos=1000000, fork=np_)
    # paged fork: base file has forked_from_id, latest segment does not
    pf = str(uuid.uuid4())
    orig = os.path.join(day, f"rollout-2026-01-02T09-00-00-{pf}.jsonl")
    seg = os.path.join(day, f"rollout-2026-01-02T09-30-00-{pf}_{uuid.uuid4()}.jsonl")
    with open(orig, "w", encoding="utf-8") as fh:
        fh.write(meta_line(pf, fork=a))
    with open(seg, "w", encoding="utf-8") as fh:
        fh.write(meta_line(pf, extra={"history_base": {"thread_id": pf}}))
    db.execute("insert into threads(id,rollout_path,created_at_ms,updated_at_ms,recency_at_ms,source,cwd,title,archived) values(?,?,?,?,?,?,?,?,0)",
               (pf, seg, now, now - 99999, now - 99999, "vscode", "C:\\work\\example-app", "paged fork"))
    ids["pf"] = pf
    db.execute("insert into thread_attachments values('1',?,'pull_request','k',?,0)",
               (a, json.dumps({"url": "https://github.com/example-org/example-app/pull/1", "root": "/r", "headBranch": "feat/42"})))
    db.execute("insert into thread_attachments values('2',?,'worktree','k',?,0)", (a, json.dumps({"root": "/wt/1"})))
    db.commit()
    db.close()
    with open(os.path.join(home, "session_index.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": a, "thread_name": "Commit naming (indexed)", "updated_at": "x"}) + "\n")
        fh.write(json.dumps({"id": ids["xfork"], "thread_name": "Language & Diagram Sync", "updated_at": "x"}) + "\n")
    gs = {"electron-persisted-atom-state": {"sidebar-custom-sections-v3": {"acct": {
        "sectionOrder": ["custom:u", "custom:l"],
        "sections": [
            {"id": "u", "name": "Alpha project", "hostSectionIds": {"local": "s1"}, "itemKeys": [
                f"codex:thread:local:{a}", "codex:thread:remote:task_e_aaaabbbbccccdddd0000111122223333",
                "codex:thread:remote:task_e_9999888877776666555544443333aaaa", f"codex:thread:local:{f1}",
                f"codex:thread:local:{ids['xfork']}"]},
            {"id": "l", "name": "Settings work", "hostSectionIds": {"local": "s3"},
             "itemKeys": [f"codex:thread:local:{ids[k]}" for k in ("plan", "cfg", "cfg_fork_a", "cfg_fork", "cfg_fork_b")]}]}}}}
    with open(os.path.join(home, ".codex-global-state.json"), "w", encoding="utf-8") as fh:
        json.dump(gs, fh)
    with open(os.path.join(home, "config.toml"), "w", encoding="utf-8") as fh:
        fh.write('model = "test-model-1"\n[mcp_servers.x]\nmodel = "not-this"\n')
    _transcripts(home, ids, rollouts)
    return ids


def _ui(parts, kinds):
    return {"type": "response_item", "payload": {"type": "message", "role": "user",
            "content": [{"type": "input_text", "text": t} for t in parts],
            "internal_chat_message_metadata_passthrough": {"content_item_kinds": kinds}}}


def _asst(t, phase="final_answer"):
    return {"type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": phase,
                                                 "content": [{"type": "output_text", "text": t}]}}


def _transcripts(home, ids, rollouts):
    ctx = "REPEATED-HANDOFF-CONTEXT " * 20
    base = rollouts["cfg"]
    lines = [
        _ui(["# AGENTS.md instructions\nAGENTS-MD-TEXT", "<environment_context>ENVCTX</environment_context>"],
            ["agents_md.instructions", "environments.environment_context"]),
        _ui([ctx, "Please fix config loader issues 11, 12 and 13 (GOAL-MARKER)"], ["user.text", "user.text"]),
        {"type": "response_item", "payload": {"type": "reasoning", "summary": [{"text": "REASONING-LEAK"}], "encrypted_content": "x" * 5000}},
        _asst("Looking at the config loader…", "commentary"),
        {"type": "response_item", "payload": {"type": "function_call", "name": "shell", "arguments": json.dumps({"command": ["bash", "-lc", "rg ConfigLoader"]})}},
        {"type": "response_item", "payload": {"type": "function_call_output", "output": "HUGE-TOOL-OUTPUT " * 20000}},
        {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "apply_patch", "input": "*** Begin Patch\n" + "+line\n" * 2000}},
        {"type": "token_usage_record", "payload": {"usage": {"total": 123}}},
        _asst("Fixed 11 and 12 on branch feat/13-config; 13 needs a decision on defaults. FINAL-1"),
        _ui([ctx, "what about 13?"], ["user.text", "user.text"]),
        {"type": "event_msg", "payload": {"type": "turn_aborted", "reason": "interrupted"}},
    ]
    with open(base, "a", encoding="utf-8") as fh:
        for o in lines:
            fh.write(json.dumps(o) + "\n")
    seg = base.replace(".jsonl", "_11111111-2222-3333-4444-555555555555.jsonl")
    with open(seg, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "session_meta", "payload": {"session_id": ids["cfg"], "id": ids["cfg"], "history_base": {"thread_id": ids["cfg"]}}}) + "\n")
        fh.write(json.dumps({"type": "compacted", "payload": {"message": "", "replacement_history": [
            _ui(["Please fix config loader issues 11, 12 and 13 (GOAL-MARKER)"], ["user.text"])["payload"]]}}) + "\n")
        fh.write(json.dumps(_ui(["SEGMENT-USER-MSG: go with option B for 13"], ["user.text"])) + "\n")
        fh.write(json.dumps(_asst("Implemented option B for 13. FINAL-2")) + "\n")
    with open(rollouts["cfg_fork"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "compacted", "payload": {"message": "", "replacement_history": [
            _ui(["INHERITED-PARENT-GOAL"], ["user.text"])["payload"]]}}) + "\n")
        fh.write(json.dumps(_ui(["focus on 12 only"], ["user.text"])) + "\n")
        fh.write(json.dumps(_asst("12 done. FINAL-FORK")) + "\n")
    for k in ("plan", "cfg_fork_a"):
        with open(rollouts[k], "a", encoding="utf-8") as fh:
            fh.write(json.dumps(_ui([f"user ask for {k}"], ["user.text"])) + "\n")
            fh.write(json.dumps(_asst(f"done {k}")) + "\n")
