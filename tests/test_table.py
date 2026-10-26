"""表（仕様.md の5.3）。

表は Word に合わせ込まない（比べる正解がない）ので、決まりごと（読み取り、左端・右端、列の幅、
折り返し、改ページ、表の後の本文の位置）を確かめる。
"""
import fitz

from va_document.doctypes import DOC_TYPES
from va_document.document import BODY, parse, parse_table
from va_document.layout import CELL_PAD_X, Typesetter
from va_document.pdfwriter import write_pdf

SAIBAN = DOC_TYPES["Saiban"]


def test_parse_alignment_and_double_rule():
    t = parse_table(["| :-: 科目 | 摘要 | :-- 金額 |", "|===|:---:|---:|", "| 参加費 | 500円 | 48,000 |"])
    # 見出しの行：記号のあるセルは記号の配置、ないセルは列の配置
    assert t.header == [("center", "科目"), ("center", "摘要"), ("left", "金額")]
    # それ以外の行：列の配置（区切りの行の :）
    assert t.rows == [[("left", "参加費"), ("center", "500円"), ("right", "48,000")]]
    assert t.double_rule


def test_parse_single_rule_and_escaped_bar():
    t = parse_table(["| A | B |", "| --- | --- |", r"| a \| b | c |"])
    assert not t.double_rule
    assert t.rows == [[("left", "a | b"), ("left", "c")]]


def test_not_a_table_without_separator():
    ps = parse(["| これは表ではない |", "本文"], SAIBAN)
    assert [p.kind for p in ps] == [BODY, BODY]
    assert ps[0].text == "| これは表ではない |"


def layout(lines):
    ts = Typesetter(SAIBAN)
    out = ts.layout(parse(lines, SAIBAN))
    return ts, out


def test_left_edge_is_body_indent_and_right_edge_is_text_right():
    ts, _ = layout(["# 一", "## 二", "| A | B |", "|---|---|", "| a | b |"])
    piece = ts.tables[0]
    # ## の下の本文の左インデントは2字（本文の2行目以降の位置）
    assert abs(piece.col_x[0] - 2 * ts.pitch) < 0.01
    assert abs(piece.col_x[-1] - ts.text_w) < 0.01


def test_table_before_first_heading_starts_at_left_margin():
    ts, _ = layout(["| A | B |", "|---|---|", "| a | b |"])
    assert ts.tables[0].col_x[0] == 0


def test_short_columns_do_not_wrap():
    ts, _ = layout(["| 項目 | 内容 | 金額 |", "|---|---|---:|",
                    "| 休業損害 | " + "長い説明の文章。" * 10 + " | 1,080,000 |"])
    piece = ts.tables[0]
    widths = [b - a for a, b in zip(piece.col_x, piece.col_x[1:])]
    # 短い列は「折り返さずに収まる幅」がある（休業損害は4字、1,080,000 は半角9字＝4.5字）
    assert widths[0] >= 4 * ts.pitch + 2 * CELL_PAD_X - 0.01
    assert widths[2] >= 4.5 * ts.pitch + 2 * CELL_PAD_X - 0.01
    # 長い説明の列だけが折り返し、その行は高くなる
    assert piece.rows[1].bottom - piece.rows[1].top > piece.rows[0].bottom - piece.rows[0].top


def test_no_hanging_punctuation_in_cells():
    ts, _ = layout(["| A |", "|---|", "| " + "あ" * 40 + "、い |"])
    piece = ts.tables[0]
    right = piece.col_x[-1] - CELL_PAD_X
    assert all(g.x + ts.pitch <= right + 0.01 for g in piece.glyphs)


def test_body_after_table_starts_on_next_grid_row():
    ts, lines = layout(["前", "| A |", "|---|", "| a |", "後"])
    piece = ts.tables[0]
    after = [ln for ln in lines if ln.glyphs[0].ch == "後"][0]
    top_of_after = ts.margin_top + after.row * ts.line_pitch
    assert top_of_after >= piece.rows[-1].bottom - 0.01
    assert top_of_after - piece.rows[-1].bottom < ts.line_pitch


def test_long_table_breaks_between_rows():
    rows = ["| 日付 | 内容 |", "|---|---|"] + [f"| {k}日 | 経過 |" for k in range(1, 60)]
    ts, _ = layout(rows)
    pages = sorted({p.page for p in ts.tables})
    assert pages[0] == 1 and len(pages) >= 2
    bottom = ts.margin_top + ts.lines_page * ts.line_pitch
    assert all(r.bottom <= bottom + 0.01 for p in ts.tables for r in p.rows)
    # 見出しの行は繰り返さない（2ページ目以降の piece の最初の行は見出しではない）
    assert sum(len(p.rows) for p in ts.tables) == 60


def test_table_in_pdf(tmp_path):
    ts, lines = layout(["| 科目 | 金額 |", "|===|---:|", "| 参加費 | 48,000 |"])
    path = tmp_path / "表.pdf"
    write_pdf(ts, lines, str(path))
    with fitz.open(path) as doc:
        text = doc[0].get_text()
        drawings = doc[0].get_drawings()
    assert "参加費" in text and "48,000" in text
    # 罫線：横の線（見出しの行の上・2重線の2本・最後の行の下）と縦の線（列の境目3本）
    assert len(drawings) >= 1


def test_double_rule_if_any_column_has_equals():
    """2行目のどれか1列にでも = があれば2重線（|===|---| も |===|===| も同じ）。"""
    assert parse_table(["| A | B |", "|===|---|", "| a | b |"]).double_rule
    assert parse_table(["| A | B |", "|===|===|", "| a | b |"]).double_rule
    assert not parse_table(["| A | B |", "|---|---|", "| a | b |"]).double_rule
