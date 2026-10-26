"""貼り付けた文章の整形（VA公用文 clsPreFormatter.ExecuteSimpleCleanup と同じことをする。仕様.md の5.1）。

外部のツール（AI のチャット画面、Obsidian など）が付ける、VA Documentのマークダウンにない要素を取り除く。
・コードブロックの記号（```）の行（AI の出力に付く。VA Documentで足したもの）
・先頭のフロントマター（1行目が「---」で、10行以内に閉じの「---」があり、その間が「key: value」か空行だけのもの）
・水平線（「-」「*」「_」の1種類だけが3字以上続く行。間の空白は無視する）
・WikiLink（[[A|B]] → B、[[A]] → A）。マークダウンのリンク（[文字](URL)）は取り除かず、そのまま残す
  （VA公用文も、Word のハイパーリンクは外すが、文字として書かれたマークダウンのリンクは残す〔2026-10-23 確認〕。
  URL に意味があることもあるので、字を消さない側にした）
・対になった強調記号（__x__ → x、_x_。記号の直後が半角空白のものと、「_」で前後が英数字のもの〔file_name〕は除く。
  中に改行を含むものは対象外）。**x** は太字、*x* は傍点の記号なので残す（document.py。2026-10-24 班長指示。
  VA公用文は **x** も *x* も取り除く）
取り除いた数は report に数える（画面で利用者に知らせるため）。
表の行（| で始まる行）は、水平線の判定の対象外とする（表の区切りの行 |---| を消さないため）。
"""
import re
from collections import Counter

_FENCE_RE = re.compile(r"^\s*```")
_WIKI_RE = re.compile(r"\[\[([^\[\]\n]+?)\]\]")
# 長い記号から先に処理する（__ を先に除かないと、_ の対として誤って処理されるため）
_EMPHASIS = [
    (re.compile(r"__([^_\n]+?)__"), 2, True),
    (re.compile(r"_([^_\n]+?)_"), 1, True),
]


def is_horizontal_rule(line):
    s = re.sub(r"[ 　\t]", "", line)
    return len(s) >= 3 and s[0] in "-*_" and s == s[0] * len(s)


def front_matter_end(lines):
    """先頭がフロントマターなら、閉じの「---」の行の番号（0 から）を返す。そうでなければ -1。"""
    if len(lines) < 2 or lines[0].strip() != "---":
        return -1
    for i in range(1, min(len(lines), 11)):
        s = lines[i].strip()
        if s == "---":
            return i
        if s and ":" not in s:
            return -1
    return -1


def _is_alnum(ch):
    return ch.isascii() and ch.isalnum()


def _remove_emphasis(text, report):
    for pattern, mark_len, check_alnum in _EMPHASIS:
        out, pos = [], 0
        for m in pattern.finditer(text):
            inner = m.group(1)
            skip = inner.startswith(" ")
            if not skip and check_alnum:
                before = text[m.start() - 1] if m.start() > 0 else ""
                after = text[m.end()] if m.end() < len(text) else ""
                skip = _is_alnum(before) or _is_alnum(after)
            if skip:
                continue
            out.append(text[pos:m.start()])
            out.append(inner)
            pos = m.end()
            report["強調記号"] += 1
        out.append(text[pos:])
        text = "".join(out)
    return text


def clean(text):
    """文章を整形し、(整形した文章, 取り除いた要素の数 Counter) を返す。"""
    lines, _, report = clean_lines(text)
    return "\n".join(lines), report


def clean_lines(text):
    """文章を整形し、(整形した行のリスト, 元の位置, 取り除いた要素の数) を返す。

    元の位置は、整形した行ごとの (元の行の番号, [整形した行の各字の、元の行での位置 ＋ 行末]) で、確認表示と
    エディターを連動させるために使う（2026-10-23）。行を消す整形（コードブロックの記号・フロントマター・水平線）
    は行ごと除き、行の中の整形（WikiLink・強調記号）は字を消すだけなので、残った字は元の行の字を順に拾える。
    """
    report = Counter()
    raw = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u2028", "\n").replace("\v", "\n").split("\n")
    lines = list(enumerate(raw))
    # コードブロックの記号の行
    kept = [(n, l) for n, l in lines if not _FENCE_RE.match(l)]
    report["コードブロックの記号"] += len(lines) - len(kept)
    lines = kept
    # フロントマター
    end = front_matter_end([l for _, l in lines])
    if end >= 0:
        lines = lines[end + 1:]
        report["フロントマター"] += 1
    # 水平線（表の行は除く）
    kept = [(n, l) for n, l in lines if l.lstrip().startswith("|") or not is_horizontal_rule(l)]
    report["水平線"] += len(lines) - len(kept)
    out, origins = [], []
    for n, line in kept:
        # WikiLink（[[A|B]] → B）と強調記号は、行の中で整形する（どちらも行をまたがない）
        def wiki(m):
            report["WikiLink"] += 1
            inner = m.group(1)
            return inner.split("|", 1)[1] if "|" in inner else inner
        cleaned = _remove_emphasis(_WIKI_RE.sub(wiki, line), report)
        out.append(cleaned)
        origins.append((n, _char_map(line, cleaned)))
    return out, origins, +report


def _char_map(original, cleaned):
    """整形した行の各字が、元の行の何字目か（字を消しただけなので、元の行を前から順に拾う）。末尾に行末を足す。"""
    cols, j = [], 0
    for ch in cleaned:
        while j < len(original) and original[j] != ch:
            j += 1
        cols.append(min(j, len(original)))
        j += 1
    cols.append(len(original))
    return cols
