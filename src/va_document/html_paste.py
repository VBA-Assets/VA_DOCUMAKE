"""Word・ブラウザーの書式付きの字の貼り付け（Ctrl+V。太字・傍点・蛍光ペン・段落とセルの配置を記号にする。2026-10-31 班長決定）。

字は、クリップボードのプレーンな字（Ctrl+V でこれまで貼っていた字）だけから取り、HTML（CF_HTML）は、どの字に書式が
あるかを知るためだけに使う。HTML の字とプレーンな字を突き合わせ、合わなければ書式を諦める（None を返す。呼ぶ側は
これまでどおり字を貼る）。これで、隠し文字などの HTML にだけある字が入ることも、利用者の字が変わることもない。
HTML はメモリの中で読むだけで、どこにも残さない。クリップボードは、利用者が Ctrl+V を押したときだけ読む。
仮名化する語は、記号を付ける前に語の単位で記号に置き換える（語の途中で書式が変わっても、語を見逃さない）。

見出し・箇条書き・段落番号は記号にしない（Word の番号の字は、プレーンな字のまま残る）。ブラウザーの見出しと表の見出しの
セルは、ほぼすべてが太字で見分ける役に立たないので、太字にもしない。Excel の HTML は読まない。
"""
import ctypes
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser

from .document import split_inline_full

BOLD, DOTS, HIGHLIGHT = 1, 2, 4
_SPACES = " \t\r\n\xa0"
_ALIGN_MARKS = {"center": ":-: ", "right": "--: "}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BLOCKS = {"p"} | _HEADINGS
_BROWSER_BLOCKS = _BLOCKS | {"address", "article", "aside", "blockquote", "dd", "details", "div", "dl", "dt", "figcaption",
                             "figure", "footer", "header", "li", "main", "nav", "ol", "pre", "section", "summary", "ul"}
_VOID = {"br", "img", "hr", "meta", "link"}
_FONT_WEIGHT_RE = re.compile(r"(?<![-\w])font-weight:\s*([\w]+)")
_EMPHASIS_RE = re.compile(r"(?<![-\w])(?:font-emphasize|text-emphasis(?:-style)?):\s*([\w]+)")
_HIGHLIGHT_RE = re.compile(r"(?<![-\w])mso-highlight:\s*([\w]+)")
_TEXT_ALIGN_RE = re.compile(r"(?<![-\w])text-align:\s*(\w+)")
_FRAGMENT_RE = re.compile(rb"StartFragment:(\d+).*?EndFragment:(\d+)", re.S)


def read_html():
    """クリップボードの HTML（CF_HTML のバイト列）。なければ None。Windows だけ。"""
    if sys.platform != "win32":
        return None
    user32, kernel32 = ctypes.WinDLL("user32"), ctypes.WinDLL("kernel32")
    user32.RegisterClipboardFormatW.argtypes = [ctypes.c_wchar_p]
    user32.RegisterClipboardFormatW.restype = ctypes.c_uint
    user32.IsClipboardFormatAvailable.argtypes = [ctypes.c_uint]
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.GetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    fmt = user32.RegisterClipboardFormatW("HTML Format")
    if not fmt or not user32.IsClipboardFormatAvailable(fmt) or not user32.OpenClipboard(None):
        return None
    try:
        handle = user32.GetClipboardData(fmt)
        pointer = kernel32.GlobalLock(handle) if handle else None
        if not pointer:
            return None
        try:
            return ctypes.string_at(pointer, kernel32.GlobalSize(handle))
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def fragment(data):
    """CF_HTML のバイト列から (選んだ部分の HTML, ブラウザーのものか) を返す。Word・ブラウザーのものでなければ None。
    ブラウザーは、コピーしたページの SourceURL で見分ける（Excel もファイルの SourceURL を持つので、Office の宣言で除く）。"""
    m = _FRAGMENT_RE.search(data[:300])
    if not m:
        return None
    head = data[:int(m.group(1))]
    word = b"office:word" in head
    if not word and (b"SourceURL:" not in head or b"schemas-microsoft-com:office" in head):
        return None
    try:
        return data[int(m.group(1)):int(m.group(2))].decode("utf-8"), not word
    except UnicodeDecodeError:
        return None


@dataclass
class _Lines:
    """HTML の行（段落・セル）。chars は空白を除いた [(字, 書式)]。"""
    chars: list
    align: str = ""


@dataclass
class _Table:
    rows: list = field(default_factory=list)         # 行 → セル → [_Lines]


class _Unsupported(Exception):
    """記号にできない HTML（入れ子の表・結合したセルなど）。"""


class _Html(HTMLParser):
    """Word・ブラウザーの HTML を、段落（_Lines）と表（_Table）の並びにする。"""

    def __init__(self, browser=False):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self._browser = browser
        self._block_tags = _BROWSER_BLOCKS if browser else _BLOCKS
        self._stack = []            # 開いている要素 [(名前, 足す書式, 消す書式, 字を読まないか, 配置)]
        self._chars = []
        self._in_block = False
        self._table = None
        self._cell = None

    def _flags(self):
        flags = 0
        plain_bold = False
        for tag, add, clear, _ignore, _align in self._stack:
            flags = (flags | add) & ~clear
            plain_bold = plain_bold or tag in _HEADINGS or tag == "th"
        return flags & ~BOLD if self._browser and plain_bold else flags

    def _align_now(self):
        """今の字の配置（要素の入れ子の中で、いちばん内側の指定）。"""
        return next((s[4] for s in reversed(self._stack) if s[4]), "")

    def _flush(self):
        """今の行を閉じる。"""
        line = _Lines(self._chars, self._align_now())
        self._chars = []
        if not line.chars and (self._browser or not self._in_block):     # ブラウザーの空の要素は、行にならない
            return
        (self._cell if self._cell is not None else self.blocks).append(line)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        style = (a.get("style") or "").lower()
        if tag == "table":
            if self._table is not None:
                raise _Unsupported
            self._flush()
            self._table = _Table()
        elif tag == "tr":
            if self._table is None:
                raise _Unsupported
            self._table.rows.append([])
        elif tag in ("td", "th"):
            if self._table is None or not self._table.rows or a.get("colspan", "1") != "1" or a.get("rowspan", "1") != "1":
                raise _Unsupported
            self._cell = []
            self._table.rows[-1].append(self._cell)
        elif tag in self._block_tags:
            self._flush()
            self._in_block = True
        elif tag == "br":
            in_block, self._in_block = self._in_block, True
            self._flush()
            self._in_block = in_block
        if tag in _VOID:
            return
        add, clear = 0, 0
        if tag in ("b", "strong"):
            add |= BOLD
        m = _FONT_WEIGHT_RE.search(style)
        if m:
            weight = m.group(1)
            if weight in ("normal", "lighter") or (weight.isdigit() and int(weight) < 600):
                clear |= BOLD
            else:
                add |= BOLD
        m = _EMPHASIS_RE.search(style)
        if m and m.group(1) not in ("none", "initial", "unset", "inherit"):
            add |= DOTS
        m = _HIGHLIGHT_RE.search(style)
        if tag == "mark" or (m and m.group(1) != "none"):
            add |= HIGHLIGHT
        m = _TEXT_ALIGN_RE.search(style)
        align = (m.group(1) if m else ("" if tag == "table" else a.get("align") or "")).lower()
        self._stack.append((tag, add, clear, "mso-list:ignore" in style.replace(" ", ""), align))

    def handle_endtag(self, tag):
        if tag in self._block_tags:
            self._flush()
            self._in_block = False
        elif tag in ("td", "th"):
            self._flush()
            self._cell = None
        elif tag == "table":
            self.blocks.append(self._table)
            self._table = None
        for k in range(len(self._stack) - 1, -1, -1):
            if self._stack[k][0] == tag:
                del self._stack[k:]
                break

    def handle_data(self, data):
        if any(s[3] for s in self._stack):
            return                  # Word の番号の字（プレーンな字に、番号が入っている）
        flags = self._flags()
        self._chars += [(c, flags) for c in data if c not in _SPACES]

    def finish(self):
        self.close()
        self._flush()
        return self.blocks


def _overlay(line, plain):
    """プレーンな字の1行に、HTML の行の書式を重ねる。字ごとの書式のリストを返す。合わなければ None。"""
    where = [k for k, c in enumerate(plain) if c not in _SPACES]
    skip = len(where) - len(line.chars)
    # プレーンな字にだけある字は、Word の番号（「1.」とタブ）だけを認める
    if skip < 0 or (skip and "\t" not in plain[:where[skip]]):
        return None
    flags = [0] * len(plain)
    for (c, f), k in zip(line.chars, where[skip:]):
        if plain[k] != c:
            return None
        flags[k] = f
    for k, c in enumerate(plain):       # 間の空白は、前後の字が同じ書式のときだけ含める（端の空白を記号の内側に入れない）
        if c in _SPACES or c == "　":
            before = next((flags[j] for j in range(k - 1, -1, -1) if plain[j] not in _SPACES + "　"), 0)
            after = next((flags[j] for j in range(k + 1, len(plain)) if plain[j] not in _SPACES + "　"), 0)
            flags[k] = before if before == after else 0
    return flags


def _wrap(text, flags):
    stars = ("**" if flags & BOLD else "") + ("*" if flags & DOTS else "")
    high = "==" if flags & HIGHLIGHT else ""
    return stars + high + text + high + stars


def _marked(plain, flags, dictionary):
    """(記号の付いた字, 書式があるか) を返す。仮名化する語は、語の最初の字の書式で、語全体を記号に置き換える。記号を読み
    直して字が元に戻らなければ（字の中の * などと重なるとき）、書式を付けない。"""
    units, pos = [], 0
    for a, b, entry in dictionary.spans(plain):
        units += list(zip(plain[pos:a], flags[pos:a]))
        units.append((entry.token, flags[a]))
        pos = b
    units += list(zip(plain[pos:], flags[pos:]))
    text = "".join(u for u, _ in units)
    if not any(f for _, f in units):
        return text, False
    out, run, current = [], [], 0
    for unit, f in units:
        if f != current:
            out.append(_wrap("".join(run), current) if run else "")
            run, current = [], f
        run.append(unit)
    out.append(_wrap("".join(run), current))
    line = "".join(out)
    return (line, True) if split_inline_full(line).plain == text else (text, False)


def _paragraph(line, plain, dictionary, align):
    flags = _overlay(line, plain)
    if flags is None:
        raise _Unsupported
    text, marked = _marked(plain, flags, dictionary)
    mark = _ALIGN_MARKS.get(line.align, "") if align and text else ""
    return mark + text, marked or bool(mark)


def _table_lines(table, plain_rows, dictionary):
    """表をマークダウンの行にする。(行のリスト, 書式があるか)。"""
    columns = len(table.rows[0])
    out, formatted = [], False
    for row, plain in zip(table.rows, plain_rows):
        cells = plain.split("\t")
        if len(row) != columns or len(cells) != columns or any(len(c) > 1 for c in row):
            raise _Unsupported
        texts = []
        for cell, text in zip(row, cells):
            line = cell[0] if cell else _Lines([])
            body, marked = _paragraph(line, text, dictionary, False)
            mark = _ALIGN_MARKS.get(line.align, "")
            formatted = formatted or marked or bool(mark and body)
            texts.append((mark if body else "") + body.replace("|", "\\|"))
        out.append("| " + " | ".join(texts) + " |")
    return [out[0], "|" + "---|" * columns] + out[1:], formatted


def _word_lines(blocks, lines, dictionary, first_align):
    """Word の HTML は、段落とプレーンな字の行が1対1になる。(行のリスト, 書式があるか, 読んだ行数)。"""
    while blocks and isinstance(blocks[-1], _Lines) and not blocks[-1].chars:
        blocks.pop()
    out, formatted, n = [], False, 0
    for block in blocks:
        if isinstance(block, _Table):
            if not block.rows:
                raise _Unsupported
            rows, marked = _table_lines(block, lines[n:n + len(block.rows)], dictionary)
            n += len(block.rows)
        else:
            if n >= len(lines):
                raise _Unsupported
            text, marked = _paragraph(block, lines[n], dictionary, first_align or n > 0)
            rows = [text]
            n += 1
        out += rows
        formatted = formatted or marked
    return out, formatted, n


def _browser_lines(blocks, lines, dictionary, first_align):
    """ブラウザーの HTML は、段落とプレーンな字の行が1対1にならない（段落の間の空の行、pre の中の改行など）。続く段落の字を
    まとめて、プレーンな字の行に先頭から割り当てる。空の行はプレーンな字のまま残す。"""
    out, formatted, n = [], False, 0

    def flow(run):
        nonlocal formatted, n
        chars, aligns = [], {}
        for line in run:
            aligns[len(chars)] = line.align
            chars += line.chars
        pos = 0
        while pos < len(chars):
            if n >= len(lines):
                raise _Unsupported
            plain = lines[n]
            count = sum(c not in _SPACES for c in plain)
            if pos + count > len(chars):
                raise _Unsupported
            text, marked = _paragraph(_Lines(chars[pos:pos + count], aligns.get(pos, "") if count else ""),
                                      plain, dictionary, first_align or n > 0)
            out.append(text)
            formatted = formatted or marked
            pos += count
            n += 1

    def blank_lines():
        nonlocal n
        while n < len(lines) and not lines[n].strip():
            out.append("")
            n += 1

    run = []
    for block in blocks:
        if isinstance(block, _Lines):
            run.append(block)
            continue
        flow(run)
        run = []
        blank_lines()
        if not block.rows:
            raise _Unsupported
        rows, marked = _table_lines(block, lines[n:n + len(block.rows)], dictionary)
        n += len(block.rows)
        out += rows
        formatted = formatted or marked
    flow(run)
    blank_lines()
    return out, formatted, n


def convert(data, plain, dictionary, first_align=True):
    """Word・ブラウザーの CF_HTML（data）とプレーンな字（plain）から、記号の付いた行のリストを作る。Word・ブラウザーのもの
    でないとき、書式がないとき、字が突き合わないとき、記号にできないとき（結合したセル、セルの中の改行など）は None。
    first_align が偽なら、1行目に配置の記号を付けない（行の途中に貼るとき）。"""
    found = fragment(data)
    if found is None:
        return None
    html, browser = found
    parser = _Html(browser)
    try:
        parser.feed(html)
        blocks = parser.finish()
        lines = plain.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n").split("\n")
        out, formatted, n = (_browser_lines if browser else _word_lines)(blocks, lines, dictionary, first_align)
    except _Unsupported:
        return None
    if not formatted or n != len(lines) or any(dictionary.spans(line) for line in out):
        return None
    return out
