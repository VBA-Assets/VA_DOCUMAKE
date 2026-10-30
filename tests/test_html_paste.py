"""Word・ブラウザーの書式付きの字の貼り付け。tests\\data\\word_clip は、Word（16.0.20527）で作った見本を別の Word でコピーした
ときのクリップボードの実物（選んだ部分の HTML と、プレーンな字）。tests\\data\\browser_clip は、Edge・Chrome で同じようにコピー
した実物（CF_HTML の全体と、プレーンな字）。"""
import re
from pathlib import Path

import pytest

from va_document import html_paste
from va_document.pseudonym import Dictionary

DATA = Path(__file__).resolve().parent / "data" / "word_clip"


def cf_html(fragment, word=True):
    """CF_HTML のバイト列を作る。"""
    ns = "urn:schemas-microsoft-com:office:word" if word else "urn:schemas-microsoft-com:office:excel"
    head = f'<html xmlns:w="{ns}"><body><!--StartFragment-->'.encode()
    tail = b"<!--EndFragment--></body></html>"
    body = fragment.encode("utf-8")
    prefix = "Version:1.0\r\nStartHTML:{:010d}\r\nEndHTML:{:010d}\r\nStartFragment:{:010d}\r\nEndFragment:{:010d}\r\n\r\n"
    size = len(prefix.format(0, 0, 0, 0))
    a, b = size + len(head), size + len(head) + len(body)
    return prefix.format(size, b + len(tail), a, b).encode() + head + body + tail


def sample(name):
    return ((DATA / f"{name}.html").read_text(encoding="utf-8"), (DATA / f"{name}.txt").read_text(encoding="utf-8-sig"))


def without_cell_break(fragment, plain):
    """見本の表の、セルの中の改行（字のまま貼る場合の見本）を除く。"""
    return re.sub(r"<span lang=EN-US><br>\s*</span>改行", "", fragment), plain.replace("\r\n改行", "").replace("\n改行", "")


def convert(fragment, plain, dictionary=None, **k):
    return html_paste.convert(cf_html(fragment), plain, dictionary or Dictionary(), **k)


def test_formats_become_marks():
    """実物のコピー：太字・傍点・蛍光ペン・配置・表が記号になる。字はプレーンな字のまま。下線・斜体・色は字だけになる。"""
    out = convert(*without_cell_break(*sample("all")))
    assert out[:8] == ["通常の字と**太字の語**と続きの字。", "通常の字と*傍点の語*と続きの字。", "通常の字と==蛍光ペンの語==と続きの字。",
                       ":-: 中央揃えの段落", "--: 右揃えの段落", "下線の語と斜体の語と赤い語。",
                       "**==太字と蛍光ペンの重なり==**。", "見出しスタイルの段落"]
    assert out[8:13] == ["\t箇条書きの段落", "1.\t段落番号の段落", "字下げのある段落", "語の途中の甲野**太郎**の太字。",
                         "記号 * と | と ** を含む字。"]
    assert out[13:] == ["| **項目** | 金額 | 備考 |", "|---|---|---|", "| 休業損害 | 1,080,000 | --: A\\|B |", "| 通院 |  | 二行目あり |"]


def test_inline_selection():
    assert convert(*sample("inline")) == ["**太字の語**と続き"]


def test_center_paragraph_and_first_align():
    assert convert(*sample("center")) == [":-: 中央揃えの段落"]
    assert convert(*sample("center"), first_align=False) is None       # 記号がなければ、書式はない（ふつうに貼る）


def test_cell_with_line_break_is_left_to_plain_paste():
    """セルの中の改行は表にできないので、書式を諦める（これまでどおり字を貼る）。"""
    assert convert(*sample("all")) is None
    assert convert(*sample("table")) is None


def test_pseudonymized_word_inside_format_change():
    """語の途中で太字が変わっても、語の単位で記号に置き換える（実名を残さない）。"""
    d = Dictionary()
    d.register("甲野太郎", "人名")
    out = convert(*without_cell_break(*sample("all")), dictionary=d)
    assert out[11] == "語の途中の〔人名Ａ〕の太字。" and "甲野" not in "\n".join(out)
    frag = "<p class=MsoNormal><b>甲野太郎</b>は<b>甲野</b>太郎。</p>"
    assert convert(frag, "甲野太郎は甲野太郎。", d) == ["**〔人名Ａ〕**は**〔人名Ａ〕**。"]


@pytest.mark.parametrize("fragment, plain", [
    ("<p>字が<b>違う</b></p>", "字が同じ"),                               # 字が合わない
    ("<p>字<b>太字</b></p><p style='display:none'>隠し文字</p>", "字太字"),  # HTML にだけある字
    ("<p>隠し</p>", "隠し"),                                              # 書式がない
    ("<table><tr><td colspan=2>結合</td></tr></table>", "結合"),          # 結合したセル
    ("<table><tr><td><table><tr><td><b>字</b></td></tr></table></td></tr></table>", "字"),   # 入れ子の表
])
def test_gives_up_and_keeps_plain_text(fragment, plain):
    assert convert(fragment, plain) is None


def test_not_word_html_is_ignored():
    assert html_paste.convert(cf_html("<p><b>太字</b></p>", word=False), "太字", Dictionary()) is None
    assert html_paste.convert(b"", "字", Dictionary()) is None


def browser_html(fragment):
    """ブラウザーの CF_HTML のバイト列を作る（SourceURL があり、Office の宣言がない）。"""
    head = b"<html>\r\n<body>\r\n<!--StartFragment-->"
    tail = b"<!--EndFragment-->\r\n</body>\r\n</html>"
    body = fragment.encode("utf-8")
    prefix = ("Version:0.9\r\nStartHTML:{:010d}\r\nEndHTML:{:010d}\r\nStartFragment:{:010d}\r\nEndFragment:{:010d}\r\n"
              "SourceURL:https://example.com/\r\n")
    size = len(prefix.format(0, 0, 0, 0))
    a, b = size + len(head), size + len(head) + len(body)
    return prefix.format(size, b + len(tail), a, b).encode() + head + body + tail


def browser(fragment, plain, dictionary=None, **k):
    return html_paste.convert(browser_html(fragment), plain, dictionary or Dictionary(), **k)


def browser_sample(name):
    folder = DATA.parent / "browser_clip"
    return (folder / f"{name}.html").read_bytes(), (folder / f"{name}.txt").read_bytes().decode("utf-8")


def test_browser_copy_becomes_marks():
    """Edge のコピーの実物：太字（strong・b・span の 700）・蛍光ペン・傍点・配置・表が記号になる。見出しと表の見出しの
    セルは太字にしない。斜体は字だけ。空の行と、pre の中の改行は、プレーンな字のまま。"""
    data, plain = browser_sample("all")
    assert html_paste.convert(data, plain, Dictionary()) == [
        "見出しの字",
        "本文の**太字の語**と、**bタグの語**と、**spanの太字**と、斜体の語と、==マークの語==と、*傍点の語*。",
        "", ":-: 中央の段落", "", "--: 右の段落", "",
        "divの行", "brの次の行", "箇条の一", "**箇条の二**", "番号の一", "番号の二", "引用の字",
        "コードの1行目", "コードの2行目",
        "| 項目 | 値 |", "|---|---|", "| **太字セル** | --: 右セル |", "| 三 | :-: 中央セル |",
        "最後の段落　全角空白 と半角空白。"]


def test_browser_copy_of_part_of_a_line():
    """Edge・Chrome のコピーの実物：行の途中だけ、段落をまたぐ選び方（font-weight: 400 は太字でない）。"""
    data, plain = browser_sample("inline")
    assert html_paste.convert(data, plain, Dictionary()) == ["行の途中の**太字**だけ"]
    data, plain = browser_sample("part_cross")
    lines = html_paste.convert(data, plain, Dictionary(), first_align=False)
    assert lines[0].startswith("**の語**と、") and lines[-1] == ":-: 中央の"


def test_browser_copy_keeps_the_plain_text():
    """記号を除いた字は、プレーンな字と同じ。"""
    from va_document.document import split_inline_full
    data, plain = browser_sample("all")
    lines = html_paste.convert(data, plain, Dictionary())
    bare = [re.sub(r"^(:-:|--:) ", "", line) for line in lines if not line.startswith("|")]
    assert [split_inline_full(line).plain for line in bare] == [line for line in plain.split("\n") if "\t" not in line]


def test_browser_replaces_pseudonyms():
    dictionary = Dictionary()
    dictionary.register("甲野太郎", "人名")
    assert browser("<p>甲野<b>太郎</b>と<b>乙</b></p>", "甲野太郎と乙", dictionary) == ["〔人名Ａ〕と**乙**"]


@pytest.mark.parametrize("fragment, plain, expected", [
    ('<p style="font-weight: 400">字<span style="font-weight: 600">太</span></p>', "字太", ["字**太**"]),
    ('<strong style="font-weight: 400">細</strong><b>太</b>', "細太", ["細**太**"]),
    ('<b style="font-weight: normal"><span style="font-weight: 700">太</span>細</b>', "太細", ["**太**細"]),
    ('<h2><strong>見出し</strong></h2><p><b>本文</b></p>', "見出し\n本文", ["見出し", "**本文**"]),
    ('<div style="text-align: center"><p><b>字</b></p></div>', "字", [":-: **字**"]),
    ('<div style="text-align: center"><p style="text-align: left"><b>字</b></p></div>', "字", ["**字**"]),
    ('<table align="center"><tr><td><b>字</b></td><td>字</td></tr></table>', "字\t字", ["| **字** | 字 |", "|---|---|"]),
])
def test_browser_styles(fragment, plain, expected):
    assert browser(fragment, plain) == expected


@pytest.mark.parametrize("fragment, plain", [
    ("<p>書式なし</p>", "書式なし"),
    ("<p><b>字</b>が合わない</p>", "別の字が合わない"),
    ("<p><b>字</b></p>", "字\n余りの行"),
    ("<ul><li><b>字</b></li></ul>", "• 字"),                                    # プレーンな字にだけ印がある
    ("<table><tr><td colspan=2><b>字</b></td></tr></table>", "字"),              # 結合したセル
])
def test_browser_gives_up_and_keeps_plain_text(fragment, plain):
    assert browser(fragment, plain) is None


def test_excel_html_with_source_url_is_ignored():
    data = browser_html("<b>太字</b>").replace(b"<html>", b'<html xmlns:x="urn:schemas-microsoft-com:office:excel">')
    data = cf_with_offsets(data)
    assert html_paste.fragment(data) is None


def cf_with_offsets(data):
    """<html> を書き換えて字数が変わった CF_HTML の、StartFragment を直す。"""
    start = data.index(b"<!--StartFragment-->") + len(b"<!--StartFragment-->")
    end = data.index(b"<!--EndFragment-->")
    data = re.sub(rb"StartFragment:\d{10}", b"StartFragment:%010d" % start, data)
    return re.sub(rb"EndFragment:\d{10}", b"EndFragment:%010d" % end, data)


def test_marks_that_cannot_be_read_back_are_dropped():
    """字の中の * と重なって記号として読めない行は、書式を付けず字を残す（ほかの行の書式は付ける）。"""
    assert convert("<p><b>2*3</b></p><p><b>字</b></p>", "2*3\n字") == ["2*3", "**字**"]


def test_spaces_stay_outside_marks():
    assert convert("<p>前 <b>太字</b> 後</p>", "前 太字 後") == ["前 **太字** 後"]
    assert convert("<p><b>語 語</b></p>", "語 語") == ["**語 語**"]
