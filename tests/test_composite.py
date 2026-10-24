"""複合見出し（字のない見出しの行のすぐ後の見出しを1行にまとめる。VA疑似アウトラインと同じ。2026-10-24 班長指示）。"""
from va_documake import config
from va_documake.doctypes import DOC_TYPES
from va_documake.document import HEADING, parse
from va_documake.layout import Typesetter
from va_documake.session import Session

DT = DOC_TYPES["Saiban"]
LONG = "当事者は、長い見出しを折り返すと、２行目はまとめた段の数だけ右から始まる。"
SRC = ["[TOC]", "#", "## " + LONG, "本文。", "## 請求の原因", "#", "##", "### 三段まとめ", "本文。"]


def lines_by_para(src, dt=DT):
    ts = Typesetter(dt)
    paras = parse(src, dt)
    out = {}
    for ln in ts.layout(paras):
        out.setdefault(ln.para_index, []).append(ln)
    return ts, paras, out


def test_composite_heading_is_one_line():
    ts, paras, by = lines_by_para(SRC)
    assert [p.composite for p in paras] == [False, True, False, False, False, True, True, False, False]
    assert 1 not in by and 5 not in by and 6 not in by                  # 字のない見出しは行にしない
    first, second = by[2]
    assert "".join(g.ch for g in first.glyphs).startswith("第１　１　当事者")
    assert first.glyphs[0].x == 0 and round(second.glyphs[0].x / ts.pitch, 3) == 2   # 第１の段の折り返し（1字）＋1字
    assert all(g.is_number for g in first.glyphs[:5]) and not first.glyphs[5].is_number     # 「第１　１　」が番号
    assert "".join(g.ch for g in by[7][0].glyphs).startswith("第２　１　(1) 三段まとめ")
    # 番号は、まとめた後も続く（「２　請求の原因」は第１の段の中の２番目）
    assert "".join(g.ch for g in by[4][0].glyphs) == "２　請求の原因"


def test_composite_heading_in_toc():
    """目次には、外側の段の1項目として載せる（字のない見出しは載せない）。"""
    ts, paras, by = lines_by_para(SRC)
    toc = ["".join(g.ch for g in ln.glyphs if not g.is_number) for ln in by[0]]
    assert toc[0].startswith("第１　１ 当事者")
    assert any(t.startswith("２ 請求の原因") for t in toc) and any(t.startswith("第２　１　(1) 三段まとめ") for t in toc)
    assert by[0][0].glyphs[0].x == 0                                    # 第１の段の位置
    _, paras1, by1 = lines_by_para(["[TOC:1]", "#", "## まとめた見出し", "## 載せない"])
    assert ["".join(g.ch for g in ln.glyphs if not g.is_number) for ln in by1[0]] == ["第１　１ まとめた見出し"]


def test_not_merged_when_left_add_is_not_one():
    """左インデントの増加量が1字でない文書の種類（契約書1・技術文書）では、まとめない（VA疑似アウトラインと同じ）。"""
    for key in ("Keiyaku1", "Technical"):
        paras = parse(["#", "## 見出し"], DOC_TYPES[key])
        assert not paras[0].composite and paras[0].kind == HEADING


def test_editor_position_round_trip():
    text = "#\n## 当事者\n本文。"
    s = Session(config.AppConfig(vadm_folder="未使用"))
    s.typeset(text)
    m = s.layout_map
    for ch in "当者":
        col = text.splitlines()[1].index(ch)
        page, x, top, h = m.locate(1, col)
        assert m.hit(page, x + 1, top + h / 2) == (1, col)
