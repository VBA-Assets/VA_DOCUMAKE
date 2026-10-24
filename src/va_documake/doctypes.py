"""文書の種類ごとの書式の設定（VA公用文 cstSettings.bas の値を写したもの。仕様.md の6）。

VA公用文の版が上がって値が変わったら、ここを写し直す。値の意味は cstSettings.bas の冒頭の説明と同じ。
"""
from dataclasses import dataclass

# 番号スタイル（VA公用文の値）→ 字の種類
_STYLE = {14: "fw", 0: "hw", 20: "kana", 12: "hwkana", 4: "alpha", 2: "roman", 18: "circled"}

# 表題の配置
TITLE_CENTER, TITLE_JUSTIFY, TITLE_LEFT = "center", "justify", "left"


@dataclass(frozen=True)
class DocType:
    """1つの文書の種類の書式。"""
    key: str                        # VA公用文の文書の種類の名前（Saiban など）
    label: str                      # 画面に出す名前
    margins: tuple                  # 余白（mm）（上, 下, 左, 右）
    chars_lines: tuple              # 文字数, 行数
    number_formats: tuple           # 見出しの番号書式（%n をレベル n の番号に置き換える）
    number_styles: tuple            # 番号の字の種類
    heading_left: tuple             # 見出しの左インデント（字）
    heading_first: tuple            # 見出しの最初の行のインデント（字）
    text_left: tuple                # 本文の左インデント（字）
    text_first: tuple               # 本文の最初の行のインデント（字）
    left_add: int                   # 階層ごとに増やす左インデント（字）
    title_align: str                # 表題の配置
    title_indent: int               # 表題のインデント（字。両端揃えのとき前後に空ける字数）
    reset_on: tuple = tuple(range(9))   # リスト開始レベル（0：振り直さない）
    start_at: tuple = (1,) * 9          # 開始番号
    list_bullet: str = "・"         # 箇条書きの記号
    list_number: str = "%1　"       # 段落番号の書式
    list_number_style: str = "circled"
    list_left: int = 1              # リストの、見出しからの左インデントの増加量（字）
    list_first: int = -1            # リストの最初の行のインデント（字）


def _styles(s):
    return tuple(_STYLE[int(v)] for v in s.split(","))


def _nums(s):
    return tuple(float(v) for v in s.split(","))


_ONES = (1,) * 9
_SAIBAN_NUMBERS = ("第%1　", "%2　", "(%3) ", "%4　", "(%5) ", "%6　", "(%7) ", "%8　", "(%9) ")
_SAIBAN_STYLES = _styles("14,14,0,20,12,4,4,2,2")
_SAIBAN_HEADING_FIRST = _nums("-1,-1,-1,-1,-1,-.5,-1,-.5,-1")
_TECH_NUMBERS = tuple(".".join(f"%{k}" for k in range(1, n + 1)) + "." for n in range(1, 10))

DOC_TYPES = {d.key: d for d in (
    DocType("Saiban", "裁判所提出書類", (35, 27, 30, 17.5), (37, 26), _SAIBAN_NUMBERS, _SAIBAN_STYLES,
            _ONES, _SAIBAN_HEADING_FIRST, _ONES, _ONES, 1, TITLE_CENTER, 0),
    DocType("Naiyou", "内容証明", (30, 30, 30, 30), (19, 26),
            ("第%1　", "%2　", "（%3）", "%4　", "（%5）", "%6　", "（%7）", "%8　", "（%9）"),
            _styles("14,14,14,20,20,4,4,2,2"),
            _ONES, _nums("-1,-1,-1,-1,-1,-.5,-1.5,-.5,-1.5"), _ONES, _ONES, 1, TITLE_CENTER, 0),
    DocType("Kouyou", "公用文", (25, 20, 25, 20), (40, 40), _SAIBAN_NUMBERS, _SAIBAN_STYLES,
            _ONES, _SAIBAN_HEADING_FIRST, _ONES, _ONES, 1, TITLE_JUSTIFY, 3),
    DocType("Keiyaku1", "契約書1（法令型）", (25, 20, 25, 20), (40, 40),
            ("", "第%2条　", "%3　", "（%4）", "%5　", "", "", "", ""),
            _styles("0,14,14,14,20,0,0,0,0"),
            _nums("1,1,1,3,4,0,0,0,0"), _nums("0,-1,-1,-2,-1,0,0,0,0"), _ONES, _ONES, 0, TITLE_JUSTIFY, 3,
            reset_on=(0, 0, 2, 3, 4, 5, 6, 7, 8), start_at=(1, 1, 2, 1, 1, 1, 1, 1, 1)),
    DocType("Keiyaku2", "契約書2（実務型）", (25, 25, 25, 25), (38, 38),
            ("第%1条", "%2　", "(%3) ", "%4　", "", "", "", "", ""),
            _styles("14,14,0,20,0,0,0,0,0"),
            _nums("1,1,1,1,0,0,0,0,0"), _nums("-1,-1,-1,-1,0,0,0,0,0"),
            _nums("0,1,1,1,1,1,1,1,1"), _ONES, 1, TITLE_CENTER, 0),
    DocType("Business", "ビジネス文書", (25, 25, 25, 25), (38, 38),
            ("第%1 ", "%2　", "(%3) ", "%4　", "(%5) ", "%6　", "(%7) ", "%8　", "(%9) "),
            _styles("0,0,0,20,20,4,4,2,2"),
            _ONES, _nums("-1,-.5,-1,-1,-1.5,-.5,-1,-.5,-1"), _ONES, _ONES, 1, TITLE_CENTER, 0),
    DocType("Technical", "技術文書", (25, 25, 25, 25), (38, 38), _TECH_NUMBERS, _styles("0,0,0,0,0,0,0,0,0"),
            (0,) * 9, (0,) * 9, (0,) * 9, (0,) * 9, 0, TITLE_LEFT, 0,
            list_bullet="-", list_number="%1)", list_number_style="alpha", list_left=0, list_first=0),
)}

# ページ番号の位置（VA公用文 basSetup.ConfigHeaderFooter の選択肢）
PAGE_NUMBER_NONE, PAGE_NUMBER_TOP_RIGHT = "None", "TopRight"
PAGE_NUMBER_BOTTOM_CENTER, PAGE_NUMBER_BOTTOM_CENTER_DECORATED = "BottomCenter", "BottomCenterDecorated"
PAGE_NUMBER_BOTTOM_RIGHT = "BottomRight"
# 画面と構文ファイルの区切りの行に出す名前（VA公用文のセットアップ画面の呼び方）
PAGE_NUMBER_LABELS = {PAGE_NUMBER_NONE: "なし", PAGE_NUMBER_TOP_RIGHT: "右上", PAGE_NUMBER_BOTTOM_CENTER: "中下",
                      PAGE_NUMBER_BOTTOM_CENTER_DECORATED: "中下（飾り）", PAGE_NUMBER_BOTTOM_RIGHT: "右下"}

FW_DIGITS = "０１２３４５６７８９"
KANA = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"
HW_KANA = "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜｦﾝ"
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
ROMAN = ("i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x")


def number_text(style, n):
    """番号の字の種類に応じて、n を文字列にする。"""
    if style == "fw":
        return "".join(FW_DIGITS[int(d)] for d in str(n))
    if style == "hw":
        return str(n)
    if style == "kana":
        return KANA[n - 1]
    if style == "hwkana":
        return HW_KANA[n - 1]
    if style == "alpha":
        return "abcdefghijklmnopqrstuvwxyz"[n - 1]
    if style == "roman":
        return ROMAN[n - 1]
    if style == "circled":
        return CIRCLED[n - 1]
    raise ValueError(style)
