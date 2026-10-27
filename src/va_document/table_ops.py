"""エディターの、表のセルの操作（セルの先頭の配置の記号、区切りの行の列の配置。2026-10-24 班長指示）。

メインの画面（app.MainWindow）の部品（mixin。editor_ops.EditorMixin が混ぜる）。self.text（tk.Text）は MainWindow が持つ。
"""
from .document import CELL_ALIGN_RE, CENTER_MARK, RIGHT_MARK, cell_separators, is_table_line, parse_separator


class TableCellMixin:
    """表のセルの操作（MainWindow に混ぜて使う）。"""

    def _table_cells(self, separator=False):
        """カーソルのあるセル（字を選んでいれば、選んだ範囲にかかるセル）[(行, 左の | の位置, 右の | の位置)]。
        表の区切りの行（2行目）は除く（separator が真なら、区切りの行のセルだけ）。"""
        a, b = self._sel_range(insert=True)
        (la, ca), (lb, cb) = [tuple(int(v) for v in x.split(".")) for x in (a, b)]
        out = []
        for n in range(la, lb + 1):
            line = self.text.get(f"{n}.0", f"{n}.end")
            if not is_table_line(line) or (parse_separator(line) is None) == separator:
                continue
            seps = cell_separators(line)
            bounds = list(zip(seps, seps[1:]))
            if a == b:
                # カーソルが表の外側（最初の | の前・最後の | の後）なら、いちばん近いセル
                hit = [(s, e) for s, e in bounds if s < ca <= e] or (bounds[-1:] if bounds and ca > bounds[-1][1] else bounds[:1])
            else:
                lo, hi = (ca if n == la else 0), (cb if n == lb else len(line))
                hit = [(s, e) for s, e in bounds if s + 1 < hi and e > lo]
            out += [(n, s, e) for s, e in hit]
        return out

    def _cell_content(self, n, s, e):
        """セルの中身の位置 (配置の記号を置く位置, 字の始め, 字の終わり, 配置の記号の一致)。前後の空白は除く。"""
        line = self.text.get(f"{n}.0", f"{n}.end")
        pos = s + 1
        while pos < e and line[pos] in " 　":
            pos += 1
        end = e
        while end > pos and line[end - 1] in " 　":
            end -= 1
        m = CELL_ALIGN_RE.match(line, pos, end)
        start = pos + len(m.group(0)) if m and not m.group(1) else pos
        while start < end and line[start] in " 　":
            start += 1
        return pos, start, end, m

    def _align_cells(self, cells, mark):
        """セルの先頭の配置の記号を付け替える。すべてのセルが既にその記号なら外す。"""
        if not cells:
            return
        found = [self._cell_content(n, s, e)[3] for n, s, e in cells]
        release = all(m and m.group(2).strip() == mark.strip() for m in found)
        for n, s, e in sorted(cells, reverse=True):          # 右・下のセルから（前の位置がずれないように）
            pos, _, _, m = self._cell_content(n, s, e)
            if m:
                self.text.delete(f"{n}.{m.start(2)}", f"{n}.{m.end(2)}")
            if not release:
                self.text.insert(f"{n}.{pos}", mark)

    def _align_columns(self, columns, mark):
        """区切りの行のセルの : を付け替える（中央は :---:、右は ---:）。すべての列が既にその配置なら、
        左（---）に戻す。- と = の種類と数は変えない（2重線の設定は変わらない）。"""
        if not columns:
            return
        want = {CENTER_MARK: (True, True), RIGHT_MARK: (False, True)}[mark]

        def parts(n, s, e):
            cell = self.text.get(f"{n}.{s + 1}", f"{n}.{e}")
            core = cell.strip(" 　")
            lead = len(cell) - len(cell.lstrip(" 　"))
            return s + 1 + lead, core
        release = all((parts(*c)[1].startswith(":"), parts(*c)[1].endswith(":")) == want for c in columns)
        for n, s, e in sorted(columns, reverse=True):
            start, core = parts(n, s, e)
            body = core.strip(":")
            left, right = (False, False) if release else want
            new = (":" if left else "") + body + (":" if right else "")
            if new != core:
                self.text.delete(f"{n}.{start}", f"{n}.{start + len(core)}")
                self.text.insert(f"{n}.{start}", new)
