"""仮名化（仕様.md の7。VA仮名化と同じ決まり＋VA DocuMakeの違い）。"""
import pytest

from va_documake.pseudonym import Dictionary, NotRegistrable, number_to_letters, overlaps_token, tokens_in


def test_letters():
    assert [number_to_letters(n) for n in (1, 2, 26, 27, 28, 52, 53)] == ["Ａ", "Ｂ", "Ｚ", "ＡＡ", "ＡＢ", "ＡＺ", "ＢＡ"]


def test_register_by_kind_in_order():
    d = Dictionary()
    assert d.register("山田太郎", "人名") == "〔人名Ａ〕"
    assert d.register("株式会社乙山", "法人") == "〔法人Ａ〕"
    assert d.register("鈴木花子", "人名") == "〔人名Ｂ〕"
    # 同じ語をもう一度登録すると、同じ記号
    assert d.register("山田太郎", "人名") == "〔人名Ａ〕"


def test_selection_is_trimmed():
    d = Dictionary()
    assert d.register("　山田太郎 \r\n", "人名") == "〔人名Ａ〕"
    assert d.find("山田太郎").token == "〔人名Ａ〕"


@pytest.mark.parametrize("word", ["〔人名Ａ〕", "人名", "名", "名Ａ", "人名Ｂ", "Ａ", "ABC", "AB", "その他", "他Ａ", "改行\nを含む",
                                  "あ" * 101])
def test_not_registrable(word):
    with pytest.raises(NotRegistrable):
        Dictionary().register(word, "人名")


@pytest.mark.parametrize("word", ["山田太郎", "ABC商事", "Smith", "東京都千代田区", "１２３４"])
def test_registrable(word):
    assert not overlaps_token(word)
    Dictionary().register(word, "人名")


def test_letters_are_not_reused_after_unregister():
    """解除した記号の英字は使い直さない（前の会話の回答の記号が、別の人の実名に戻らないように）。"""
    d = Dictionary()
    d.register("山田太郎", "人名")
    d.register("鈴木花子", "人名")
    d.unregister("鈴木花子")
    assert d.register("佐藤次郎", "人名") == "〔人名Ｃ〕"
    # 記号でも解除できる
    assert d.unregister("〔人名Ａ〕").word == "山田太郎"


def test_pseudonymize_longest_first():
    d = Dictionary()
    d.register("山田", "人名")          # 短い語を先に登録しても
    d.register("山田太郎", "人名")
    assert d.pseudonymize("山田太郎と山田花子") == "〔人名Ｂ〕と〔人名Ａ〕花子"


def test_restore_including_half_width_letters_and_unknown():
    d = Dictionary()
    d.register("山田太郎", "人名")
    text, unknown = d.restore("〔人名Ａ〕と〔人名A〕と〔人名Ｚ〕")
    assert text == "山田太郎と山田太郎と〔人名Ｚ〕"
    assert unknown == ["〔人名Ｚ〕"]


def test_add_known_continues_letters():
    """構文ファイルと PDF から求めた対応を加えると、次の登録はその続きの英字になる。"""
    d = Dictionary()
    d.add_known("山田太郎", "〔人名Ｃ〕")
    d.note_used("〔人名Ｅ〕")
    assert d.register("佐藤次郎", "人名") == "〔人名Ｆ〕"


def test_spans_longest_first_non_overlapping():
    d = Dictionary()
    d.register("山田", "人名")
    d.register("山田太郎", "人名")
    spans = d.spans("山田太郎と山田")
    assert [(s, e, x.word) for s, e, x in spans] == [(0, 4, "山田太郎"), (5, 7, "山田")]


def test_tokens_in():
    assert tokens_in("〔人名Ａ〕と〔法人B〕と〔不明Ａ〕") == ["〔人名Ａ〕", "〔法人Ｂ〕"]


def test_rename_keeps_token():
    """元の語を変えても、記号は変わらない（過去の文書・テンプレートの使い回し。2026-10-25 班長指示）。"""
    d = Dictionary()
    d.register("山田太郎", "人名")
    d.register("鈴木花子", "人名")
    assert d.rename("〔人名Ａ〕", "佐藤次郎") == "山田太郎"
    assert d.find("〔人名Ａ〕").word == "佐藤次郎" and "山田太郎" not in d.entries
    assert d.restore("〔人名Ａ〕と〔人名Ｂ〕")[0] == "佐藤次郎と鈴木花子"
    assert d.rename("佐藤次郎", "佐藤次郎") == "佐藤次郎"        # 同じ語なら何もしない
    with pytest.raises(NotRegistrable):
        d.rename("〔人名Ａ〕", "鈴木花子")                           # ほかの記号の語
    with pytest.raises(NotRegistrable):
        d.rename("〔人名Ａ〕", "人名Ｃ")                             # 記号と重なる語
    assert d.find("〔人名Ａ〕").word == "佐藤次郎"
    assert d.register("田中一郎", "人名") == "〔人名Ｃ〕"
