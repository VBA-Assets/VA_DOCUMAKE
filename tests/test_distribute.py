"""均等割付（[原告]{5}。Word の均等割り付けと同じ。2026-10-24 班長指示）。"""
from va_documake.doctypes import DOC_TYPES
from va_documake.document import parse
from va_documake.layout import Typesetter

DT = DOC_TYPES["Saiban"]


def layout(src):
    ts = Typesetter(DT)
    paras = parse(src, DT)
    return ts, paras, ts.layout(paras)


def test_distribute_spreads_characters():
    ts, paras, lines = layout(["[原告]{5}甲野太郎", "[原告代理人]{5}弁護士", "[被告]{５}丙川",
                               "[長すぎる字]{2}はそのまま", "[A1]{5}半角", "[片方だけ{5}", "[]{5}空"])
    x = [[(g.ch, round(g.x / ts.pitch, 3), g.index) for g in ln.glyphs] for ln in lines]
    assert x[0][:3] == [("原", 0, 0), ("告", 4, 1), ("甲", 5, 2)]          # 「原　　　告」の幅。次の字は5字目から
    assert [c for c, _, _ in x[1][:6]] == list("原告代理人弁") and x[1][5][1] == 5   # 字数どおりなら字の幅のまま
    assert x[2][:3] == [("被", 0, 0), ("告", 4, 1), ("丙", 5, 2)]          # 全角の数字も読む
    assert [g for g in x[3][:6]] == [(c, k, k) for k, c in enumerate("長すぎる字は")]   # はみ出すときは割り付けない
    assert x[4][:3] == [("A", 0, 0), ("1", 4.5, 1), ("半", 5, 2)]          # 半角は半字。最後の字が5字目の右端に来る
    assert paras[5].text == "[片方だけ{5}" and paras[6].text == "[]{5}空"   # 記号とみなさない


def test_distributed_text_is_not_broken_or_stretched():
    """割り付けた字の途中では改行せず、両端揃えでも中の字間は変えない。表のセルでも使える。"""
    head = "あ" * (DT.chars_lines[0] - 2)                                 # 4字の幅は1行目に入りきらない
    ts, paras, lines = layout([head + "[原告]{4}本文", "| [原告]{6} | 金額 |", "|---|---|", "| 被告 | 1 |"])
    first, second = lines[0], lines[1]
    assert "原" not in [g.ch for g in first.glyphs] and [g.ch for g in second.glyphs][:2] == ["原", "告"]
    assert round((second.glyphs[1].x - second.glyphs[0].x) / ts.pitch, 3) == 3
    cell = [g for g in ts.tables[0].glyphs if g.row == 0 and g.col == 0]
    assert [g.ch for g in cell] == ["原", "告"] and round((cell[1].x - cell[0].x) / ts.pitch, 3) == 5
    piece = ts.tables[0]
    assert piece.col_x[1] - piece.col_x[0] >= 6 * ts.pitch                # 列の幅は割り付けた幅が入るように


def test_large_count_does_not_hang():
    """字数が1行（セル）の幅より大きくても止まらず、割り付ける幅は1行（セル）の幅までにする（2026-10-24、
    大きな字数を入れると画面が固まった）。"""
    ts, paras, lines = layout(["# 見出し", "[原告]{99}甲野太郎", "+30 [被告]{20}乙山", "| [代理人]{99} | 金額 |",
                               "|---|---|", "| 原告 | 1 |"])
    by = {}
    for ln in lines:
        by.setdefault(ln.para_index, []).append(ln)
    first = by[1][0].glyphs
    assert [g.ch for g in first][:2] == ["原", "告"]
    assert first[1].x + ts.advance("告") <= ts.text_w + 0.01               # 本文の右端を超えない
    assert [g.ch for g in by[1][1].glyphs][:2] == ["甲", "野"]              # 次の字は次の行
    g = by[2][0].glyphs
    assert g[1].x + ts.advance(g[1].ch) <= ts.text_w + 0.01
    piece = ts.tables[0]
    cell = [c for c in piece.glyphs if c.row == 0 and c.col == 0]
    assert cell[-1].x + ts.advance("人") <= piece.col_x[1] + 0.01           # セルの右の罫線を超えない
