#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Acceptance tests. Each hook is fed real hook input the same way the agent does (JSON on stdin -> stdout),
and both sides are checked:

  what should be stopped (BLOCK/DENY) is stopped + what should pass (OK) is not stopped.
  GUARDRAILS_HOME points at a temporary folder, so your real settings and log are never touched.
Usage: python3 tests/run_tests.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time

# Windows consoles default to cp932/cp1252 and cannot print the check marks below -> always write UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(os.path.dirname(HERE), "hooks")
TMP = tempfile.mkdtemp(prefix="guardrails_test_")
os.makedirs(os.path.join(TMP, ".claude", "guardrails"), exist_ok=True)
NOTES = os.path.join(TMP, "notes")
os.makedirs(NOTES)
with open(os.path.join(NOTES, "infra.md"), "w", encoding="utf-8") as f:
    f.write("# インフラメモ\n請求書の原本は 経理サーバー の /share/invoices/2026 に置いてある。\n")
with open(os.path.join(NOTES, "infra_en.md"), "w", encoding="utf-8") as f:
    f.write("# Infra notes\nThe invoice originals are stored on the accounting server under /share/invoices.\n")
with open(os.path.join(NOTES, "infra_ko.md"), "w", encoding="utf-8") as f:
    f.write("# 인프라 메모\n청구서 원본은 경리 서버의 /share/invoices 에 있습니다.\n")
ENVF = os.path.join(TMP, "app.env")
with open(ENVF, "w", encoding="utf-8") as f:
    f.write("API_TOKEN=zq7-THIS-IS-A-FAKE-TOKEN-91xx\nAPP_NAME=myservice-production\n")
CFG = os.path.join(TMP, ".claude", "guardrails", "config.json")
with open(CFG, "w", encoding="utf-8") as f:
    json.dump({"notes_dirs": [NOTES], "secret_files": [ENVF],
               "pipe_guard_tools": ["notify_send.py", "inbox_check"]}, f)
ENV = dict(os.environ, GUARDRAILS_HOME=TMP)

PASS = FAIL = 0


def transcript(rows):
    fd, path = tempfile.mkstemp(suffix=".jsonl", dir=TMP)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


def user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def tool_result(text):
    return {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": text}]}}


def assistant(text):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def run_hook(hook, payload, close_stdin=True):
    p = subprocess.Popen([sys.executable, os.path.join(HOOKS, hook)], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ENV)
    p.stdin.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    p.stdin.flush()
    # close_stdin=True: communicate() closes stdin itself. Closing it here first makes
    # Python <=3.13 raise "ValueError: flush of closed file" inside communicate().
    t0 = time.time()
    try:
        out, err = p.communicate(timeout=10) if close_stdin else (p.stdout.read(), p.stderr.read())
    except subprocess.TimeoutExpired:
        p.kill()
        return "HANG", time.time() - t0
    p.wait(timeout=10)
    out = out.decode("utf-8", "replace").strip()
    LAST_OUT[0] = out
    if not out:
        return "OK", time.time() - t0
    o = json.loads(out)
    if o.get("decision") == "block":
        return "BLOCK", time.time() - t0
    if (o.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny":
        return "DENY", time.time() - t0
    return "OK", time.time() - t0


SKIP = 0
LAST_OUT = [""]


def check(name, hook, payload, want, max_sec=None, **kw):
    global PASS, FAIL, SKIP
    if not os.path.exists(os.path.join(HOOKS, hook)):
        SKIP += 1
        return
    got, sec = run_hook(hook, payload, **kw)
    ok = got == want and (max_sec is None or sec <= max_sec)
    PASS += ok
    FAIL += (not ok)
    print("%s %-58s want=%-5s got=%-5s %.2fs" % ("✅" if ok else "🔴", name, want, got, sec))


def stop(rows, **extra):
    d = {"hook_event_name": "Stop", "transcript_path": transcript(rows), "stop_hook_active": False,
         "session_id": "test-session"}
    d.update(extra)
    return d


def bash(cmd):
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": cmd}}


print("=== done_gate")
check("claim with no evidence -> stop", "ag_done_gate.py",
      stop([user("ログイン画面のバグ直して"), assistant("login.py の判定を修正しました。")]), "BLOCK")
check("claim with a test result -> pass", "ag_done_gate.py",
      stop([user("直して"), tool_result("===== 12 passed in 0.8s ====="), assistant("修正しました。")]), "OK")
check("evidence only in an earlier turn -> stop", "ag_done_gate.py",
      stop([user("A直して"), tool_result("3 passed"), assistant("A を直しました。"),
            user("Bも"), assistant("B も修正しました。")]), "BLOCK")
check("plan ('will fix') -> pass", "ag_done_gate.py",
      stop([user("直して"), assistant("これから login.py を修正します。")]), "OK")
check("condition ('once fixed') -> pass", "ag_done_gate.py",
      stop([user("?"), assistant("直したら報告します。")]), "OK")
check("claim inside a quote -> pass", "ag_done_gate.py",
      stop([user("?"), assistant("ログには「修正しました」とだけ書かれていました。")]), "OK")
check("re-entry (stop_hook_active) -> pass", "ag_done_gate.py",
      stop([user("直して"), assistant("修正しました。")], stop_hook_active=True), "OK")
check("English 'fixed', no evidence -> stop", "ag_done_gate.py",
      stop([user("fix it"), assistant("I fixed the null check in parser.py.")]), "BLOCK")

print("=== unknown_gate")
check("'don't know' when the notes have it -> stop", "ag_unknown_gate.py",
      stop([user("請求書の原本ってどこ？"), assistant("請求書の原本の場所は分かりません。")]), "BLOCK")
check("'don't know' on a topic not in the notes -> pass", "ag_unknown_gate.py",
      stop([user("来月の天気は？"), assistant("来月の天気は分かりません。")]), "OK")
check("reply without 'don't know' -> pass", "ag_unknown_gate.py",
      stop([user("請求書の原本ってどこ？"), assistant("経理サーバーの /share/invoices/2026 です。")]), "OK")
check("list of the phrases themselves -> pass", "ag_unknown_gate.py",
      stop([user("請求書の件"), assistant("分かりません、見当たりません、どこですか、は拾う対象です。")]), "OK")

check("'don't know' quoted from the user -> pass", "ag_unknown_gate.py",
      stop([user("請求書の件"), assistant("請求書について、利用者は「原本の場所が分かりません」と言っていました。")]), "OK")

print("=== secret_guard")
wf = lambda url: {"hook_event_name": "PreToolUse", "tool_name": "WebFetch", "tool_input": {"url": url, "prompt": "x"}}
check(".env value in WebFetch -> deny", "ag_secret_guard.py",
      wf("https://example.com/?t=zq7-THIS-IS-A-FAKE-TOKEN-91xx"), "DENY")
check("WebFetch with no secret -> pass", "ag_secret_guard.py", wf("https://example.com/docs"), "OK")
check("value of a non-secret key (APP_NAME) -> pass", "ag_secret_guard.py",
      wf("https://example.com/?app=myservice-production"), "OK")
check("secret value in curl -> deny", "ag_secret_guard.py",
      bash("curl -H 'Authorization: Bearer zq7-THIS-IS-A-FAKE-TOKEN-91xx' https://api.example.com"), "DENY")
check("curl referring to an env var (no value) -> pass", "ag_secret_guard.py",
      bash('curl -H "Authorization: Bearer $API_TOKEN" https://api.example.com'), "OK")
check("local cat (nothing leaves) -> pass", "ag_secret_guard.py", bash("cat " + ENVF), "OK")
check("GitHub token format sent to MCP -> deny", "ag_secret_guard.py",
      {"hook_event_name": "PreToolUse", "tool_name": "mcp__chat__send",
       "tool_input": {"text": "ghp_" + "A" * 36}}, "DENY")

print("=== pipe_guard")
check("tool | tail -3 -> deny", "ag_pipe_guard.py", bash("python3 notify_send.py --to ops | tail -3"), "DENY")
check("tool | grep -> deny", "ag_pipe_guard.py", bash("inbox_check --all | grep -v OK"), "DENY")
check("tool | head over ssh -> deny", "ag_pipe_guard.py", bash("ssh host 'inbox_check --all | head -5'"), "DENY")
check("cut inside bash -c -> deny", "ag_pipe_guard.py", bash("bash -c \"inbox_check | tail -1\""), "DENY")
check("output to a file -> pass", "ag_pipe_guard.py", bash("inbox_check --all > /tmp/out.txt"), "OK")
check("reading the tool as a file -> pass", "ag_pipe_guard.py", bash("cat notify_send.py | head -40"), "OK")
check("tool as grep's target file -> pass", "ag_pipe_guard.py", bash("grep -n def notify_send.py | head"), "OK")
check("unregistered tool | tail -> pass", "ag_pipe_guard.py", bash("ls -la | tail -3"), "OK")
check("unrelated | head on another line -> pass", "ag_pipe_guard.py",
      bash("inbox_check > /tmp/o.txt\nawk '{print $1}' /tmp/o.txt | head"), "OK")
check("quoted heredoc body -> pass", "ag_pipe_guard.py",
      bash("cat > note.md <<'EOF'\ninbox_check | tail -1 と書いて止められた\nEOF"), "OK")
check("cut with sed -n -> deny", "ag_pipe_guard.py", bash("inbox_check | sed -n '1,4p'"), "DENY")

print("=== no_excuse_gate")
check("'will handle later', no evidence -> stop", "ag_no_excuse_gate.py",
      stop([user("?"), assistant("残りの2件は後ほど対応します。")]), "BLOCK")
check("'not implemented ... out of scope', no evidence -> stop", "ag_no_excuse_gate.py",
      stop([user("?"), assistant("CSV 出力は未実装ですが、今回は対象外とします。")]), "BLOCK")
check("'can't' after trying it -> pass", "ag_no_excuse_gate.py",
      stop([user("?"), assistant("CSV 出力は未実装です。`export --csv` を実行したら "
                                 "エラー: unknown flag が返ってきたので、この版ではできません。")]), "OK")
check("'haven't tried' is not evidence -> stop", "ag_no_excuse_gate.py",
      stop([user("?"), assistant("まだ試していないので、次回やります。")]), "BLOCK")
check("'can't' in a plain technical explanation -> pass", "ag_no_excuse_gate.py",
      stop([user("?"), assistant("この API は読み取り専用なので、書き込みはできません。")]), "OK")
check("'not out of scope' (negated) -> pass", "ag_no_excuse_gate.py",
      stop([user("?"), assistant("TODO が残っていますが、対象外ではありません。")]), "OK")
check("item finished in this reply -> pass", "ag_no_excuse_gate.py",
      stop([user("?"), assistant("⬜ だった CSV 出力は、今回実装しました。できない点はありません。")]), "OK")
check("a number inside a condition is not evidence -> stop", "ag_no_excuse_gate.py",
      stop([user("?"), assistant("依頼が3件出たら、後で対応します。")]), "BLOCK")

print("=== languages: done_gate (claim without evidence stops; plans, negations and claims with evidence pass)")
D = "ag_done_gate.py"
for lang, claim, plan in [
    ("en", "The bug is now fixed and everything works.", "I'll fix it after lunch."),
    ("ko", "로그인 버그를 수정했습니다.", "로그인 버그를 수정하겠습니다."),
    ("zh", "已经修复了登录问题。", "我会修复这个问题。"),
    ("de", "Ich habe den Fehler behoben.", "Ich werde den Fehler später beheben."),
    ("es", "He corregido el error de inicio de sesión.", "Voy a corregir el error."),
    ("pt", "Corrigi o bug no login.", "Vou corrigir o bug."),
    ("fr", "J'ai corrigé le bug.", "Je vais corriger le bug."),
]:
    check("%s: claim with no evidence -> stop" % lang, D, stop([user("?"), assistant(claim)]), "BLOCK")
    check("%s: plan -> pass" % lang, D, stop([user("?"), assistant(plan)]), "OK")
    check("%s: claim with a test result -> pass" % lang, D,
          stop([user("?"), tool_result("Ran 4 tests in 0.1s\n\nOK (4)"), assistant(claim)]), "OK")
check("en: plan (will ... pass) -> pass", D, stop([user("?"), assistant("I will make sure the tests pass.")]), "OK")
check("en: condition (once ... fixed) -> pass", D, stop([user("?"), assistant("Once the parser is fixed, the tests pass.")]), "OK")
check("en: negation (haven't fixed) -> pass", D, stop([user("?"), assistant("I haven't fixed the parser yet.")]), "OK")
check('en: "fixed" inside a quote -> pass', D, stop([user("?"), assistant('The commit message just says "fixed typo".')]), "OK")

print("=== languages: Chinese short claims (完成了 / 修好了 / 搞定了) vs questions and plans")
for claim in ["完成了。", "修好了", "搞定了。"]:
    check("zh: bare claim %s, no evidence -> stop" % claim, D, stop([user("?"), assistant(claim)]), "BLOCK")
for q in ["完成了吗？", "修好了吗？", "完成了没有", "是否完成了？", "有没有修好？"]:
    check("zh: question %s -> pass" % q, D, stop([user("?"), assistant(q)]), "OK")
for plan in ["完成了之后我会通知你。", "修好了再测试。"]:
    check("zh: plan %s -> pass" % plan, D, stop([user("?"), assistant(plan)]), "OK")
check("zh: 修好了没问题 is still a claim -> stop", D, stop([user("?"), assistant("修好了没问题。")]), "BLOCK")

print("=== languages: no_excuse_gate")
N = "ag_no_excuse_gate.py"
for lang, bad in [
    ("en", "I'll handle the remaining edge cases later."),
    ("ko", "나머지는 나중에 처리하겠습니다."),
    ("zh", "剩下的部分之后再处理。"),
    ("de", "Den Rest mache ich später, ich werde mich darum kümmern."),
    ("es", "El resto lo haré más tarde."),
    ("pt", "O resto vou fazer depois."),
    ("fr", "Je le ferai plus tard."),
]:
    check("%s: promise to do it later (no evidence) -> stop" % lang, N, stop([user("?"), assistant(bad)]), "BLOCK")
check("en: not implemented + out of scope -> stop", N,
      stop([user("?"), assistant("CSV export is not implemented yet, and it's out of scope for now.")]), "BLOCK")
check("en: can't after trying it -> pass", N,
      stop([user("?"), assistant("I ran `export --csv` and got an error: unknown flag. This version can't export CSV, and CSV export is not implemented.")]), "OK")
check("en: haven't tried is not evidence -> stop", N,
      stop([user("?"), assistant("I haven't tried it yet, so I'll do it next time.")]), "BLOCK")
check("en: can't in a spec explanation -> pass", N,
      stop([user("?"), assistant("This API is read-only, so writes can't be done through it.")]), "OK")
check("en: a number inside a condition is not evidence -> stop", N,
      stop([user("?"), assistant("If 3 more requests come in, I'll handle it later.")]), "BLOCK")
check("ko: after trying it -> pass", N,
      stop([user("?"), assistant("실행해 봤더니 오류가 났어요. 나머지는 나중에 하겠습니다.")]), "OK")

print("=== languages: unknown_gate")
U = "ag_unknown_gate.py"
check("en: I don't know when the notes have it -> stop", U,
      stop([user("Where are the invoice originals?"), assistant("I don't know where the invoice originals are.")]), "BLOCK")
check("en: topic not in the notes -> pass", U,
      stop([user("What's the weather next month?"), assistant("I don't know what the weather will be next month.")]), "OK")
check("ko: 모르겠습니다 when the notes have it -> stop", U,
      stop([user("청구서 원본은 어디에 있나요?"), assistant("청구서 원본이 어디에 있는지 모르겠습니다.")]), "BLOCK")

print("=== Codex transcript format")


def cx_user(text):
    return {"type": "response_item", "payload": {"type": "message", "role": "user",
                                                 "content": [{"type": "input_text", "text": text}]}}


def cx_tool(text):
    return {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "c1", "output": text}}


def cx_assistant(text):
    return {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                                                 "content": [{"type": "output_text", "text": text}]}}


check("codex: claim with a test result -> pass", D,
      stop([cx_user("Run the tests"), cx_tool("Process exited with code 0\nOutput:\n1 passed\n"),
            cx_assistant("Tests pass, done.")], last_assistant_message="Tests pass, done."), "OK")
check("codex: claim with no evidence -> stop", D,
      stop([cx_user("Fix it"), cx_assistant("I fixed the login bug.")], last_assistant_message="I fixed the login bug."), "BLOCK")
check("codex: injected <hook_prompt> is not a user turn -> pass", D,
      stop([cx_user("Run the tests"), cx_tool("Process exited with code 0\nOutput:\n1 passed\n"),
            cx_user("<hook_prompt hook_run_id=\"stop:1\">check</hook_prompt>"),
            cx_assistant("Tests pass, done.")], last_assistant_message="Tests pass, done."), "OK")
check("codex: evidence from an earlier turn does not count -> stop", D,
      stop([cx_user("A"), cx_tool("1 passed"), cx_assistant("A fixed."), cx_user("Now B"),
            cx_assistant("I fixed B too.")], last_assistant_message="I fixed B too."), "BLOCK")
check("codex: unknown_gate reads the user turn too -> stop", U,
      stop([cx_user("Where are the invoice originals?"), cx_assistant("Sorry, I don't know where the invoice originals are kept.")],
           last_assistant_message="Sorry, I don't know where the invoice originals are kept."), "BLOCK")

print("=== Codex PreToolUse input (same shape as Claude Code)")


def cx_pre(cmd):
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": cmd},
            "session_id": "codex-session", "transcript_path": transcript([cx_user("run it")]), "cwd": TMP,
            "turn_id": "turn-1", "tool_use_id": "call-1", "model": "codex-model", "permission_mode": "default"}


check("codex: secret value in curl -> deny", "ag_secret_guard.py",
      cx_pre("curl -H 'Authorization: Bearer zq7-THIS-IS-A-FAKE-TOKEN-91xx' https://api.example.com"), "DENY")
check("codex: registered tool | tail -> deny", "ag_pipe_guard.py", cx_pre("inbox_check --all | tail -3"), "DENY")

print("=== common: caller that never closes stdin")
check("body written, stdin left open -> decided within 1s (done_gate)", "ag_done_gate.py",
      stop([user("直して"), assistant("修正しました。")]), "BLOCK", close_stdin=False, max_sec=1.0)
check("body written, stdin left open -> decided within 1s (pipe_guard)", "ag_pipe_guard.py",
      bash("inbox_check | tail -1"), "DENY", close_stdin=False, max_sec=1.0)

print("=== common: the same text is stopped only once")
rows = [user("直して"), assistant("同じ文面テスト用：parser を修正しました。")]
check("first time -> stop", "ag_done_gate.py", stop(rows), "BLOCK")
check("same text, second time -> pass", "ag_done_gate.py", stop(rows), "OK")
check("same text in another session -> stop", "ag_done_gate.py", stop(rows, session_id="another-session"), "BLOCK")

print("=== messages: English by default, Japanese via config")
JA_CFG = os.path.join(TMP, "config_ja.json")
with open(JA_CFG, "w", encoding="utf-8") as f:
    json.dump({"message_language": "ja", "pipe_guard_tools": ["inbox_check"]}, f)


def check_text(name, hook, payload, want, needle, env_extra=None):
    global ENV
    saved = ENV
    if env_extra:
        ENV = dict(ENV, **env_extra)
    try:
        check(name, hook, payload, want)
    finally:
        ENV = saved
    if not os.path.exists(os.path.join(HOOKS, hook)):
        return
    global PASS, FAIL
    ok = needle in LAST_OUT[0]
    PASS += ok
    FAIL += (not ok)
    print("%s %-58s reason contains %r" % ("✅" if ok else "🔴", "  " + name.split(":")[0] + ": reason text", needle))


check_text("done_gate: default language is English", "ag_done_gate.py",
           stop([user("fix"), assistant("Message test EN: I fixed the parser.")]), "BLOCK", "no tool result in this turn")
check_text("done_gate: message_language=ja gives Japanese", "ag_done_gate.py",
           stop([user("fix"), assistant("Message test JA: I fixed the parser.")]), "BLOCK", "確かめた痕跡",
           {"GUARDRAILS_CONFIG": JA_CFG})
check_text("pipe_guard: default language is English", "ag_pipe_guard.py",
           bash("inbox_check | tail -2"), "DENY", "cuts the output of a registered tool")
check_text("pipe_guard: message_language=ja gives Japanese", "ag_pipe_guard.py",
           bash("inbox_check | tail -2"), "DENY", "登録された道具", {"GUARDRAILS_CONFIG": JA_CFG})
check_text("secret_guard: key format label is English by default", "ag_secret_guard.py",
           {"hook_event_name": "PreToolUse", "tool_name": "mcp__chat__send",
            "tool_input": {"text": "ghp_" + "B" * 36}}, "DENY", "GitHub token format")

print("=== common code, exercised through each hook (so a one-hook package still tests the shared files)")
JA_FULL_CFG = os.path.join(TMP, "config_ja_full.json")
with open(JA_FULL_CFG, "w", encoding="utf-8") as f:
    json.dump({"message_language": "ja", "notes_dirs": [NOTES], "secret_files": [ENVF],
               "pipe_guard_tools": ["inbox_check"]}, f)
check("body written, stdin left open -> decided within 1s (unknown_gate)", U,
      stop([user("請求書の原本ってどこ？"), assistant("stdin テスト：請求書の原本の場所は分かりません。")]),
      "BLOCK", close_stdin=False, max_sec=1.0)
check("body written, stdin left open -> decided within 1s (no_excuse_gate)", N,
      stop([user("?"), assistant("stdin テスト：残りは後ほど対応します。")]), "BLOCK", close_stdin=False, max_sec=1.0)
check("body written, stdin left open -> decided within 1s (secret_guard)", "ag_secret_guard.py",
      wf("https://example.com/?stdin=1&t=zq7-THIS-IS-A-FAKE-TOKEN-91xx"), "DENY", close_stdin=False, max_sec=1.0)
for hook, rows in [
    (U, [user("Where are the invoice originals?"), assistant("Once-test: I don't know where the invoice originals are.")]),
    (N, [user("?"), assistant("Once-test: I'll handle the remaining edge cases later.")]),
]:
    check("%s: first time -> stop" % hook[:-3], hook, stop(rows), "BLOCK")
    check("%s: same text, second time -> pass" % hook[:-3], hook, stop(rows), "OK")
    check("%s: same text in another session -> stop" % hook[:-3], hook, stop(rows, session_id="another-session"), "BLOCK")
check("codex: unknown_gate skips an injected <hook_prompt> when reading the user turn -> stop", U,
      stop([cx_user("Where are the invoice originals?"),
            cx_user("<hook_prompt hook_run_id=\"stop:1\">check</hook_prompt>"),
            cx_assistant("Sorry, I don't know where those are kept.")],
           last_assistant_message="Sorry, I don't know where those are kept."), "BLOCK")
check_text("unknown_gate: default language is English", U,
           stop([user("Where are the invoice originals?"), assistant("Message test EN: I don't know where the invoice originals are.")]),
           "BLOCK", "the notes seem to cover this")
check_text("unknown_gate: message_language=ja gives Japanese", U,
           stop([user("Where are the invoice originals?"), assistant("Message test JA: I don't know where the invoice originals are.")]),
           "BLOCK", "手元のメモ", {"GUARDRAILS_CONFIG": JA_FULL_CFG})
check_text("no_excuse_gate: default language is English", N,
           stop([user("?"), assistant("Message test EN: I'll handle the rest later.")]), "BLOCK", "without any sign of having tried")
check_text("no_excuse_gate: message_language=ja gives Japanese", N,
           stop([user("?"), assistant("Message test JA: I'll handle the rest later.")]), "BLOCK", "確かめた跡なし",
           {"GUARDRAILS_CONFIG": JA_FULL_CFG})
check_text("secret_guard: message_language=ja gives Japanese", "ag_secret_guard.py",
           wf("https://example.com/?ja=1&t=zq7-THIS-IS-A-FAKE-TOKEN-91xx"), "DENY", "鍵が入っています",
           {"GUARDRAILS_CONFIG": JA_FULL_CFG})

print("=== modes: done_gate_mode (block / warn) and secret_guard_mode (block / log); a bad value falls back to block")
LOG = os.path.join(TMP, ".claude", "guardrails", "guardrails.log")
LEDGER = os.path.join(TMP, ".claude", "guardrails", "secret_ledger.log")
SECRET = "zq7-THIS-IS-A-FAKE-TOKEN-91xx"
GH = "ghp_" + "C" * 36


def mode_cfg(name, **keys):
    path = os.path.join(TMP, "config_%s.json" % name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dict({"secret_files": [ENVF]}, **keys), f)
    return {"GUARDRAILS_CONFIG": path}


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def check_with(name, hook, payload, want, env_extra, extra_checks):
    """Run with another config, then check more things about the result (each counted as its own PASS/FAIL)."""
    global ENV, PASS, FAIL
    if not os.path.exists(os.path.join(HOOKS, hook)):
        check(name, hook, payload, want)   # counts the skip
        return
    saved = ENV
    ENV = dict(ENV, **env_extra)
    try:
        check(name, hook, payload, want)
    finally:
        ENV = saved
    for label, fn in extra_checks:
        ok = bool(fn(LAST_OUT[0]))
        PASS += ok
        FAIL += (not ok)
        print("%s %-58s" % ("✅" if ok else "🔴", "  " + label))


def sysmsg(out):
    try:
        return json.loads(out).get("systemMessage") or ""
    except ValueError:
        return ""


check_with("done_gate_mode=block (explicit) -> stop", D,
           stop([user("fix"), assistant("Mode test block: I fixed the parser.")]), "BLOCK",
           mode_cfg("dg_block", done_gate_mode="block"), [])
check_with("done_gate_mode=warn -> never stops", D,
           stop([user("fix"), assistant("Mode test warn: I fixed the parser.")]), "OK",
           mode_cfg("dg_warn", done_gate_mode="warn"),
           [("warn: same message shown as systemMessage", lambda o: "no tool result in this turn" in sysmsg(o)),
            ("warn: the claim is quoted in the message", lambda o: "I fixed the parser" in sysmsg(o)),
            ("warn: no decision field in the output", lambda o: '"decision"' not in o)])
check_with("done_gate_mode=warn, claim with evidence -> silent", D,
           stop([user("fix"), tool_result("3 passed"), assistant("Mode test warn ok: I fixed the parser.")]), "OK",
           mode_cfg("dg_warn", done_gate_mode="warn"), [("warn: nothing printed when there is evidence", lambda o: o == "")])
check_with("done_gate_mode=WARN (any case) -> never stops", D,
           stop([user("fix"), assistant("Mode test WARN: I fixed the parser.")]), "OK",
           mode_cfg("dg_warn_uc", done_gate_mode="WARN"), [])
check_with("done_gate_mode=bogus -> falls back to block", D,
           stop([user("fix"), assistant("Mode test bogus: I fixed the parser.")]), "BLOCK",
           mode_cfg("dg_bad", done_gate_mode="warm"),
           [("bad done_gate_mode: one line in the log", lambda o: read(LOG).count("invalid done_gate_mode='warm'") == 1)])

LEAK = wf("https://example.com/?mode=1&t=" + SECRET)
check_with("secret_guard_mode=block (explicit) -> deny", "ag_secret_guard.py", LEAK, "DENY",
           mode_cfg("sg_block", secret_guard_mode="block"), [])
if os.path.exists(LEDGER):
    os.remove(LEDGER)
check_with("secret_guard_mode=log -> never denies", "ag_secret_guard.py", LEAK, "OK",
           mode_cfg("sg_log", secret_guard_mode="log"),
           [("log: prints nothing (the tool call goes through)", lambda o: o == ""),
            ("log: one ledger line with tool, file and key name",
             lambda o: [ln.split("\t")[1:] for ln in read(LEDGER).splitlines()] == [["WebFetch", ENVF, "API_TOKEN"]]),
            ("log: ledger line starts with a timestamp",
             lambda o: read(LEDGER)[:4].isdigit() and read(LEDGER)[4] == "-"),
            ("log: the secret value is NOT in the ledger", lambda o: SECRET not in read(LEDGER)),
            ("log: the secret value is NOT in the log", lambda o: SECRET not in read(LOG))])
check_with("secret_guard_mode=log, key-format hit -> never denies", "ag_secret_guard.py",
           {"hook_event_name": "PreToolUse", "tool_name": "mcp__chat__send", "tool_input": {"text": GH}}, "OK",
           mode_cfg("sg_log", secret_guard_mode="log"),
           [("log: key-format hit appended (file '-')",
             lambda o: read(LEDGER).splitlines()[-1].split("\t")[1:] == ["mcp__chat__send", "-", "GitHub token format"]),
            ("log: the token is NOT in the ledger", lambda o: GH not in read(LEDGER) and "C" * 20 not in read(LEDGER))])
check_with("secret_guard_mode=log, no secret -> no ledger line", "ag_secret_guard.py", wf("https://example.com/clean"), "OK",
           mode_cfg("sg_log", secret_guard_mode="log"),
           [("log: ledger unchanged when nothing leaks", lambda o: len(read(LEDGER).splitlines()) == 2)])
check_with("secret_guard_mode=bogus -> falls back to deny", "ag_secret_guard.py", LEAK, "DENY",
           mode_cfg("sg_bad", secret_guard_mode="off"),
           [("bad secret_guard_mode: one line in the log", lambda o: read(LOG).count("invalid secret_guard_mode='off'") == 1)])

print("=== pipe_guard: redirections (2>&1, >&2, &>, |&) are not statement separators; real & and && still are")
P = "ag_pipe_guard.py"
check("tool 2>&1 | tail -1 -> deny", P, bash("inbox_check 2>&1 | tail -1"), "DENY")
check("tool |& tail -1 -> deny", P, bash("inbox_check |& tail -1"), "DENY")
check("python3 tool.py 2>&1 | head -> deny", P, bash("python3 notify_send.py 2>&1 | head"), "DENY")
check("tool 2>&1 >&2 | grep -> deny", P, bash("inbox_check --all 2>&1 >&2 | grep -v OK"), "DENY")
check("tool &>/dev/stdout | tail -> deny", P, bash("inbox_check --all &>/dev/stdout | tail -1"), "DENY")
check("tool 2>&1 > out.txt -> pass", P, bash("inbox_check 2>&1 > out.txt"), "OK")
check("tool > out.txt 2>&1 -> pass", P, bash("inbox_check > out.txt 2>&1"), "OK")
check("tool &> out.txt; then read the file -> pass", P, bash("inbox_check &> out.txt; cat out.txt"), "OK")
check("sleep 1 & tool -> pass", P, bash("sleep 1 & inbox_check"), "OK")
check("tool > f & (background), other cmd | head -> pass", P,
      bash("inbox_check > /tmp/o.txt & grep -c ERR /tmp/log.txt | head"), "OK")
check("tool > f && other cmd | head -> pass", P,
      bash("inbox_check > /tmp/o.txt && grep -c ERR /tmp/o.txt | head"), "OK")
check("unregistered tool 2>&1 | tail -> pass", P, bash("mytool 2>&1 | tail"), "OK")

print("=== pipe_guard: built-in default tools (on unless pipe_guard_use_defaults is false; your tools are added to them)")
NO_CFG = {"GUARDRAILS_CONFIG": os.path.join(TMP, "no_such_config.json")}
check_with("no config at all: pytest 2>&1 | tail -5 -> deny", P, bash("pytest 2>&1 | tail -5"), "DENY", NO_CFG, [])
check_with("no config at all: npm test | tail -> deny", P, bash("npm test | tail"), "DENY", NO_CFG, [])
check_with("no config at all: ls | grep x -> pass", P, bash("ls | grep x"), "OK", NO_CFG, [])
check_with("no config at all: ps aux | grep python -> pass", P, bash("ps aux | grep python"), "OK", NO_CFG, [])
check("defaults + your tools: pytest 2>&1 | tail -5 -> deny", P, bash("pytest 2>&1 | tail -5"), "DENY")
check("defaults + your tools: npm test | tail -> deny", P, bash("npm test | tail"), "DENY")
check("defaults + your tools: your tool (inbox_check) | tail -> deny", P, bash("inbox_check | tail"), "DENY")
check("default: python3 -m pytest -q | tail -3 -> deny", P, bash("python3 -m pytest -q | tail -3"), "DENY")
check("default: git push 2>&1 | tail -3 -> deny", P, bash("git push origin main 2>&1 | tail -3"), "DENY")
check("default: uv sync | tail (uv is also a wrapper) -> deny", P, bash("uv sync | tail -2"), "DENY")
check("default: go test ./... | grep FAIL -> deny", P, bash("go test ./... | grep FAIL"), "DENY")
check("default: ls | grep x -> pass", P, bash("ls | grep x"), "OK")
check("default: ps aux | grep python -> pass", P, bash("ps aux | grep python"), "OK")
check("default: npm view (subcommand not listed) | head -> pass", P, bash("npm view react versions | head"), "OK")
check("default: git log | head (subcommand not listed) -> pass", P, bash("git log --oneline | head -20"), "OK")
OPT_OUT = mode_cfg("pg_optout", pipe_guard_use_defaults=False, pipe_guard_tools=["inbox_check"])
check_with("use_defaults=false: pytest | tail -> pass", P, bash("pytest 2>&1 | tail -5"), "OK", OPT_OUT, [])
check_with("use_defaults=false: npm test | tail -> pass", P, bash("npm test | tail"), "OK", OPT_OUT, [])
check_with("use_defaults=false: your tool still -> deny", P, bash("inbox_check | tail"), "DENY", OPT_OUT, [])
check_with("use_defaults=false and no tools -> pass", P, bash("pytest | tail"), "OK",
           mode_cfg("pg_optout_empty", pipe_guard_use_defaults=False), [])

sys.dont_write_bytecode = True   # never leave __pycache__ (with this machine's paths) inside the package
sys.path.insert(0, HOOKS)
import _common  # noqa: E402
missing = sorted(set(_common.MESSAGES["en"]) ^ set(_common.MESSAGES["ja"]))
ok = not missing
PASS += ok
FAIL += (not ok)
print("%s %-58s %s" % ("✅" if ok else "🔴", "en and ja message tables have the same keys", missing or ""))

print("\n=== %d PASS / %d FAIL ===" % (PASS, FAIL) + (" (%d skipped: hook not in this package)" % SKIP if SKIP else ""))
sys.exit(1 if FAIL else 0)
