#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""done_gate.py — 「直しました」と言う前に、このターンで実際に測ったかを見る（Stop フック）

AI エージェントは、テストを走らせていなくても「修正しました」「動作確認済みです」と書く。
規則（「確かめてから報告する」）をプロンプトに書いても、読んだ上で破る。だから機械で見る。

見ているもの：
  ① 最後の返答に「完了の主張」があるか（仮定・予定・打ち消しは除く）
  ② このターン（最後の人の発言以降）のツール結果に「測った痕跡」があるか
     （PASS/FAIL・passed/failed・exit code・rc=・テスト件数など）
  ①あり・②なし のときだけ、1回止めて「何で確かめたかを書くか、確かめてから言い直す」よう返す。
"""
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

HOOK = "done_gate"

CLAIM = C.lang_re("claim", 
    r"(直しました|直りました|修正しました|修正済み|完了しました|解決しました|対応しました|"
    r"できました|動きました|通りました|動作確認(?:済み|しました)|確認済みです|"
    r"直した|修正した|完了した|解決した|動いた|通った|"
    r"\b(?:(?:I've|I have|I|is|are|has been|have been|was|were|now)\s+(?:fixed|resolved|implemented|completed|updated|corrected|patched)|"
    r"(?:it|this|that|everything|the (?:bug|issue|test|build|fix)s?) (?:now )?(?:works|passes|is working)|"
    r"works now|should (?:now )?work|all (?:tests )?pass(?:ed|ing)?|tests? (?:now )?pass(?:es|ed)?|"
    r"(?:is|are|all) done|successfully (?:fixed|implemented|updated|deployed|resolved)|"
    r"verified|confirmed (?:working|fixed)|the (?:bug|issue|error) is (?:gone|resolved))\b)", re.I)
NOT_CLAIM = C.lang_re("not_claim", 
    r"(直したら|修正したら|直したい|修正したい|直します|修正します|直すつもり|"
    r"できましたら|完了しましたら|"
    r"(?:直した|修正した|完了した)(?:もの|こと|わけ)(?:は|では)?\s*(?:ありません|ない)|"
    r"\b(?:I'll|I will|will|going to|plan to|need to|to be|once|if|until|after|not yet|haven't|have not|hasn't|"
    r"isn't|aren't|wasn't|not)\b[^.!?]{0,30}\b(?:fix|fixed|resolve|resolved|implement|implemented|work|pass|done|verified)\b)", re.I)
EVIDENCE = re.compile(
    r"(\bPASS(?:ED)?\b|exited with code \d+|\bFAIL(?:ED)?\b|\b\d+ passed\b|\b\d+ failed\b|exit code|rc=\d|"
    r"\bOK \(\d+|Ran \d+ tests?|✓|✔|✗|assert|Traceback|error:|HTTP/\d(?:\.\d)? \d{3}|"
    r"\bstatus[:= ]\s*\d{3}\b)", re.I)
QUOTED = re.compile(r"「[^「」]*」|『[^『』]*』|`[^`\n]*`|```.*?```|“[^”\n]*”|«[^»\n]*»|„[^“\n]*“|‘[^’\n]*’|\"[^\"\n]{1,200}\"", re.S)


def claims_done(text):
    body = QUOTED.sub(" ", text or "")
    for sent in re.split(r"(?<=[。！？!?\n])|(?<=\.)\s", body):
        if CLAIM.search(sent) and not NOT_CLAIM.search(sent):
            return sent.strip()
    return ""


def has_evidence(results):
    return any(EVIDENCE.search(r or "") for r in results)


def main(data):
    if data.get("stop_hook_active"):
        C.log(HOOK, "skip: 再入")
        return
    text = C.last_assistant_text(data)
    claim = claims_done(text)
    if not claim:
        return
    results = C.tool_results_since_last_user(data)
    if has_evidence(results):
        C.log(HOOK, "ok: 主張あり・痕跡あり（ツール結果 %d 件）" % len(results))
        return
    if C.already_blocked(HOOK, text, data):
        C.log(HOOK, "skip: 同じ文面で止め済み")
        return
    C.log(HOOK, "BLOCK: 痕跡なしの完了主張「%s」" % claim[:80])
    C.stop_block(C.msg("done_gate.block", claim=claim[:80]))


if __name__ == "__main__":
    C.run(HOOK, main)
