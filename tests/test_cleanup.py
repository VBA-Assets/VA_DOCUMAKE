"""貼り付けた文章の整形（VA公用文 clsPreFormatter と同じ。仕様.md の5.1）。"""
from va_document.cleanup import clean


def test_front_matter_removed():
    text, rep = clean("---\ntitle: 準備書面\ndate: 2026-10-23\n---\n本文")
    assert text == "本文" and rep["フロントマター"] == 1


def test_front_matter_needs_key_value():
    """閉じの --- までに key: value でない行があれば、フロントマターではなく水平線として扱う（本文は残す）。"""
    text, rep = clean("---\n本文の1行目\n---\n本文の2行目")
    assert text == "本文の1行目\n本文の2行目" and rep["水平線"] == 2 and "フロントマター" not in rep


def test_horizontal_rules_removed():
    text, rep = clean("前\n---\n* * *\n___\n後")
    assert text == "前\n後" and rep["水平線"] == 3


def test_table_separator_is_kept():
    text, _ = clean("| A | B |\n|---|---|\n| 1 | 2 |")
    assert text == "| A | B |\n|---|---|\n| 1 | 2 |"


def test_code_fence_removed():
    text, rep = clean("```markdown\n# 見出し\n```")
    assert text == "# 見出し" and rep["コードブロックの記号"] == 2


def test_links():
    """WikiLink は文字だけにする。マークダウンのリンクは、VA公用文と同じくそのまま残す（URL を消さない）。"""
    text, rep = clean("詳しくは[裁判所のサイト](https://www.courts.go.jp/)と[[ページ|別名]]、[[索引]]を見る。")
    assert text == "詳しくは[裁判所のサイト](https://www.courts.go.jp/)と別名、索引を見る。"
    assert rep["WikiLink"] == 2 and "リンク" not in rep


def test_emphasis_removed_inner_text_kept():
    """**x**（太字）と *x*（傍点）は記号なので残し、ほかの強調記号は取り除く（2026-10-24 班長指示。VA公用文は
    ** も * も取り除く）。"""
    text, rep = clean("これは**重要**で、*注意*と__大事__と_強調_がある。")
    assert text == "これは**重要**で、*注意*と大事と強調がある。" and rep["強調記号"] == 2


def test_emphasis_exceptions():
    """箇条書きの「* 」、片方だけの **、英数字の中の _ は変えない（VA公用文と同じ）。"""
    assert clean("* 項目 *")[0] == "* 項目 *"
    assert clean("**片方だけ")[0] == "**片方だけ"
    assert clean("file_name_x と a_b_c")[0] == "file_name_x と a_b_c"


def test_nothing_to_clean():
    text, rep = clean("# 請求の原因\n本文。")
    assert text == "# 請求の原因\n本文。" and not rep
