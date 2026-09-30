#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mutation test: break the code on purpose, one spot at a time, and confirm the acceptance tests turn red.

Green tests alone do not show that the tests can catch anything. A spot that can be broken without a red test is not protected.
Usage: python3 tests/mutate.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

# Windows consoles default to cp932/cp1252 and cannot print the check marks below -> always write UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUTANTS = [
    ("done_gate: evidence check always true", "hooks/ag_done_gate.py",
     'return any(EVIDENCE.search(r or "") for r in results)', "return True"),
    ("pipe_guard: stop removing heredoc bodies", "hooks/ag_pipe_guard.py",
     'cmd = HEREDOC_QUOTED.sub("", cmd)', "pass"),
    ("pipe_guard: ignore commands inside ssh", "hooks/ag_pipe_guard.py",
     'if name == "ssh" and depth < 3:', "if False:"),
    ("pipe_guard: every single & splits statements again (2>&1 bug)", "hooks/ag_pipe_guard.py",
     'if sep == "&" and redirect_amp(s, i):', "if False:"),
    ("pipe_guard: |& splits statements again", "hooks/ag_pipe_guard.py",
     'return prev in "<>|" or nxt == ">"', 'return prev in "<>" or nxt == ">"'),
    ("pipe_guard: &> splits statements again", "hooks/ag_pipe_guard.py",
     'return prev in "<>|" or nxt == ">"', 'return prev in "<>|"'),
    ("pipe_guard: background & no longer separates", "hooks/ag_pipe_guard.py",
     'return prev in "<>|" or nxt == ">"', "return True"),
    ("pipe_guard: built-in default tools ignored", "hooks/ag_pipe_guard.py",
     "tools = DEFAULT_TOOLS + tools", "pass"),
    ("pipe_guard: defaults replace your tools instead of adding", "hooks/ag_pipe_guard.py",
     "tools = DEFAULT_TOOLS + tools", "tools = DEFAULT_TOOLS"),
    ("pipe_guard: pipe_guard_use_defaults=false ignored", "hooks/ag_pipe_guard.py",
     'if cfg.get("pipe_guard_use_defaults", True) is not False:', "if True:"),
    ("pipe_guard: 'tool subcommand' entries (npm test) never match", "hooks/ag_pipe_guard.py",
     'return bool(sub) and ("%s %s" % (name, sub) in names', 'return False and ("%s %s" % (name, sub) in names'),
    ("pipe_guard: 'tool subcommand' entries match any subcommand", "hooks/ag_pipe_guard.py",
     'return bool(sub) and ("%s %s" % (name, sub) in names or "%s %s" % (stem, sub) in names)',
     'return any(n.startswith(name + " ") for n in names)'),
    ("pipe_guard: wrapper names (uv) not matched", "hooks/ag_pipe_guard.py",
     "if any(name_hits(w, r, names) for w, r in wrapped):", "if False:"),
    ("secret_guard: drop the secret-key-name filter", "hooks/ag_secret_guard.py",
     "if SECRET_KEY.search(key) and len(val) >= MIN_LEN:", "if len(val) >= MIN_LEN:"),
    ("no_excuse_gate: drop the negation guard", "hooks/ag_no_excuse_gate.py",
     "not EVIDENCE_NEG.match(text[m.end():m.end() + 8])", "True"),
    ("unknown_gate: stop removing quotes", "hooks/ag_unknown_gate.py",
     'body = QUOTED.sub("□", body)', "pass"),
    ("_common: wait for EOF instead of parsing as data arrives", "hooks/_common.py",
     '                try:\n                    result["data"] = json.loads(buf.getvalue().decode("utf-8", "replace"))\n'
     '                    break\n                except ValueError:\n                    continue', "                continue"),
    ("phrases: empty the other-language table", "hooks/phrases.py", "LANGS = {", "LANGS = {} and {"),
    ("no_excuse_gate: drop the English leading negation (haven't tried)", "hooks/ag_no_excuse_gate.py",
     "and not EVIDENCE_NEG_PRE.search(text[max(0, m.start() - 24):m.start()])", ""),
    ("done_gate: drop English plans and negations", "hooks/ag_done_gate.py",
     """r"\\b(?:I'll|I will|will|going to""", """r"\\b(?:XXNOPE"""),
    ("_common: count Codex injected messages as user turns", "hooks/_common.py",
     'if p["role"] == "user" and text.lstrip().startswith("<"):', 'if False:'),
    ("_common: ignore Codex tool results", "hooks/_common.py",
     'if p.get("type") == "function_call_output":', 'if False:'),
    ("_common: drop the session from the stop-once memory", "hooks/_common.py",
     'hook + "\\0" + session + "\\0" + (text or "")', 'hook + "\\0" + (text or "")'),
    ("_common: drop the stop-once memory", "hooks/_common.py",
     "    if fp in seen:\n        return True", "    pass"),
    ("phrases: drop the Chinese question exclusion (完成了吗)", "hooks/phrases.py",
     'r"了(?:吗|嗎|么|麼)", ', ""),
    ("_common: ignore message_language (always English)", "hooks/_common.py",
     'return lang if lang in MESSAGES else "en"', 'return "en"'),
    ("done_gate: warn mode silently drops the message", "hooks/ag_done_gate.py",
     '        C.warn(C.msg("done_gate.block", claim=claim[:80]))\n        return', "        return"),
    ("done_gate: warn mode still blocks", "hooks/ag_done_gate.py",
     '("block", "warn")) == "warn":', '("block", "warn")) == "never":'),
    ("_common: warn goes to stderr only (no systemMessage)", "hooks/_common.py",
     '    sys.stdout.write(json.dumps({"systemMessage": reason}, ensure_ascii=False))', "    pass"),
    ("secret_guard: log mode writes the value into the ledger", "hooks/ag_secret_guard.py",
     "        write_ledger(tool, hits)\n", '        write_ledger(tool, hits + [("-", text)])\n'),
    ("secret_guard: log mode skips the ledger", "hooks/ag_secret_guard.py",
     "        write_ledger(tool, hits)\n", "        pass\n"),
    ("secret_guard: log mode still denies", "hooks/ag_secret_guard.py",
     '("block", "log")) == "log":', '("block", "log")) == "never":'),
    ("_common: invalid mode falls open (uses the non-blocking mode)", "hooks/_common.py",
     '"/".join(allowed), allowed[0]))\n    return allowed[0]', '"/".join(allowed), allowed[0]))\n    return allowed[-1]'),
    ("_common: invalid mode is not logged", "hooks/_common.py",
     '    log(hook, "invalid %s=%r', '    0 and log(hook, "invalid %s=%r'),
    # install.py mutants are judged by tests/test_install.py (5th field)
    ("install: own lines recognised by file name only (removes same-name checks from other folders)", "install.py",
     "    return any(_same_file(path, os.path.join(HOOKS_DIR, name)) for name, path in hook_paths(entry))",
     '    cmd = str(entry.get("command", "")).replace("\\\\", "/")\n'
     '    return any(("hooks/" + h) in cmd for h in STOP_HOOKS + [p for p, _ in PRE_HOOKS])',
     "tests/test_install.py"),
    ("install: add a check again although another folder already registered it", "install.py",
     "            skip.add(name)\n", "            pass\n", "tests/test_install.py"),
    ("install: ~ in a command is not expanded", "install.py",
     "    return os.path.expanduser(p)", "    return p", "tests/test_install.py"),
    ("install: `python` on PATH used without checking it starts Python (Store stub)", "install.py",
     "        if found and (works or _runs_python3)(found):", "        if found:", "tests/test_install.py"),
    ("install: the stub check accepts any program as Python", "install.py",
     '        ok = r.returncode == 0 and r.stdout.strip() == "3"', "        ok = True", "tests/test_install.py"),
    ("install: Windows falls back to `python3` when sys.executable is unknown", "install.py",
     '("python" if win else "python3")', '"python3"', "tests/test_install.py"),
    ("install: old-name lines (before the ag_ prefix) of this folder are left behind", "install.py",
     "        if name in NAMES or name in LEGACY:", "        if name in NAMES:", "tests/test_install.py"),
    ("install: old-name lines of another folder are removed too", "install.py",
     "    return any(_same_file(path, os.path.join(HOOKS_DIR, name)) for name, path in hook_paths(entry))",
     "    return any(name in LEGACY or _same_file(path, os.path.join(HOOKS_DIR, name)) for name, path in hook_paths(entry))",
     "tests/test_install.py"),
]


# Mutants in the shared files (_common.py / phrases.py) whose code path only some hooks use.
# In a package without any of these hooks, the broken spot is never executed, so the mutant cannot be
# caught there (and cannot do harm there). It is skipped and reported. Mutants not listed here apply to every hook.
USED_BY = {
    "phrases: empty the other-language table": ["ag_done_gate.py", "ag_unknown_gate.py", "ag_no_excuse_gate.py"],
    "_common: count Codex injected messages as user turns": ["ag_done_gate.py", "ag_unknown_gate.py"],
    "_common: ignore Codex tool results": ["ag_done_gate.py"],
    "_common: drop the session from the stop-once memory": ["ag_done_gate.py", "ag_unknown_gate.py", "ag_no_excuse_gate.py"],
    "_common: drop the stop-once memory": ["ag_done_gate.py", "ag_unknown_gate.py", "ag_no_excuse_gate.py"],
    "phrases: drop the Chinese question exclusion (完成了吗)": ["ag_done_gate.py"],
    "_common: warn goes to stderr only (no systemMessage)": ["ag_done_gate.py"],
    "_common: invalid mode falls open (uses the non-blocking mode)": ["ag_done_gate.py", "ag_secret_guard.py"],
    "_common: invalid mode is not logged": ["ag_done_gate.py", "ag_secret_guard.py"],
}


def applies(name, rel):
    if not os.path.exists(os.path.join(ROOT, rel)):
        return False
    users = USED_BY.get(name)
    return users is None or any(os.path.exists(os.path.join(ROOT, "hooks", h)) for h in users)


def main():
    survived = ran = 0
    for name, rel, old, new, *test in MUTANTS:
        test = test[0] if test else "tests/run_tests.py"
        if not applies(name, rel):
            continue
        d = tempfile.mkdtemp(prefix="guardrails_mut_")
        shutil.copytree(ROOT, d, dirs_exist_ok=True)
        path = os.path.join(d, rel)
        ran += 1
        src = open(path, encoding="utf-8").read()
        if src.count(old) != 1:
            print("⚠ mutant does not apply (did the code change?):", name)
            survived += 1
            continue
        open(path, "w", encoding="utf-8").write(src.replace(old, new))
        try:
            r = subprocess.run([sys.executable, test], cwd=d,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            reds = [ln for ln in r.stdout.splitlines() if ln.startswith("🔴")]
            killed = r.returncode != 0
        except subprocess.TimeoutExpired:
            killed, reds = True, ["timeout"]
        survived += (not killed)
        print("%s %s %s" % ("✅ killed" if killed else "🔴 survived", name,
                             ("| " + reds[0].split("want")[0].strip()) if reds else ""))
        shutil.rmtree(d, ignore_errors=True)
    print("\n=== %d mutants, %d survived ===" % (ran, survived)
          + (" (%d skipped: hook not in this package, or shared code only those hooks use)" % (len(MUTANTS) - ran) if ran < len(MUTANTS) else ""))
    sys.exit(1 if survived else 0)


if __name__ == "__main__":
    main()
