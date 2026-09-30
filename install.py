#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""install.py — add or remove the checks in Claude Code / Codex (no need to edit settings.json by hand)

Usage:
    python3 install.py              install for Claude Code (backs up your current settings first)
    python3 install.py --codex      install for Codex (~/.codex/hooks.json)
    python3 install.py --uninstall  remove (only the lines this tool added; can be combined with --codex)
    python3 install.py --check      only show what is installed (changes nothing)
    --allow-duplicates  also register a check that is already registered from another folder (runs twice)
    --lang ja  (or GUARDRAILS_LANG=ja)  show the installer's messages in Japanese (default: English)

Safety promises:
  - Before changing anything, the current settings file is copied to <file>.bak-<date-time>
  - Only this tool's lines are added. Your other settings are left alone
  - "This tool's lines" means lines that run a file inside THIS folder's hooks/. A check with the
    same name installed from another folder (another package, or your own copy) is never removed
  - The check files were renamed on 2026-09-30 (done_gate.py -> ag_done_gate.py, and so on).
    Lines an older version wrote for THIS folder (the old names) are replaced with the new names.
    Old-name lines that point to another folder are left alone
  - Running it again never adds the same line twice
  - If the settings file is broken and cannot be read, nothing is written
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.join(HERE, "hooks")
STOP_HOOKS = ["ag_done_gate.py", "ag_unknown_gate.py", "ag_no_excuse_gate.py"]
PRE_HOOKS = [("ag_pipe_guard.py", "Bash"), ("ag_secret_guard.py", "Bash|WebFetch|WebSearch|mcp__.*")]
NAMES = STOP_HOOKS + [p for p, _ in PRE_HOOKS]
# 2026-09-30 までのファイル名（ag_ なし）。このフォルダの hooks/ を指す旧名の行は「この道具の行」として外す
LEGACY = [h[len("ag_"):] for h in NAMES]

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
        "check_elsewhere": "Registered from another folder (not this one): %(list)s",
        "dup_skip": "Skipped %(name)s: it is already registered from another folder, so it was not added twice. That line was left as is:\n    %(cmd)s\n  To use this folder's copy instead: run `install.py --uninstall` in that folder (or remove the line), then run install here again. To register both anyway: --allow-duplicates",
        "dup_added": "Note: %(name)s is also registered from another folder. That line was left as is (both will run):\n    %(cmd)s",
        "check_old": "Old file names from this folder (written by an older version): %(list)s -- run install again to switch to the new names",
        "dead_other": "Note: this line runs %(name)s from a file that does not exist any more. It was not written by this folder, so it was left as is. Remove it by hand if you no longer need it:\n    %(cmd)s",
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
        "check_elsewhere": "別のフォルダから入っている見張り（このフォルダのものではない）: %(list)s",
        "dup_skip": "%(name)s は入れませんでした: 別のフォルダから同じ見張りがすでに入っているので、二重にしませんでした。その行はそのまま残してあります:\n    %(cmd)s\n  このフォルダの方に切り替えるには: そのフォルダで `install.py --uninstall` を実行する（または行を消す）→ ここでもう一度入れる。両方とも入れるには: --allow-duplicates",
        "dup_added": "注意: %(name)s は別のフォルダからも入っています。その行はそのまま残してあります（両方が動きます）:\n    %(cmd)s",
        "check_old": "このフォルダの旧いファイル名の行（前の版が書いたもの）: %(list)s → もう一度 install すると新しい名前に置き換わります",
        "dead_other": "注意: この行は、もう存在しないファイルの %(name)s を動かそうとしています。このフォルダが書いた行ではないので、消さずに残しました。要らなければ手で消してください:\n    %(cmd)s",
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


def _runs_python3(cmd):
    """cmd が本当に Python 3 を起動するか（Windows の Microsoft Store の「スタブ」は Python を起動せず、ストアへの案内を出して失敗する）。"""
    if cmd in _RUNS:
        return _RUNS[cmd]
    try:
        r = subprocess.run([cmd, "-c", "import sys; print(sys.version_info[0])"],
                           capture_output=True, text=True, timeout=15)
        ok = r.returncode == 0 and r.stdout.strip() == "3"
    except (OSError, subprocess.SubprocessError):
        ok = False
    _RUNS[cmd] = ok
    return ok


_RUNS = {}


def python_cmd(executable=None, platform=None, which=None, works=None):
    """フックを起動する Python を返す（コマンド, PATH 上の python を使えず絶対パスにしたか）。
    Microsoft Store 版 Python の本体は WindowsApps\\<版番号入りフォルダ> にあり、更新でフォルダ名が変わる。
    そこを直接書くと更新後にフックが起動しなくなるので、PATH 上の `python` で書く。
    ★ただし PATH 上の `python` が Microsoft Store の「スタブ」（Python を起動しない）なら使わない。
      実際に1回起動して確かめ、ダメなら今動いている Python の絶対パスで書き、注意を出す。
    ★Windows で `python3` は書かない（Python を入れていても `python3` はスタブのことが多い）。"""
    win = (sys.platform if platform is None else platform) == "win32"
    py = (sys.executable if executable is None else executable) or ("python" if win else "python3")
    if win and "windowsapps" in py.lower():
        found = (which or shutil.which)("python")
        if found and (works or _runs_python3)(found):
            return "python", False
        return py, True
    return py, False


def command_for(hook):
    py = python_cmd()[0]
    cmd = py if py == "python" else '"%s"' % py
    return '%s "%s"' % (cmd, os.path.join(HOOKS_DIR, hook))


# コマンドの中の「.py で終わるパス」。引用符つき（空白を含んでよい）か、引用符なし（空白を含まない）
PY_PATH = re.compile(r'"([^"]+?\.py)"|\'([^\']+?\.py)\'|(\S+?\.py)(?=\s|$)')


def _expand(p):
    """~ / $HOME / ${HOME} / %USERPROFILE% を展開する（フックはシェル経由で動くので、書き手はこれらを使いうる）。"""
    home = os.path.expanduser("~").replace("\\", "/")
    p = re.sub(r"\$\{HOME\}|\$HOME(?![A-Za-z0-9_])|%USERPROFILE%", lambda m: home, p, flags=re.I)
    return os.path.expanduser(p)


def _same_file(a, b):
    """a と b が同じ場所を指すか。区切り（\\ と /）・大文字小文字（Windows）・.. ・シンボリックリンクを揃えて比べる。"""
    def forms(p):
        p = os.path.normcase(os.path.normpath(_expand(p.replace("\\", "/"))))
        return {p, os.path.normcase(os.path.realpath(p))}
    return bool(forms(a) & forms(b))


def hook_paths(entry):
    """行のコマンドに出てくる、見張りの名前（NAMES か旧名 LEGACY）で終わるパスを (名前, パス) で返す。"""
    cmd = str(entry.get("command", ""))
    out = []
    for m in PY_PATH.finditer(cmd):
        path = next(g for g in m.groups() if g)
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        if name in NAMES or name in LEGACY:
            out.append((name, path))
    return out


def ours(entry):
    """この道具（＝このフォルダ）が足した行か。
    ★このフォルダの hooks/ の中のファイルを動かす行だけ。同じ名前でも別の場所のファイルなら他人の行（消さない）。
    （2026-09-28: 名前だけで見分けていたため、単品版を入れると別の場所の同名の見張りまで消えた）"""
    return any(_same_file(path, os.path.join(HOOKS_DIR, name)) for name, path in hook_paths(entry))


def entries(settings):
    """settings の全イベント・全グループの行（{"type": "command", "command": ...}）を順に返す。"""
    for groups in (settings.get("hooks") or {}).values():
        for group in groups if isinstance(groups, list) else []:
            for h in group.get("hooks", []) if isinstance(group, dict) else []:
                if isinstance(h, dict):
                    yield h


def others(settings):
    """このフォルダ以外から入っている同名の見張り: [(名前, コマンド, ファイルが在るか)]。"""
    return [(name, str(h.get("command", "")), os.path.exists(_expand(path)))
            for h in entries(settings) if not ours(h) for name, path in hook_paths(h)]


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


def add_ours(settings, skip=()):
    installed = [h for h in NAMES if os.path.exists(os.path.join(HOOKS_DIR, h)) and h not in skip]
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
    if "--check" in argv:
        mine = [h for h in NAMES if any(ours(e) and h in [n for n, _ in hook_paths(e)] for e in entries(settings))]
        print(t["check"] % {"list": ", ".join(mine) if mine else t["none"]})
        old = sorted({n for e in entries(settings) if ours(e) for n, _ in hook_paths(e) if n in LEGACY})
        if old:
            print(t["check_old"] % {"list": ", ".join(old)})
        elsewhere = sorted({n for n, _, _ in others(settings)})
        if elsewhere:
            print(t["check_elsewhere"] % {"list": ", ".join(elsewhere)})
        return 0
    bak = backup(path)
    settings = strip_ours(settings)
    if "--uninstall" in argv:
        write(path, settings)
        print(t["removed"] % {"bak": bak or t["no_file"]})
        return 0
    # 別のフォルダから入っている同名の見張りは消さない。ファイルが在る（動いている）なら、二重にしないため足さない
    skip, notes = set(), []
    for name, cmd, alive in others(settings):
        if not os.path.exists(os.path.join(HOOKS_DIR, name)):
            continue
        if not alive:
            notes.append(t["dead_other"] % {"name": name, "cmd": cmd})
        elif "--allow-duplicates" in argv:
            notes.append(t["dup_added"] % {"name": name, "cmd": cmd})
        else:
            skip.add(name)
            notes.append(t["dup_skip"] % {"name": name, "cmd": cmd})
    settings, installed = add_ours(settings, skip)
    write(path, settings)
    print(t["installed"] % {"list": ", ".join(installed) if installed else t["none"]})
    for n in notes:
        print(n)
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
