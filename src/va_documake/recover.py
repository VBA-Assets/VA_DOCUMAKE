"""構文ファイル（記号入り）と PDF（実名入り）を突き合わせて、対応表を作り直す（仕様.md の7）。

・PDF から、本文の範囲（上下の余白の内側）の字を、描いた順に取り出して1本の文字列にする
  （ページ番号は余白にあるので入らない。行の切れ目はつなぐ）。VA DocuMakeは字を文書の順に描く（pdfwriter）。
・構文ファイルの文書を、PDF と同じ並び（見出しの番号＋本文、表はセルの順。配置の記号は除く）の
  1本の文字列にし、記号（〔人名Ａ〕など）は1字の目印（私用領域の字）に置き換える。
・2つを difflib で突き合わせ、目印の字に対応する PDF の字の並びを、その記号の元の語とする。同じ記号が
  何度も出てくるときは、いちばん多く対応した語を採り、食い違いがあれば知らせる。
・求めた語で目印を置き換えた文字列が PDF の文字列と一致すれば、すべての記号が確かに求まっている（exact）。
試作（試作\\recover_map.py）で、同じ版なら短い文書・14ページの文書とも、すべての記号の元の語が求まった。
"""
import difflib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import fitz  # PyMuPDF

from .doctypes import DOC_TYPES
from .document import TABLE, TOC, parse
from .document import heading_label
from .layout import toc_entries
from .layout import Typesetter
from .pdfwriter import read_id
from .pseudonym import TOKEN_RE, Dictionary, normalize_token

_MARK_BASE = 0xE000
_TOC_FILL = "\uF8FF"     # 目次の点線とページ番号の位置（PDF にだけある。一致の確かめでは「点の並び＋数字」とみなす）
_SPACE_RE = re.compile(r"\s+")


class PdfMismatch(ValueError):
    """PDF が、構文ファイルと同じ文書のものではない。"""


@dataclass
class Recovery:
    found: dict = field(default_factory=dict)       # 記号 → 元の語
    conflicts: dict = field(default_factory=dict)   # 記号 → {語: 回数}（違う語が対応した記号）
    missing: list = field(default_factory=list)     # 元の語が求まらなかった記号
    exact: bool = False                             # 求めた語で戻すと、PDF の文章と一字残らず一致したか


def pdf_body_text(path, ts):
    """PDF の本文の範囲の字を、描いた順に1本の文字列にする（空白も残す。名前の中の空白を戻すため）。"""
    top = ts.margin_top
    bottom = ts.margin_top + ts.lines_page * ts.line_pitch
    out = []
    with fitz.open(path) as doc:
        for page in doc:
            for span in page.get_texttrace():
                for ch in span["chars"]:
                    x, y = ch[2]    # 字の左端と基準線（用紙の上端から）
                    # 本文の左端より左（行番号）は除く
                    if top < y <= bottom + 1 and x >= ts.margin_left - 1:
                        out.append(chr(ch[0]))
    return "".join(out)


def vadm_body_text(lines, dt):
    """構文ファイルの文書を、PDF と同じ並びの文字列にする。(文字列, {目印: 記号}) を返す。"""
    marks = {}

    def sub(m):
        tok = normalize_token(m.group(0))
        if tok not in marks:
            marks[tok] = chr(_MARK_BASE + len(marks))
        return marks[tok]
    paras = parse([TOKEN_RE.sub(sub, ln) for ln in lines], dt)
    parts = []
    for p in paras:
        if p.kind == TABLE:
            for row in [p.table.header] + p.table.rows:
                parts.extend(text for _, text in row)
        elif p.kind == TOC:
            # 目次の行（番号＋半角の空白＋見出し。点線とページ番号は PDF にだけあり、突き合わせでは飛ばされる）
            for hi, h in toc_entries(paras, p.level):
                number = heading_label(paras, hi)[1]
                parts.append(number.rstrip(" 　") + (" " if number.strip() else "") + h.text + _TOC_FILL)
        else:
            parts.append(p.number + p.text)
    return "".join(parts), {v: k for k, v in marks.items()}


def recover(vadm_lines, pdf_path, dt):
    """突き合わせて Recovery を返す。"""
    v, mark_to_token = vadm_body_text(vadm_lines, dt)
    p = pdf_body_text(pdf_path, Typesetter(dt))
    sm = difflib.SequenceMatcher(None, v, p, autojunk=False)
    votes = defaultdict(Counter)
    pending = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        seg_v, seg_p = v[i1:i2], p[j1:j2]
        if len(seg_v) == 1 and seg_v in mark_to_token and tag == "replace":
            # 目印だけの区間なら、その区間の PDF の字が元の語
            votes[mark_to_token[seg_v]][seg_p] += 1
        elif any(c in mark_to_token for c in seg_v) and seg_p:
            pending.append((seg_v, seg_p))
    # 目印と文字が混ざった区間・目印が隣り合う区間（版ずれ、「〔その他Ａ〕〔人名Ａ〕」など）は、
    # 求まった記号を語に戻してみて、求まらない目印が1つだけ残り、その前後の字が PDF の区間の前後と
    # 合うときに当てはめる。新しく求まった記号があれば、繰り返す
    progress = True
    while pending and progress:
        progress = False
        rest = []
        for seg_v, seg_p in pending:
            unknown = [k for k, c in enumerate(seg_v) if c in mark_to_token and not votes[mark_to_token[c]]]
            if len(unknown) != 1:
                if unknown:
                    rest.append((seg_v, seg_p))
                continue
            k = unknown[0]

            def expand(s):
                return "".join(votes[mark_to_token[c]].most_common(1)[0][0] if c in mark_to_token else c for c in s)
            before, after = expand(seg_v[:k]), expand(seg_v[k + 1:])
            if seg_p.startswith(before) and seg_p.endswith(after) and len(seg_p) > len(before) + len(after):
                votes[mark_to_token[seg_v[k]]][seg_p[len(before):len(seg_p) - len(after)]] += 1
                progress = True
        pending = rest
    # 予備：まだ求まらない記号は、記号の前後の字（3〜8字ずつ）が PDF で「前の字＋何か＋後の字」に
    # なっている箇所を探す（版ずれで、記号の近くが書き換わった場合のため）
    for k, ch in enumerate(v):
        tok = mark_to_token.get(ch)
        if tok is None or votes[tok]:
            continue
        before = re.split(f"[{chr(_MARK_BASE)}-{chr(_MARK_BASE + 0x0FFF)}]", v[max(0, k - 8):k])[-1]
        after = re.split(f"[{chr(_MARK_BASE)}-{chr(_MARK_BASE + 0x0FFF)}]", v[k + 1:k + 9])[0]
        if len(before) < 3 or len(after) < 3:
            continue
        for m in re.finditer(re.escape(before) + "(.{1,40}?)" + re.escape(after), p):
            votes[tok][m.group(1)] += 1
    r = Recovery()
    for tok in mark_to_token.values():
        if votes[tok]:
            r.found[tok] = votes[tok].most_common(1)[0][0]
            if len(votes[tok]) > 1:
                r.conflicts[tok] = dict(votes[tok])
        else:
            r.missing.append(tok)
    restored = "".join(r.found.get(mark_to_token.get(c), c) if c in mark_to_token else c for c in v)
    # 比べるときは空白を除く（行末の半角空白は行の外に出し、PDF に描かないことがある）
    pattern = "".join(r"\.*\d+" if piece == _TOC_FILL else re.escape(piece)
                      for piece in re.split(f"({_TOC_FILL})", _SPACE_RE.sub("", restored)) if piece)
    r.exact = (not r.missing and not r.conflicts
               and re.fullmatch(pattern, _SPACE_RE.sub("", p), flags=re.S) is not None)
    return r


def rebuild_dictionary(content, pdf_path, doc_type=None):
    """構文ファイル（vadm.Content）と PDF から、辞書を作り直す。(Dictionary, Recovery) を返す。

    PDF の識別子の文書ID が違えば PdfMismatch を出す。版が違っても突き合わせる（求まらない記号・
    違う語が対応した記号は Recovery に入るので、利用者に尋ねる。違う語が対応した記号は辞書に入れない）。
    構文ファイルに出てくる記号の英字は、元の語が求まらなくても使ったものとして覚え、新しい語に
    同じ記号を振らない。文書の種類は、doc_type（DOC_TYPES のキー）がなければ区切りの行の設定による。
    """
    pdf_id = read_id(pdf_path)
    if pdf_id is None or pdf_id[0] != content.doc_id:
        raise PdfMismatch("この PDF は、構文ファイルと同じ文書のものではありません。")
    if doc_type is None:
        doc_type = content.settings.doc_type if content.settings else "Saiban"
    r = recover(content.body, pdf_path, DOC_TYPES[doc_type])
    d = Dictionary()
    for m in TOKEN_RE.finditer(content.body_text):
        d.note_used(m.group(0))
    for tok, word in r.found.items():
        if tok not in r.conflicts:
            d.add_known(word, tok)
    return d, r
