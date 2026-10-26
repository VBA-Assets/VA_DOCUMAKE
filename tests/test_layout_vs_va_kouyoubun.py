"""行組みが VA公用文（Word）と一致することを確かめる（仕様.md の12）。

正解は tests/data/<見本>/VA公用文_字の位置.json：班長の Word とは別に起動した Word で、見本を VA公用文 Ver8D3 に
より整え、1字ずつ Selection.Information で読み取った位置（試作/Make-VaKouyoubunPdf.ps1。2026-10-23）。
Word の値は画面の画素に丸められているので、左右の位置は 1pt までの差を一致とみなす。
"""
import difflib
import json
from collections import defaultdict
from pathlib import Path

import pytest

from va_document.cleanup import clean
from va_document.doctypes import DOC_TYPES
from va_document.document import parse
from va_document.layout import Typesetter

DATA = Path(__file__).parent / "data"

# (見本のフォルダ, 文書の種類, VA公用文の側で一致しない字の数)
# 公用文の4字：VA公用文で箇条書き「- 第１、第２、第３」の「第１、」が消えたため（検討メモの5。VA公用文の課題）
CASES = [
    ("裁判所", "Saiban", 0), ("半角と箇条書き", "Saiban", 0), ("公用文", "Kouyou", 4),
    ("内容証明", "Naiyou", 0), ("契約書1", "Keiyaku1", 0), ("契約書2", "Keiyaku2", 0),
    ("ビジネス", "Business", 0), ("技術", "Technical", 0), ("見出しが浅くなる", "Saiban", 0),
    ("長い文書", "Saiban", 0),
    # 整形：フロントマター・水平線・強調記号・WikiLink の除去、行頭の空白のインデント、右揃えの段落の後は
    # 変換しないこと。VA公用文の正解は、配置を整える前に設定して作った（Make-VaKouyoubunPdf.ps1 -AlignBefore）
    ("整形", "Saiban", 0),
]


def word_chars(path):
    d = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = defaultdict(set)
    for c in d:
        rows[c["page"]].add(c["ys"])
    index = {pg: {y: i for i, y in enumerate(sorted(ys))} for pg, ys in rows.items()}
    return [(c["c"], c["page"], index[c["page"]][c["ys"]], c["xs"]) for c in d]


def python_chars(md_path, doc_type):
    dt = DOC_TYPES[doc_type]
    ts = Typesetter(dt)
    text, _ = clean(md_path.read_text(encoding="utf-8"))
    lines = ts.layout(parse(text.splitlines(), dt))
    # Word の字には見出し・段落番号の番号が含まれないので、番号の字は除く
    return [(g.ch, ln.page, ln.row, ts.margin_left + g.x) for ln in lines for g in ln.glyphs if not g.is_number]


@pytest.mark.parametrize("folder,doc_type,allowed", CASES, ids=[c[0] for c in CASES])
def test_same_position_as_va_kouyoubun(folder, doc_type, allowed):
    w = word_chars(DATA / folder / "VA公用文_字の位置.json")
    p = python_chars(DATA / folder / "見本.md", doc_type)
    sm = difflib.SequenceMatcher(None, [c[0] for c in w], [c[0] for c in p], autojunk=False)
    pairs = [(w[i + k], p[j + k]) for i, j, n in sm.get_matching_blocks() for k in range(n)]
    # 字の並びが同じ（VA公用文の側で消えた字を除く）
    assert len(p) - len(pairs) <= allowed and len(w) == len(pairs)
    # 同じページの同じ行にある字
    wrong_row = [(a, b) for a, b in pairs if (a[1], a[2]) != (b[1], b[2])]
    # 左右の位置の差が 1pt を超える字（VA公用文の側で字が消えた行の字は、その数だけ許す）
    wrong_x = [(a, b) for a, b in pairs if (a[1], a[2]) == (b[1], b[2]) and abs(a[3] - b[3]) > 1.0]
    if allowed:
        assert len(wrong_row) == 0 and len(wrong_x) <= allowed
    else:
        assert wrong_row == [] and wrong_x == []
