#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""install.py — add or remove the checks in Claude Code / Codex (no need to edit settings.json by hand)

Usage:
    python3 install.py              install for Claude Code (backs up your current settings first)
    python3 install.py --codex      install for Codex (~/.codex/hooks.json)
    python3 install.py --uninstall  remove (only the lines this tool added; can be combined with --codex)
    python3 install.py --check      only show what is installed (changes nothing)
    --lang ja  (or GUARDRAILS_LANG=ja)  show the installer's messages in Japanese (default: English)

Safety promises:
  - Before changing anything, the current settings file is copied to <file>.bak-<date-time>
  - Only this tool's lines are added. Your other settings are left alone
  - Running it again never adds the same line twice
  - If the settings file is broken and cannot be read, nothing is written
"""
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.join(HERE, "hooks")
STOP_HOOKS = ["done_gate.py", "unknown_gate.py", "no_excuse_gate.py"]
PRE_HOOKS = [("pipe_guard.py", "Bash"), ("secret_guard.py", "Bash|WebFetch|WebSearch|mcp__.*")]

TEXT = {
    "en": {
        "bad_json": "Could not read %(name)s (the JSON is not valid). Stopping without changing anything.",
        "bad_json_detail": "  File: %(path)s\n  Error: %(err)s",
        "check": "Installed checks: %(list)s",
        "none": "none",
        "removed": "Removed. Backup: %(bak)s",
        "no_file": "(there was no settings file before)",
        "installed": "Installed: %(list)s",
        "backup": "Backup: %(bak)s",
        "codex_next": "Takes effect from the next Codex session. Codex asks you to trust new hooks the first time; say yes.",
        "codex_remove": "To remove: python3 install.py --codex --uninstall",
        "claude_next": "Takes effect from the next Claude Code session. To remove: python3 install.py --uninstall",
        "store_python": "Warning: `python` was not found on PATH, so the full path %(py)s was used. If a Microsoft Store update moves Python, run install again.",
    },
    "ja": {
        "bad_json": "%(name)s が読めませんでした（JSON の書き方に誤りがあります）。何も変えずに止めます。",
        "bad_json_detail": "  場所: %(path)s\n  内容: %(err)s",
        "check": "入っている見張り: %(list)s",
        "none": "なし",
        "removed": "外しました（控え: %(bak)s）",
        "no_file": "元の設定ファイルは無かった",
        "installed": "入れました: %(list)s",
        "backup": "控え: %(bak)s",
        "codex_next": "次に開く Codex のセッションから効きます。★Codex は新しいフックを初回に「確認して」と聞いてくるので、許可してください。",
        "codex_remove": "外すときは: python3 install.py --codex --uninstall",
        "claude_next": "次に開く Claude Code のセッションから効きます。外すときは: python3 install.py --uninstall",
        "store_python": "注意: PATH に `python` が見つからなかったので、絶対パス %(py)s で登録しました。Microsoft Store の更新で Python の場所が変わったら、もう一度入れ直してください。",
    },
}


def pick_lang(argv):
    lang = os.environ.get("GUARDRAILS_LANG") or "en"
    for i, a in enumerate(argv):
        if a == "--lang" and i + 1 < len(argv):
            lang = argv[i + 1]
        elif a.startswith("--lang="):
            lang = a.split("=", 1)[1]
    lang = lang.lower()
    return lang if lang in TEXT else "en"


def settings_path(codex=False):
    home = os.environ.get("GUARDRAILS_HOME") or os.path.expanduser("~")
    if codex:
        base = os.environ.get("CODEX_HOME") if not os.environ.get("GUARDRAILS_HOME") else None
        return os.path.join(base or os.path.join(home, ".codex"), "hooks.json")
    return os.path.join(home, ".claude", "settings.json")


def python_cmd(executable=None, platform=None, which=None):
    """フックを起動する Python を返す（コマンド, PATH に無くて絶対パスにしたか）。
    Microsoft Store 版 Python の本体は WindowsApps\\<版番号入りフォルダ> にあり、更新でフォルダ名が変わる。
    そこを直接書くと更新後にフックが起動しなくなるので、PATH 上の `python` で書く。"""
    py = (sys.executable if executable is None else executable) or "python3"
    if (sys.platform if platform is None else platform) == "win32" and "windowsapps" in py.lower():
        if (which or shutil.which)("python"):
            return "python", False
        return py, True
    return py, False


def command_for(hook):
    py = python_cmd()[0]
    cmd = py if py == "python" else '"%s"' % py
    return '%s "%s"' % (cmd, os.path.join(HOOKS_DIR, hook))


def ours(entry):
    """この道具が足した行か（フォルダ名を変えても見分けられるよう、hooks/<名前>.py で見る）。"""
    cmd = str(entry.get("command", "")).replace("\\", "/")
    return any(("hooks/" + h) in cmd for h in STOP_HOOKS + [p for p, _ in PRE_HOOKS])


def load(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if not text.strip():
        return {}
    return json.loads(text)


def strip_ours(settings):
    hooks = settings.get("hooks") or {}
    for event in list(hooks):
        kept = []
        for group in hooks[event]:
            inner = [h for h in group.get("hooks", []) if not ours(h)]
            if inner:
                g = dict(group)
                g["hooks"] = inner
                kept.append(g)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if hooks:
        settings["hooks"] = hooks
    else:
        settings.pop("hooks", None)
    return settings


def add_ours(settings):
    installed = [h for h in STOP_HOOKS + [p for p, _ in PRE_HOOKS] if os.path.exists(os.path.join(HOOKS_DIR, h))]
    hooks = settings.setdefault("hooks", {})
    stop = [{"type": "command", "command": command_for(h)} for h in STOP_HOOKS if h in installed]
    if stop:
        hooks.setdefault("Stop", []).append({"hooks": stop})
    for h, matcher in PRE_HOOKS:
        if h in installed:
            hooks.setdefault("PreToolUse", []).append(
                {"matcher": matcher, "hooks": [{"type": "command", "command": command_for(h)}]})
    return settings, installed


def backup(path):
    if not os.path.exists(path):
        return None
    dst = "%s.bak-%s" % (path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(path, dst)
    return dst


def write(path, settings):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def main(argv):
    t = TEXT[pick_lang(argv)]
    codex = "--codex" in argv
    path = settings_path(codex)
    try:
        settings = load(path)
    except ValueError as e:
        print(t["bad_json"] % {"name": os.path.basename(path)})
        print(t["bad_json_detail"] % {"path": path, "err": e})
        return 2
    present = [h for h in STOP_HOOKS + [p for p, _ in PRE_HOOKS]
               if h in json.dumps(settings.get("hooks") or {}, ensure_ascii=False)]
    if "--check" in argv:
        print(t["check"] % {"list": ", ".join(present) if present else t["none"]})
        return 0
    bak = backup(path)
    settings = strip_ours(settings)
    if "--uninstall" in argv:
        write(path, settings)
        print(t["removed"] % {"bak": bak or t["no_file"]})
        return 0
    settings, installed = add_ours(settings)
    write(path, settings)
    print(t["installed"] % {"list": ", ".join(installed)})
    print(t["backup"] % {"bak": bak or t["no_file"]})
    if python_cmd()[1]:
        print(t["store_python"] % {"py": python_cmd()[0]})
    if codex:
        print(t["codex_next"])
        print(t["codex_remove"])
    else:
        print(t["claude_next"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
