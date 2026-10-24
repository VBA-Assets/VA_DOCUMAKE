"""構文ファイル（仕様.md の8）と、PDF との突き合わせによる対応表の作り直し（仕様.md の7）。"""
from pathlib import Path

import pytest

from va_documake import vadm
from va_documake.doctypes import DOC_TYPES, PAGE_NUMBER_TOP_RIGHT
from va_documake.document import parse
from va_documake.layout import Typesetter
from va_documake.pdfwriter import write_pdf
from va_documake.pseudonym import Dictionary
from va_documake.recover import PdfMismatch, rebuild_dictionary, recover

DATA = Path(__file__).parent / "data"
TRIAL = DATA / "AI往復試験"


# ---------- 書き出し・読み込み ----------

def test_doc_id():
    ids = {vadm.new_doc_id() for _ in range(50)}
    assert len(ids) == 50
    assert all(len(i) == 8 and not set(i) & set("0O1I") for i in ids)
    assert vadm.file_name("K7Q29XMD") == "K7Q29XMD.vadm"


def test_build_and_read_back(tmp_path):
    settings = vadm.Settings("Keiyaku1", PAGE_NUMBER_TOP_RIGHT)
    text = vadm.build("K7Q29XMD", 3, settings, "{表題}契約書\n# 目的\n〔人名Ａ〕は、\n\n")
    sep = "==== VA DocuMake 文書ID K7Q29XMD 版 3 種類 契約書1（法令型） ページ番号 右上 行番号 なし ===="
    assert sep in text.splitlines()
    path = tmp_path / "K7Q29XMD.vadm"
    vadm.write_file(path, text)
    c = vadm.read_file(path)
    assert (c.doc_id, c.version, c.settings) == ("K7Q29XMD", 3, settings)
    assert c.body == ["{表題}契約書", "# 目的", "〔人名Ａ〕は、"]
    assert c.prompt is not None
    assert list(tmp_path.iterdir()) == [path]   # 一時ファイルが残らない
    # 行番号（2026-10-24）。行番号の書いていない区切りの行（それより前の構文ファイル）は「なし」
    on = vadm.Settings("Saiban", PAGE_NUMBER_TOP_RIGHT, True)
    assert vadm.parse_separator(vadm.separator_line("K7Q29XMD", 1, on))[2] == on
    assert not vadm.parse_separator(sep.replace(" 行番号 なし", ""))[2].line_numbers


def test_old_separator_without_settings():
    """往復試験の構文ファイル（設定のない区切りの行）も読める。"""
    c = vadm.read_file(TRIAL / "K7Q29XMD.vadm")
    assert (c.doc_id, c.version, c.settings) == ("K7Q29XMD", 1, None)
    assert c.body[0].startswith("令和８年（ワ）第〔番号Ａ〕号")
    assert c.body[-1] == "{右}以上"


@pytest.mark.parametrize("n", [1, 2, 3])
def test_trial_answers(n):
    c = vadm.read_file(TRIAL / f"回答_{n}.txt")
    assert (c.doc_id, c.version) == ("K7Q29XMD", 1)
    assert c.prompt is None
    assert c.body[-1] == "{右}以上"


def test_answer_with_preface_and_code_block():
    answer = ("ご依頼のとおり直しました。\n\n```markdown\n"
              "==== VA DocuMake 文書ID K7Q29XMD 版 2 種類 裁判所提出書類 ページ番号 中下 ====\n"
              "# 認否\n認める。\n```\n\n記号はすべて元のまま残しています。\n")
    c = vadm.parse_text(answer)
    assert c.version == 2 and c.settings.doc_type == "Saiban"
    assert c.body == ["# 認否", "認める。"]


def test_no_separator():
    with pytest.raises(vadm.NoSeparator):
        vadm.parse_text("# 認否\n認める。\n")


# ---------- 取り込む前の確かめ ----------

def make_dictionary():
    d = Dictionary()
    d.register("甲野太郎", "人名")
    d.register("乙山商事株式会社", "法人")
    return d


CURRENT = ["{表題}準備書面", "{右}令和８年９月１７日", "# 認否", "〔人名Ａ〕の主張は争う。", "{改ページ}", "〔法人Ａ〕は認める。"]


def answer(body, version=3, doc_id="K7Q29XMD"):
    return vadm.parse_text(f"==== VA DocuMake 文書ID {doc_id} 版 {version} ====\n" + "\n".join(body))


def test_review_same_text_is_clean():
    r = vadm.review(answer(CURRENT), "K7Q29XMD", 3, CURRENT, make_dictionary())
    assert r.clean and not r.changes


def test_review_other_document_stops():
    with pytest.raises(vadm.OtherDocument):
        vadm.review(answer(CURRENT, doc_id="ZZZZZZZZ"), "K7Q29XMD", 3, CURRENT, make_dictionary())


def test_review_reports_tokens_marks_changes_and_old_version():
    body = ["準備書面", "{右}令和８年９月１７日", "# 認否", "〔人名A〕の主張は争う。〔人名Ｃ〕も同じ。", "{改ページ}", "追加した段落。"]
    r = vadm.review(answer(body, version=1), "K7Q29XMD", 3, CURRENT, make_dictionary())
    assert r.older
    assert r.unknown_tokens == ["〔人名Ｃ〕"]
    assert r.lost_tokens == ["〔法人Ａ〕"]          # 〔人名A〕（半角）は消えたことにしない
    assert r.lost_marks == [("{表題}", "{表題}準備書面")]
    changed_old = [ln for _, old, _ in r.changes for ln in old]
    changed_new = [ln for _, _, new in r.changes for ln in new]
    assert "{表題}準備書面" in changed_old and "〔法人Ａ〕は認める。" in changed_old
    assert "追加した段落。" in changed_new
    assert "# 認否" not in changed_old    # 変わっていない行は出さない
    # 変わった・増えた行は、回答の文書の何行目か（エディターで印を付けるため）
    assert [body[k] for k in r.changed_lines] == ["準備書面", "〔人名A〕の主張は争う。〔人名Ｃ〕も同じ。", "追加した段落。"]


# ---------- 突き合わせによる対応表の作り直し ----------

WORDS = [("甲野太郎", "人名"), ("乙山商事株式会社", "法人"), ("丙川　次郎", "人名"), ("丁田三郎", "人名"),
         ("戊村四郎", "人名"), ("原告", "その他")]


def save_pair(tmp_path, real_lines, doc_type="Saiban", page_number=None, words=WORDS, version=5):
    """実名の文章から、同じ版の PDF と構文ファイルを作る（VA DocuMakeの［保存］と同じ）。"""
    dt = DOC_TYPES[doc_type]
    d = Dictionary()
    for w, k in words:
        d.register(w, k)
    ts = Typesetter(dt)
    lines = ts.layout(parse(real_lines, dt))
    pdf = tmp_path / "実名.pdf"
    kw = {"page_number": page_number} if page_number else {}
    write_pdf(ts, lines, str(pdf), doc_id="K7Q29XMD", version=version, **kw)
    settings = vadm.Settings(doc_type, page_number or vadm.Settings().page_number)
    text = vadm.build("K7Q29XMD", version, settings, d.pseudonymize("\n".join(real_lines)))
    return d, pdf, vadm.parse_text(text)


@pytest.mark.parametrize("sample", ["裁判所", "長い文書"])
def test_rebuild_same_version(tmp_path, sample):
    real = (DATA / sample / "見本.md").read_text(encoding="utf-8").splitlines()
    original, pdf, content = save_pair(tmp_path, real)
    d, r = rebuild_dictionary(content, pdf)
    expected = {e.token: e.word for e in original.entries.values() if e.token in content.body_text}
    assert r.found == expected and not r.missing and not r.conflicts
    assert r.exact
    # 作り直した辞書で戻すと、元の実名の文章になる
    assert d.restore(content.body_text)[0] == "\n".join(real)
    # 次に登録する語は、続きの英字（人名は甲野・丙川・丁田・戊村の4つ）
    assert d.register("己野五郎", "人名") == "〔人名Ｅ〕"


def test_rebuild_with_table_and_top_right_page_number(tmp_path):
    real = ["{表題}損害の一覧", "# 損害", "甲野太郎の損害は、次の表のとおりである。",
            "| 項目 | {右}金額 |", "|===|---:|", "| 甲野太郎の休業損害 | 1,080,000 |", "| 乙山商事株式会社の負担分 | 500,000 |",
            "表のとおり、甲野太郎の損害は乙山商事株式会社が負う。", "{改ページ}", "{右}以上"]
    original, pdf, content = save_pair(tmp_path, real, page_number=PAGE_NUMBER_TOP_RIGHT)
    d, r = rebuild_dictionary(content, pdf)
    assert r.exact
    assert d.restore(content.body_text)[0] == "\n".join(real)


def test_rebuild_after_ai_changed_text(tmp_path):
    """版ずれ（AI の回答で上書きした後、PDF を保存していない）：変わっていない部分から求め、残りは尋ねる。"""
    real = (DATA / "裁判所" / "見本.md").read_text(encoding="utf-8").splitlines()
    original, pdf, content = save_pair(tmp_path, real)
    body = list(content.body)
    body.insert(10, "なお、〔人名Ａ〕の主張は失当である。")
    body[-3] = "（この段落は AI が書き直した。）"
    content.body = body
    d, r = rebuild_dictionary(content, pdf)
    assert not r.exact
    expected = {e.token: e.word for e in original.entries.values()}
    assert all(expected[t] == w for t, w in r.found.items() if t not in r.conflicts)
    assert r.found["〔人名Ａ〕"] == "甲野太郎"


def test_rebuild_rejects_other_pdf(tmp_path):
    real = ["# 認否", "甲野太郎の主張は争う。"]
    _, pdf, content = save_pair(tmp_path, real)
    content.doc_id = "ZZZZZZZZ"
    with pytest.raises(PdfMismatch):
        rebuild_dictionary(content, pdf)


def test_recover_reports_missing_when_word_cannot_be_found(tmp_path):
    real = ["# 認否", "甲野太郎の主張は争う。"]
    _, pdf, content = save_pair(tmp_path, real)
    r = recover(content.body + ["〔人名Ｚ〕の陳述書"], pdf, DOC_TYPES["Saiban"])
    assert r.found["〔人名Ａ〕"] == "甲野太郎"
    assert not r.exact


def test_review_reports_blank_lines_added_by_ai():
    """空の行は1行の空きになるので、AI が足した空行も変わった行として示す（文書の初めと終わりの空行は除く）。"""
    body = list(CURRENT)
    body.insert(3, "")
    r = vadm.review(answer(body), "K7Q29XMD", 3, CURRENT + [""], make_dictionary())
    assert r.changed_lines == [3] and not r.removed


def test_prompt_allows_table_changes_on_request():
    """AI への指示：表の2行目・セルの配置の記号は「私が求めたときを除き」変えない。2重線はすべての列を = にする。"""
    assert "セルの先頭の配置の記号は、私が求めたときを除き、変えない" in vadm.PROMPT
    assert "2行目のすべての列の - を = にする" in vadm.PROMPT


@pytest.mark.parametrize("mark", ["{目次}", "{目次:1}"])
def test_rebuild_with_toc(tmp_path, mark):
    """目次（見出しが2回、PDF に出る）があっても、突き合わせで記号の元の語が求まる。"""
    real = ["{表題}準備書面", mark, "{改ページ}", "# 甲野太郎の主張について", "甲野太郎は、乙山商事株式会社と契約した。",
            "## 乙山商事株式会社の反論", "反論する。"]
    original, pdf, content = save_pair(tmp_path, real)
    d, r = rebuild_dictionary(content, pdf)
    assert r.exact and not r.missing
    assert d.restore(content.body_text)[0] == "\n".join(real)


def test_rebuild_with_bold(tmp_path):
    """太字（**文字**）の記号は PDF に出ないが、突き合わせで記号の元の語が求まる（太字の中の記号も）。"""
    real = ["# 認否", "**甲野太郎**の主張は争う。", "| 当事者 | 主張 |", "|---|---|", "| **乙山商事株式会社** | 争う |"]
    original, pdf, content = save_pair(tmp_path, real)
    d, r = rebuild_dictionary(content, pdf)
    assert r.exact and not r.missing
    assert d.restore(content.body_text)[0] == "\n".join(real)


def test_prompt_allows_bold_on_request():
    assert "太字は **語**、傍点は *語* で書く" in vadm.PROMPT and "・太字・斜体" not in vadm.PROMPT


def test_rebuild_with_highlight(tmp_path):
    """蛍光ペン（==文字==）は保存する PDF に出ないが、突き合わせで記号の元の語が求まる。"""
    real = ["# 認否", "==甲野太郎の主張==は争う。", "| 当事者 | 主張 |", "|---|---|", "| ==乙山商事株式会社== | 争う |"]
    original, pdf, content = save_pair(tmp_path, real)
    d, r = rebuild_dictionary(content, pdf)
    assert r.exact and not r.missing
    assert d.restore(content.body_text)[0] == "\n".join(real)


def test_prompt_explains_highlight():
    assert "==語== は私が画面で付けた目印（蛍光ペン。PDF には出ない）" in vadm.PROMPT
    assert "蛍光ペンの記号（==語==）と均等割付の記号（{均等:5}語{均等}）は、私が求めたときを除き、付け外ししない" in vadm.PROMPT


def test_review_reports_lost_indent_but_not_changed_count():
    """AI の回答で {イン:N} が消えたら知らせる。字数を変えただけなら知らせない。"""
    current = ["# 認否", "{イン:2}{字下}主張は争う。"]
    r = vadm.review(answer(["# 認否", "{イン:3}{字下}主張は争う。"]), "K7Q29XMD", 3, current, make_dictionary())
    assert not r.lost_marks
    r = vadm.review(answer(["# 認否", "{字下}主張は争う。"]), "K7Q29XMD", 3, current, make_dictionary())
    assert [m for m, _ in r.lost_marks] == ["{イン}"]
    assert "{イン:2} は段落の左インデントを全角2字にする記号" in vadm.PROMPT


def test_rebuild_with_distribute(tmp_path):
    """均等割付の記号は PDF に出ないが、突き合わせで記号の元の語が求まる（割り付けた中の記号も）。"""
    real = ["{均等:5}原告{均等}甲野太郎", "{均等:6}{右}被告{均等}乙山商事株式会社", "# 認否", "{均等:8}甲野太郎{均等}の主張は争う。"]
    original, pdf, content = save_pair(tmp_path, real)
    d, r = rebuild_dictionary(content, pdf)
    assert r.exact and not r.missing
    assert d.restore(content.body_text)[0] == "\n".join(real)


def test_rebuild_with_dots(tmp_path):
    """傍点の黒丸は図形で描くので PDF の字に入らず、突き合わせで記号の元の語が求まる（傍点の中の記号も）。"""
    real = ["原告　甲野太郎", "# 認否", "*甲野太郎*の主張は***争う***。", "| 当事者 | 主張 |", "|---|---|", "| *乙山商事株式会社* | 否認 |"]
    original, pdf, content = save_pair(tmp_path, real)
    d, r = rebuild_dictionary(content, pdf)
    assert r.exact and not r.missing
    assert d.restore(content.body_text)[0] == "\n".join(real)

def test_rebuild_with_composite_heading(tmp_path):
    """複合見出し（番号が続けて並ぶ）と目次があっても、突き合わせで記号の元の語が求まる。"""
    real = ["{目次}", "{改ページ}", "#", "## 甲野太郎の主張", "本文。", "#", "## 乙山商事株式会社の反論", "反論する。"]
    original, pdf, content = save_pair(tmp_path, real)
    d, r = rebuild_dictionary(content, pdf)
    assert r.exact and not r.missing
    assert d.restore(content.body_text)[0] == "\n".join(real)

