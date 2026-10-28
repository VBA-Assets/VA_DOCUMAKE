"""見出しと次の本文を分けない・表を途中で分けない・ページの先頭の見出しの前の空行を詰める（2026-10-28 班長決定）。"""
from va_document.doctypes import DOC_TYPES
from va_document.document import parse
from va_document.layout import Typesetter

DT = DOC_TYPES["Saiban"]
N = Typesetter(DT).lines_page       # 1ページの行数


def layout(src, keep=True):
    ts = Typesetter(DT, keep=keep)
    paras = parse(src, DT)
    lines = ts.layout(paras)
    return ts, lines


def where(lines, text):
    """その字で始まる行の (ページ, 行)。"""
    ln = next(ln for ln in lines if "".join(g.ch for g in ln.glyphs if not g.is_number).startswith(text))
    return ln.page, ln.row


def fill(n):
    return [f"本文{k}" for k in range(n)]


def test_heading_at_page_bottom_moves_with_body():
    """ページの最後の行に来た見出しは、次の本文と一緒に次のページへ送る。"""
    src = fill(N - 1) + ["# 見出し", "見出しの本文"]
    _, old = layout(src, keep=False)
    assert where(old, "見出し") == (1, N - 1)
    ts, lines = layout(src)
    assert where(lines, "見出し") == (2, 0) and where(lines, "見出しの本文") == (2, 1)
    assert ts.para_rows[N - 1] == N         # 確認表示との連動も、送った行を指す


def test_heading_followed_by_subheadings_moves_together():
    """見出しの直後が下位の見出しなら、続く見出しすべてと本文の1行目を同じページに置く。"""
    src = fill(N - 2) + ["# 上", "## 下", "下の本文"]
    _, lines = layout(src)
    assert where(lines, "上") == (2, 0) and where(lines, "下") == (2, 1) and where(lines, "下の本文") == (2, 2)


def test_blank_between_heading_and_body_is_counted():
    src = fill(N - 2) + ["# 見出し", "", "見出しの本文"]
    _, lines = layout(src)
    assert where(lines, "見出し") == (2, 0) and where(lines, "見出しの本文") == (2, 2)


def test_heading_that_fits_is_not_moved():
    src = fill(N - 2) + ["# 見出し", "見出しの本文"]
    _, lines = layout(src)
    assert where(lines, "見出し") == (1, N - 2) and where(lines, "見出しの本文") == (1, N - 1)


def test_heading_before_page_break_is_not_moved():
    """見出しの後が改ページなら、分けない相手の本文がないので送らない。"""
    src = fill(N - 1) + ["# 見出し", "<<<", "次のページ"]
    _, lines = layout(src)
    assert where(lines, "見出し") == (1, N - 1) and where(lines, "次のページ") == (2, 0)


def test_group_longer_than_a_page_is_not_moved():
    """見出しだけが続き、まとめると1ページを超えるときは、この見出しと次の見出しの1行目だけをまとめる。"""
    src = fill(N - 1) + [f"# 見出し{k}" for k in range(N + 5)] + ["本文"]
    _, lines = layout(src)
    assert where(lines, "見出し0") == (2, 0) and where(lines, "見出し1") == (2, 1)


def test_blank_before_heading_at_page_top_is_dropped():
    """ページの先頭に来た、見出しの直前の空行は詰める。改ページの直後・ほかの空行は詰めない。"""
    _, lines = layout(fill(N) + ["", "# 見出し", "本文"])
    assert where(lines, "見出し") == (2, 0)
    _, lines = layout(fill(N) + ["", "本文の前"])
    assert where(lines, "本文の前") == (2, 1)
    _, lines = layout(["本文", "<<<", "", "# 見出し", "本文"])
    assert where(lines, "見出し") == (2, 1)
    _, lines = layout(["", "# 見出し", "本文"])                # 文書の先頭
    assert where(lines, "見出し") == (1, 1)
    _, lines = layout(fill(N) + ["", "# 見出し", "本文"], keep=False)
    assert where(lines, "見出し") == (2, 1)


def table(n):
    return ["| 日付 | 内容 |", "|---|---|"] + [f"| {k}日 | 経過 |" for k in range(1, n + 1)]


def test_table_that_fits_a_page_is_moved_whole():
    """1ページに収まる表は、途中で分けずに次のページへ送る。"""
    src = fill(N - 3) + table(5)
    ts, _ = layout(src, keep=False)
    assert len(ts.tables) == 2
    ts, _ = layout(src)
    assert len(ts.tables) == 1 and ts.tables[0].page == 2 and len(ts.tables[0].rows) == 6
    assert ts.tables[0].rows[0].top == ts.margin_top


def test_heading_moves_with_table_that_fits():
    """見出しの次が表なら、1ページに収まる表は表全体と一緒に送る。"""
    src = fill(N - 4) + ["# 経過", ] + table(5)
    ts, lines = layout(src)
    assert where(lines, "経過") == (2, 0) and ts.tables[0].page == 2


def test_long_table_repeats_header_row():
    """1ページに収まらない表は行の境目で分け、次のページの先頭で見出しの行を繰り返す。"""
    ts, _ = layout(fill(3) + table(70))
    assert len(ts.tables) >= 2 and ts.tables[0].page == 1
    for piece in ts.tables:
        assert piece.rows[0].index == 0 and piece.rows[0].top in (ts.tables[0].rows[0].top, ts.margin_top)
        heads = [g.ch for g in piece.glyphs if g.row == 0]
        assert "".join(heads) == "日付内容"
    ts, _ = layout(fill(3) + table(70), keep=False)
    assert [p.rows[0].index for p in ts.tables][1:] != [0] * (len(ts.tables) - 1)
