# -*- coding: utf-8 -*-
"""言語ごとの言い回しの表（日本語・英語は各フックに直接書いてある。ここはそれ以外の言語）。

エージェントは、使う人の言語で返事をする。英語の言い回しだけを見る見張りは、
韓国語の「수정했습니다」やドイツ語の「Ich habe es behoben」を1つも拾えない。

言語を足すときは、下の LANGS に1言語分の辞書を書き、tests/run_tests.py に
「鳴るべき例」と「鳴ってはいけない例」を1つずつ足す。
config.json の "languages" で使う言語を絞れる（未指定なら全部）。

キー：
  claim             完了の主張（done_gate）
  not_claim         予定・仮定・打ち消し（done_gate が主張から外す）
  unknown           「分からない／見当たらない／どこですか」（unknown_gate）
  retract           訂正・引用（unknown_gate が外す）
  promise_when      「後で／次回」（no_excuse_gate）
  promise_act       「やります／対応します」（no_excuse_gate）
  incomplete        未完了の印（no_excuse_gate）
  refusal           「できません／対象外」（no_excuse_gate）
  closing           いま片付けた（no_excuse_gate が外す）
  evidence          行って確かめた跡（no_excuse_gate）
  evidence_neg_pre  証拠語の直前の打ち消し（英語の "haven't tried" 型。no_excuse_gate）
  evidence_neg_post 証拠語の直後の打ち消し（日本語「試していない」・韓国語「해 보지 않았」型）
"""

LANGS = {
    "ko": {
        "claim": [r"(?:수정|해결|완료|구현|처리)(?:했습니다|했어요|했다|됐습니다|되었습니다|됐어요|완료)",
                  r"고쳤(?:습니다|어요|다)", r"(?:이제|잘) 작동합니다", r"테스트(?:가|를)? 통과(?:했습니다|했어요|합니다)"],
        "not_claim": [r"(?:수정|해결|구현|처리)(?:하겠습니다|할게요|할 예정|하면|하려고|하지 않았|못했)",
                      r"고치(?:겠습니다|면|려고)", r"고치지 (?:않았|못했)"],
        "unknown": [r"모르겠습니다|모릅니다|잘 모르겠어요", r"찾을 수 없(?:습니다|어요)|찾지 못했(?:습니다|어요)",
                    r"어디에 있(?:나요|습니까|어요)\?*", r"알려 ?주(?:세요|시겠어요)"],
        "retract": [r"정정|잘못|라고 (?:답했|말했)"],
        "promise_when": [r"나중에|다음에|추후|이후에|별도로|시간이 (?:나면|되면)"],
        "promise_act": [r"하겠습니다|할게요|처리하겠습니다|진행하겠습니다|확인하겠습니다|검토하겠습니다"],
        "incomplete": [r"미구현|구현되지 않|아직 (?:안|못)|남아 있|TODO"],
        "refusal": [r"할 수 없습니다|불가능합니다|지원하지 않습니다|범위 밖|제외하겠습니다|보류"],
        "closing": [r"(?:구현|수정|처리|완료)했습니다"],
        "evidence": [r"실행(?:했|해 ?봤)|시도(?:했|해 ?봤)|테스트(?:했|해 ?봤)|재현(?:했|해 ?봤)|출력(?:은|이|:)|에러(?:가|:)|오류(?:가|:)"],
        "evidence_neg_pre": [r"(?:아직|안|못)\s*$"],
        "evidence_neg_post": [r"^.{0,8}?(?:않|못 ?했|안 ?했|본 적 없)"],
    },
    "zh": {
        "claim": [r"已(?:经)?(?:修复|修好|解决|完成|实现|修改|處理|修復|解決|完成|實現)", r"(?:修复|修好|解决|修復|解決)了",
                  r"(?:现在|現在)(?:可以)?(?:正常)?(?:运行|運行|工作)了", r"测试(?:全部)?通过|測試(?:全部)?通過",
                  r"(?:完成|搞定|弄好|做好)了"],
        "not_claim": [r"(?:会|將|将|會|准备|準備|计划|計劃|打算|稍后|稍後)(?:去)?(?:修复|修復|解决|解決|实现|實現|处理|處理)",
                      r"(?:如果|若|等|一旦)[^。！？]{0,20}(?:修复|修復|解决|解決|完成|搞定|修好)", r"(?:没有|沒有|未|还没|還沒)(?:修复|修復|解决|解決|完成)",
                      # questions, not claims: 完成了吗？ / 修好了没有 / 是否完成了 / 有没有修好
                      r"了(?:吗|嗎|么|麼)", r"了(?:没有|沒有|没|沒)(?:[？?。！!]|\s*$)", r"(?:是否|有没有|有沒有)[^。！？]{0,6}(?:完成|修复|修復|修好|解决|解決|搞定)",
                      # plans: 完成了之后我会… / 修好了再测试
                      r"(?:完成|修复|修復|修好|解决|解決|搞定)了?(?:之后|之後|以后|以後|再)"],
        "unknown": [r"我?不(?:知道|清楚|确定|確定)", r"(?:找不到|没有找到|沒有找到|未找到)", r"在哪(?:里|裡|儿|兒)?", r"请告诉我|請告訴我"],
        "retract": [r"更正|纠正|糾正|错误|錯誤"],
        "promise_when": [r"稍后|稍後|之后|之後|以后|以後|下次|后续|後續|另行|有空"],
        "promise_act": [r"(?:再|会|會|将|將)(?:处理|處理|修复|修復|实现|實現|跟进|跟進|确认|確認|看看)"],
        "incomplete": [r"未实现|未實現|尚未|还没|還沒|待办|待辦|TODO|剩下"],
        "refusal": [r"无法|無法|不能|做不到|不支持|不支援|超出范围|超出範圍|暂不|暫不"],
        "closing": [r"已(?:经)?(?:实现|實現|完成|修复|修復)"],
        "evidence": [r"(?:运行|運行|执行|執行|尝试|嘗試|测试|測試|复现|復現)(?:了|过|過)", r"输出[:：]|輸出[:：]|报错|報錯|错误[:：]|錯誤[:：]"],
        "evidence_neg_pre": [r"(?:没|沒|未|没有|沒有|还没|還沒)\s*$"],
    },
    "de": {
        "claim": [r"\b(?:ich habe|habe ich|wurde|ist|sind)\b[^.!?]{0,30}\b(?:behoben|gefixt|repariert|korrigiert|gelöst|implementiert|erledigt)\b",
                  r"\bfunktioniert (?:jetzt|wieder)\b", r"\b(?:alle )?Tests (?:sind )?(?:grün|bestanden|laufen durch)\b"],
        "not_claim": [r"\b(?:werde|wird|möchte|sollte|muss|noch nicht|nicht|wenn|sobald|falls)\b[^.!?]{0,30}\b(?:beheben|behoben|fixen|gefixt|lösen|gelöst|implementieren|implementiert)\b"],
        "unknown": [r"\bich weiß (?:es )?nicht\b", r"\b(?:kann|konnte) (?:ich )?(?:es |sie |ihn )?nicht finden\b|\bnicht gefunden\b",
                    r"\bwo (?:ist|sind|finde ich|liegt|liegen)\b", r"\bkönnen Sie mir sagen\b"],
        "retract": [r"\bKorrektur\b|\bfalsch\b|\bhabe ich geschrieben\b"],
        "promise_when": [r"\bspäter\b|\bnächstes Mal\b|\bin einem (?:separaten|späteren) (?:PR|Schritt)\b|\bgesondert\b|\bbei Gelegenheit\b|\bvorerst\b"],
        "promise_act": [r"\b(?:ich )?werde\b|\bkümmere mich\b|\bschaue (?:ich )?mir\b|\bnehme ich mir\b"],
        "incomplete": [r"\bnoch nicht implementiert\b|\bTODO\b|\bfehlt noch\b|\boffen\b|\bunvollständig\b"],
        "refusal": [r"\bnicht möglich\b|\bkann (?:ich )?nicht\b|\bnicht unterstützt\b|\baußerhalb des Umfangs\b|\büberspringe\b|\bzurückstellen\b"],
        "closing": [r"\bhabe (?:ich )?(?:jetzt )?(?:implementiert|behoben|erledigt|ergänzt)\b"],
        "evidence": [r"\b(?:ausgeführt|versucht|getestet|reproduziert)\b|\bFehlermeldung\b|\bAusgabe:"],
        "evidence_neg_pre": [r"\b(?:nicht|noch nicht|nie|ohne)\s+(?:\w+\s+)?$"],
    },
    "es": {
        "claim": [r"\b(?:he|ha|han|hemos) (?:corregido|arreglado|solucionado|resuelto|implementado|completado)\b",
                  r"\b(?:ya )?(?:está|quedó|queda) (?:corregido|arreglado|solucionado|resuelto|listo)\b",
                  r"\bahora funciona\b", r"\b(?:todas las )?pruebas pasan\b"],
        "not_claim": [r"\b(?:voy a|vamos a|lo|se|cuando|si|una vez|aún no|todavía no|no)\b[^.!?]{0,30}\b(?:corregir|arreglar|solucionar|resolver|implementar|corregido|arreglado|resuelto)\b"],
        "unknown": [r"\bno (?:lo )?sé\b", r"\bno (?:pude|puedo) encontrar\b|\bno encontré\b", r"\bdónde (?:está|están|se encuentra)\b", r"\bpodrías decirme\b"],
        "retract": [r"\bcorrección\b|\bme equivoqué\b|\berróneo\b"],
        "promise_when": [r"\bmás (?:tarde|adelante)\b|\bla próxima vez\b|\ben (?:otro|un futuro) (?:PR|paso)\b|\bpor separado\b|\bpor ahora\b"],
        "promise_act": [r"\b(?:lo )?(?:haré|revisaré|implementaré|corregiré|abordaré|me encargo)\b"],
        "incomplete": [r"\bno (?:está )?implementado\b|\bTODO\b|\bpendiente\b|\bfalta\b|\bincompleto\b"],
        "refusal": [r"\bno es posible\b|\bno (?:puedo|se puede)\b|\bno soportado\b|\bfuera del alcance\b|\bomitir\b"],
        "closing": [r"\bhe (?:ya )?(?:implementado|corregido|completado|añadido)\b"],
        "evidence": [r"\b(?:ejecuté|probé|intenté|reproduje)\b|\bsalida:|\berror:"],
        "evidence_neg_pre": [r"\b(?:no|aún no|todavía no|nunca|sin)\s+(?:\w+\s+)?$"],
    },
    "pt": {
        "claim": [r"\b(?:corrigi|consertei|resolvi|implementei|conclu[ií])\b", r"\b(?:foi|está|ficou) (?:corrigido|resolvido|consertado|pronto)\b",
                  r"\bagora funciona\b", r"\b(?:todos os )?testes passa(?:m|ram)\b"],
        "not_claim": [r"\b(?:vou|irei|quando|se|assim que|ainda não|não)\b[^.!?]{0,30}\b(?:corrigir|consertar|resolver|implementar|corrigido|resolvido)\b"],
        "unknown": [r"\bnão (?:sei|tenho certeza)\b", r"\bnão (?:consegui|consigo) encontrar\b|\bnão encontrei\b", r"\bonde (?:está|estão|fica)\b", r"\bpode me dizer\b"],
        "retract": [r"\bcorreção\b|\berrei\b|\bequivocado\b"],
        "promise_when": [r"\bmais tarde\b|\bdepois\b|\bna próxima\b|\bem (?:outro|um futuro) (?:PR|passo)\b|\bseparadamente\b|\bpor enquanto\b"],
        "promise_act": [r"\b(?:vou|irei) (?:fazer|verificar|implementar|corrigir|tratar)\b|\bfarei\b"],
        "incomplete": [r"\bnão implementado\b|\bTODO\b|\bpendente\b|\bfalta\b|\bincompleto\b"],
        "refusal": [r"\bnão é possível\b|\bnão (?:consigo|posso)\b|\bnão suportado\b|\bfora do escopo\b|\bpular\b"],
        "closing": [r"\b(?:já )?(?:implementei|corrigi|conclu[ií]|adicionei)\b"],
        "evidence": [r"\b(?:executei|testei|tentei|reproduzi|rodei)\b|\bsaída:|\berro:"],
        "evidence_neg_pre": [r"\b(?:não|ainda não|nunca|sem)\s+(?:\w+\s+)?$"],
    },
    "fr": {
        "claim": [r"\b(?:j'ai|nous avons|a été|est) (?:corrigé|résolu|réparé|implémenté|terminé)\b",
                  r"\bça (?:marche|fonctionne) (?:maintenant|désormais)\b", r"\b(?:tous les )?tests passent\b"],
        "not_claim": [r"\b(?:je vais|je vais le|on va|quand|si|une fois|pas encore|pas)\b[^.!?]{0,30}\b(?:corriger|résoudre|réparer|implémenter|corrigé|résolu)\b"],
        "unknown": [r"\bje ne sais pas\b", r"\bje n'ai pas (?:pu )?trouvé\b|\bintrouvable\b", r"\boù (?:est|sont|se trouve)\b", r"\bpourriez-vous me dire\b"],
        "retract": [r"\bcorrection\b|\bje me suis trompé\b|\berroné\b"],
        "promise_when": [r"\bplus tard\b|\bla prochaine fois\b|\bdans une (?:future|autre) (?:PR|étape)\b|\bséparément\b|\bpour l'instant\b"],
        "promise_act": [r"\bje (?:le )?(?:ferai|traiterai|vérifierai|corrigerai|m'en occuperai)\b"],
        "incomplete": [r"\bpas (?:encore )?implémenté\b|\bTODO\b|\ben attente\b|\bmanque\b|\bincomplet\b"],
        "refusal": [r"\bpas possible\b|\bje ne peux pas\b|\bnon pris en charge\b|\bhors (?:du )?périmètre\b|\bignorer\b"],
        "closing": [r"\bj'ai (?:maintenant )?(?:implémenté|corrigé|terminé|ajouté)\b"],
        "evidence": [r"\b(?:exécuté|testé|essayé|reproduit|lancé)\b|\bsortie\s?:|\berreur\s?:"],
        "evidence_neg_pre": [r"\b(?:pas|jamais|sans|n'ai pas)\s+(?:\w+\s+)?$"],
    },
}
