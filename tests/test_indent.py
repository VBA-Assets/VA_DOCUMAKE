"""左インデント（{イン:2}。VA公用文の「行間詰め」と同じく、インデントの自動調節の対象外。2026-10-24 班長指示）。"""
from va_documake.doctypes import DOC_TYPES
from va_documake.document import HEADING, parse
from va_documake.layout import Typesetter

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
    paras, x = lines_of(["# 見出し", "本文。", "{イン:3}" + LONG, "{イン:2}{字下}" + LONG, "{字下}{イン：０}" + LONG,
                         "{インデント:4}長い形も読む。", "{イン}数字を省くと1字。", "次の本文。"])
    assert [p.left_indent for p in paras] == [None, None, 3, 2, 0, 4, 1, None]
    assert x[2][0] == 3 and all(v == 3 for v in x[2][1:])          # 2行目からも同じ位置
    assert x[3][0] == 3 and all(v == 2 for v in x[3][1:])          # 字下げと一緒：1行目だけ1字下げ
    assert x[4][0] == 1 and all(v == 0 for v in x[4][1:])          # 順は逆でもよい・0 は左端
    assert x[5] == [4] and x[6] == [1]
    assert x[1] == x[7] == [2]                                     # 自動のインデント（第１の本文は2字）は変わらない


def test_indent_paragraph_is_not_converted():
    """{イン:N} の段落は見出し・箇条書き・段落番号にしない。{字下} と一緒でも、後の段落の変換は止めない。"""
    paras = parse(["# 第一", "{イン:1}{字下}# 見出しにしない", "{イン:1}- 箇条にしない", "**{イン:2}1. 番号にしない**",
                   "# 第二"], DT)
    assert [p.kind for p in paras] == [HEADING, "body", "body", "body", HEADING]
    assert paras[1].text == "# 見出しにしない" and paras[3].text == "1. 番号にしない" and paras[3].left_indent == 2
    assert paras[4].number.startswith("第２")
