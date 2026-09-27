# -*- coding: utf-8 -*-
"""全フック共通の部品。Python 3.8+ 標準ライブラリのみ・ネットワークは使わない。

設計の約束（どのフックも守る）:
  1. 壊れたら通す（fail open）。ただし黙らない＝ログに必ず1行書く。
  2. 同じ文面では2回止めない（止め続けてセッションが進まなくなるのを防ぐ）。
  3. stdin は締切つきで読む。呼び出し元が stdin を閉じ忘れても止まらない。
"""
import hashlib
import io
import json
import os
import sys
import threading
import time

for _name in ("stdin", "stdout", "stderr"):
    _f = getattr(sys, _name, None)
    if _f is not None and hasattr(_f, "reconfigure"):
        try:
            _f.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                   # noqa: BLE001
            pass

HOME = os.environ.get("GUARDRAILS_HOME") or os.path.expanduser("~")
BASE = os.path.join(HOME, ".claude", "guardrails")
CONFIG_PATH = os.environ.get("GUARDRAILS_CONFIG") or os.path.join(BASE, "config.json")
LOG_PATH = os.path.join(BASE, "guardrails.log")
STATE_DIR = os.path.join(BASE, "state")


def log(hook, msg):
    try:
        os.makedirs(BASE, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("%s %s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), hook, msg))
    except OSError:
        pass


def config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


# Text that the hooks send back to the agent. English by default; config.json "message_language": "ja" for Japanese.
# Each entry is a complete message with named placeholders (no sentence fragments glued together).
MESSAGES = {
    "en": {
        "done_gate.block":
            "done_gate: You wrote \"{claim}\", but no tool result in this turn shows that it was checked "
            "(a test result, an exit code, or command output).\n"
            "Please do one of these:\n"
            "  1. Check it now (run the tests, or try the actual operation once)\n"
            "  2. If you have not checked it, say that it is not verified\n"
            "(If you checked it some other way, add one line saying what you looked at, and it will go through.)",
        "no_excuse.why_promise": "a promise to do it later ({when} ... {act})",
        "no_excuse.why_refusal": "\"{ref}\" about unfinished work ({inc})",
        "no_excuse.block":
            "no_excuse_gate: You wrote {why} without any sign of having tried:\n  {excerpt}\n"
            "Rewrite it as \"I checked up to here, and this is where it stops\", with the evidence "
            "(the command you ran and its output, or the lines you read).\n"
            "If you can do it now, keep going instead of putting it off.",
        "unknown.hit": "  - {path} ({count} matching terms): {line}",
        "unknown.block":
            "unknown_gate: You are about to write \"{sentence}\", but the notes seem to cover this:\n{hits}\n"
            "Read them first, and answer from them if the answer is there. If it really is not there, "
            "add one line saying where you looked and write that you could not find it; that will go through.",
        "secret.deny":
            "secret_guard: The input to a tool that sends data outside ({tool}) contains a secret (matched: {names}).\n"
            "Change it so the value itself is not sent (refer to an environment variable, mask it, or leave that line out).",
        "secret.shape.anthropic": "Anthropic key format",
        "secret.shape.openai": "OpenAI key format",
        "secret.shape.google": "Google key format",
        "secret.shape.github": "GitHub token format",
        "secret.shape.aws": "AWS access key format",
        "secret.shape.slack": "Slack token format",
        "secret.shape.private_key": "private key",
        "pipe.deny":
            "pipe_guard: This cuts the output of a registered tool with head/tail/grep or similar.\n"
            "This tool prints its warnings only when something is wrong, and they fall outside the part you keep.\n"
            "If the output is long, write it to a file (`> /tmp/out.txt`), read all of it, then look at the part you need.",
    },
    "ja": {
        "done_gate.block":
            "done_gate: 「{claim}」と書いていますが、このターンのツール結果に確かめた痕跡"
            "（テスト結果・終了コード・実行出力）が見当たりません。\n"
            "次のどちらかにしてください：\n"
            "  1. いま実際に確かめる（テストを走らせる／当の操作を1回やってみる）\n"
            "  2. 確かめていないなら「未確認」と書き直す\n"
            "（別の手段で確かめたなら、何を見て言っているかを1行添えれば通ります）",
        "no_excuse.why_promise": "後でやる約束（{when}…{act}）",
        "no_excuse.why_refusal": "未完了（{inc}）への「{ref}」",
        "no_excuse.block":
            "no_excuse_gate: {why} を、確かめた跡なしで書いています：\n  {excerpt}\n"
            "「ここまで確かめて、ここで止まっている」＋確かめた現物（叩いたコマンドと出力／読んだ行）の形にしてください。\n"
            "いまできることなら、後回しにせずこのまま進めてください。",
        "unknown.hit": "  - {path}（語 {count} 個一致）: {line}",
        "unknown.block":
            "unknown_gate: 「{sentence}」と書こうとしていますが、手元のメモに関係しそうな記述があります：\n{hits}\n"
            "先に読んで、答えが書いてあればそれで答えてください。読んだうえで本当に無ければ、"
            "探した場所を1行添えて「見当たらない」と書けば通ります。",
        "secret.deny":
            "secret_guard: 外へ出るツール（{tool}）の入力に鍵が入っています：{names}\n"
            "値そのものを送らずに済む形に直してください（環境変数で参照する・伏せ字にする・該当行を除く）。",
        "secret.shape.anthropic": "Anthropic の鍵の形",
        "secret.shape.openai": "OpenAI の鍵の形",
        "secret.shape.google": "Google の鍵の形",
        "secret.shape.github": "GitHub トークンの形",
        "secret.shape.aws": "AWS アクセスキーの形",
        "secret.shape.slack": "Slack トークンの形",
        "secret.shape.private_key": "秘密鍵",
        "pipe.deny":
            "pipe_guard: 登録された道具の出力を head/tail/grep 等で切ろうとしています。\n"
            "この道具の警告は異常のときだけ出て、切った範囲の外に落ちます。\n"
            "出力が長いなら `> /tmp/out.txt` に落として、全部読んでから必要な所を見てください。",
    },
}


def message_language():
    lang = str(config().get("message_language") or "en").lower()
    return lang if lang in MESSAGES else "en"


def msg(key, **kw):
    """Look up a message in the configured language (falls back to English) and fill in the placeholders."""
    table = MESSAGES[message_language()]
    return (table.get(key) or MESSAGES["en"][key]).format(**kw)


def lang_re(key, base, flags=0):
    """base（日本語・英語）に、phrases.py の他言語の言い回しを足して compile する。

    config.json の "languages"（例 ["ko", "de"]）で絞れる。未指定なら phrases.py の全言語。
    """
    import re
    try:
        import phrases
        langs = config().get("languages") or list(phrases.LANGS)
        extra = [alt for lg in langs for alt in phrases.LANGS.get(lg, {}).get(key, [])]
    except Exception as e:                                  # noqa: BLE001
        log("lang_re", "phrases を読めなかった（日本語・英語だけで動く）: %r" % (e,))
        extra = []
    pat = "(?:%s)" % base + "".join("|(?:%s)" % a for a in extra)
    return re.compile(pat, flags)


def read_stdin_json(deadline=3.0):
    """stdin を別スレッドで読み、JSON として完成した瞬間に返す。

    素朴な「締切つき read()」は、本文を書いたのに閉じない呼び出し元で EOF を待って本文を捨てる。
    読めた分を毎回パースすれば、その場合でも本文を掴んで即座に抜けられる。
    """
    buf = io.BytesIO()
    done = threading.Event()
    result = {}

    def reader():
        try:
            fd = sys.stdin.fileno()
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                buf.write(chunk)
                try:
                    result["data"] = json.loads(buf.getvalue().decode("utf-8", "replace"))
                    break
                except ValueError:
                    continue
        except Exception as e:                              # noqa: BLE001
            result["error"] = repr(e)
        finally:
            done.set()

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    done.wait(deadline)
    if "data" in result:
        return result["data"]
    raw = buf.getvalue().decode("utf-8", "replace")
    try:
        return json.loads(raw) if raw.strip() else {}
    except ValueError:
        return {}


def last_assistant_text(data, n_chars=4000):
    """Stop フックの入力から、最後のアシスタント発言を取る（Claude Code・Codex とも last_assistant_message を渡す）。"""
    if isinstance(data.get("last_assistant_message"), str):
        return data["last_assistant_message"][-n_chars:]
    for kind, text in reversed(events(data)):
        if kind == "assistant" and text.strip():
            return text[-n_chars:]
    return ""


def transcript(data, max_lines=3000):
    path = data.get("transcript_path") or ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()[-max_lines:]
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def events(data):
    """会話記録を [(種類, 本文)] に揃えて返す。種類＝user / assistant / tool_result。

    Claude Code（type=user/assistant・content に tool_result）と
    Codex（type=response_item・payload が message / function_call_output）の両方を読む。
    Codex が自分で差し込む user メッセージ（<hook_prompt> など "<" で始まるもの）は人の発言に数えない。
    """
    out = []
    for o in transcript(data):
        p = o.get("payload")
        if o.get("type") == "response_item" and isinstance(p, dict):
            if p.get("type") == "function_call_output":
                body = p.get("output")
                out.append(("tool_result", body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)))
            elif p.get("type") == "message" and p.get("role") in ("user", "assistant"):
                text = "".join(x.get("text", "") for x in p.get("content") or [] if isinstance(x, dict))
                if p["role"] == "user" and text.lstrip().startswith("<"):
                    continue
                out.append((p["role"], text))
            continue
        c = (o.get("message") or {}).get("content")
        if o.get("type") == "user":
            if isinstance(c, str):
                out.append(("user", c))
            elif isinstance(c, list):
                results = [x for x in c if isinstance(x, dict) and x.get("type") == "tool_result"]
                for x in results:
                    body = x.get("content")
                    out.append(("tool_result", body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)))
                if not results:
                    out.append(("user", "".join(x.get("text", "") for x in c if isinstance(x, dict))))
        elif o.get("type") == "assistant":
            if isinstance(c, str):
                out.append(("assistant", c))
            elif isinstance(c, list):
                out.append(("assistant", "".join(x.get("text", "") for x in c
                                                 if isinstance(x, dict) and x.get("type") == "text")))
    return out


def tool_results_since_last_user(data):
    """最後の「人の発言」以降のツール結果の本文を返す（＝今回のターンで実際に測ったもの）。"""
    out = []
    for kind, text in reversed(events(data)):
        if kind == "user":
            break
        if kind == "tool_result":
            out.append(text)
    return list(reversed(out))


def last_user_text(data):
    for kind, text in reversed(events(data)):
        if kind == "user":
            return text
    return ""


def already_blocked(hook, text, data=None):
    """同じセッション・同じ文面で一度止めていれば True。止めていなければ記録して False。

    セッションを鍵に含める（含めないと、別の日の別のセッションで同じ文面が出ても二度と止めない）。
    """
    session = str((data or {}).get("session_id") or "")
    fp = hashlib.sha256((hook + "\0" + session + "\0" + (text or "")).encode("utf-8")).hexdigest()
    path = os.path.join(STATE_DIR, hook + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            seen = json.load(f)
    except (OSError, ValueError):
        seen = []
    if fp in seen:
        return True
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump((seen + [fp])[-200:], f)
    except OSError:
        pass
    return False


def stop_block(reason):
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    sys.stdout.flush()


def pretool_deny(reason):
    sys.stdout.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}, ensure_ascii=False))
    sys.stdout.flush()


def run(hook, main):
    """fail open で main(data) を回し、ブロックしているスレッドを道連れにせず終わる。"""
    try:
        main(read_stdin_json())
    except Exception as e:                                  # noqa: BLE001
        log(hook, "ERROR（通した）: %r" % (e,))
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        os._exit(0)
