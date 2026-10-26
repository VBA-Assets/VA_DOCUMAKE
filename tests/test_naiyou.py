"""内容証明の字数・行数のチェック（VA内容証明郵便と同じ数え方。2026-10-24 班長指示）。"""
from va_document import naiyou
from va_document.doctypes import DOC_TYPES
from va_document.document import parse
from va_document.layout import Typesetter

DT = DOC_TYPES[naiyou.DOC_TYPE]


def check(src):
    ts = Typesetter(DT)
    return naiyou.check(ts, ts.layout(parse(src, DT)))


def test_count_chars_like_va_naiyou():
    """全角・半角の空白と、閉じ括弧「）」「)」は数えない（VA内容証明郵便の GetAdjustedCharCount と同じ）。"""
    assert naiyou.count_chars("（甲）　乙 (A)") == 5          # （ 甲 乙 ( A
    assert naiyou.count_chars("") == 0


def test_normal_document_passes():
    """1行19字・26行の格子で組むので、ふつうの文章（句読点のぶら下げで20字の行を含む）は通る。"""
    body = "通知人は、被通知人に対し、次のとおり通知します。" * 30
    assert check([":=: 通知書", "# 請求", body, "--: 以上"]) is None


def test_too_many_chars_in_a_line():
    """半角の英数字は半字で組むが、1字と数えるので、1行に20字を超えることがある。最初に見つかった行を返す。"""
    p = check(["本文。", "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"])
    assert p.kind == "chars" and p.page == 1 and p.count > naiyou.MAX_CHARS
    assert p.text.startswith("ABCDEF") and "20 字まで" in p.message()


def test_too_many_lines_in_a_page():
    """表は行の高さが本文の行より低いので、1枚に26行を超えることがある。字のない行は数えない。"""
    rows = ["| 項目 | 金額 |", "|---|---|"] + [f"| 項目{k} | {k} |" for k in range(40)]
    p = check(rows)
    assert p.kind == "lines" and p.page == 1 and p.count > naiyou.MAX_LINES
    assert "26 行まで" in p.message() and p.text
    # 空の行（字のない行）は数えない
    assert check([""] * 10 + ["本文。"] * 20) is None
