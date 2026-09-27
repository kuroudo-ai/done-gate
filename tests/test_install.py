#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Acceptance tests for install.py (never touches your real settings: GUARDRAILS_HOME points at a temporary folder)."""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = FAIL = 0


def run(home, *args, **env_extra):
    env = {k: v for k, v in os.environ.items() if k != "GUARDRAILS_LANG"}
    env.update(GUARDRAILS_HOME=home, **env_extra)
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


ALL_HOOKS = ["done_gate.py", "unknown_gate.py", "no_excuse_gate.py", "pipe_guard.py", "secret_guard.py"]
on_disk = [h for h in ALL_HOOKS if os.path.exists(os.path.join(ROOT, "hooks", h))]
MARK = on_disk[0] if on_disk else "done_gate.py"   # a hook this package ships (packages may hold just one)


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
check("Windows Store Python (WindowsApps) -> registered as `python`, not the versioned path",
      install.python_cmd(STORE, "win32", ALIAS) == ("python", False))
check("Windows Store Python but `python` not on PATH -> full path, with a warning",
      install.python_cmd(STORE, "win32", lambda name: None) == (STORE, True))
check("Windows python.org Python (no WindowsApps) -> full path as before",
      install.python_cmd(ORG, "win32", ALIAS) == (ORG, False))
check("macOS/Linux -> sys.executable as before (even if the path says WindowsApps)",
      install.python_cmd("/Users/me/WindowsApps/bin/python3", "darwin", ALIAS) == ("/Users/me/WindowsApps/bin/python3", False))
saved = (install.sys.executable, install.sys.platform, install.shutil.which)
try:
    install.sys.executable, install.sys.platform, install.shutil.which = STORE, "win32", ALIAS
    s_store, _ = install.add_ours({})
    install.sys.platform = "darwin"
    s_mac, _ = install.add_ours({})
finally:
    install.sys.executable, install.sys.platform, install.shutil.which = saved
cmds = [c["command"] for g in sum(s_store["hooks"].values(), []) for c in g["hooks"]]
check("Store Python -> every hook command starts with `python \"` and has no WindowsApps",
      cmds and all(c.startswith('python "') and "WindowsApps" not in c for c in cmds))
cmds = [c["command"] for g in sum(s_mac["hooks"].values(), []) for c in g["hooks"]]
check("non-Windows -> every hook command starts with the quoted sys.executable",
      cmds and all(c.startswith('"%s" "' % STORE) for c in cmds))

print("\n=== install: %d PASS / %d FAIL ===" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
