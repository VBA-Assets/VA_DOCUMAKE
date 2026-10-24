"""確認表示とエディターの連動（2026-10-23 班長指示）。

組んだ結果（どの字がどのページのどこにあるか）と、エディターの位置（何行目の何字目）を対応づける。
・エディターでカーソルを動かすと、その字のあるページを確認表示に出し、字の位置に印を付ける（locate）。
・確認表示をクリックすると、その字の位置にエディターのカーソルを動かす（hit）。
位置はどちらも、確認表示を最後に組んだときのもの（入力の途中では、少しずれることがある）。
"""
import bisect
from collections import defaultdict

from .document import CELL_ALIGNS, TABLE, TOC, cell_separators, leading_wrap, split_inline
from .layout import CELL_PAD_X


class LayoutMap:
    def __init__(self, ts, lines, paras, cleaned_lines, origins):
        """ts・lines は組んだ結果、paras は段落、cleaned_lines・origins は整形した行と元の位置（cleanup.clean_lines）。"""
        self.ts, self.lines, self.paras, self.origins = ts, lines, paras, origins
        self.cleaned_lines = cleaned_lines
        self.kept = [orig for orig, _ in origins]          # 整形した行 → 元の行（昇順）
        self.para_of_line = {}
        for pi, p in enumerate(paras):
            if p.src_line < 0:
                continue
            last = p.src_end if p.kind == TABLE else p.src_line
            for n in range(p.src_line, last + 1):
                self.para_of_line[n] = pi
        self.lines_of_para = defaultdict(list)
        for ln in lines:
            self.lines_of_para[ln.para_index].append(ln)
        self.pieces_of_para = defaultdict(list)
        for piece in getattr(ts, "tables", []):
            self.pieces_of_para[piece.para_index].append(piece)

    # ---------- 共通 ----------

    def _row_top(self, row):
        """通しの行の番号 → (ページ 0 から, 行の上端の y)。"""
        ts = self.ts
        return row // ts.lines_page, ts.margin_top + (row % ts.lines_page) * ts.line_pitch

    def _cleaned_line(self, orig_line):
        """元の行 → 整形した行（整形で除いた行なら、次に残った行。なければ最後の行）。"""
        k = bisect.bisect_left(self.kept, orig_line)
        return min(k, len(self.kept) - 1) if self.kept else None

    def _cleaned_col(self, line, orig_col):
        cols = self.origins[line][1]
        return min(bisect.bisect_left(cols, orig_col), len(cols) - 1)

    def _orig(self, line, col):
        orig_line, cols = self.origins[line]
        return orig_line, cols[max(0, min(col, len(cols) - 1))]

    # ---------- エディター → 確認表示 ----------

    def locate(self, orig_line, orig_col):
        """エディターの位置 → (ページ 0 から, x, 行の上端の y, 行の高さ)。ポイント、用紙の左上から。"""
        line = self._cleaned_line(orig_line)
        if line is None:
            return None
        col = self._cleaned_col(line, orig_col) if self.kept[line] == orig_line else 0
        pi = self.para_of_line.get(line)
        if pi is None:
            return None
        p, ts = self.paras[pi], self.ts
        if p.kind == TABLE:
            return self._locate_table(p, pi, line, col)
        lines = self.lines_of_para.get(pi)
        if not lines:
            # 空の行・改ページなど、字のない段落は、その行の左端
            row = ts.para_rows.get(pi)
            if row is None:
                return None
            page, top = self._row_top(row)
            return page, ts.margin_left, top, ts.line_pitch
        idx = len(p.number) + p.text_index(col)
        target = lines[0]
        for ln in lines:
            if ln.glyphs and ln.glyphs[0].index <= idx:
                target = ln
        g = min(target.glyphs, key=lambda g: abs(g.index - idx))
        x = g.x + (ts.advance(g.ch) if idx > g.index else 0)
        page, top = self._row_top((target.page - 1) * ts.lines_page + target.row)
        return page, ts.margin_left + x, top, ts.line_pitch

    def _locate_table(self, p, pi, line, col):
        r = line - p.src_line
        table_row = 0 if r <= 1 else r - 1          # 2行目は区切りの行
        for piece in self.pieces_of_para.get(pi, []):
            for row in piece.rows:
                if row.index == table_row:
                    cell = _cell_at(self.cleaned_text(line), col)
                    k = max(0, min(cell, len(piece.col_x) - 2))
                    return piece.page - 1, self.ts.margin_left + piece.col_x[k] + CELL_PAD_X, row.top, row.bottom - row.top
        return None

    def cleaned_text(self, line):
        return self.cleaned_lines[line]

    # ---------- 確認表示 → エディター ----------

    def hit(self, page, x, y):
        """確認表示の位置（ページ 0 から、用紙の左上からのポイント）→ エディターの位置 (元の行, 元の字)。"""
        ts = self.ts
        for piece in getattr(ts, "tables", []):
            if piece.page - 1 != page:
                continue
            for row in piece.rows:
                if row.top <= y < row.bottom and ts.margin_left + piece.col_x[0] <= x <= ts.margin_left + piece.col_x[-1]:
                    return self._hit_table(piece, row, x - ts.margin_left)
        on_page = [ln for ln in self.lines if ln.page - 1 == page and ln.glyphs]
        if not on_page:
            return None

        def dist(ln):
            top = ts.margin_top + ln.row * ts.line_pitch
            return 0 if top <= y < top + ts.line_pitch else min(abs(y - top), abs(y - top - ts.line_pitch))
        ln = min(on_page, key=dist)
        rel = x - ts.margin_left
        g = min(ln.glyphs, key=lambda g: abs(g.x + ts.advance(g.ch) / 2 - rel))
        idx = g.index + (1 if rel > g.x + ts.advance(g.ch) / 2 else 0)
        p = self.paras[ln.para_index]
        col = p.source_col(idx - len(p.number))
        return self._orig(p.src_line, col)

    def _hit_table(self, piece, row, rel_x):
        k = max(0, min(bisect.bisect_right(piece.col_x, rel_x) - 1, len(piece.col_x) - 2))
        p = self.paras[piece.para_index]
        line = p.src_line + (0 if row.index == 0 else row.index + 1)
        glyphs = [g for g in piece.glyphs if g.row == row.index and g.col == k]
        if glyphs:
            return self.cell_glyph_source(piece, min(glyphs, key=lambda g: abs(g.x - rel_x)))
        return self._orig(line, _cell_start(self.cleaned_text(line), k))

    # ---------- 字の元の位置 ----------

    def glyph_source(self, ln, g):
        """本文の字の元の位置 (元の行, 元の字)。番号の字・目次の字は None。"""
        p = self.paras[ln.para_index]
        if g.is_number or p.kind == TOC or g.index < len(p.number):
            return None
        return self._orig(p.src_line, p.source_col(g.index - len(p.number)))

    def cell_glyph_source(self, piece, g):
        """表のセルの字の元の位置 (元の行, 元の字)。"""
        p = self.paras[piece.para_index]
        line = p.src_line + (0 if g.row == 0 else g.row + 1)
        text = self.cleaned_text(line)
        start = _cell_start(text, g.col)
        # セルの字の番号は、太字の記号（**）を除いた字の番号
        seps = [s for s in cell_separators(text) if s >= start]
        seg = text[start:seps[0] if seps else len(text)].rstrip(" 　")
        plain, _, _, cols = split_inline(seg)
        # 「**{右}金額**」は、配置の記号が太字（蛍光ペン）の記号の内側にある（セルの字は記号の後から）
        skip = next((len(m) for m in CELL_ALIGNS if leading_wrap(seg) and plain.startswith(m)), 0)
        return self._orig(line, start + cols[min(g.index + skip, len(cols) - 1)])


def _cell_at(text, col):
    """表の行の col 字目が、何列目のセルか。"""
    seps = cell_separators(text)
    if seps and text[:seps[0]].strip() == "":
        return max(0, bisect.bisect_right(seps, col) - 1)
    return bisect.bisect_right(seps, col)


def _cell_start(text, k):
    """表の行の k 列目のセルの中身（前の空白・配置の記号を除く）が始まる位置。"""
    seps = cell_separators(text)
    if seps and text[:seps[0]].strip() == "":
        start = seps[0] + 1
        seps = seps[1:]
    else:
        start = 0
    bounds = [start] + [s + 1 for s in seps]
    pos = bounds[min(k, len(bounds) - 1)]
    while pos < len(text) and text[pos] in " 　":
        pos += 1
    for mark in CELL_ALIGNS:
        if text.startswith(mark, pos):
            pos += len(mark)
            while pos < len(text) and text[pos] in " 　":
                pos += 1
            break
    return pos
