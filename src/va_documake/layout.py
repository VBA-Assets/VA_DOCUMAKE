"""行組み：段落を、VA公用文（Word の「文字数と行数を指定」）と同じ規則で、1字ずつ位置を決めて組む。

規則は仕様.md の6。試作（試作/typeset.py）で、VA公用文の7種類すべての見本と一致を確かめたもの。
座標はポイント単位で、x は本文の左端から、行はページの中の何行目か（0 から）で表す。
"""
import math
import unicodedata
from dataclasses import dataclass, field, replace

from .document import BLANK, BULLET, CENTER, FOOTER, HEADER, HEADING, NUMBER, PAGE_BREAK, RIGHT, SECTION_BREAK, TABLE
from .document import TITLE, TOC, TOC_LEVELS, heading_label, squeezed_numbers
from .doctypes import (PAGE_NUMBER_BOTTOM_CENTER, PAGE_NUMBER_BOTTOM_CENTER_DECORATED, PAGE_NUMBER_BOTTOM_RIGHT,
                       PAGE_NUMBER_TOP_RIGHT, TITLE_CENTER, TITLE_JUSTIFY, TITLE_LEFT)

MM = 72 / 25.4
PAGE_W, PAGE_H = 210 * MM, 297 * MM
FONT_SIZE = 12

# ページ番号・ヘッダー・フッターの位置
HEADER_DISTANCE, FOOTER_DISTANCE = 20 * MM, 15 * MM  # VA公用文 basSetup.ConfigPage
FOOTER_BASELINE_OFFSET = 3.32   # フッターの位置から基準線までの高さ（VA公用文の PDF〔下中央〕で測った値）
# ヘッダー・フッターの行送り：Word の1行（ＭＳ 明朝 12pt）の高さ。行の高さの真ん中に字を置くとして、フッターの基準線の
# 高さ（FOOTER_BASELINE_OFFSET）から求めた値（約 15.27pt）。行の下端は基準線の FOOTER_BASELINE_OFFSET 下
HF_LINE_PITCH = FONT_SIZE + 2 * (FOOTER_BASELINE_OFFSET - FONT_SIZE * 36 / 256)
HF_BELOW = FOOTER_BASELINE_OFFSET
HF_ABOVE = HF_LINE_PITCH - HF_BELOW
# 余白に入りきらないヘッダー・フッターを、用紙の端の側へずらすときの限り（用紙の端からの距離。2026-10-25 班長決定）
HF_EDGE_MIN = 5 * MM
_FOOTER_PAGE_NUMBERS = (PAGE_NUMBER_BOTTOM_CENTER, PAGE_NUMBER_BOTTOM_CENTER_DECORATED, PAGE_NUMBER_BOTTOM_RIGHT)
_NAIYOU = "Naiyou"              # 内容証明（ヘッダー・フッターを付けない。naiyou.DOC_TYPE と同じ）

# 表の値（仕様.md の5.3。Word に合わせ込まず、Word の既定に寄せた読みやすい値）
CELL_PAD_X = 1.9 * MM           # セルの左右の余白（Word の既定 1.9mm）
CELL_PAD_Y = 1.5                # セルの上下の余白（ポイント）
# 傍点の黒丸（VAスタイルの傍点の既定「黒丸」と同じ形）：半径と、字の基準線から黒丸の中心までの高さ（ポイント）。
# 本文の行では行の間に置き、字の位置・改行・改ページは変えない（2026-10-24 班長指示）
DOT_RADIUS = 0.08 * 12
DOT_RISE = 1.15 * 12
# 傍点のある表の行は、上をこれだけ空ける（表の行は字の上の余白が狭く、黒丸が上の罫線に重なるため）
DOT_ROW_EXTRA = 2.5
CELL_LINE_PITCH = FONT_SIZE * 1.3  # セルの中の行送り（VA公用文が表に使う「行間詰め」の1行に近い値）
RULE_WIDTH = 0.5                # 罫線の太さ（ポイント）
DOUBLE_RULE_GAP = 2.0           # 2重線の2本の間（ポイント。1.5pt では画面で1本に見えた）

# 禁則（Word の「標準」）
NO_START = set("!%),.:;?]}¢°’”‰′″℃、。々〉》」』】〕゛゜ゝゞ・ヽヾ！％），．：；？］｝｡｣､･ｧｨｩｪｫｬｭｮｯｰﾞﾟ￠")
NO_END = set("$([\\{£¥‘“〈《「『【〔＄（［｛｢￡￥")
# ぶら下げる句読点（全角だけ。半角の「,」「.」は英数字の語の一部として扱う〔110,000、Ver.3.2〕）
HANG = set("、。，．､｡")


def is_half(ch):
    """半角の字か（Unicode の東アジアの幅が「狭い」「半角」のもの。ＭＳ 明朝ではこれらの字の幅が全角の半分）。"""
    return unicodedata.east_asian_width(ch) in ("Na", "H")


SPACE_STRETCH_MAX = 0.3 * 12    # 両端揃えで半角空白1つを広げる上限（字の大きさの 0.3 倍。2026-10-24、Word の目次の行で読み取った値）
TOC_HANG = 1                    # 目次の折り返した行のぶら下げ（字。本文の見出しと同じく1字。2026-10-24 班長決定）
TOC_TAB_FROM_RIGHT = 0.32       # 目次のページ番号の右揃えのタブ（本文の右端から。VA公用文で作った目次入りの PDF で読み取った値）
TOC_MIN_LEADER = 6.0            # 見出しとページ番号の間に、最低限残す幅（ポイント）
TOC_DOT_STEP = 6.1212           # 目次の点線の点の間隔（用紙の左端から。VA公用文で作った目次入りの PDF で読み取った値）
TOC_MAX_PASSES = 5              # 見出しのページが定まるまで組み直す回数の上限


def toc_entries(paras, levels=TOC_LEVELS):
    """目次に載せる見出し [(段落の番号, 段落)]（levels 段目まで。既定は3段目まで。目次より前の見出しも載せる。
    Word と同じ）。目次の段落（[TOC:2] など）の level が、載せる段。"""
    # 複合見出しは、まとめた見出しを外側の段の1項目にする（字のない外側の見出しは載せない）
    return [(pi, p) for pi, p in enumerate(paras)
            if p.kind == HEADING and not p.composite and heading_label(paras, pi)[0] <= levels]


@dataclass
class Glyph:
    ch: str
    x: float                # 本文の左端からの位置（ポイント）
    is_number: bool = False  # 見出し・段落番号の番号の字か（本文の字ではない）
    index: int = -1          # 段落の何字目か（番号＋本文の通し。0 から）
    bold: bool = False       # 太字（**文字**。ＭＳ ゴシックで描く）
    highlight: bool = False  # 蛍光ペン（==文字==。確認表示だけで黄色に塗る）
    dot: bool = False        # 傍点（*文字*。字の上に黒丸を付ける）
    pseudonym: bool = False  # 仮名化した語の字（確認表示だけで地に色を付ける。2026-10-24 班長指示）
    scale: float = 1.0       # 字の横の倍率（複合見出しの外側の括弧の番号を全角1字の幅に縮める。2026-10-26）


@dataclass
class Line:
    page: int               # 1 から
    row: int                # ページの中の何行目か（0 から。ヘッダー・フッターの行は -1）
    glyphs: list = field(default_factory=list)
    para_index: int = -1    # 何番目の段落の行か
    area: str = None        # ヘッダー・フッターの行なら HEADER・FOOTER
    y: float = None         # ヘッダー・フッターの行の基準線（用紙の上端から。ポイント）


@dataclass
class TableGlyph:
    ch: str
    x: float                # 本文の左端からの位置（ポイント）
    y: float                # 基準線の、用紙の上端からの位置（ポイント）
    row: int = -1           # 表の何行目か（0 が見出しの行）
    col: int = -1           # 何列目か
    index: int = -1         # セルの何字目か
    bold: bool = False      # 太字
    highlight: bool = False  # 蛍光ペン
    dot: bool = False       # 傍点
    pseudonym: bool = False  # 仮名化した語の字


@dataclass
class TableRow:
    top: float              # 行の上の端（用紙の上端から。ポイント）
    bottom: float           # 行の下の端
    double_below: bool = False  # この行の下を2重線にするか（見出しの行）
    index: int = -1             # 表の何行目か（0 が見出しの行）


@dataclass
class TablePiece:
    """1つのページに入る表の部分（ページをまたぐ表は、ページごとに分かれる）。"""
    page: int
    col_x: list             # 列の境目の位置（本文の左端から。左端・各列の右端）
    para_index: int = -1    # 何番目の段落の表か
    rows: list = field(default_factory=list)
    glyphs: list = field(default_factory=list)


class Typesetter:
    def __init__(self, dt, page_number=PAGE_NUMBER_BOTTOM_CENTER):
        """dt は文書の種類、page_number はページ番号の位置（ヘッダー・フッターをページ番号の直下・直上に置くため）。"""
        self.dt = dt
        self.page_number = page_number
        self.page_number_shift = {}     # ページ → ページ番号をずらす量（ヘッダー・フッターが余白に入りきらないとき）
        self.warnings = []              # 利用者に知らせること（ヘッダーが本文に重なるなど）
        top, bottom, left, right = dt.margins
        chars, lines = dt.chars_lines
        self.margin_top, self.margin_left = top * MM, left * MM
        # 字送り・行送りは Word と同じく 0.05pt 刻みに丸め、本文の幅を「字送り×字数」にする
        # （右余白が少し増減する。VA公用文 clsVariablesManager.CalcMargine と同じ計算）
        self.pitch = round((PAGE_W - (left + right) * MM) / chars * 20) / 20
        self.text_w = self.pitch * chars
        self.line_pitch = round((PAGE_H - (top + bottom) * MM) / lines * 20) / 20
        self.lines_page = lines
        self.first_level = None

    # ---------- 1字・1段落 ----------

    def advance(self, ch):
        """1字の送り幅。全角は格子の1字（字送り）、半角はその半分。書体の字の幅には頼らない。"""
        return self.pitch / 2 if is_half(ch) else self.pitch

    def glyph_w(self, g):
        """描いた字の幅（横の倍率を掛けたもの）。"""
        return self.advance(g.ch) * g.scale

    def squeeze_items(self, s):
        """番号を全角1字の幅に収めた (字, 送り幅) の列。括弧の番号（「(3)」「（ア）」）は、括弧をそれぞれ 1/4 字、中の字に
        残りの 1/2 字を分ける（VA疑似アウトラインの FontMag と同じ割り振り）。ほかの番号（「第１」「１１」「a」）は、
        字の幅の割合のまま1字に収める（1字より狭い「a」は、1字の幅の中ほどに描く。place_number_glyphs）。"""
        if len(s) >= 3 and s[0] in "(（" and s[-1] in ")）":
            inner = len(s) - 2
            return ([(s[0], self.pitch / 4)] + [(ch, self.pitch / 2 / inner) for ch in s[1:-1]]
                    + [(s[-1], self.pitch / 4)])
        natural = sum(self.advance(ch) for ch in s)
        return [(ch, self.advance(ch) * self.pitch / natural) for ch in s]

    def place_number_glyphs(self, glyphs, chars):
        """番号の字の横の倍率と位置を、送り幅に合わせる。送り幅が字の幅より狭ければ縮め、広ければ（1字に収めた「a」）
        縮めずに送り幅の中ほどに置く。"""
        for g, (_, w) in zip(glyphs, chars):
            adv = self.advance(g.ch)
            g.scale = min(1.0, w / adv)
            g.x += (w - adv * g.scale) / 2

    def word_char(self, ch):
        """英数字の語を作る字（半角で、空白でないもの）か。均等割付の字の並び（2字以上の項目）は語の字ではない。"""
        return len(ch) == 1 and is_half(ch) and ch != " "

    def make_items(self, text, spans=(), limit=None):
        """(字, 送り幅) の列。均等割付（[字]{N}）の字は、1つの項目（字の並び, N 字の幅）にまとめる（途中で
        改行せず、両端揃えでも中の字間は変えない。字数より字が多いときは、割り付けずに字の幅のまま。2026-10-24）。
        limit は組む幅（段落の1行・セルの中）。割り付ける幅は、これより広くしない（大きな字数を入れたとき）。"""
        items, k = [], 0
        for start, end, n in sorted(spans):
            items += [(ch, self.advance(ch)) for ch in text[k:start]]
            s = text[start:end]
            natural = sum(self.advance(ch) for ch in s)
            wide = n * self.pitch if limit is None else min(n * self.pitch, limit)
            items.append((s, max(wide, natural)))
            k = end
        items += [(ch, self.advance(ch)) for ch in text[k:]]
        return items

    def breakable(self, items, k):
        """items[k-1] と items[k] の間で改行できるか（英単語の途中では改行しない。「-」の後は改行できる）。"""
        a, b = items[k - 1][0], items[k][0]
        return not (self.word_char(a) and self.word_char(b) and a != "-")

    def indents(self, p):
        """段落の (左インデント, 最初の行のインデント, 右インデント) をポイントで返す（VA公用文 basIndent）。"""
        dt = self.dt
        if p.align == TITLE:
            # 表題：VA公用文の「表題」スタイル（左右に同じ字数のインデント）
            ind = dt.title_indent * self.pitch
            return ind, 0.0, ind
        if p.left_indent is not None:
            # +N：指定した字数の左インデント（自動調節の対象外。1行目は -> ・行頭の空白の分だけ下げる）
            left = min(p.left_indent, self.dt.chars_lines[0] - 1) * self.pitch
            return left, p.first_indent * self.pitch, 0.0
        if p.kind == HEADING:
            x = p.level - 1
            add = dt.left_add * (p.level - self.first_level)
            return (dt.heading_left[x] + add) * self.pitch, dt.heading_first[x] * self.pitch, 0.0
        if not p.body_level or self.first_level is None:
            # 見出し・本文として整えない段落：行頭の空白から変換したインデントだけを付ける
            return 0.0, p.first_indent * self.pitch, 0.0
        x = p.body_level - 1
        add = dt.left_add * (p.body_level - self.first_level)
        if p.kind in (BULLET, NUMBER):
            return (dt.heading_left[x] + add + dt.list_left) * self.pitch, dt.list_first * self.pitch, 0.0
        return (dt.text_left[x] + add) * self.pitch, dt.text_first[x] * self.pitch, 0.0

    def break_lines(self, items, left, first, right, width=None, hang_allowed=True):
        """(字, 送り幅) の列を行に分ける。width は組む幅（省略すると本文の幅。表のセルでは中の幅）。

        hang_allowed が False のとき（表のセル）は、句読点をぶら下げず、前の字ごと次の行へ送る
        （ぶら下げると、セルの右の罫線にかかるため）。

        各行は (行頭の x, [(字, 送り幅), ...], ぶら下げ有無, 最終行か, 行末の半角空白の数)。
        """
        width = self.text_w if width is None else width
        lines = []
        i = 0
        n = len(items)
        start_x = left + first
        while i < n:
            avail = width - right - start_x
            j = i
            used = 0.0
            while j < n and used + items[j][1] <= avail + 0.01:
                used += items[j][1]
                j += 1
            hang = False
            if j < n:
                # ぶら下げ：次の字が句読点なら、行の外に出して同じ行に入れる。ただし、その次の字が
                # 行頭禁則の字（「。）」の「）」など）なら、ぶら下げずに前の字ごと次の行へ送る
                if hang_allowed and items[j][0] in HANG and not (j + 1 < n and items[j + 1][0] in NO_START):
                    j += 1
                    hang = True
                # 次の字が半角空白なら、空白を行末に残して改行する
                elif items[j][0] == " ":
                    while j < n and items[j][0] == " ":
                        j += 1
                else:
                    # 英単語の途中・行頭禁則・行末禁則にならない位置まで、改行位置を前へ戻す
                    k = j
                    while k - 1 > i and (not self.breakable(items, k)
                                         or items[k][0] in NO_START or items[k - 1][0] in NO_END):
                        k -= 1
                    if k - 1 > i or self.breakable(items, k):
                        j = k
                    # 語が1行より長いときは、語の途中で改行する（j をそのまま使う）
            if j == i:
                # 1つの項目も入らないとき（行より広い均等割付など）は、その項目だけで1行にする。これがないと、
                # 同じ位置を繰り返して止まらなくなる（2026-10-24、均等割付に大きな字数を入れると画面が固まった）
                j = i + 1
            # 行末の半角空白は、行の外に出す（両端揃えの計算に入れない）
            trail = 0
            while j - trail - 1 > i and items[j - trail - 1][0] == " ":
                trail += 1
            lines.append((start_x, items[i:j], hang, j >= n, trail))
            i = j
            start_x = left
        return lines

    def place_line(self, align, start_x, chars, hang, last, trail, num_here, right, line_width=None):
        """1行の字の位置を決め、[(字, x)] を返す。line_width は組む幅（省略すると本文の幅）。"""
        width = sum(w for _, w in chars)
        avail = (self.text_w if line_width is None else line_width) - right - start_x
        # 両端揃えで字間を配る範囲（ぶら下げた句読点・行末の空白を除く）
        n_body = len(chars) - (1 if hang else 0) - trail
        # 字間を足せる位置（k 番目の字の後ろ）。英数字の語の中には足さない
        spots = {k for k in range(n_body - 1)
                 if not (self.word_char(chars[k][0]) and self.word_char(chars[k + 1][0]))}
        # 行の中に半角空白があるときは、まず空白を広げる（英文の行と同じそろえ方。見出しの番号「(1) 」の空白は
        # 本文の字ではないので数えない）。空白1つを広げるのは SPACE_STRETCH_MAX までで、残りは字と字の間に均等に配る
        # （2026-10-24、VA公用文の目次の折り返した行で、Word が空白に 3.58pt、残りを字の間に配っていた）
        spaces = {k for k in range(num_here, n_body - 1) if chars[k][0] == " "}
        if align == TITLE:
            align = {TITLE_CENTER: CENTER, TITLE_LEFT: "left", TITLE_JUSTIFY: "justify"}[self.dt.title_align]
        x, gaps = start_x, {}
        if align == CENTER:
            x = start_x + (avail - width) / 2
        elif align == RIGHT:
            x = start_x + (avail - width)
        elif align != "left" and (not last or hang):
            # 両端揃え。句読点をぶら下げた行は、段落の最後の行でもそろえる
            body_w = sum(w for _, w in chars[:n_body])
            extra = avail - body_w
            if extra > 0 and spaces:
                others = spots - spaces
                per_space = extra / len(spaces) if not others else min(extra / len(spaces), SPACE_STRETCH_MAX)
                rest = extra - per_space * len(spaces)
                gaps = {k: per_space for k in spaces}
                if others and rest > 0:
                    gaps.update({k: rest / len(others) for k in others})
            elif extra > 0 and spots:
                gaps = {k: extra / len(spots) for k in spots}
        out = []
        for k, (ch, w) in enumerate(chars):
            if len(ch) > 1:
                # 均等割付：1字目を左端、最後の字を項目の右端に置き、字の間を均等に空ける（Word と同じ）
                adv = [self.advance(c) for c in ch]
                gap = (w - sum(adv)) / (len(ch) - 1)
                cx = x
                for c, a in zip(ch, adv):
                    out.append((c, cx))
                    cx += a + gap
            else:
                out.append((ch, x))
            x += w + gaps.get(k, 0.0)
        return out

    # ---------- 文書 ----------

    def layout(self, paras):
        """段落のリストを組み、Line のリストを返す。表は self.tables に TablePiece のリストとして入れる。

        目次（[TOC]）があれば、目次の長さで見出しのページが変わるので、見出しのページが定まるまで組み直す。
        """
        pages = None
        for _ in range(TOC_MAX_PASSES):
            out = self._layout(paras, pages)
            levels = max((p.level for p in paras if p.kind == TOC), default=0)
            if not levels:
                break
            found = {pi: self.para_rows[pi] // self.lines_page + 1 for pi, _ in toc_entries(paras, levels)}
            if found == pages:
                break
            pages = found
        self._mark_inline(paras, out)
        return out

    def _mark_inline(self, paras, lines):
        """太字（**文字**）・蛍光ペン（==文字==）・傍点（*文字*）の字に印を付ける。字の位置は変えない（ＭＳ ゴシックも、
        字の幅はＭＳ 明朝と同じ。傍点の黒丸は行の間に置く）。見出し・段落番号・箇条書きの本文がすべて太字（蛍光ペン）
        なら、番号（記号）も太字（蛍光ペン）にする（2026-10-24 班長指示）。傍点は番号には付けない。"""
        def whole(p, marked):
            return bool(marked) and all(k in marked for k, ch in enumerate(p.text) if not ch.isspace())
        for ln in lines:
            p = paras[ln.para_index] if 0 <= ln.para_index < len(paras) else None
            if p is None or not (p.bold or p.highlight or p.dots):
                continue
            bold_all, mark_all = whole(p, p.bold), whole(p, p.highlight)
            for g in ln.glyphs:
                if g.is_number:
                    g.bold, g.highlight = bold_all, mark_all
                else:
                    k = g.index - len(p.number)
                    g.bold, g.highlight, g.dot = k in p.bold, k in p.highlight, k in p.dots
        for piece in self.tables:
            t = paras[piece.para_index].table
            for g in piece.glyphs:
                g.bold = g.index in t.bold.get((g.row, g.col), ())
                g.highlight = g.index in t.highlight.get((g.row, g.col), ())
                g.dot = g.index in t.dots.get((g.row, g.col), ())

    def _layout(self, paras, toc_pages):
        # 最初の階層：見出しを順に読み、より浅い見出しが出たら、そこから基準を変える（VA公用文の xFirst）
        self.first_level = None
        self.tables = []
        self.para_rows = {}     # 段落 → 始まる行（通しの行の番号。空の行・表も含む。確認表示とエディターの連動に使う）
        self.blank_rows = []    # 空の段落の行（通しの行の番号。行番号を数えるのに使う）
        # セクションごとの、始まるページとヘッダー・フッターの段落
        sections = [{"start": 1, HEADER: [], FOOTER: []}]
        out = []
        row = 0
        for pi, p in enumerate(paras):
            self.para_rows[pi] = row
            if p.area:
                sections[-1][p.area].append(pi)     # 本文の行は使わない（_layout_areas で組む）
                continue
            if p.kind == TABLE:
                row = self.layout_table(p, row, pi)
                continue
            if p.kind == TOC:
                for hi, h in toc_entries(paras, p.level):
                    page = (toc_pages or {}).get(hi, 0)
                    level, number, _, _ = heading_label(paras, hi)
                    row = self.layout_toc_entry(out, pi, h, page, row, level, number)
                continue
            if p.kind in (PAGE_BREAK, SECTION_BREAK):
                if row % self.lines_page:
                    row += self.lines_page - row % self.lines_page
                if p.kind == SECTION_BREAK:
                    self.first_level = None
                    sections.append({"start": row // self.lines_page + 1, HEADER: [], FOOTER: []})
                continue
            if p.kind == BLANK or not (p.number or p.text):
                # 空の行・中身のない配置の行（--: だけの行など）は、Word の空の段落と同じく1行使う
                self.blank_rows.append(row)
                row += 1
                continue
            if p.kind == HEADING and (self.first_level is None or p.level < self.first_level):
                self.first_level = p.level
            if p.composite:
                continue            # 複合見出し：次の見出しと1行にまとめる
            number, merged, outer, squeeze = p.number, 0, p, ()
            if p.kind == HEADING:
                _, number, merged, outer = heading_label(paras, pi)
                squeeze = squeezed_numbers(paras, pi)
            left, first, right = self.indents(outer)
            # 複合見出しは外側の見出しの位置から書き出し、折り返した行は、まとめた段の数だけ右から始める
            left, first = left + merged * self.pitch, first - merged * self.pitch
            shift = len(number)
            items = self.make_items(number + p.text, [(a + shift, b + shift, n) for a, b, n in p.distribute],
                                    self.text_w - right - left - max(first, 0.0))
            for a, b in squeeze:
                items[a:b] = self.squeeze_items(number[a:b])
            num_left = len(number)
            offset = len(p.number) - len(number)      # 字の番号は、この見出しの番号の1字目を 0 とする（前の番号は負）
            for start_x, chars, hang, last, trail in self.break_lines(items, left, first, right):
                num_here = min(num_left, len(chars))
                placed = self.place_line(p.align, start_x, chars, hang, last, trail, num_here, right)
                glyphs = [Glyph(ch, x, k < num_here, offset + k) for k, (ch, x) in enumerate(placed)]
                self.place_number_glyphs(glyphs[:num_here], chars)
                out.append(Line(row // self.lines_page + 1, row % self.lines_page, glyphs, pi))
                offset += sum(len(ch) for ch, _ in chars)
                num_left -= num_here
                row += 1
        self._layout_areas(paras, out, sections)
        return out

    # ---------- ヘッダー・フッター（[HEADER] [FOOTER]。2026-10-25 班長指示） ----------

    def _layout_areas(self, paras, out, sections):
        """ヘッダー・フッターの段落を組み、行（Line.area・Line.y）として out に足す。ヘッダーはセクションの最初のページ
        （文書の最初のページ、セクション区切りの直後のページ）だけ、フッターはセクションの全ページに出す（「別紙」
        「付紙」などをヘッダーに書く使い方のため。2026-10-25 班長指示）。本文の行は使わない。内容証明では組まない
        （VA内容証明郵便がヘッダー・フッターを消すのと同じ）。"""
        self.page_number_shift, self.warnings = {}, []
        if not any(s[HEADER] or s[FOOTER] for s in sections):
            return
        if self.dt.key == _NAIYOU:
            self.warnings.append("内容証明には、ヘッダー・フッターを付けません（[HEADER]・[FOOTER] の行は組みません）。")
            return
        pages = max([ln.page for ln in out] + [piece.page for piece in self.tables] + [1])
        for si, s in enumerate(sections):
            last = sections[si + 1]["start"] - 1 if si + 1 < len(sections) else pages
            for area in (HEADER, FOOTER):
                laid = [(pi, glyphs) for pi in s[area] for glyphs in self._area_lines(paras[pi])]
                end = s["start"] if area == HEADER else last
                if not laid or last < s["start"]:
                    continue
                pn_y, ys, over = self.area_baselines(area, len(laid))
                if over:
                    where = f"{s['start']} ページ" if end == s["start"] else f"{s['start']}〜{end} ページ"
                    name = "ヘッダーが上" if area == HEADER else "フッターが下"
                    self.warnings.append(f"{name}の余白に入りきらず、本文に重なっています（{where}）。行を減らしてください。")
                for page in range(s["start"], end + 1):
                    if pn_y is not None:
                        self.page_number_shift[page] = pn_y - self._page_number_y(area)
                    for (pi, glyphs), y in zip(laid, ys):
                        out.append(Line(page, -1, [replace(g) for g in glyphs], pi, area, y))

    def _area_lines(self, p):
        """ヘッダー・フッターの段落を、本文の幅で組んだ行（[Glyph] のリスト）。字のない段落も1行使う。"""
        if not p.text:
            return [[]]
        left, first, right = self.indents(p)
        items = self.make_items(p.text, p.distribute, self.text_w - right - left - max(first, 0.0))
        out, offset = [], 0
        for start_x, chars, hang, last, trail in self.break_lines(items, left, first, right):
            placed = self.place_line(p.align, start_x, chars, hang, last, trail, 0, right)
            out.append([Glyph(ch, x, False, offset + k) for k, (ch, x) in enumerate(placed)])
            offset += sum(len(ch) for ch, _ in chars)
        return out

    def _page_number_y(self, area):
        """ヘッダー（フッター）の側のページ番号の基準線（用紙の上端から。ずらす前）。右上は要確認（仕様.md の6.4）。"""
        if area == HEADER:
            return HEADER_DISTANCE + FONT_SIZE * 220 / 256
        return PAGE_H - FOOTER_DISTANCE - FOOTER_BASELINE_OFFSET

    def page_number_baseline(self, page, style):
        """ページ番号の基準線（用紙の上端から）。ヘッダー・フッターが余白に入りきらず、ずらしたときは、ずらした位置。"""
        return self._page_number_y(HEADER if style == PAGE_NUMBER_TOP_RIGHT else FOOTER) + self.page_number_shift.get(page, 0.0)

    def area_baselines(self, area, n):
        """ヘッダー（area が HEADER）・フッターの n 行の位置。(同じ側のページ番号の基準線〔なければ None〕,
        [各行の基準線], 本文に重なるか) を返す（基準線は用紙の上端から）。

        ヘッダーはページ番号の直下から、フッターはページ番号の直上まで、HF_LINE_PITCH おきに積む。同じ側にページ番号が
        なければ、ページ番号の位置から書き出す（ヘッダー）・ページ番号の位置で終える（フッター）。行が本文の範囲（上下の
        余白の内側）にかかるときは、本文を動かさず、ページ番号ごと用紙の端の側へずらす（端から HF_EDGE_MIN まで）。
        それでも入らなければ、本文に重なるとして知らせる（2026-10-25 班長決定）。
        """
        b0 = self._page_number_y(area)
        if area == HEADER:
            has_pn = self.page_number == PAGE_NUMBER_TOP_RIGHT
            ys = [b0 + (k + has_pn) * HF_LINE_PITCH for k in range(n)]
            over = ys[-1] + HF_BELOW - self.margin_top
            room = b0 - HF_ABOVE - HF_EDGE_MIN
            shift = -min(max(over, 0.0), room)
        else:
            has_pn = self.page_number in _FOOTER_PAGE_NUMBERS
            ys = [b0 - (n - k - (0 if has_pn else 1)) * HF_LINE_PITCH for k in range(n)]
            over = self.margin_top + self.lines_page * self.line_pitch - (ys[0] - HF_ABOVE)
            room = PAGE_H - HF_EDGE_MIN - (b0 + HF_BELOW)
            shift = min(max(over, 0.0), room)
        return (b0 + shift if has_pn else None), [y + shift for y in ys], over > room + 0.01

    def line_baseline(self, ln):
        """行の字の基準線（用紙の上端から）。ヘッダー・フッターの行も。"""
        return ln.y if ln.area else self.baseline(ln.row)

    def line_box(self, ln):
        """行の (上端, 高さ)（用紙の上端から。確認表示とエディターの連動に使う）。"""
        if ln.area:
            return ln.y - HF_ABOVE, HF_LINE_PITCH
        return self.margin_top + ln.row * self.line_pitch, self.line_pitch

    # ---------- 目次（[TOC]。2026-10-24 班長指示） ----------

    def layout_toc_entry(self, out, pi, h, page, row, level=None, number=None):
        """目次の1項目（見出し h）を組み、次の行を返す。VA公用文で整えた文書に Word の「自動作成の目次 1」を
        入れたものに合わせる（2026-10-24、別の Word で読み取った値）：
        ・左インデントは、第１の段 0 字、１の段 1 字、(1) の段 2 字。
        ・折り返した行は、本文の見出しと同じく1字ぶら下げ（1行目の書き出しより1字右から始める）。ここだけは VA公用文
          （Word の目次。ぶら下げなし）と違う（2026-10-24 班長決定）。
        ・折り返した行の1行目も両端揃えにしない（Word の目次は両端揃え。2026-10-24 班長決定）。
        ・番号と見出しの間は半角の空白（本文の見出しの全角の空白ではない）。
        ・見出しの後から、右揃えのタブ（本文の右端より TOC_TAB_FROM_RIGHT 左）まで点線を引き、ページ番号を右にそろえる。
        """
        level = h.level if level is None else level                 # 複合見出しは外側の段と、まとめた番号
        number = h.number if number is None else number
        left = (level - 1) * self.pitch
        prefix = number.rstrip(" 　") + (" " if number.strip() else "")
        text = prefix + h.text
        items = [(ch, self.advance(ch)) for ch in text]
        tab_x = self.text_w - TOC_TAB_FROM_RIGHT
        number = str(page) if page else "0"
        num_w = sum(self.advance(ch) for ch in number)
        broken = self.break_lines(items, left + TOC_HANG * self.pitch, -TOC_HANG * self.pitch, 0) or [(left, [], False, True, 0)]
        offset = 0
        for k, (start_x, chars, hang, last, trail) in enumerate(broken):
            # 折り返した行も両端揃えにせず、格子どおり左から並べる（Word の目次は両端揃えで、1行目の字の間隔が
            # 2行目と違って上下の字がずれる。2026-10-24 班長決定）
            is_last = k == len(broken) - 1
            placed = self.place_line("left", start_x, chars, False, is_last, trail, 0, 0)
            glyphs = [Glyph(ch, x, False, offset + j) for j, (ch, x) in enumerate(placed)]
            offset += len(chars)
            if is_last:
                end = (placed[-1][1] + self.advance(placed[-1][0])) if placed else start_x
                if end + TOC_MIN_LEADER + num_w > tab_x:
                    # 見出しが右端まで来たときは、点線とページ番号を次の行に置く
                    out.append(Line(row // self.lines_page + 1, row % self.lines_page, glyphs, pi))
                    row += 1
                    glyphs, end = [], left + TOC_HANG * self.pitch
                glyphs += self._toc_leader(end, tab_x - num_w)
                x = tab_x - num_w
                for ch in number:
                    glyphs.append(Glyph(ch, x, True, -1))
                    x += self.advance(ch)
            out.append(Line(row // self.lines_page + 1, row % self.lines_page, glyphs, pi))
            row += 1
        return row

    def _toc_leader(self, start, end):
        """目次の点線。Word と同じく「.」の字を、用紙の左端から TOC_DOT_STEP おきの決まった位置（どの行でも縦に
        そろう）に、見出しの最後の字が終わる位置より右のますから、ページ番号の手前のますまで並べる（2026-10-24、
        班長が VA公用文で作った目次入りの PDF で読み取った）。start・end は本文の左端からの位置。"""
        step = TOC_DOT_STEP
        first = math.ceil((self.margin_left + start) / step - 1e-9)
        last = math.floor((self.margin_left + end) / step + 1e-9) - 1
        return [Glyph(".", k * step - self.margin_left, True, -1) for k in range(first, last + 1)]

    # ---------- 表（仕様.md の5.3） ----------

    def table_left(self, p):
        """表の左端（本文の左端から）。直前の見出しに属する本文の左インデント（本文の2行目以降の位置）。"""
        if not p.body_level or self.first_level is None:
            return 0.0
        x = p.body_level - 1
        return (self.dt.text_left[x] + self.dt.left_add * (p.body_level - self.first_level)) * self.pitch

    def longest_unbreakable(self, text, spans=(), limit=None):
        """折り返せない最も長い字の並び（英数字の語・行頭禁則でつながる字・均等割付の字など）の幅。"""
        items = self.make_items(text, spans, limit)
        best = cur = 0.0
        for k, (ch, w) in enumerate(items):
            if k and (self.breakable(items, k) and ch not in NO_START and items[k - 1][0] not in NO_END):
                cur = 0.0
            cur += w
            best = max(best, cur)
        return best

    def column_widths(self, table, width):
        """列の幅。表の幅を width（本文の右端まで）にする（ブラウザの表の列の幅と同じ考え方）。

        各列の「最小の幅」は折り返せない最も長い字の並びが収まる幅、「最大の幅」は折り返さずに収まる幅。
        全体が収まるときは、最大の幅に比べて余りを足す。収まらないときは、短い列から順に、最大の幅が
        「残りの幅を残りの列で等分した幅」以下の列に最大の幅を与え（折り返さない）、残った幅を長い列に、
        最大の幅に比べて配る（長い説明の列だけが折り返す）。長い列も最小の幅より狭くはしない。
        """
        rows = [table.header] + table.rows
        n = len(table.header)
        pad = 2 * CELL_PAD_X
        floor = self.pitch + pad
        spans = table.distribute
        limit = width - pad         # 割り付ける幅は、表の幅より広くしない
        maxw = [max(max(sum(w for _, w in self.make_items(r[k][1], spans.get((ri, k), ()), limit))
                        for ri, r in enumerate(rows)) + pad, floor) for k in range(n)]
        minw = [max(max(self.longest_unbreakable(r[k][1], spans.get((ri, k), ()), limit)
                        for ri, r in enumerate(rows)) + pad, floor) for k in range(n)]
        if sum(maxw) <= width:
            total = sum(maxw)
            return [w + (width - total) * w / total for w in maxw]
        if sum(minw) >= width:
            # 最小の幅も収まらないときは、最小の幅に比べて縮める（語の途中で折り返す）
            total = sum(minw)
            return [w * width / total for w in minw]
        widths = [None] * n
        rest, open_cols = width, list(range(n))
        changed = True
        while changed and open_cols:
            changed = False
            share = rest / len(open_cols)
            for k in sorted(open_cols, key=lambda k: maxw[k]):
                if maxw[k] <= share:
                    widths[k] = maxw[k]
                    rest -= maxw[k]
                    open_cols.remove(k)
                    changed = True
                    break
        # 残りの長い列に、最大の幅に比べて配る（最小の幅は確保する）
        total = sum(maxw[k] for k in open_cols)
        for k in open_cols:
            widths[k] = maxw[k] * rest / total
        short = [k for k in open_cols if widths[k] < minw[k]]
        if short:
            fixed = sum(minw[k] for k in short)
            others = [k for k in open_cols if k not in short]
            total = sum(maxw[k] for k in others)
            for k in short:
                widths[k] = minw[k]
            for k in others:
                widths[k] = maxw[k] * (rest - fixed) / total
        return widths

    def layout_cell(self, align, text, width, spans=()):
        """セルの中を組み、[(行の番号, [(字, x)])] を返す。x はセルの中の左端から。spans は均等割付の範囲。"""
        inner = width - 2 * CELL_PAD_X
        items = self.make_items(text, spans, inner)
        out = []
        if not items:
            return out
        cell_align = {"left": "justify", CENTER: CENTER, RIGHT: RIGHT}.get(align, "justify")
        for k, (start_x, chars, hang, last, trail) in enumerate(self.break_lines(items, 0, 0, 0, inner, False)):
            out.append((k, self.place_line(cell_align, start_x, chars, hang, last, trail, 0, 0, inner)))
        return out

    def layout_table(self, p, row, para_index=-1):
        """表を組んで self.tables に入れ、表の次の本文が始まる行（通しの行の番号）を返す。

        表は格子に合わせず、行の高さはセルの中の行数で決める。ページの下に入りきらない行は次のページへ送る
        （見出しの行は繰り返さない）。表の次の本文は、表の下の端より後の、最初の格子の行から始める。
        """
        t = p.table
        left = self.table_left(p)
        widths = self.column_widths(t, self.text_w - left)
        col_x = [left]
        for w in widths:
            col_x.append(col_x[-1] + w)
        page_top = self.margin_top
        page_bottom = self.margin_top + self.lines_page * self.line_pitch
        page = row // self.lines_page + 1
        y = page_top + (row % self.lines_page) * self.line_pitch
        piece = TablePiece(page, col_x, para_index=para_index)
        self.tables.append(piece)
        for ri, cells in enumerate([t.header] + t.rows):
            is_header = ri == 0
            laid = [self.layout_cell(a, s, widths[k], t.distribute.get((ri, k), ())) for k, (a, s) in enumerate(cells)]
            n_lines = max([len(c) for c in laid] + [1])
            extra = DOT_ROW_EXTRA if any((ri, k) in t.dots for k in range(len(cells))) else 0
            height = (n_lines * CELL_LINE_PITCH + 2 * CELL_PAD_Y + extra
                      + (DOUBLE_RULE_GAP if is_header and t.double_rule else 0))
            if y + height > page_bottom + 0.01 and y > page_top + 0.01:
                # 次のページへ送る（ページの上から始まる行は、入りきらなくても送らない）
                page += 1
                y = page_top
                if piece.rows:
                    piece = TablePiece(page, col_x, para_index=para_index)
                    self.tables.append(piece)
                else:
                    piece.page = page
            piece.rows.append(TableRow(y, y + height, is_header and t.double_rule, ri))
            for k, lines in enumerate(laid):
                ci = 0
                for li, placed in lines:
                    base = (y + CELL_PAD_Y + extra + li * CELL_LINE_PITCH + (CELL_LINE_PITCH - FONT_SIZE) / 2
                            + FONT_SIZE * 220 / 256)
                    for ch, x in placed:
                        piece.glyphs.append(TableGlyph(ch, col_x[k] + CELL_PAD_X + x, base, ri, k, ci))
                        ci += 1
            y += height
        # 表の次の本文は、表の下の端より後の、最初の格子の行から
        rows_used = -(-(y - page_top - 0.01) // self.line_pitch)
        return (page - 1) * self.lines_page + int(rows_used)

    def baseline(self, row):
        """その行の字の基準線の、用紙の上端からの位置（ポイント）。

        Word は、行の高さの真ん中に字の高さ（ＭＳ 明朝は上端から下端まで 1em、うち上端から基準線まで
        220/256 em）を置く（2026-10-23、VA公用文の PDF と 0.17pt 以内で一致）。
        """
        return self.margin_top + row * self.line_pitch + (self.line_pitch - FONT_SIZE) / 2 + FONT_SIZE * 220 / 256
