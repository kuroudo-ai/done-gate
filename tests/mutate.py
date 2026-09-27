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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUTANTS = [
    ("done_gate: evidence check always true", "hooks/done_gate.py",
     'return any(EVIDENCE.search(r or "") for r in results)', "return True"),
    ("pipe_guard: stop removing heredoc bodies", "hooks/pipe_guard.py",
     'cmd = HEREDOC_QUOTED.sub("", cmd)', "pass"),
    ("pipe_guard: ignore commands inside ssh", "hooks/pipe_guard.py",
     'if name == "ssh" and depth < 3:', "if False:"),
    ("secret_guard: drop the secret-key-name filter", "hooks/secret_guard.py",
     "if SECRET_KEY.search(key) and len(val) >= MIN_LEN:", "if len(val) >= MIN_LEN:"),
    ("no_excuse_gate: drop the negation guard", "hooks/no_excuse_gate.py",
     "not EVIDENCE_NEG.match(text[m.end():m.end() + 8])", "True"),
    ("unknown_gate: stop removing quotes", "hooks/unknown_gate.py",
     'body = QUOTED.sub("□", body)', "pass"),
    ("_common: wait for EOF instead of parsing as data arrives", "hooks/_common.py",
     '                try:\n                    result["data"] = json.loads(buf.getvalue().decode("utf-8", "replace"))\n'
     '                    break\n                except ValueError:\n                    continue', "                continue"),
    ("phrases: empty the other-language table", "hooks/phrases.py", "LANGS = {", "LANGS = {} and {"),
    ("no_excuse_gate: drop the English leading negation (haven't tried)", "hooks/no_excuse_gate.py",
     "and not EVIDENCE_NEG_PRE.search(text[max(0, m.start() - 24):m.start()])", ""),
    ("done_gate: drop English plans and negations", "hooks/done_gate.py",
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
    ("done_gate: warn mode silently drops the message", "hooks/done_gate.py",
     '        C.warn(C.msg("done_gate.block", claim=claim[:80]))\n        return', "        return"),
    ("done_gate: warn mode still blocks", "hooks/done_gate.py",
     '("block", "warn")) == "warn":', '("block", "warn")) == "never":'),
    ("_common: warn goes to stderr only (no systemMessage)", "hooks/_common.py",
     '    sys.stdout.write(json.dumps({"systemMessage": reason}, ensure_ascii=False))', "    pass"),
    ("secret_guard: log mode writes the value into the ledger", "hooks/secret_guard.py",
     "        write_ledger(tool, hits)\n", '        write_ledger(tool, hits + [("-", text)])\n'),
    ("secret_guard: log mode skips the ledger", "hooks/secret_guard.py",
     "        write_ledger(tool, hits)\n", "        pass\n"),
    ("secret_guard: log mode still denies", "hooks/secret_guard.py",
     '("block", "log")) == "log":', '("block", "log")) == "never":'),
    ("_common: invalid mode falls open (uses the non-blocking mode)", "hooks/_common.py",
     '"/".join(allowed), allowed[0]))\n    return allowed[0]', '"/".join(allowed), allowed[0]))\n    return allowed[-1]'),
    ("_common: invalid mode is not logged", "hooks/_common.py",
     '    log(hook, "invalid %s=%r', '    0 and log(hook, "invalid %s=%r'),
]


# Mutants in the shared files (_common.py / phrases.py) whose code path only some hooks use.
# In a package without any of these hooks, the broken spot is never executed, so the mutant cannot be
# caught there (and cannot do harm there). It is skipped and reported. Mutants not listed here apply to every hook.
USED_BY = {
    "phrases: empty the other-language table": ["done_gate.py", "unknown_gate.py", "no_excuse_gate.py"],
    "_common: count Codex injected messages as user turns": ["done_gate.py", "unknown_gate.py"],
    "_common: ignore Codex tool results": ["done_gate.py"],
    "_common: drop the session from the stop-once memory": ["done_gate.py", "unknown_gate.py", "no_excuse_gate.py"],
    "_common: drop the stop-once memory": ["done_gate.py", "unknown_gate.py", "no_excuse_gate.py"],
    "phrases: drop the Chinese question exclusion (完成了吗)": ["done_gate.py"],
    "_common: warn goes to stderr only (no systemMessage)": ["done_gate.py"],
    "_common: invalid mode falls open (uses the non-blocking mode)": ["done_gate.py", "secret_guard.py"],
    "_common: invalid mode is not logged": ["done_gate.py", "secret_guard.py"],
}


def applies(name, rel):
    if not os.path.exists(os.path.join(ROOT, rel)):
        return False
    users = USED_BY.get(name)
    return users is None or any(os.path.exists(os.path.join(ROOT, "hooks", h)) for h in users)


def main():
    survived = ran = 0
    for name, rel, old, new in MUTANTS:
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
            r = subprocess.run([sys.executable, "tests/run_tests.py"], cwd=d,
                               capture_output=True, text=True, timeout=120)
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
