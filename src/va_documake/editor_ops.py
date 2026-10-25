"""エディター（入力欄）の操作：配置・改ページなどの記号、見出しのレベル、標準、記号の色付け、貼り付け、検索。

メインの画面（app.MainWindow）の部品（mixin）。self.text（tk.Text）・self.session などは MainWindow が持つ。
"""
import math
import re
import tkinter as tk

from . import vadm
from .document import (BULLET, BULLET_MARK, CELL_ALIGN_RE, CENTER_MARK, DISTRIBUTE_CLOSE_RE, DISTRIBUTE_OPEN,
                       DISTRIBUTE_RE, HEADING, HEADING_BUTTON_MARK, HEADING_MARK_RE, INDENT_MARK, LEAD_ALIGN_MARKS,
                       LEFT_INDENT_MARK, LIST_MARK_RE, NUMBER, NUMBER_MARK, RIGHT_MARK, TABLE, area_of,
                       cell_separators, has_inline_marks, inline_mark_spans, is_line_mark, lead_mark_len, leading_wrap,
                       move_wraps_after_marks, parse, parse_separator, remove_bold, split_inline, split_lead_marks)
from .find_dialog import FindDialog
from .layout import is_half
from .pseudonym import TOKEN_RE, normalize_token
from .undo import undoable


class EditorMixin:
    """エディターの操作（MainWindow に混ぜて使う）。"""

    def _highlight(self):
        self.text.tag_remove("registered", "1.0", "end")
        self.text.tag_remove("mark", "1.0", "end")
        self.text.tag_remove("bold", "1.0", "end")
        self.text.tag_remove("highlight", "1.0", "end")
        self.text.tag_remove("dots", "1.0", "end")
        raw = self.raw_text()
        wrap_marks, bold_text, highlight_text, dot_text = self._inline_spans(raw)
        for a, b in _mark_spans(raw) + self._markdown_spans(raw) + wrap_marks:
            self.text.tag_add("mark", f"1.0+{a}c", f"1.0+{b}c")
        for a, b in bold_text:
            self.text.tag_add("bold", f"1.0+{a}c", f"1.0+{b}c")
        for a, b in highlight_text:
            self.text.tag_add("highlight", f"1.0+{a}c", f"1.0+{b}c")
        for a, b in dot_text:
            self.text.tag_add("dots", f"1.0+{a}c", f"1.0+{b}c")
        for m in TOKEN_RE.finditer(raw):           # 仮名化した語の記号（エディターは常に仮名）
            self.text.tag_add("registered", f"1.0+{m.start()}c", f"1.0+{m.end()}c")

    def _tokenize_editor(self):
        """エディターの中の、仮名化した語（打った・貼った実名）を記号に置き換える（エディターは常に仮名。
        2026-10-24 班長決定）。置き換えは Ctrl+Z 1回で戻る（戻すと、次に組み直すときにまた記号になる）。"""
        if self._loading:
            return
        spans = self.session.dictionary.spans(self.raw_text())
        if not spans:
            return
        insert = self.text.index("insert")
        with undoable(self.text):
            for a, b, entry in reversed(spans):
                self.text.delete(f"1.0+{a}c", f"1.0+{b}c")
                self.text.insert(f"1.0+{a}c", entry.token)
        self.text.mark_set("insert", insert)
        self.text.edit_modified(False)
        self._update_title()

    def _replace_in_editor(self, old, new):
        """エディターの old をすべて new に置き換える（仮名化の解除で、記号を元の語に戻すとき）。Ctrl+Z 1回で戻る。"""
        raw = self.raw_text()
        starts = [m.start() for m in re.finditer(re.escape(old), raw)]
        if not starts:
            return
        with undoable(self.text):
            for a in reversed(starts):
                self.text.delete(f"1.0+{a}c", f"1.0+{a + len(old)}c")
                self.text.insert(f"1.0+{a}c", new)
        self.text.edit_modified(False)

    def _markdown_spans(self, raw):
        """マークダウンの記号（見出しの #、箇条書きの「- 」、段落番号の「1. 」、表の | と区切りの行）の位置。

        読み取り（document.parse）で、見出しなどとして読まれる行だけに付ける（右揃えの段落の後など、変換しない
        所の # には付けない）。
        """
        lines = raw.split("\n")
        pos = [0]
        for line in lines:
            pos.append(pos[-1] + len(line) + 1)
        out = []
        for p in parse(lines, self.session.doc_type):
            if p.src_line < 0:
                continue
            n = p.src_line
            if p.kind in (HEADING, BULLET, NUMBER) and p.src_col > 0:
                # 記号の終わりは本文の1字目の前（「**# 見出し**」では、前の ** と # の両方）
                out.append((pos[n], pos[n] + (p.source_col(0) if p.text else p.src_col)))
            elif p.kind == TABLE:
                for k in range(n, p.src_end + 1):
                    if k == n + 1:
                        out.append((pos[k], pos[k] + len(lines[k])))     # 区切りの行
                        continue
                    out += [(pos[k] + c, pos[k] + c + 1) for c in cell_separators(lines[k])]
        return out

    def _inline_spans(self, raw):
        """字を囲む記号（** == * [字]{N}）の位置と、太字・蛍光ペン・傍点の字の範囲。"""
        out, pos = ([], [], [], []), 0
        for line in raw.split("\n"):
            if has_inline_marks(line):
                for found, spans in zip(out, inline_mark_spans(line)):
                    found += [(pos + x, pos + y) for x, y in spans]
            pos += len(line) + 1
        return out

    def on_bold(self):
        """選んだ文字列を太字にする（**文字** で囲む。Word の Ctrl+B。2026-10-24 班長指示）。
        既に囲まれていれば、記号を外す。行をまたぐ選択と、空白だけの選択には付けない。

        見出しの行で押したとき（選んでいない、または見出しの字をすべて選んだとき）は、同じ段の見出しの行を
        すべて太字にする。その見出しが既に太字なら、同じ段の見出しの太字をすべて外す（同じ段の見出しの太字を
        そろえるため。組むときは書いたとおりにする。2026-10-24 班長決定）。
        """
        target = self._heading_for_bold()
        if target:
            self._bold_headings(*target)
            return
        self._toggle_wrap("**")

    def on_highlight(self):
        """選んだ文字列に蛍光ペンを付ける（==文字== で囲む。Word の Ctrl+Alt+H。2026-10-24 班長指示）。
        既に囲まれていれば、記号を外す。蛍光ペンは確認表示だけで黄色に塗り、保存する PDF と印刷には出さない。"""
        self._toggle_wrap("==")

    def on_dots(self):
        """選んだ文字列に傍点を付ける（*文字* で囲む。2026-10-24 班長指示）。既に付いていれば外す。"""
        self._toggle_wrap("*")

    def on_distribute(self):
        """選んだ字を均等割付にする（[文字]{N} の形で挟む。N は選んだ字の数〔半角は半字〕を切り上げた字数で、
        目次と同じくエディターで手で直す。2026-10-24 班長指示）。既に挟まれていれば外す。行をまたぐ選択と、
        空白だけの選択には付けない。Ctrl+Z 1回で戻せる。"""
        try:
            a, b = self.text.index("sel.first"), self.text.index("sel.last")
        except tk.TclError:
            # 表のセルにカーソルがあれば、そのセルの字全体を挟む・外す（配置の記号の後から。2026-10-24 班長指示）
            cells = self._table_cells()
            if not cells:
                return
            n, s, e = cells[0]
            _, start, end, _ = self._cell_content(n, s, e)
            if start >= end:
                return
            a, b = f"{n}.{start}", f"{n}.{end}"
            whole = DISTRIBUTE_RE.fullmatch(self.text.get(a, b))
            if whole:
                with undoable(self.text):
                    self.text.delete(a, b)
                    self.text.insert(a, whole.group(1))
                return
        sel = self.text.get(a, b)
        if not sel.strip(" 　") or "\n" in sel:
            return
        before = self.text.get(f"{a} linestart", a).endswith(DISTRIBUTE_OPEN)
        after = DISTRIBUTE_CLOSE_RE.match(self.text.get(b, f"{b} lineend"))
        whole = DISTRIBUTE_RE.fullmatch(sel)
        with undoable(self.text):
            if before and after:
                self.text.delete(b, f"{b}+{len(after.group(0))}c")
                self.text.delete(f"{a}-{len(DISTRIBUTE_OPEN)}c", a)
                a = self.text.index(f"{a}-{len(DISTRIBUTE_OPEN)}c")
                b = self.text.index(f"{a}+{len(sel)}c")
            elif whole:
                self.text.delete(a, b)
                self.text.insert(a, whole.group(1))
                b = self.text.index(f"{a}+{len(whole.group(1))}c")
            else:
                closing = f"]{{{math.ceil(sum(0.5 if is_half(c) else 1 for c in sel))}}}"
                self.text.insert(b, closing)
                self.text.insert(a, DISTRIBUTE_OPEN)
                a = self.text.index(f"{a}+{len(DISTRIBUTE_OPEN)}c")
                b = self.text.index(f"{a}+{len(sel)}c")
        self.text.tag_remove("sel", "1.0", "end")
        self.text.tag_add("sel", a, b)
        self.text.mark_set("insert", b)

    def _toggle_wrap(self, wrap):
        """選んだ文字列を wrap（** == *）で囲む。既に囲まれていれば外す。行をまたぐ選択と、空白だけの選択には
        付けない。Ctrl+Z 1回で戻せる。太字と傍点は * の数で見分ける（「***語***」は太字と傍点。* が2つ以上なら太字、
        奇数なら傍点）。"""
        try:
            a, b = self.text.index("sel.first"), self.text.index("sel.last")
        except tk.TclError:
            return
        sel = self.text.get(a, b)
        if not sel.strip(" 　") or "\n" in sel:
            return
        # 選択の前後の空白は囲まない（「** 文字**」は記号にならない）
        a = self.text.index(f"{a}+{len(sel) - len(sel.lstrip(' 　'))}c")
        b = self.text.index(f"{b}-{len(sel) - len(sel.rstrip(' 　'))}c")
        sel = self.text.get(a, b)
        n = len(wrap)

        def run(s, from_end=False):
            """s の端から続く、記号の字（* か =）の数。"""
            s = s[::-1] if from_end else s
            return len(s) - len(s.lstrip(wrap[0]))

        def wrapped(left, right):
            return left % 2 == 1 and right % 2 == 1 if wrap == "*" else left >= n and right >= n
        outside = wrapped(run(self.text.get(f"{a} linestart", a), True), run(self.text.get(b, f"{b} lineend")))
        with undoable(self.text):
            if outside:
                self.text.delete(b, f"{b}+{n}c")
                self.text.delete(f"{a}-{n}c", a)
                a = self.text.index(f"{a}-{n}c")
                b = self.text.index(f"{a}+{len(sel)}c")
            elif len(sel) > 2 * n and wrapped(run(sel), run(sel, True)):
                self.text.delete(a, b)
                self.text.insert(a, sel[n:-n])
                b = self.text.index(f"{a}+{len(sel) - 2 * n}c")
            else:
                self.text.insert(b, wrap)
                self.text.insert(a, wrap)
                a = self.text.index(f"{a}+{n}c")
                b = self.text.index(f"{a}+{len(sel)}c")
        self.text.tag_remove("sel", "1.0", "end")
        self.text.tag_add("sel", a, b)
        self.text.mark_set("insert", b)

    def _heading_lines(self):
        """見出しとして読まれる行 {エディターの行の番号（1 から）: 見出しの階層}。"""
        return {p.src_line + 1: p.level for p in parse(self.raw_text().split("\n"), self.session.doc_type)
                if p.kind == HEADING}

    def _heading_for_bold(self):
        """［太字］で同じ段の見出しをそろえるときの (行の番号, 見出しの階層)。そうでなければ None。"""
        try:
            a, b = self.text.index("sel.first"), self.text.index("sel.last")
        except tk.TclError:
            a = b = self.text.index("insert")
        n = int(a.split(".")[0])
        if int(b.split(".")[0]) != n:
            return None
        level = self._heading_lines().get(n)
        parts = _split_heading(self.text.get(f"{n}.0", f"{n}.end"))
        if not level or parts is None:
            return None
        if a != b:
            # 見出しの一部だけを選んだときは、その字だけを太字にする
            if split_inline(self.text.get(a, b))[0].strip(" 　") != split_inline(parts[1])[0].strip(" 　"):
                return None
        return n, level

    def _bold_headings(self, n, level):
        """同じ段（level）の見出しの行を、すべて太字にする（n 行目の見出しが太字なら、すべて外す）。Ctrl+Z 1回で戻せる。"""
        release = _whole_bold(_split_heading(self.text.get(f"{n}.0", f"{n}.end"))[1])
        insert = self.text.index("insert")
        with undoable(self.text):
            for k, lv in self._heading_lines().items():
                line = self.text.get(f"{k}.0", f"{k}.end")
                parts = _split_heading(line) if lv == level else None
                if parts is None:
                    continue
                prefix, body = parts
                plain = remove_bold(body)       # 蛍光ペンの記号は残す
                core = plain.strip(" 　")
                if not core:
                    continue
                if release:
                    new = prefix + plain
                else:
                    lead = plain[:len(plain) - len(plain.lstrip(" 　"))]
                    new = prefix + lead + "**" + core + "**" + plain[len(lead) + len(core):]
                if new != line:
                    self.text.delete(f"{k}.0", f"{k}.end")
                    self.text.insert(f"{k}.0", new)
        self.text.tag_remove("sel", "1.0", "end")
        self.text.mark_set("insert", insert)

    def _selection(self):
        try:
            return self.text.get("sel.first", "sel.last")
        except tk.TclError:
            return ""

    def _line_range(self):
        try:
            first = int(self.text.index("sel.first").split(".")[0])
            last_index = self.text.index("sel.last")
            last = int(last_index.split(".")[0])
            if last_index.endswith(".0") and last > first:
                last -= 1
        except tk.TclError:
            first = last = int(self.text.index("insert").split(".")[0])
        return first, last

    def on_align(self, mark):
        """選んだ行（なければカーソルの行）に配置の記号（-> を含む）を付ける。ほかの配置の記号は付け替える
        （+N は残す）。

        対象の行がすべて既にその記号なら、記号を外して標準（左）に戻す（同じボタンをもう一度押すと解除）。
        表の行では、［中央］［右］は、カーソルのあるセル（選んでいれば、選んだ範囲にかかるセル）の先頭の配置の記号を
        付け外しする。区切りの行（2行目）のセルでは、その列の配置（:--- の : の付け方）を変える（2026-10-24 班長指示）。
        """
        cells = self._table_cells() if mark in (CENTER_MARK, RIGHT_MARK) else []
        # 区切りの行の列の配置は、カーソル（選んだ範囲）が区切りの行の中だけにあるときに変える
        columns = self._table_cells(separator=True) if mark in (CENTER_MARK, RIGHT_MARK) and not cells else []
        first, last = self._line_range()
        rows = []
        for n in range(first, last + 1):
            line = self.text.get(f"{n}.0", f"{n}.end")
            if line.lstrip().startswith("|") or is_line_mark(line) or vadm.SEPARATOR_RE.match(line):
                continue
            rows.append((n, line, move_wraps_after_marks(line)))
        if not rows and not cells and not columns:
            return

        def has(norm):
            lead = split_lead_marks(norm)
            return lead.first if mark == INDENT_MARK else lead.align == mark
        release = all(has(norm) for _, _, norm in rows)
        with undoable(self.text):          # 何行あっても、Ctrl+Z 1回で戻せる
            self._align_cells(cells, mark)
            self._align_columns(columns, mark)
            for n, line, norm in rows:
                # 「**:=: 準備書面**」は「:=: **準備書面**」として扱う。配置の記号と -> は付け替え、
                # +N・[HEADER] は残す（記号の順は、ヘッダー・配置・インデント・字下げ）
                lead = split_lead_marks(norm)
                rest = lead.rest
                align = "" if release or mark == INDENT_MARK else mark
                first = not release and mark == INDENT_MARK
                prefix = lead._replace(align=align, first=first, rest="").join()
                if norm != line:
                    self.text.delete(f"{n}.0", f"{n}.end")
                    self.text.insert(f"{n}.0", prefix + rest)
                elif prefix != line[:len(line) - len(rest)]:
                    # 記号の部分だけを書き換える（行の選択が残るように）
                    self.text.delete(f"{n}.0", f"{n}.{len(line) - len(rest)}")
                    self.text.insert(f"{n}.0", prefix)

    def _table_cells(self, separator=False):
        """カーソルのあるセル（字を選んでいれば、選んだ範囲にかかるセル）[(行, 左の | の位置, 右の | の位置)]。
        表の区切りの行（2行目）は除く（separator が真なら、区切りの行のセルだけ）。"""
        try:
            a, b = self.text.index("sel.first"), self.text.index("sel.last")
        except tk.TclError:
            a = b = self.text.index("insert")
        (la, ca), (lb, cb) = [tuple(int(v) for v in x.split(".")) for x in (a, b)]
        out = []
        for n in range(la, lb + 1):
            line = self.text.get(f"{n}.0", f"{n}.end")
            if not line.lstrip().startswith("|") or (parse_separator(line) is None) == separator:
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

    def on_indent(self):
        """選んだ行（なければカーソルの行）に +1 を付ける。対象の行がすべて既に +N なら外す（ほかの
        ボタンと同じく、もう一度押すと解除。字数は、目次と同じくエディターで手で直す。2026-10-24 班長指示）。
        既に +N のある行の字数は変えない。見出し・箇条書き・段落番号の行には付けない（付けると見出しなどで
        なくなるため）。Ctrl+Z 1回で戻せる。"""
        def target(line):
            if (not line.strip() or line.lstrip().startswith("|") or is_line_mark(line)
                    or vadm.SEPARATOR_RE.match(line)):
                return None
            parts = split_lead_marks(move_wraps_after_marks(line))
            if not parts[1] and (HEADING_MARK_RE.match(parts[3]) or LIST_MARK_RE.match(parts[3])):
                return None
            return parts
        self._toggle_lines(target, lambda p: p.left,
                           lambda p, release: p._replace(left="" if release else p.left or LEFT_INDENT_MARK).join())

    def on_area(self, mark):
        """選んだ行（なければカーソルの行）を、ヘッダー・フッターの行にする（行頭に [HEADER] [FOOTER] を付ける。
        2026-10-25 班長指示）。もう片方の記号は付け替える。対象の行がすべて既にその記号なら外す（ほかのボタンと同じ）。
        配置の記号・+N・-> は残す。表・改ページなどの記号の行・区切りの行と、見出し・箇条書き・段落番号の行には
        付けない（付けると見出しなどでなくなるため。［インデント］と同じ）。Ctrl+Z 1回で戻せる。"""
        def target(line):
            if line.lstrip().startswith("|") or is_line_mark(line) or vadm.SEPARATOR_RE.match(line):
                return None
            parts = split_lead_marks(move_wraps_after_marks(line))
            if not (parts.area or parts.left or parts.first) and (
                    HEADING_MARK_RE.match(parts.rest) or LIST_MARK_RE.match(parts.rest)):
                return None
            return parts
        self._toggle_lines(target, lambda p: area_of(p.area) == area_of(mark),
                           lambda p, release: p._replace(area="" if release else mark).join())

    def _toggle_lines(self, target, has, build):
        """行頭の記号を付け外しするボタン（［インデント］［ヘッダー］［見出し］［箇条書き］［段落番号］）の共通の流れ。
        選んだ行（なければカーソルの行）のうち、target(行) が None でない行を対象とする。対象の行がすべて
        has(target の結果) なら外し、そうでなければ付ける（行は build(target の結果, 外すか) に書き換える）。
        対象の行がなければ何もしない。Ctrl+Z 1回で戻せる。"""
        first, last = self._line_range()
        found = [target(self.text.get(f"{n}.0", f"{n}.end")) for n in range(first, last + 1)]
        found = [p for p in found if p is not None]
        if not found:
            return
        release = all(has(p) for p in found)

        def change(line, n):
            parts = target(line)
            return None if parts is None else build(parts, release)
        self._edit_lines(change)

    def _edit_lines(self, change):
        """選んだ行（なければカーソルの行）を change(行, 番号) で書き換える（None は変えない）。Ctrl+Z 1回で戻せる。"""
        first, last = self._line_range()
        with undoable(self.text):
            for n in range(first, last + 1):
                line = self.text.get(f"{n}.0", f"{n}.end")
                new = change(line, n)
                if new is not None and new != line:
                    # 変わった所だけを書き換える（前後の同じ字は残す。行の選択が残り、続けて押せるように）
                    head = 0
                    while head < min(len(line), len(new)) and line[head] == new[head]:
                        head += 1
                    tail = 0
                    while (tail < min(len(line), len(new)) - head
                           and line[len(line) - 1 - tail] == new[len(new) - 1 - tail]):
                        tail += 1
                    self.text.delete(f"{n}.{head}", f"{n}.{len(line) - tail}")
                    self.text.insert(f"{n}.{head}", new[head:len(new) - tail])

    def _heading_level_before(self, n):
        """n 行目より前の、いちばん近い見出しの階層（なければ 0）。"""
        for k in range(n - 1, 0, -1):
            m = HEADING_MARK_RE.match(move_wraps_after_marks(self.text.get(f"{k}.0", f"{k}.end")))
            if m:
                return len(m.group(1))
        return 0

    def _level_for_plain(self, n):
        """n 行目の本文（字のない行）を Alt+Shift+←／→ で見出しにするときのレベル。←・→ とも、直前の見出しと同じ。
        直前に見出しがなければ、［見出し］と同じ ##（2026-10-25 班長指示）。"""
        return self._heading_level_before(n) or len(HEADING_BUTTON_MARK.strip())

    def on_outline(self, step):
        """見出しのレベルを上げ下げする（Word の Alt+Shift+←／→）。step は -1（上げる）・+1（下げる）。

        見出しは # の数を1つ減らす・増やす。# から上げると本文、9 から下げると本文になる（# から上げるのは
        2026-10-25 班長指示。それまでは # より上げなかった）。本文の行は、上げても下げても、直前の見出しと同じ
        レベルの見出しになる（上げるのは Word と同じ。下げるのは 2026-10-25 班長指示。それまでは下げなかった）。
        直前に見出しがなければ、［見出し］と同じ ## にする（公用文では第１のレベルを基本的に使わないため。
        2026-10-25 班長指示）。
        字のない行も、見出しの記号だけの行にする（選んだ行がすべて字のない行のとき。2026-10-25 班長指示）。
        """
        blank = self._blank_range()

        def change(line, n):
            if blank:
                return "#" * self._level_for_plain(n) + " "
            if _special_line(line):
                return None
            line = move_wraps_after_marks(line)     # 「**# 見出し**」は「# **見出し**」として扱う
            m = HEADING_MARK_RE.match(line)
            if m:
                level = len(m.group(1)) + step
                if level < 1 or level > 9:
                    return line[m.end():]
                return "#" * level + " " + line[m.end():]
            if line.strip():
                level = self._level_for_plain(n)
                return "#" * level + " " + _strip_list(line.lstrip(" 　"))
            return None
        self._edit_lines(change)
        if blank:
            self._caret_to_line_end()

    def _blank_range(self):
        """選んだ行（なければカーソルの行）が、すべて字のない行か（空白だけの行も含む）。"""
        first, last = self._line_range()
        return all(not self.text.get(f"{n}.0", f"{n}.end").strip(" 　\t") for n in range(first, last + 1))

    def _caret_to_line_end(self):
        """字のない行に記号を付けた後、続けて字を打てるよう、カーソルを最後の行の行末に置く（選択は外す）。"""
        _, last = self._line_range()
        self.text.tag_remove("sel", "1.0", "end")
        self.text.mark_set("insert", f"{last}.end")

    def on_paragraph_kind(self, mark):
        """選んだ行（なければカーソルの行）を、見出し（## ）・箇条書き（- ）・段落番号（1. ）にする（2026-10-25 班長指示）。
        ほかの見出し・箇条書き・段落番号の記号は付け替える。対象の行がすべて既にその種類なら、記号を外して本文に
        戻す（見出しは、どのレベルでも見出しとみなす。レベルは、エディターで # の数を直す）。表・改ページなどの記号の行・
        区切りの行と、配置・+N・->・[HEADER] の記号のある行には付けない（見出しのレベルの上げ下げと同じ）。
        字のない行は、選んだ行がすべて字のない行のときだけ記号を付け、カーソルを行末に置く（まだ打っていない行を
        見出しなどにしてから書くため。2026-10-25 班長指示）。字のある行と一緒に選んだ字のない行（1行の空き）には
        付けない。Ctrl+Z 1回で戻せる。"""
        blank = self._blank_range()

        def target(line):
            if blank:
                return "", ""
            if _special_line(line):
                return None
            body = move_wraps_after_marks(line).lstrip(" 　")   # 「**# 見出し**」は「# **見出し**」として扱う
            kind, end = _paragraph_kind(body)
            return kind, body[end:]
        self._toggle_lines(target, lambda p: p[0] == mark, lambda p, release: ("" if release else mark) + p[1])
        if blank:
            self._caret_to_line_end()

    def on_plain(self):
        """標準の本文（左寄せ）にする（Word の Ctrl+Shift+N）。見出し・箇条書き・段落番号・配置の記号を外す。"""
        def change(line, n):
            if line.lstrip().startswith("|") or is_line_mark(line) or vadm.SEPARATOR_RE.match(line):
                return None
            # 「**:-: # 見出し**」は「:-: # **見出し**」として扱う。配置・+N・-> の記号を外す（ヘッダー・フッターの
            # 記号は、置く場所の記号なので残す。Word の「標準」でも、ヘッダーの段落はヘッダーのまま）
            lead = split_lead_marks(move_wraps_after_marks(line))
            if lead.area:
                return lead.area + lead.rest
            line = lead.rest
            m = HEADING_MARK_RE.match(line)
            if m:
                line = line[m.end():]
            return _strip_list(line)
        self._edit_lines(change)

    def on_line_mark(self, mark):
        """カーソルの行の前に、改ページなどの記号だけの行を入れる。"""
        n = int(self.text.index("insert").split(".")[0])
        self.text.insert(f"{n}.0", mark + "\n")

    def on_find(self, replace):
        """検索と置換の画面を開く（開いていれば前に出す）。選んでいる文字があれば、検索する文字列に入れる。"""
        selected = self._selection()
        if self._find_dialog is None or not self._find_dialog.winfo_exists():
            self._find_dialog = FindDialog(self)
        self._find_dialog.show(selected if "\n" not in selected else "", replace)

    def _replace_undoable(self, text):
        """エディターの文章を、Ctrl+Z（元に戻す）で戻せる形で置き換える（AI の回答の貼り付けで使う。
        2026-10-23 班長決定。［貼り付けを元に戻す］のボタンの代わり）。text は仮名の文章。"""
        with undoable(self.text):
            self.text.delete("1.0", "end")
            self.text.insert("1.0", text)
        self.text.edit_modified(False)
        self._update_title()
        self.refresh()

    def _on_paste(self, event=None):
        """貼り付け（Ctrl+V）は、仮名化した語を記号に置き換えて貼る（エディターは常に仮名。2026-10-24）。"""
        try:
            clip = self.clipboard_get()
        except tk.TclError:
            return None
        spans = self.session.dictionary.spans(clip)
        if not spans:
            return None
        try:
            self.text.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        self.text.insert("insert", self.session.dictionary.pseudonymize(clip))
        self.text.see("insert")
        self.status.configure(text=f"貼り付けた文章の仮名化した語 {len(spans)} か所を、記号に置き換えました。")
        return "break"


# 表の行の、セルの先頭の配置の記号（| の後。太字・蛍光ペンの記号の内側にあってもよい）。group(2) が配置の記号
_CELL_MARK_RE = re.compile(r"(?<!\\)\|[ 　]*" + CELL_ALIGN_RE.pattern)


def _mark_spans(text):
    """配置・改ページなどの記号の位置 [(始め, 終わり)]（文章の初めからの字数）。記号として読まれる所だけ
    （行頭の配置の記号、その行だけの改ページなどの記号、表のセルの先頭の配置の記号）。"""
    out, pos = [], 0
    for line in text.split("\n"):
        stripped = line.strip()
        if is_line_mark(stripped):
            start = pos + line.index(stripped)
            out.append((start, start + len(stripped)))
        elif line.lstrip().startswith("|"):
            for m in _CELL_MARK_RE.finditer(line):
                out.append((pos + m.start(2), pos + m.end(2)))
        else:
            body = line.lstrip(" 　")
            # 「**:=: 準備書面**」の記号は、前の ** の後にある
            off = 0
            if move_wraps_after_marks(body) != body:
                while leading_wrap(body[off:]):
                    off += len(leading_wrap(body[off:]))
            # 行頭の配置・+N・-> の記号
            lead = len(body) - off - len(split_lead_marks(body[off:])[3])
            if lead:
                start = pos + len(line) - len(body) + off
                out.append((start, start + lead))
        pos += len(line) + 1
    return out


def _special_line(line):
    """見出しのレベルを変えない行（表・改ページなどの記号の行・配置の記号の行・区切りの行・空の行）。"""
    s = line.strip()
    lead = split_lead_marks(move_wraps_after_marks(line))
    return (not s or s.startswith("|") or is_line_mark(s) or vadm.SEPARATOR_RE.match(line)
            or bool(lead.align or lead.left or lead.first or lead.area))


def _split_heading(line):
    """見出しの行を (記号まで, 見出しの字) に分ける（行頭の空白・配置の記号、「**# 見出し**」の形も扱う）。
    見出しの記号がなければ None。"""
    rest = line.lstrip(" 　")
    prefix = line[:len(line) - len(rest)]
    rest = move_wraps_after_marks(rest)
    for mark in LEAD_ALIGN_MARKS:
        if lead_mark_len(rest, mark):
            n = lead_mark_len(rest, mark)
            prefix, rest = prefix + rest[:n], rest[n:]
            break
    m = HEADING_MARK_RE.match(rest)
    return (prefix + rest[:m.end()], rest[m.end():]) if m else None


def _whole_bold(body):
    """見出しの字が、すべて太字か。"""
    plain, bold, _, _ = split_inline(body)
    return bool(plain.strip()) and all(k in bold for k, ch in enumerate(plain) if not ch.isspace())


def _paragraph_kind(body):
    """行頭の見出し・箇条書き・段落番号の記号 (［見出し］などで付ける記号, 記号の字数)。なければ ("", 0)。"""
    m = HEADING_MARK_RE.match(body)
    if m:
        return HEADING_BUTTON_MARK, m.end()
    m = LIST_MARK_RE.match(body)
    if m:
        return (BULLET_MARK if m.group(0) == BULLET_MARK else NUMBER_MARK), m.end()
    return "", 0


def _strip_list(line):
    """行頭の箇条書き（「- 」）・段落番号（「1. 」）を外す。"""
    m = LIST_MARK_RE.match(line)
    return line[m.end():] if m else line
