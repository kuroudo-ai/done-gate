#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Acceptance tests for install.py (never touches your real settings: GUARDRAILS_HOME points at a temporary folder)."""
import json
import os
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
PASS = FAIL = 0


def run(home, *args, **env_extra):
    env = {k: v for k, v in os.environ.items() if k != "GUARDRAILS_LANG"}
    env.update(GUARDRAILS_HOME=home, **env_extra)
    env["PYTHONIOENCODING"] = "utf-8"   # the child inherits the console encoding (cp932 on Japanese Windows)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "install.py")] + list(args),
                       env=env, capture_output=True, text=True, timeout=30, encoding="utf-8")
    return r.returncode, r.stdout


def settings(home):
    with open(os.path.join(home, ".claude", "settings.json"), encoding="utf-8") as f:
        return json.load(f)


def check(name, ok):
    global PASS, FAIL
    PASS += bool(ok)
    FAIL += (not ok)
    print("%s %s" % ("✅" if ok else "🔴", name))


ALL_HOOKS = ["ag_done_gate.py", "ag_unknown_gate.py", "ag_no_excuse_gate.py", "ag_pipe_guard.py", "ag_secret_guard.py"]
on_disk = [h for h in ALL_HOOKS if os.path.exists(os.path.join(ROOT, "hooks", h))]
MARK = on_disk[0] if on_disk else "ag_done_gate.py"   # a hook this package ships (packages may hold just one)


def count_ours(s):
    return json.dumps(s).replace("\\\\", "/").count("hooks/" + MARK)


home = tempfile.mkdtemp()
os.makedirs(os.path.join(home, ".claude"))
mine = {"model": "opus", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo my-own-hook"}]}]}}
with open(os.path.join(home, ".claude", "settings.json"), "w") as f:
    json.dump(mine, f)

rc, out = run(home)
s = settings(home)
check("install -> rc=0", rc == 0)
check("install -> %s added once" % MARK, count_ours(s) == 1)
check("install -> your own setting (model) is kept", s.get("model") == "opus")
check("install -> your own hook (echo my-own-hook) is kept", "my-own-hook" in json.dumps(s))
check("install -> a backup is made", any(n.startswith("settings.json.bak-") for n in os.listdir(os.path.join(home, ".claude"))))

registered = [h for h in ALL_HOOKS if ("hooks/" + h) in json.dumps(s).replace("\\\\", "/")]
check("install -> only hooks present in the folder are added (%d present)" % len(on_disk), sorted(registered) == sorted(on_disk))
check("install -> every registered hook file exists",
      all(os.path.exists(c["command"].split('"')[-2]) for g in sum(s["hooks"].values(), [])
          for c in g["hooks"] if "my-own-hook" not in c["command"]))

run(home)
check("installing twice does not add twice", count_ours(settings(home)) == 1)

rc, out = run(home, "--check")
check("--check -> reports it is installed", MARK in out)

rc, out = run(home, "--uninstall")
s = settings(home)
check("uninstall -> %s removed" % MARK, count_ours(s) == 0)
check("uninstall -> your own hook is kept", "my-own-hook" in json.dumps(s))
check("uninstall -> your own setting (model) is kept", s.get("model") == "opus")

home2 = tempfile.mkdtemp()
os.makedirs(os.path.join(home2, ".claude"))
with open(os.path.join(home2, ".claude", "settings.json"), "w") as f:
    f.write("{ this is not json")
rc, out = run(home2)
with open(os.path.join(home2, ".claude", "settings.json")) as f:
    body = f.read()
check("broken settings.json -> stops without writing (rc=2, content unchanged)", rc == 2 and body == "{ this is not json")

home3 = tempfile.mkdtemp()
rc, out = run(home3)
check("no settings.json -> creates it and installs", rc == 0 and count_ours(settings(home3)) == 1)

home4 = tempfile.mkdtemp()
os.makedirs(os.path.join(home4, ".codex"))
with open(os.path.join(home4, ".codex", "hooks.json"), "w") as f:
    json.dump({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo codex-own-hook"}]}]}}, f)
rc, out = run(home4, "--codex")
with open(os.path.join(home4, ".codex", "hooks.json")) as f:
    cx = json.load(f)
check("--codex -> installs into ~/.codex/hooks.json", rc == 0 and count_ours(cx) == 1)
check("--codex -> existing Codex hook is kept", "codex-own-hook" in json.dumps(cx))
check("--codex -> does not create Claude Code settings", not os.path.exists(os.path.join(home4, ".claude", "settings.json")))
rc, out = run(home4, "--codex", "--uninstall")
with open(os.path.join(home4, ".codex", "hooks.json")) as f:
    cx = json.load(f)
check("--codex --uninstall -> removed, existing hook kept", count_ours(cx) == 0 and "codex-own-hook" in json.dumps(cx))

home5 = tempfile.mkdtemp()
rc, out = run(home5)
check("output is English by default", rc == 0 and "Installed:" in out and "入れました" not in out)
rc, out = run(home5, "--check", "--lang", "ja")
check("--lang ja -> Japanese output", rc == 0 and "入っている見張り" in out)
rc, out = run(home5, "--check", GUARDRAILS_LANG="ja")
check("GUARDRAILS_LANG=ja -> Japanese output", rc == 0 and "入っている見張り" in out)
rc, out = run(home5, "--check", "--lang=fr")
check("unknown language -> falls back to English", rc == 0 and "Installed checks:" in out)

# Microsoft Store Python lives in WindowsApps\<versioned folder>, which changes on update -> register `python` from PATH.
sys.path.insert(0, ROOT)
import install  # noqa: E402

STORE = r"C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.11_3.11.2544.0_x64__qbz5n2kfra8p0\python3.11.exe"
ORG = r"C:\Users\me\AppData\Local\Programs\Python\Python311\python.exe"
ALIAS = lambda name: r"C:\Users\me\AppData\Local\Microsoft\WindowsApps\python.exe"
RUNS, STUB = (lambda cmd: True), (lambda cmd: False)
check("Windows Store Python (WindowsApps) -> registered as `python`, not the versioned path",
      install.python_cmd(STORE, "win32", ALIAS, RUNS) == ("python", False))
# The Microsoft Store "stub" (python.exe / python3.exe in WindowsApps when Python is not installed from the Store)
# does not start Python. Registering it means no check ever runs.
check("Windows: `python` on PATH is the Store stub -> full path of the running Python, with a warning",
      install.python_cmd(STORE, "win32", ALIAS, STUB) == (STORE, True))
check("Windows: sys.executable unknown -> `python`, never `python3` (often the Store stub)",
      install.python_cmd("", "win32", ALIAS, RUNS) == ("python", False))
stub_dir = tempfile.mkdtemp(prefix="guardrails_stub_")
if os.name == "nt":
    stub = os.path.join(stub_dir, "python.bat")
    body = "@echo Python was not found; run without arguments to install from the Microsoft Store\r\n@exit /b 9009\r\n"
else:
    stub = os.path.join(stub_dir, "python")
    body = "#!/bin/sh\necho 'Python was not found; run without arguments to install from the Microsoft Store'\nexit 9009\n"
with open(stub, "w") as f:
    f.write(body)
os.chmod(stub, 0o755)
check("stub check: a program that only prints the Store message is not Python", install._runs_python3(stub) is False)
check("stub check: the Python running this test is Python", install._runs_python3(sys.executable) is True)
check("Windows Store Python but `python` not on PATH -> full path, with a warning",
      install.python_cmd(STORE, "win32", lambda name: None) == (STORE, True))
check("Windows python.org Python (no WindowsApps) -> full path as before",
      install.python_cmd(ORG, "win32", ALIAS) == (ORG, False))
check("macOS/Linux -> sys.executable as before (even if the path says WindowsApps)",
      install.python_cmd("/Users/me/WindowsApps/bin/python3", "darwin", ALIAS) == ("/Users/me/WindowsApps/bin/python3", False))
saved = (install.sys.executable, install.sys.platform, install.shutil.which)
try:
    install.sys.executable, install.sys.platform, install.shutil.which = STORE, "win32", ALIAS
    install._RUNS[ALIAS("python")] = True   # the alias path only exists on Windows; treat it as a real Python here
    s_store, _ = install.add_ours({})
    install.sys.platform = "darwin"
    s_mac, _ = install.add_ours({})
finally:
    install.sys.executable, install.sys.platform, install.shutil.which = saved
    install._RUNS.pop(ALIAS("python"), None)
cmds = [c["command"] for g in sum(s_store["hooks"].values(), []) for c in g["hooks"]]
check("Store Python -> every hook command starts with `python \"` and has no WindowsApps",
      cmds and all(c.startswith('python "') and "WindowsApps" not in c for c in cmds))
cmds = [c["command"] for g in sum(s_mac["hooks"].values(), []) for c in g["hooks"]]
check("non-Windows -> every hook command starts with the quoted sys.executable",
      cmds and all(c.startswith('"%s" "' % STORE) for c in cmds))

# ---------------------------------------------------------------------------------------------
# Lines this package did NOT write must survive, even when they run a check with the same name.
# (2026-09-28: the single-check package removed same-name checks installed from another place,
#  because install.py recognised "its own" lines by the file name only.)
# Judged by comparing the whole set of (event, matcher, command) before and after.
import shutil  # noqa: E402


def triples(s):
    return {(ev, g.get("matcher", ""), h.get("command", ""))
            for ev, groups in (s.get("hooks") or {}).items() for g in groups for h in g.get("hooks", [])}


def package(hook_names):
    """A package folder holding this install.py and the given check files (install.py only looks at the names)."""
    d = tempfile.mkdtemp(prefix="guardrails_pkg_")
    os.makedirs(os.path.join(d, "hooks"))
    shutil.copy2(os.path.join(ROOT, "install.py"), d)
    for h in hook_names:
        with open(os.path.join(d, "hooks", h), "w") as f:
            f.write("# dummy\n")
    return d


def run_pkg(pkg, home, *args):
    env = {k: v for k, v in os.environ.items() if k != "GUARDRAILS_LANG"}
    env.update(GUARDRAILS_HOME=home, HOME=home, USERPROFILE=home, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, os.path.join(pkg, "install.py")] + list(args),
                       env=env, capture_output=True, text=True, timeout=30, encoding="utf-8")
    return r.returncode, r.stdout


def conf(home, codex):
    return os.path.join(home, ".codex", "hooks.json") if codex else os.path.join(home, ".claude", "settings.json")


def load_conf(home, codex):
    with open(conf(home, codex), encoding="utf-8") as f:
        return json.load(f)


def save_conf(home, codex, s):
    os.makedirs(os.path.dirname(conf(home, codex)), exist_ok=True)
    with open(conf(home, codex), "w", encoding="utf-8") as f:
        json.dump(s, f)


def cmds_of(pkg, s):
    return [c for _, _, c in triples(s) if os.path.join(pkg, "hooks").replace("\\", "/") in c.replace("\\", "/")]


for codex in (False, True):
    tag = "[codex] " if codex else ""
    flag = ["--codex"] if codex else []

    # 1. The incident: in-house checks at $HOME/.claude/hooks, then the secret_guard single package.
    home = tempfile.mkdtemp(prefix="guardrails_home_")
    inhouse = os.path.join(home, ".claude", "hooks")
    os.makedirs(inhouse)
    for h in ("ag_done_gate.py", "ag_no_excuse_gate.py", "ag_unknown_gate.py", "ag_secret_guard.py"):
        open(os.path.join(inhouse, h), "w").close()
    before = {"hooks": {
        "Stop": [{"hooks": [
            {"type": "command", "command": "python3 %s" % os.path.join(inhouse, "ag_done_gate.py")},
            {"type": "command", "command": "python3 $HOME/.claude/hooks/ag_no_excuse_gate.py"},
            {"type": "command", "command": 'python3 "%s"' % os.path.join(inhouse, "ag_unknown_gate.py")}]}],
        "PreToolUse": [
            {"matcher": "mcp__claude-peers__send_message",
             "hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/ag_unknown_gate.py"}]},
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 $HOME/.claude/hooks/ag_unknown_gate.py"}]}]}}
    save_conf(home, codex, before)
    pkg_secret = package(["ag_secret_guard.py"])
    rc, out = run_pkg(pkg_secret, home, *flag)
    after = load_conf(home, codex)
    check(tag + "incident: same-name checks from another place (Stop + PreToolUse, other matchers) all survive",
          rc == 0 and triples(before) <= triples(after))
    check(tag + "incident: the only added line is this package's secret_guard",
          [c for _, _, c in triples(after) - triples(before)] == cmds_of(pkg_secret, after)
          and len(cmds_of(pkg_secret, after)) == 1)

    # 1b. A package that ships a check already registered from another place: not added twice, not removed.
    save_conf(home, codex, before)
    pkg_dup = package(["ag_done_gate.py", "ag_pipe_guard.py"])
    rc, out = run_pkg(pkg_dup, home, *flag)
    after = load_conf(home, codex)
    added = [c for _, _, c in triples(after) - triples(before)]
    check(tag + "same check already from another folder -> kept, not added twice, told why",
          rc == 0 and triples(before) <= triples(after) and len(added) == 1 and "ag_pipe_guard.py" in added[0]
          and "ag_done_gate.py" in out and "--allow-duplicates" in out)
    rc, out = run_pkg(pkg_dup, home, "--allow-duplicates", *flag)
    after = load_conf(home, codex)
    check(tag + "--allow-duplicates -> both registered, the other one still kept",
          rc == 0 and triples(before) <= triples(after) and len(cmds_of(pkg_dup, after)) == 2)
    # a same-name line whose file is gone: not ours -> kept (with a note), and ours is added
    dead = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "python3 /nowhere/old/hooks/ag_done_gate.py"}]}]}}
    save_conf(home, codex, dead)
    rc, out = run_pkg(pkg_dup, home, *flag)
    after = load_conf(home, codex)
    check(tag + "same-name line pointing to a missing file -> kept (note shown), this package's added",
          rc == 0 and triples(dead) <= triples(after) and len(cmds_of(pkg_dup, after)) == 2 and "/nowhere/old" in out)

    # 2. Single A then single B from different folders: both stay. 3. Same folder twice: no doubles.
    home = tempfile.mkdtemp(prefix="guardrails_home_")
    pkg_a, pkg_b = package(["ag_pipe_guard.py"]), package(["ag_secret_guard.py"])
    run_pkg(pkg_a, home, *flag)
    rc, out = run_pkg(pkg_b, home, *flag)
    s = load_conf(home, codex)
    check(tag + "single A then single B (other folders) -> both registered",
          rc == 0 and len(cmds_of(pkg_a, s)) == 1 and len(cmds_of(pkg_b, s)) == 1)
    snap = triples(s)
    run_pkg(pkg_b, home, *flag)
    run_pkg(pkg_a, home, *flag)
    s = load_conf(home, codex)
    check(tag + "installing each folder again -> nothing doubled", triples(s) == snap and len(triples(s)) == 2)

    # 4. --uninstall removes only this folder's lines.
    rc, out = run_pkg(pkg_a, home, "--uninstall", *flag)
    s = load_conf(home, codex)
    check(tag + "--uninstall A -> only A's line removed, B's kept",
          rc == 0 and triples(s) == {t for t in snap if "pipe_guard" not in t[2]} and len(cmds_of(pkg_b, s)) == 1)
    save_conf(home, codex, before)
    run_pkg(pkg_secret, home, *flag)
    rc, out = run_pkg(pkg_secret, home, "--uninstall", *flag)
    check(tag + "install + --uninstall over the in-house checks -> exactly the settings you started with",
          rc == 0 and triples(load_conf(home, codex)) == triples(before))

    # Our own line written as ~/... or with \ separators is still recognised as ours.
    home = tempfile.mkdtemp(prefix="guardrails_home_")
    pkg = os.path.join(home, "tools", "ag")
    os.makedirs(os.path.dirname(pkg))
    shutil.copytree(package(["ag_pipe_guard.py"]), pkg)
    for form in ("python3 ~/tools/ag/hooks/ag_pipe_guard.py",
                 'python3 "%s"' % os.path.join(pkg, "hooks", "ag_pipe_guard.py").replace("/", "\\")):
        save_conf(home, codex, {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": form}]}]}})
        rc, out = run_pkg(pkg, home, *flag)
        s = load_conf(home, codex)
        check(tag + "own line written as %s -> replaced, not doubled" % ("~/..." if "~" in form else "backslashes"),
              rc == 0 and len(triples(s)) == 1 and form not in [c for _, _, c in triples(s)])

    # 5. Upgrading from the old file names (until 2026-09-30 the files had no ag_ prefix: hooks/done_gate.py).
    #    Old-name lines for THIS folder are replaced by the new names; old-name lines for another folder stay.
    home = tempfile.mkdtemp(prefix="guardrails_home_")
    pkg = package(["ag_done_gate.py", "ag_pipe_guard.py"])
    elsewhere = os.path.join(home, ".claude", "hooks")
    os.makedirs(elsewhere, exist_ok=True)
    open(os.path.join(elsewhere, "done_gate.py"), "w").close()
    other_line = "python3 $HOME/.claude/hooks/done_gate.py"
    old = {"hooks": {
        "Stop": [{"hooks": [
            {"type": "command", "command": 'python3 "%s"' % os.path.join(pkg, "hooks", "done_gate.py")},
            {"type": "command", "command": other_line}]}],
        "PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": 'python3 "%s"' % os.path.join(pkg, "hooks", "pipe_guard.py")}]}]}}
    save_conf(home, codex, old)
    rc, out = run_pkg(pkg, home, "--check", *flag)
    old_line = [ln for ln in out.splitlines() if ln.startswith("Old file names from this folder")]
    check(tag + "upgrade: --check names this folder's old-name lines",
          rc == 0 and len(old_line) == 1 and "done_gate.py" in old_line[0] and "pipe_guard.py" in old_line[0])
    rc, out = run_pkg(pkg, home, *flag)
    s = load_conf(home, codex)
    base = lambda c: c.replace('"', "").replace("\\", "/").rsplit("/", 1)[-1]
    check(tag + "upgrade: old-name lines of this folder removed, only the new names added",
          rc == 0 and sorted(base(c) for c in cmds_of(pkg, s)) == ["ag_done_gate.py", "ag_pipe_guard.py"])
    check(tag + "upgrade: the same old name from another folder is kept",
          other_line in [c for _, _, c in triples(s)] and len(triples(s)) == 3)
    rc, out = run_pkg(pkg, home, "--uninstall", *flag)
    check(tag + "upgrade: --uninstall -> only the other folder's line is left",
          rc == 0 and [c for _, _, c in triples(load_conf(home, codex))] == [other_line])

print("\n=== install: %d PASS / %d FAIL ===" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
