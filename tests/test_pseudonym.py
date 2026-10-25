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
    """自動で振るとき（試験など。画面では利用者が選ぶ）は、解除した記号の英字を使い直さない。"""
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


def test_add_known_and_used_letters_are_skipped():
    """構文ファイルと PDF から求めた対応・構文ファイルにある記号の英字は使ったものとし、次の登録は、まだ使っていない
    いちばん小さい英字にする（2026-10-25 班長決定。それまでは、いちばん大きい英字の次）。"""
    d = Dictionary()
    d.add_known("山田太郎", "〔人名Ａ〕")
    d.note_used("〔人名Ｃ〕")
    assert d.register("佐藤次郎", "人名") == "〔人名Ｂ〕"
    assert d.register("田中一郎", "人名") == "〔人名Ｄ〕"


def test_choose_letters():
    """記号の英字を選べる（「依頼者はＡから、相手方はＸから」。2026-10-25 班長決定）。半角・小文字でもよい。
    今ほかの語に使っている記号は選べない。解除した記号は選べるが、別の語に付けるときは確かめる文を返す
    （2026-10-25 班長決定）。自動はＡから詰めて振る。"""
    d = Dictionary()
    assert d.register("乙山次郎", "人名", "x") == "〔人名Ｘ〕"
    assert d.register("甲野太郎", "人名") == "〔人名Ａ〕"
    assert d.register("乙山商事株式会社", "法人", "Ｘ") == "〔法人Ｘ〕"     # 種別が違えば同じ英字でよい
    with pytest.raises(NotRegistrable, match="使っています"):
        d.register("丙川三郎", "人名", "X")
    d.unregister("乙山次郎")
    assert d.reuse_warning("〔人名Ｘ〕", "乙山次郎") is None                 # 前と同じ語なら確かめない
    assert "「乙山次郎」に使った記号" in d.reuse_warning("〔人名Ｘ〕", "丙川三郎")
    assert d.reuse_warning("〔人名Ｑ〕", "丙川三郎") is None                 # 使ったことのない記号
    d.note_used("〔人名Ｒ〕")
    assert "別の語に使った記号" in d.reuse_warning("〔人名Ｒ〕", "丙川三郎")   # 前の語が分からない記号
    assert d.register("乙山次郎", "人名", "X") == "〔人名Ｘ〕"               # 解除した記号も選べる
    assert d.reuse_warning("〔人名Ｘ〕", "丙川三郎") is None                  # 今使っている記号（check_token で断る）
    for bad in ("Ａ 1", "Ａ*", "〔Ａ", "Ａ|Ｂ", "Ａ_Ｂ", "Ａ・Ｂ"):
        with pytest.raises(NotRegistrable, match="文字（英字・漢字・かな）と数字だけ"):
            d.register("丙川三郎", "人名", bad)
    with pytest.raises(NotRegistrable, match="記号の字を入れて"):
        d.check_token("人名", "")
    assert d.next_letters("人名") == "Ｂ" and d.register("丙川三郎", "人名") == "〔人名Ｂ〕"
    with pytest.raises(NotRegistrable, match="使っています"):
        d.register("丁野四郎", "人名", "x")
    assert "丙川三郎" in d.entries


def test_change_token():
    """登録した語の記号を変える。前の記号は、解除したものと同じく、別の語に付けるときに確かめる（2026-10-25 班長決定）。"""
    d = Dictionary()
    d.register("甲野太郎", "人名")
    d.register("乙山次郎", "人名")
    assert d.change_token("乙山次郎", "人名", "X") == "〔人名Ｂ〕"
    assert d.find("乙山次郎").token == "〔人名Ｘ〕" and d.find("〔人名Ｂ〕") is None
    assert d.change_token("乙山次郎", "人名", "X") == "〔人名Ｘ〕"       # 同じ記号なら何もしない
    with pytest.raises(NotRegistrable):
        d.change_token("乙山次郎", "人名", "A")                         # ほかの語の記号
    assert d.change_token("乙山次郎", "法人", "A") == "〔人名Ｘ〕"       # 種別も変えられる
    assert d.find("乙山次郎").kind == "法人"
    assert "「乙山次郎」に使った記号" in d.reuse_warning("〔人名Ｂ〕", "丙川三郎")
    assert d.register("丙川三郎", "人名") == "〔人名Ｃ〕"               # 自動は、使ったＢ・Ｘを飛ばす


def test_spans_longest_first_non_overlapping():
    d = Dictionary()
    d.register("山田", "人名")
    d.register("山田太郎", "人名")
    spans = d.spans("山田太郎と山田")
    assert [(s, e, x.word) for s, e, x in spans] == [(0, 4, "山田太郎"), (5, 7, "山田")]


def test_tokens_in():
    assert tokens_in("〔人名Ａ〕と〔法人B〕と〔不明Ａ〕") == ["〔人名Ａ〕", "〔法人Ｂ〕"]


def test_rename_keeps_token():
    """元の語を変えても、記号は変わらない（登録した語の誤りを直す。2026-10-25 班長決定）。"""
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


def test_free_labels():
    """記号の字は、英字・数字・漢字・かななど、字数の制限なく付けられる（氏名のイニシャル〔人名ＹＴ〕、番号〔人名１〕、
    漢字〔人名甲〕など。2026-10-25 班長指示）。半角の英数字・小文字は全角の大文字にそろえる。"""
    d = Dictionary()
    assert d.register("山田太郎", "人名", "yt") == "〔人名ＹＴ〕"
    assert d.register("山田花子", "人名", "ＹＨ") == "〔人名ＹＨ〕"
    assert d.register("鈴木一郎", "人名", "1") == "〔人名１〕"
    assert d.register("佐藤次郎", "人名", "甲") == "〔人名甲〕"
    assert d.register("株式会社乙山", "法人", "相手方会社2") == "〔法人相手方会社２〕"
    assert d.register("田中三郎", "人名", "abcdefghij") == "〔人名ＡＢＣＤＥＦＧＨＩＪ〕"
    assert d.pseudonymize("山田太郎と鈴木一郎") == "〔人名ＹＴ〕と〔人名１〕"
    assert d.restore("〔人名YT〕と〔人名1〕と〔人名甲〕と〔法人相手方会社2〕")[0] == "山田太郎と鈴木一郎と佐藤次郎と株式会社乙山"
    assert tokens_in("〔人名yt〕〔人名甲〕") == ["〔人名ＹＴ〕", "〔人名甲〕"]
    with pytest.raises(NotRegistrable, match="使っています"):
        d.register("矢田太一", "人名", "YT")
    assert d.next_letters("人名") == "Ａ"                    # 1字の英字の自動に影響しない


def test_words_inside_tokens_are_not_replaced():
    """記号の字に登録した語が入っていても（〔人名山田〕と「山田」）、置き換えるときに記号の中は飛ばす（2026-10-25）。"""
    d = Dictionary()
    d.register("山田太郎", "人名", "山田")
    d.register("山田", "人名", "Ｂ")
    assert d.pseudonymize("山田太郎と山田") == "〔人名山田〕と〔人名Ｂ〕"
    assert [(a, b) for a, b, _ in d.spans("〔人名山田〕と山田")] == [(7, 9)]
    assert d.pseudonymize("〔人名山田〕と〔人名不明〕と山田") == "〔人名山田〕と〔人名不明〕と〔人名Ｂ〕"
