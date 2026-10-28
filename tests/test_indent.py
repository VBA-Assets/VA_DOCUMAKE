"""左インデント（->2 。VA公用文の「行間詰め」と同じく、インデントの自動調節の対象外。2026-10-24 班長指示。記号の形は
2026-10-28 班長決定）。"""
from va_document.doctypes import DOC_TYPES
from va_document.document import HEADING, parse
from va_document.layout import Typesetter

DT = DOC_TYPES["Saiban"]
LONG = "長い段落を折り返すと、２行目も同じ位置から始まる。" * 3


def lines_of(src):
    ts = Typesetter(DT)
    paras = parse(src, DT)
    out = {}
    for ln in ts.layout(paras):
        out.setdefault(ln.para_index, []).append(round(ln.glyphs[0].x / ts.pitch, 3))
    return paras, out


def test_left_indent_in_full_width_chars():
    paras, x = lines_of(["# 見出し", "本文。", "->3 " + LONG, "->2 　" + LONG, "　->0 " + LONG,
                         "->4 四字。", "->1 一字。", "次の本文。"])
    assert [p.left_indent for p in paras] == [None, None, 3, 2, 0, 4, 1, None]
    assert x[2][0] == 3 and all(v == 3 for v in x[2][1:])          # 2行目からも同じ位置
    assert x[3][0] == 3 and all(v == 2 for v in x[3][1:])          # 記号の後ろの全角空白：1行目だけ1字下げ
    assert x[4][0] == 1 and all(v == 0 for v in x[4][1:])          # 記号の前の全角空白も同じ・0 は左端
    assert x[5] == [4] and x[6] == [1]
    assert x[1] == x[7] == [2]                                     # 自動のインデント（第１の本文は2字）は変わらない


def test_left_indent_mark_is_half_width_only():
    """マークダウンの記号と同じく、半角の ->N だけを記号とする（全角の数字・矢印、前の形の +2 、空白のないものは字のまま。
    2026-10-28 班長決定）。"""
    src = ["# 見出し", "->２ 全角の数字", "－＞２ 全角の矢印", "+2 前の形", "->2字のまま", "-> 前の字下げの記号"]
    paras = parse(src, DT)
    assert [p.left_indent for p in paras[1:]] == [None] * 5
    assert [p.text for p in paras[1:]] == src[1:]


def test_indent_paragraph_is_not_converted():
    """->N の段落は見出し・箇条書き・段落番号にしない。字下げと一緒でも、後の段落の変換は止めない。"""
    paras = parse(["# 第一", "->1 　# 見出しにしない", "->1 - 箇条にしない", "**->2 1. 番号にしない**",
                   "# 第二"], DT)
    assert [p.kind for p in paras] == [HEADING, "body", "body", "body", HEADING]
    assert paras[1].text == "# 見出しにしない" and paras[3].text == "1. 番号にしない" and paras[3].left_indent == 2
    assert paras[4].number.startswith("第２")
