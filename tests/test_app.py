"""画面（仕様.md の4）。確認画面（モーダル）は差し替えて、画面の操作の流れを確かめる。"""
import json
from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")

from tkinter import messagebox  # noqa: E402

from va_documake import ai_ops, app, config, file_ops, theme, vadm  # noqa: E402
from va_documake.pdfwriter import read_id  # noqa: E402

TEXT = "原告　甲野太郎\n:=: 準備書面（１）\n# 認否\n甲野太郎の主張は争う。\n"
PSEUDO = TEXT.replace("甲野太郎", "〔人名Ａ〕")      # エディターは常に仮名（2026-10-24 班長決定）


@pytest.fixture(scope="module")
def main_window():
    # Tk はモジュールで1つだけ作る（Windows の Python では、Tk を何度も作り直すと、まれに初期化に失敗する）
    try:
        w = app.MainWindow(cfg=config.AppConfig(vadm_folder="未使用"))
    except tk.TclError as e:
        pytest.skip(f"画面を表示できない環境（{e}）")
    w.withdraw()
    yield w
    w.destroy()


@pytest.fixture
def window(main_window, tmp_path, monkeypatch):
    # 班長の設定ファイル（%APPDATA%）には書かない
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "settings.json")
    w = main_window
    w.cfg = config.AppConfig(vadm_folder=str(tmp_path / "構文ファイル"))
    w.session = app.Session(w.cfg)
    w._load_text(TEXT)
    w.session.dictionary.register("甲野太郎", "人名")
    w._refresh_dictionary()
    w.refresh()
    return w


def test_theme(window):
    style = tk.ttk.Style(window)
    assert style.theme_use() == "clam"
    assert style.lookup("TButton", "background") == theme.CONTROL_BG
    assert style.lookup("TButton", "background", ["active"]) == theme.HOVER_BG
    assert style.lookup("TButton", "background", ["pressed"]) == theme.PRESSED_BG
    # 主要なボタンは枠線だけをアクセント色にする（地色は同じ）
    assert style.lookup("Accent.TButton", "bordercolor") == theme.ACCENT
    assert style.lookup("Accent.TButton", "background") == theme.CONTROL_BG


def test_preview_and_highlight(window):
    assert window._preview_doc is not None and len(window._preview_doc) == 1
    assert window.page_label.cget("text") == "1 / 1"
    ranges = window.text.tag_ranges("registered")
    assert [window.text.get(a, b) for a, b in zip(ranges[0::2], ranges[1::2])] == ["〔人名Ａ〕", "〔人名Ａ〕"]
    assert window.tree.get_children() == ("〔人名Ａ〕",)


def test_preview_scrolls_across_pages(window):
    """確認表示は全ページを縦に並べ、スクロールでページをまたいで送れる。"""
    window.deiconify()
    window.geometry("1200x800")
    window._load_text("\n".join(["# 見出し"] + ["本文の段落。" * 20] * 60))
    window.update()
    window._layout_pages(keep=False)
    window.update()
    n = len(window._preview_doc)
    assert n >= 3 and len(window._page_tops) == n
    assert window.page_label.cget("text") == f"1 / {n}"
    assert 0 in window._page_images and n - 1 not in window._page_images   # 見えているページだけ画像にする
    window.canvas.yview_moveto(1.0)          # スクロールバーを一番下へ
    window.update()
    window._render_visible()
    assert window.page_label.cget("text") == f"{n} / {n}" and n - 1 in window._page_images
    window.on_page(-1)
    window.update()
    assert window.page_label.cget("text") == f"{n - 1} / {n}"
    window.withdraw()


def test_editor_is_always_pseudonymized(window, monkeypatch):
    """エディターは常に仮名（記号）で、実名は確認表示で見る。仮名化した語を打つ・貼ると記号に置き換え、
    仮名化・解除でエディターの語と記号を入れ替える（2026-10-24 班長決定）。"""
    assert window.raw_text() == PSEUDO and window.real_text() == TEXT
    assert not hasattr(window, "view")
    # 仮名化した語を打つと、組み直すときに記号に置き換わる
    window.text.insert("end", "甲野太郎は認める。")
    window.refresh()
    assert window.raw_text().endswith("〔人名Ａ〕は認める。")
    # 仮名化した語を含む文章を貼ると、記号に置き換えて貼る（そのほかの文章は、ふつうの貼り付けに任せる）
    monkeypatch.setattr(window, "clipboard_get", lambda: "甲野太郎の陳述書と〔人名Ｚ〕の陳述書")
    window.text.mark_set("insert", "end")
    assert window._on_paste() == "break"
    assert window.raw_text().endswith("〔人名Ａ〕の陳述書と〔人名Ｚ〕の陳述書")
    monkeypatch.setattr(window, "clipboard_get", lambda: "ふつうの文章")
    assert window._on_paste() is None
    # 選んだ語を仮名化すると、エディターの同じ語がすべて記号になる
    window._load_text(TEXT + "乙山花子と乙山花子。\n")
    window.text.tag_add("sel", "5.0", "5.4")
    monkeypatch.setattr(ai_ops, "RegisterDialog", lambda parent, word, d: type("D", (), {"result": ("人名", "b")})())
    window.on_register()
    assert window.raw_text().endswith("〔人名Ｂ〕と〔人名Ｂ〕。\n")
    assert window.real_text().endswith("乙山花子と乙山花子。\n")
    # 解除すると、エディターの記号を元の語に戻す
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    window._unregister("〔人名Ｂ〕")
    assert window.raw_text().endswith("乙山花子と乙山花子。\n")
    # エディターの記号を選んで［選択範囲を仮名化］を押しても、解除できる
    window.text.tag_remove("sel", "1.0", "end")
    window.text.tag_add("sel", "1.3", "1.8")              # 「〔人名Ａ〕」
    window.on_register()
    assert "〔人名Ａ〕" not in window.raw_text() and window.raw_text().startswith("原告　甲野太郎")


def test_align_and_line_marks(window):
    window.text.mark_set("insert", "4.0")
    window.on_align("--: ")
    assert window.text.get("4.0", "4.end") == "--: 〔人名Ａ〕の主張は争う。"
    window.on_align(":-: ")
    assert window.text.get("4.0", "4.end") == ":-: 〔人名Ａ〕の主張は争う。"
    window.on_align(":-: ")   # 同じボタンをもう一度押すと解除する
    assert window.text.get("4.0", "4.end") == "〔人名Ａ〕の主張は争う。"
    # 複数の行：すべてが同じ記号のときだけ解除し、そうでなければそろえる
    window.text.tag_add("sel", "2.0", "4.end")
    window.on_align("--: ")
    assert [window.text.get(f"{n}.0", f"{n}.end") for n in (2, 3, 4)] == \
        ["--: 準備書面（１）", "--: # 認否", "--: 〔人名Ａ〕の主張は争う。"]
    window.on_align("--: ")
    assert [window.text.get(f"{n}.0", f"{n}.end") for n in (2, 3, 4)] == \
        ["準備書面（１）", "# 認否", "〔人名Ａ〕の主張は争う。"]
    window.text.edit_undo()      # Ctrl+Z 1回で、3行とも戻る
    assert window.text.get("2.0", "2.end") == "--: 準備書面（１）"
    window.text.tag_remove("sel", "1.0", "end")
    window.text.edit_undo()
    window.text.mark_set("insert", "4.0")
    window.on_line_mark("<<<")
    assert window.text.get("4.0", "4.end") == "<<<"


def test_save_and_import(window, tmp_path, monkeypatch):
    window.session.pdf_path = tmp_path / "準備書面.pdf"
    assert window.on_save()
    assert read_id(str(tmp_path / "準備書面.pdf")) == (window.session.doc_id, 1)
    assert window.session.vadm_path.exists()
    assert (tmp_path / "settings.json").exists()
    # ［貼り付け］：クリップボードの AI の回答を、確認の画面なしでエディターに取り込む
    # （班長のクリップボードを書き換えないよう、クリップボードの読み取りを差し替える）
    body = vadm.read_file(window.session.vadm_path).body_text.replace("争う。", "否認する。")
    answer = "直しました。\n```\n" + vadm.separator_line(window.session.doc_id, 1, window.session.settings) + "\n" + body + "\n```\n"
    monkeypatch.setattr(window, "clipboard_get", lambda: answer)
    window.on_import()
    assert "〔人名Ａ〕の主張は否認する。" in window.raw_text()          # エディターは仮名のまま
    assert "甲野太郎の主張は否認する。" in window.real_text()
    assert window.session.version == 2
    assert "否認する。" in window.session.vadm_path.read_text(encoding="utf-8")
    # 変わった段落（4行目）だけに、右端の青い線の印が付く
    ranges = window.text.tag_ranges("changed")
    assert [str(x) for x in ranges] == ["4.0", "5.0"]
    # Ctrl+Z（エディターの元に戻す）1回で、貼り付ける前の文章に戻る
    window.text.edit_undo()
    assert window.raw_text() == PSEUDO


def test_paste_rejects_other_document_and_plain_text(window, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(messagebox, "showerror", lambda *a, **k: shown.append(("error", a[1])))
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: shown.append(("info", a[1])))
    monkeypatch.setattr(window, "clipboard_get", lambda: "ふつうの文章")
    window.on_import()
    monkeypatch.setattr(window, "clipboard_get",
                        lambda: "==== VA DocuMake 文書ID ZZZZZZZZ 版 1 ====\n# 認否\n認める。")
    window.on_import()
    assert [k for k, _ in shown] == ["info", "error"] and "別の文書" in shown[1][1]
    assert window.raw_text() == PSEUDO        # どちらも、エディターは変わらない


def test_paste_warns_about_removed_paragraphs_and_tokens(window, tmp_path, monkeypatch):
    window.session.pdf_path = tmp_path / "準備書面.pdf"
    assert window.on_save()
    warned = []
    monkeypatch.setattr(messagebox, "showwarning", lambda *a, **k: warned.append(a[1]))
    sep = vadm.separator_line(window.session.doc_id, 1, window.session.settings)
    monkeypatch.setattr(window, "clipboard_get", lambda: sep + "\n原告　〔人名Ａ〕\n:=: 準備書面（１）\n# 認否\n")
    window.on_import()
    assert len(warned) == 1 and "消えた段落（1）" in warned[0] and "甲野太郎の主張は争う。" in warned[0]


def test_paste_drops_ai_marker_lines(window, tmp_path, monkeypatch):
    """AI の回答に混ざった内部の目印の行（<?thinking_complete?>）は、取り込むときに除き、状態の欄で知らせる。"""
    window.session.pdf_path = tmp_path / "準備書面.pdf"
    assert window.on_save()
    body = window.raw_text().rstrip("\n")
    sep = vadm.separator_line(window.session.doc_id, 1, window.session.settings)
    monkeypatch.setattr(window, "clipboard_get", lambda: sep + "\n" + body + "\n<?thinking_complete?>\n")
    window.on_import()
    assert "<?thinking_complete?>" not in window.raw_text()
    assert "AI の内部の目印と思われる行 1 行（<?thinking_complete?>）を除きました" in window.status.cget("text")


def _change_outside(window, old, new):
    path = window.session.vadm_path
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


def test_save_asks_when_vadm_changed_outside(window, tmp_path, monkeypatch):
    """構文ファイルが外で書き換えられていれば、黙って上書きしない（取り込む・上書きする・やめる）。"""
    window.session.pdf_path = tmp_path / "準備書面.pdf"
    assert window.on_save()
    asked = []

    def fake_changed(choice):
        class D:
            def __init__(self, parent, at_save):
                asked.append(at_save)
                self.result = choice
        return D

    # やめる：保存しない
    _change_outside(window, "争う。", "否認する。")
    monkeypatch.setattr(file_ops, "ChangedOutsideDialog", fake_changed(None))
    assert not window.on_save()
    assert asked == [True] and "否認する。" in window.session.vadm_path.read_text(encoding="utf-8")

    # 取り込む：外の中身をエディターに取り込んでから保存する
    monkeypatch.setattr(file_ops, "ChangedOutsideDialog", fake_changed("import"))
    assert window.on_save()
    assert "〔人名Ａ〕の主張は否認する。" in window.raw_text()
    assert window.session.version == 2 and not window.session.vadm_changed_outside()   # やめたときは保存していない

    # 上書きする：エディターの文章で保存する
    _change_outside(window, "否認する。", "認める。")
    monkeypatch.setattr(file_ops, "ChangedOutsideDialog", fake_changed("overwrite"))
    assert window.on_save()
    assert "否認する。" in window.session.vadm_path.read_text(encoding="utf-8")
    assert not window.session.vadm_changed_outside()


def test_find_and_replace(window):
    """検索と置換（Ctrl+F・Ctrl+H）。すべて置換は Ctrl+Z 1回で戻る。"""
    # ［検索］では置換の欄とボタンを出さず、［置換］では出す。開いたまま切り替わる（2026-10-25 班長指摘）
    window.on_find(False)
    d = window._find_dialog
    replace_parts = (d.replace_label, d.replace_entry, d.buttons["置換"], d.buttons["すべて置換"])
    assert d.title() == "検索" and not any(w.grid_info() for w in replace_parts)
    assert d.buttons["次を検索"].grid_info() and d.buttons["閉じる"].grid_info()
    window.on_find(True)
    assert window._find_dialog is d and d.title() == "置換" and all(w.grid_info() for w in replace_parts)
    window.on_find(False)
    assert d.title() == "検索" and not any(w.grid_info() for w in replace_parts)
    window.on_find(True)
    d.withdraw()
    d.find_var.set("甲野太郎")              # 仮名化した語で検索すると、エディターの記号を探す
    assert d.message.cget("text") == "2 件見つかりました。"
    assert len(window.text.tag_ranges("found")) == 4
    window.text.mark_set("insert", "1.0")
    window.text.tag_remove("sel", "1.0", "end")
    assert d.find(True)
    assert window.text.get("sel.first", "sel.last") == "〔人名Ａ〕" and window.text.index("sel.first") == "1.3"
    assert d.find(True) and window.text.index("sel.first") == "4.0"
    assert d.find(True) and window.text.index("sel.first") == "1.3"     # 最後まで行ったら初めから
    assert d.find(False) and window.text.index("sel.first") == "4.0"    # 前を検索
    # 置換：選んでいる1か所だけ
    d.replace_var.set("乙山花子")
    d.replace_one()
    assert window.raw_text().count("乙山花子") == 1 and window.raw_text().count("〔人名Ａ〕") == 1
    window.text.edit_undo()
    assert window.raw_text() == PSEUDO
    # すべて置換
    d.replace_all()
    assert window.raw_text() == PSEUDO.replace("〔人名Ａ〕", "乙山花子")
    assert d.message.cget("text").startswith("2 件を置換しました")
    window.text.edit_undo()
    assert window.raw_text() == PSEUDO
    # 大文字と小文字
    window._load_text("ABC abc")
    d.find_var.set("abc")
    assert d.message.cget("text") == "2 件見つかりました。"
    d.case_var.set(True)
    d.mark_all()
    assert d.message.cget("text") == "1 件見つかりました。"
    d.close()
    assert not window.text.tag_ranges("found")


def test_save_button_is_accent_only_when_modified(window, tmp_path):
    """［保存］は、保存していない変更があるときだけ青い枠（Accent.Ribbon.TButton）にする。"""
    window.session.pdf_path = tmp_path / "準備書面.pdf"
    window._update_title()
    assert str(window.save_button.cget("style")) == "Accent.Ribbon.TButton"      # まだ保存していない
    assert window.on_save()
    assert str(window.save_button.cget("style")) == "Ribbon.TButton"
    window.text.insert("end", "追記。")
    window.on_text_modified()
    assert str(window.save_button.cget("style")) == "Accent.Ribbon.TButton"


def test_ribbon_groups_and_reflow(window):
    """ボタンは Word のリボンと同じく組に分け、組の名前を下端にそろえて書く。大きいボタンは［選択範囲を仮名化］だけ。
    狭いときは、入らない組を次の段に送る（2026-10-24 班長指示）。"""
    rb = window.ribbon
    titles = [str(g.grid_slaves(row=1, column=0)[0].cget("text")) for g in rb.groups]
    assert titles == ["ファイル", "AI 連携", "スタイル", "書式", "挿入", "編集", "表示"]
    # 文書の種類・ページ番号の選択欄は「スタイル」の組にあり、左端がそろう（2026-10-25 に「書式」から分けた）
    window.update_idletasks()
    assert window.doc_type_box.winfo_x() == window.page_number_box.winfo_x()
    w = window.doc_type_box
    while w is not None and w not in rb.groups:
        w = w.master
    assert w is rb.groups[2]
    # 「スタイル」は選択欄と［見出し］［箇条書き］［段落番号］、「書式」は［太字］から右（2026-10-25 班長指示）
    found = {str(b.cget("text")): b for b in _all_buttons(window)}
    for text, k in (("見出し", 2), ("箇条書き", 2), ("段落番号", 2), ("太字", 3), ("傍点", 3), ("均等割付", 3), ("表題", 3)):
        assert found[text].master is rb.groups[k].body, text
    assert [int(found[t].grid_info()["row"]) for t in ("見出し", "箇条書き", "段落番号")] == [0, 1, 2]
    rb.reflow(10 ** 6)
    window.update_idletasks()
    full = sum(g.winfo_reqwidth() for g in rb.groups)
    rb.reflow(full + 10)
    assert len(rb._layout) == 1
    assert str(window.register_button.cget("compound")) == "top"
    assert str(window.register_button.cget("text")) == "選択範囲を\n仮名化"     # 大きいボタンは2行
    rb.reflow(full - 10)
    assert len(rb._layout) == 2 and len(rb._layout[1]) == 1                  # 入らない最後の組だけを次の段に
    rb.reflow(400)
    assert len(rb._layout) >= 2
    # どの段も、組を左から詰めて置く（上の段の組の幅に引きずられて間が空かない。2026-10-25 班長指摘）
    window.update_idletasks()
    by_id = {id(g): g for g in rb.groups}
    for row in rb._layout:
        groups = [by_id[i] for i in row]
        assert groups[0].winfo_x() == 0
        for a, b in zip(groups, groups[1:]):
            assert b.winfo_x() == a.winfo_x() + a.winfo_reqwidth()
    rb.reflow(full + 10)
    assert len(rb._layout) == 1


@pytest.mark.skipif(app.os.name != "nt", reason="IME の書体は Windows だけ")
def test_ime_composition_font_matches_editor(window):
    """IME の入力中の文字を、エディターと同じ書体で表示する（Tk のままでは System の小さい書体になる）。"""
    from va_documake import ime
    family, size = theme.editor_font(window)
    assert ime.set_composition_font(window.text, family, size) >= 1
    face, height = ime.composition_font(window.text)
    assert face == family and height == -round(size * window.text.winfo_fpixels("1i") / 72)


class _Click:
    def __init__(self, x, y):
        self.x, self.y = x, y


def _canvas_point(window, line, col):
    """実名の文章の (行, 字) が、確認表示（canvas の中）のどこにあるか。"""
    page, x, top, h = window.session.layout_map.locate(line, col)
    z = window._render_zoom
    return window._page_x + (x + 1) * z - window.canvas.canvasx(0), \
        window._page_tops[page] + (top + h / 2) * z - window.canvas.canvasy(0), page


def test_editor_and_preview_are_linked(window):
    """エディターのカーソル → 確認表示のページ、確認表示のクリック → エディターのカーソル。"""
    window.deiconify()
    window.geometry("1200x800")
    text = (Path(__file__).parent / "data" / "長い文書" / "見本.md").read_text(encoding="utf-8")
    window._load_text(text)
    window.update()
    window._layout_pages(keep=False)
    window.update()
    # エディターで最後の行にカーソルを置くと、確認表示は最後のページに送られ、印が付く
    last = len(text.splitlines())
    window.text.mark_set("insert", f"{last}.0")
    window._show_caret()
    window.update()
    n = len(window._preview_doc)
    assert window.page_label.cget("text") == f"{n} / {n}"
    assert window.canvas.find_withtag("caret")
    # 編集中のページ（最後のページ）を太線で囲む
    frame = window.canvas.find_withtag("current_page")
    assert len(frame) == 1
    assert window.canvas.coords(frame[0])[1] < window._page_tops[n - 1] < window.canvas.coords(frame[0])[3]
    # 確認表示の字をクリックすると、エディターのカーソルがその字へ動く
    line = last - 3
    col = len(text.splitlines()[line]) - 2     # 本文の字（行頭の「##」などの記号の上ではない）
    x, y, page = _canvas_point(window, line, col)
    window.on_preview_click(_Click(x, y))
    assert window.text.index("insert") == f"{line + 1}.{col}"
    window.withdraw()


def test_linking_converts_token_lengths(window):
    """エディターは仮名なので、記号と元の語の長さの違いを換算して確認表示と連動する。"""
    window.deiconify()
    window.geometry("1200x800")
    window.update()
    window._layout_pages(keep=False)
    window.update()
    # エディターの行「〔人名Ａ〕の主張は争う。」の「主」→ 実名の行「甲野太郎の主張は争う。」の「主」
    vline = window.text.get("4.0", "4.end")
    assert vline == "〔人名Ａ〕の主張は争う。"
    assert window._token_col(vline, vline.index("主"), to_real=True) == "甲野太郎の主張は争う。".index("主")
    # 確認表示の「主」をクリックすると、エディターの「主」にカーソルが動く
    x, y, _ = _canvas_point(window, 3, "甲野太郎の主張は争う。".index("主"))
    window.on_preview_click(_Click(x, y))
    assert window.text.index("insert") == f"4.{vline.index('主')}"
    window.withdraw()


def test_save_guard_for_tokens_and_separator(window, tmp_path, monkeypatch):
    window.session.pdf_path = tmp_path / "準備書面.pdf"
    errors = []
    monkeypatch.setattr(messagebox, "showerror", lambda *a, **k: errors.append(a[1]))
    # 区切りの行が紛れ込んでいたら、保存しない
    window.text.insert("end", "==== VA DocuMake 文書ID ABCDEFGH 版 1 ====\n")
    assert not window.on_save()
    assert errors and not (tmp_path / "準備書面.pdf").exists()
    assert "Ctrl+Z" in errors[0] and "［貼り付け］で取り込んで" in errors[0]      # AI の回答を Ctrl+V で貼ったときの案内
    # 仮名化した語の記号は、実名に戻して保存する（PDF に記号は出ない）
    window._load_text(TEXT + "〔人名Ａ〕の陳述書による。\n")
    assert window.on_save()
    import fitz
    with fitz.open(tmp_path / "準備書面.pdf") as doc:
        pdf_text = "".join(page.get_text() for page in doc)
    assert "〔" not in pdf_text and "甲野太郎の陳述書" in pdf_text
    # 仮名化した語にない記号（AI が作った記号など）は、PDF に記号のまま出ることを知らせて尋ねる
    asked = []
    window.text.insert("end", "〔人名Ｚ〕の陳述書。\n")
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: asked.append(a[1]))
    assert not window.on_save()
    assert asked and "〔人名Ｚ〕" in asked[0]


@pytest.fixture
def quiet_faulthandler():
    """Microsoft Print to PDF のドライバーは、中で Windows の例外（0x80040155）を起こして中で処理する。
    pytest の faulthandler がそれを「fatal exception」と書き出して紛らわしいので、そのテストの間は止める。"""
    import faulthandler
    was = faulthandler.is_enabled()
    faulthandler.disable()
    yield
    if was:
        faulthandler.enable()


@pytest.mark.skipif(app.os.name != "nt", reason="印刷は Windows だけ")
def test_print_to_pdf_printer(window, tmp_path, monkeypatch, quiet_faulthandler):
    """［印刷］：Microsoft Print to PDF に印刷し、実際のサイズ（A4）で、字の位置がずれないことを確かめる。"""
    import fitz
    from va_documake import printing
    if "Microsoft Print to PDF" not in printing.printers():
        pytest.skip("Microsoft Print to PDF がない")
    out = tmp_path / "印刷.pdf"
    # VA DocuMake の印刷画面で「Microsoft Print to PDF」・1部・すべてのページを選んだことにする
    chosen = []

    class Choose:
        def __init__(self, parent, pages, current_page, names, default, show_properties):
            chosen.append((pages, current_page, default))
            self.result = ("Microsoft Print to PDF", None, 1, list(range(pages)))
    monkeypatch.setattr(file_ops, "PrintDialog", Choose)
    errors = []
    monkeypatch.setattr(messagebox, "showerror", lambda *a, **k: errors.append(a[1]))
    real_print = printing.print_pdf
    names = []

    def to_file(data, dc, name, pages=None, output=None, progress=None):
        names.append(name)
        return real_print(data, dc, name, pages, output=str(out), progress=progress)
    monkeypatch.setattr(printing, "print_pdf", to_file)
    window.on_print()
    assert names == ["VA DocuMake"]          # 保存していない文書は「VA DocuMake」
    window.session.pdf_path = tmp_path / "準備書面（１）.pdf"
    names.clear()
    window.on_print()
    assert names == ["準備書面（１）"]       # 保存した文書は、Word と同じく PDF のファイル名
    for _ in range(50):
        if out.exists() and out.stat().st_size:
            break
        import time
        time.sleep(0.2)
    with fitz.open(out) as doc:
        assert len(doc) >= 1 and abs(doc[0].rect.width - 595.3) < 1 and abs(doc[0].rect.height - 841.9) < 1
    assert not errors and "1 ページをプリンターに送りました" in window.status.cget("text")
    assert chosen[1][2] == "Microsoft Print to PDF"            # 前に使ったプリンターを選んでおく


def _lines(window, a, b):
    return [window.text.get(f"{n}.0", f"{n}.end") for n in range(a, b + 1)]


def test_word_shortcuts(window, monkeypatch):
    """Word と同じショートカットキー（Ctrl+E・Ctrl+R・Ctrl+Enter）と、Tk のもとのキーを外したこと。"""
    window.text.focus_force()
    window.text.mark_set("insert", "4.2")
    window.text.event_generate("<Control-Key-e>")
    assert _lines(window, 4, 4) == [":-: 〔人名Ａ〕の主張は争う。"]
    window.text.event_generate("<Control-Key-e>")          # もう一度押すと解除（Word と同じ）
    assert _lines(window, 4, 4) == ["〔人名Ａ〕の主張は争う。"]
    window.text.event_generate("<Control-Key-r>")
    assert _lines(window, 4, 4) == ["--: 〔人名Ａ〕の主張は争う。"]
    window.text.edit_undo()
    window.text.mark_set("insert", "4.0")
    window.text.event_generate("<Control-Return>")
    assert _lines(window, 4, 5) == ["<<<", "〔人名Ａ〕の主張は争う。"]
    # Tk のもとの Ctrl+O（改行を入れる）・Ctrl+K（行末まで消す）は働かない
    opened = []
    monkeypatch.setattr(window, "on_open", lambda: opened.append(True))
    window._bind_keys()
    before = window.raw_text()
    window.text.event_generate("<Control-Key-o>")
    window.text.event_generate("<Control-Key-k>")
    assert window.raw_text() == before and opened == [True]


def test_outline_level_and_plain(window):
    """Alt+Shift+←／→ で見出しのレベルを上げ下げし、Ctrl+Shift+N で標準の本文にする（Word と同じ）。"""
    window._load_text("# 第一\n## 第二\n本文\n- 項目\n--: 以上")
    window.text.focus_force()
    window.text.mark_set("insert", "2.0")
    window.text.event_generate("<Alt-Shift-Left>")
    assert _lines(window, 2, 2) == ["# 第二"]
    window.text.event_generate("<Alt-Shift-Left>")          # # から上げると本文（2026-10-25 班長指示）
    assert _lines(window, 2, 2) == ["第二"]
    window.text.event_generate("<Alt-Shift-Right>")         # 本文を下げると、直前の見出し（#）と同じレベル
    assert _lines(window, 2, 2) == ["# 第二"]
    window.text.event_generate("<Alt-Shift-Right>")
    window.text.event_generate("<Alt-Shift-Right>")
    assert _lines(window, 2, 2) == ["### 第二"]
    # 本文を上げると、直前の見出しと同じレベルの見出し
    window.text.mark_set("insert", "3.0")
    window.text.event_generate("<Alt-Shift-Left>")
    assert _lines(window, 3, 3) == ["### 本文"]
    # 9 から下げると本文
    window._load_text("######### 九")
    window.text.mark_set("insert", "1.0")
    window.text.event_generate("<Alt-Shift-Right>")
    assert _lines(window, 1, 1) == ["九"]
    # Ctrl+Shift+N：選んだ行を標準の本文に（見出し・箇条書き・配置の記号を外す）。Ctrl+Z 1回で戻る
    window._load_text("# 第一\n- 項目\n--: 以上\n1. 番号")
    window.text.tag_add("sel", "1.0", "4.end")
    window.text.event_generate("<Control-Shift-Key-N>")
    assert _lines(window, 1, 4) == ["第一", "項目", "以上", "番号"]
    window.text.edit_undo()
    assert _lines(window, 1, 4) == ["# 第一", "- 項目", "--: 以上", "1. 番号"]
    window.text.tag_remove("sel", "1.0", "end")


def test_heading_bullet_number_buttons(window):
    """［見出し］［箇条書き］［段落番号］：選んだ行の行頭に ## ・- ・1. を付け、ほかの種類の記号とは付け替える。すべて既に
    その種類なら外す（見出しはどの段でも）。空の行・配置の記号の行・表には付けない。Ctrl+Z 1回で戻る（2026-10-25 班長指示）。"""
    window._load_text("本文\n- 項目\n\n:-: 中央\n**# 第一**\n| a | b |")
    window.text.tag_add("sel", "1.0", "6.end")
    window.on_paragraph_kind("## ")
    assert _lines(window, 1, 6) == ["## 本文", "## 項目", "", ":-: 中央", "## **第一**", "| a | b |"]
    window.on_paragraph_kind("## ")                 # すべて見出しなので外す
    assert _lines(window, 1, 6) == ["本文", "項目", "", ":-: 中央", "**第一**", "| a | b |"]
    window.text.edit_undo()
    assert _lines(window, 1, 2) == ["## 本文", "## 項目"]
    window._load_text("### 三段\n  字下げした本文\n2. 番号")
    window.text.tag_add("sel", "1.0", "3.end")
    window.on_paragraph_kind("1. ")                 # 「2. 」も段落番号なので、外さずにそろえる
    assert _lines(window, 1, 3) == ["1. 三段", "1. 字下げした本文", "1. 番号"]
    window.on_paragraph_kind("- ")
    assert _lines(window, 1, 3) == ["- 三段", "- 字下げした本文", "- 番号"]
    window.on_paragraph_kind("- ")
    assert _lines(window, 1, 3) == ["三段", "字下げした本文", "番号"]
    window.text.tag_remove("sel", "1.0", "end")
    window._load_text("# 見出し")                   # 選んでいなければカーソルの行。段の違う見出しも外す
    window.text.mark_set("insert", "1.2")
    window.on_paragraph_kind("## ")
    assert _lines(window, 1, 1) == ["見出し"]
    # 字のない行（まだ打っていない行）にも付け、カーソルを行末に置く。もう一度押すと外す（2026-10-25 班長指示）
    window._load_text("前文\n\n後")
    for mark in ("## ", "- ", "1. "):
        window.text.mark_set("insert", "2.0")
        window.on_paragraph_kind(mark)
        assert _lines(window, 2, 2) == [mark] and window.text.index("insert") == f"2.{len(mark)}"
        window.on_paragraph_kind(mark)
        assert _lines(window, 2, 2) == [""]
    window.text.mark_set("insert", "2.0")             # 続けて打てば、その種類の行になる
    window.on_paragraph_kind("- ")
    window.text.insert("insert", "項目")
    assert _lines(window, 1, 3) == ["前文", "- 項目", "後"]
    # 字のある行と一緒に選んだ字のない行（1行の空き）には付けない
    window._load_text("一\n\n二")
    window.text.tag_add("sel", "1.0", "3.end")
    window.on_paragraph_kind("- ")
    assert _lines(window, 1, 3) == ["- 一", "", "- 二"]
    window.text.tag_remove("sel", "1.0", "end")
    # Alt+Shift+← も、字のない行を見出しの記号だけの行にする（直前の見出しと同じレベル）
    window._load_text("### 三\n")
    window.text.mark_set("insert", "2.0")
    window.on_outline(-1)
    assert _lines(window, 2, 2) == ["### "] and window.text.index("insert") == "2.4"
    window.on_outline(1)                             # 下げるのは、ふつうの見出しと同じ
    assert _lines(window, 2, 2) == ["#### "]
    window._load_text("### 三\n本文\n")
    window.text.mark_set("insert", "2.0")
    window.on_outline(1)                             # 本文を下げても、直前の見出しと同じレベル（2026-10-25 班長指示）
    assert _lines(window, 2, 2) == ["### 本文"]
    window.text.mark_set("insert", "3.0")
    window.on_outline(1)                             # 字のない行も同じ
    assert _lines(window, 3, 3) == ["### "]
    window._load_text("# 第一\n")
    window.text.mark_set("insert", "2.0")
    window.on_outline(-1)
    assert _lines(window, 2, 2) == ["# "]
    window.on_outline(-1)                            # # から上げると、字のない行に戻る
    assert _lines(window, 2, 2) == [""]
    # 前に見出しがなければ、上げても下げても ##（［見出し］と同じ。2026-10-25 班長指示）
    for step in (-1, 1):
        window._load_text("前文\n")
        window.text.mark_set("insert", "2.0")
        window.on_outline(step)
        assert _lines(window, 2, 2) == ["## "]
        window.text.mark_set("insert", "1.0")
        window.on_outline(step)                      # 本文の行も同じ
        assert _lines(window, 1, 1) == ["## 前文"]


def test_marks_are_blue(window):
    """配置・改ページなどの記号は、青い字（確認表示の印と同じ色）で示す。記号として読まれない所は色を付けない。"""
    window._load_text(":=: 準備書面\n本文に--: と書いた\n<<<\n| :-: 科目 | 金額 |\n|---|---|\n| a | b |")
    window._highlight()
    ranges = window.text.tag_ranges("mark")
    marked = [window.text.get(a, b) for a, b in zip(ranges[0::2], ranges[1::2])]
    assert [m for m in marked if m.strip() in (":=:", ":-:", "--:", "<<<")] == [":=: ", "<<<", ":-: "]
    assert window.text.tag_cget("mark", "foreground") == theme.ACCENT


def test_markdown_marks_are_blue(window):
    """見出しの #・箇条書きの「- 」・段落番号の「1. 」・表の | と区切りの行も、同じ青い字で示す（読まれる所だけ）。"""
    window._load_text("# 見出し\n- 項目\n1. 番号\n| A | B |\n|---|---|\n| a | b |\n--: 以上\n# 見出しにしない")
    window._highlight()
    ranges = window.text.tag_ranges("mark")
    marked = [window.text.get(a, b) for a, b in zip(ranges[0::2], ranges[1::2])]
    assert marked == ["# ", "- ", "1. ", "|", "|", "|", "|---|---|", "|", "|", "|", "--: "]


def test_first_line_indent_button(window):
    """［字下げ］：行頭に -> を付け、もう一度押すと外す。ほかの配置の記号とは付け替える。青い字で示す。"""
    window._load_text("前文\n# 見出し")
    window.text.mark_set("insert", "1.0")
    window.on_align("-> ")
    assert _lines(window, 1, 1) == ["-> 前文"]
    window.on_align(":-: ")
    assert _lines(window, 1, 1) == [":-: 前文"]
    window.on_align("-> ")
    window._highlight()
    ranges = window.text.tag_ranges("mark")
    assert "-> " in [window.text.get(a, b) for a, b in zip(ranges[0::2], ranges[1::2])]
    window.on_align("-> ")
    assert _lines(window, 1, 1) == ["前文"]


def test_buttons_have_icons(window):
    """ボタンにアイコン（Fluent UI System Icons）を付ける。ページ送り・表示倍率はアイコンだけ。"""
    from tkinter import ttk
    from va_documake import icons
    assert window.icons is not None

    def buttons(w):
        # メインの画面のボタンだけ（検索と置換などの別の画面〔Toplevel〕は見ない）
        for c in w.winfo_children():
            if isinstance(c, tk.Toplevel):
                continue
            if isinstance(c, ttk.Button):
                yield c
            yield from buttons(c)
    found = {str(b.cget("text")).replace("\n", ""): b for b in buttons(window)}
    for text in ("開く", "保存", "印刷", "閉じる", "オプション", "選択範囲を仮名化", "コピー", "貼り付け", "表題", "中央", "右", "字下げ", "インデント", "太字", "均等割付",
                 "見出し", "箇条書き", "段落番号", "改ページ", "セクション区切り", "ヘッダー", "検索", "置換", "蛍光ペン", "幅に合わせる"):
        assert found[text].cget("image"), text
        # リボンの大きいボタン（［選択範囲を仮名化］）はアイコンの下に字、ほかはアイコンの右に字
        large = text == "選択範囲を仮名化"
        assert str(found[text].cget("compound")) == ("top" if large else "left"), text
    icon_only = [b for b in buttons(window) if not str(b.cget("text")) and b.cget("image")]
    assert len(icon_only) == 4
    # 使うアイコンのファイルと、ライセンスの文書がそろっている
    for name in list(icons.BUTTON_ICONS.values()) + list(icons.ICON_ONLY.values()):
        assert (icons.ICON_DIR / f"{name}.svg").exists(), name
    assert "MIT License" in (icons.ICON_DIR / "LICENSE").read_text(encoding="utf-8")
    assert icons.render_png("save", 24, theme.TEXT)[:4] == b"\x89PNG"
    # Office の色付きアイコンのように2色（塗りつぶし版を薄い青で下に敷く。2026-10-24 班長指示）
    for name in list(icons.BUTTON_ICONS.values()) + list(icons.ICON_ONLY.values()):
        assert (icons.ICON_DIR / f"{name}_filled.svg").exists(), name
    import fitz
    pix = fitz.Pixmap(icons.render_png("save", 32, theme.TEXT, theme.ICON_TINT))
    tint = tuple(int(theme.ICON_TINT[k:k + 2], 16) for k in (1, 3, 5))
    colors = {pix.pixel(x, y)[:3] for x in range(pix.width) for y in range(pix.height) if pix.pixel(x, y)[3] == 255}
    assert tint in colors and tuple(int(theme.TEXT[k:k + 2], 16) for k in (1, 3, 5)) in colors


def test_buttons_have_tooltips(window):
    """ボタンにマウスを重ねると説明が出る（ショートカットキーも書く）。"""
    from va_documake import tooltip
    tips = {t.text: t for t in window._tooltips}
    assert len(window._tooltips) >= 20
    assert "Ctrl+S" in tooltip.TIPS["保存"] and tooltip.TIPS["保存"] in tips
    assert "Ctrl+B" in tooltip.TIPS["太字"] and tooltip.TIPS["太字"] in tips
    assert "Ctrl+I" in tooltip.TIPS["インデント"] and tooltip.TIPS["インデント"] in tips
    assert "Ctrl+Alt+H" in tooltip.TIPS["蛍光ペン"] and tooltip.TIPS["蛍光ペン"] in tips
    # アイコンだけのボタン（＜ ＞ － ＋）にも、説明が付いている
    for key in ("＜", "＞", "－", "＋"):
        assert tooltip.TIPS[key] in tips
    # メインの画面のボタン・チェックは、すべて説明を持つ（ボタンを足したときの付け忘れを見つける。2026-10-25、
    # ［ヘッダー］に説明がなかった）。アイコンだけのボタンは、字の代わりにアイコンの名前で見る
    from va_documake import icons
    names = {v: k for k, v in icons.ICON_ONLY.items()}

    def labels(w):
        for c in w.winfo_children():
            if isinstance(c, tk.Toplevel):
                continue
            if isinstance(c, (tk.ttk.Button, tk.ttk.Radiobutton, tk.Checkbutton)):
                text = str(c.cget("text")).replace("\n", "")
                if not text:
                    image = str(c.cget("image")).split()
                    text = next((k for n, k in names.items() for i in image if n in i), "")
                yield text, c
            yield from labels(c)
    missing = [text for text, c in labels(window) if text and text not in tooltip.TIPS]
    assert not missing, missing
    assert tooltip.TIPS["ヘッダー"] in tips
    window.deiconify()
    window.update()
    tip = tips[tooltip.TIPS["保存"]]
    tip.show()
    assert tip._win is not None and tip._win.winfo_exists()
    tip.hide()
    assert tip._win is None
    window.withdraw()


def test_app_icon_exists():
    """アプリのアイコン（16〜256 画素の7つの大きさ）がある。scripts/generate_icon.py で作り直せる。"""
    from PIL import Image
    path = app.window_icon_path()
    assert path.exists()
    with Image.open(path) as im:
        assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= set(im.info["sizes"])


def test_window_position_is_restored(tmp_path):
    """閉じたときのウィンドウの大きさ・位置・確認表示の幅を、次の起動で戻す（Tk を作り直すので、別のプロセスで試す）。"""
    import subprocess
    import sys
    src = str(Path(__file__).resolve().parents[1] / "src")
    settings = tmp_path / "settings.json"
    common = (f"import sys, json, pathlib; sys.path.insert(0, {src!r})\n"
              "from va_documake import config, app\n"
              f"config.config_path = lambda: pathlib.Path({str(settings)!r})\n"
              f"cfg = config.load(); cfg.vadm_folder = {str(tmp_path)!r}\n"
              "w = app.MainWindow(cfg=cfg)\n")
    first = common + ("w.geometry('1100x720+60+70'); w.update()\n"
                      "w.panes.sash_place(0, 500, 0); w.update()\n"
                      "w.doc_type_box.set('内容証明'); w.page_number_box.set('右上'); w.on_settings_changed()\n"
                      "w.on_close()\n")
    second = common + ("w.after(2000, w.quit); w.mainloop()\n"
                       "print(w.geometry()); print(w.panes.sash_coord(0)[0]);"
                       "print(w.session.settings.doc_type, w.session.settings.page_number); w.destroy()\n")
    subprocess.run([sys.executable, "-c", first], check=True, timeout=60)
    saved = json.loads(settings.read_text(encoding="utf-8"))
    assert saved["window_geometry"] == "1100x720+60+70" and saved["window_zoomed"] is False
    assert abs(saved["preview_width"] - 500) <= 2
    out = subprocess.run([sys.executable, "-c", second], check=True, timeout=60, capture_output=True, text=True).stdout
    geometry, sash, doc_type, page_number = out.split()
    assert geometry == "1100x720+60+70" and abs(int(sash) - 500) <= 2
    # 文書の種類・ページ番号も、前回の設定で始まる
    assert (doc_type, page_number) == ("Naiyou", "TopRight")


def test_off_screen_geometry_is_ignored():
    """前回の位置が、今つながっていない画面（外したモニターなど）にあれば使わない。"""
    assert app._on_screen("1100x720+60+70")
    assert not app._on_screen("1100x720+-30000+70")
    assert not app._on_screen("こわれた値")
    assert not app._on_screen("10x10+60+70")


def test_toc_button_and_preview_link(window):
    """［目次］：カーソルの行の前に [TOC:3] を入れ（段数は手で直す。2026-10-24 班長指示）、青い字で示す。
    目次の行をクリックしても連動が崩れない。"""
    window._load_text("# 第一\n本文\n# 第二\n本文")
    window.text.mark_set("insert", "1.0")
    from tkinter import ttk

    def buttons(w):
        for c in w.winfo_children():
            if isinstance(c, ttk.Button):
                yield c
            yield from buttons(c)
    next(b for b in buttons(window.ribbon) if str(b.cget("text")) == "目次").invoke()
    assert _lines(window, 1, 2) == ["[TOC:3]", "# 第一"]
    window.refresh()
    ranges = window.text.tag_ranges("mark")
    assert "[TOC:3]" in [window.text.get(a, b) for a, b in zip(ranges[0::2], ranges[1::2])]
    m = window.session.layout_map
    page, x, top, h = m.locate(0, 0)          # [TOC] の行 → 目次の1行目
    assert page == 0
    assert m.hit(page, x + 1, top + h / 2)[0] == 0


def test_bold_shortcut_and_highlight(window):
    """Ctrl+B（on_bold）で選んだ字を **…** で囲み、もう一度で外す。記号は青、中の字は太字で示す（2026-10-24）。"""
    window._load_text("# 認否\n主張は争う。\n")
    window.text.tag_add("sel", "2.0", "2.2")           # 「主張」
    window.on_bold()
    assert window.text.get("2.0", "2.end") == "**主張**は争う。"
    assert window.text.get("sel.first", "sel.last") == "主張"
    window._highlight()
    marks = window.text.tag_ranges("mark")
    texts = [window.text.get(a, b) for a, b in zip(marks[0::2], marks[1::2])]
    assert texts.count("**") == 2
    bold = window.text.tag_ranges("bold")
    assert [window.text.get(a, b) for a, b in zip(bold[0::2], bold[1::2])] == ["主張"]
    window.on_bold()                                     # 同じ選択でもう一度押すと外す
    assert window.text.get("2.0", "2.end") == "主張は争う。"
    window.text.edit_undo()                              # Ctrl+Z 1回で、外す前に戻る
    assert window.text.get("2.0", "2.end") == "**主張**は争う。"

def test_outline_and_plain_on_heading_wrapped_in_bold(window):
    """「**# 見出し**」の行も、Alt+Shift+→（on_outline）・Ctrl+Shift+N（on_plain）で見出しとして扱う。"""
    window._load_text("**# 請求原因**\n本文。\n")
    window.text.mark_set("insert", "1.3")
    window.on_outline(1)
    assert window.text.get("1.0", "1.end") == "## **請求原因**"
    window.on_plain()
    assert window.text.get("1.0", "1.end") == "**請求原因**"

def test_bold_on_heading_line_applies_to_same_level(window):
    """見出しの行で［太字］を押すと、同じ段の見出しの行をすべて太字にし、もう一度で外す（2026-10-24 班長決定）。
    見出しの一部だけを選んだときは、その字だけ。本文の行で、選ばずに押しても何もしない。"""
    window._load_text("# 請求の原因\n本文。\n## 小見出し\n**# 被告の主張**\n本文の**一部**。\n# 結論\n")

    def lines():
        return window.raw_text().split("\n")[:6]
    window.text.mark_set("insert", "1.2")
    window.on_bold()
    # 「**# 見出し**」の形は、VA DocuMakeが書く形（# **見出し**）にそろう
    assert lines() == ["# **請求の原因**", "本文。", "## 小見出し", "# **被告の主張**", "本文の**一部**。", "# **結論**"]
    window.text.mark_set("insert", "6.3")
    window.on_bold()                                     # 太字の見出しで押すと、同じ段の太字をすべて外す
    assert lines() == ["# 請求の原因", "本文。", "## 小見出し", "# 被告の主張", "本文の**一部**。", "# 結論"]
    window.text.edit_undo()                              # Ctrl+Z 1回で、外す前に戻る
    assert lines()[0] == "# **請求の原因**" and lines()[5] == "# **結論**"
    # 見出しの字をすべて選んだときも、同じ段をそろえる
    window._load_text("# 請求の原因\n# 結論\n")
    window.text.tag_add("sel", "1.2", "1.end")
    window.on_bold()
    assert window.raw_text().split("\n")[:2] == ["# **請求の原因**", "# **結論**"]
    # 見出しの一部だけを選んだときは、その字だけ
    window._load_text("# 請求の原因\n# 結論\n")
    window.text.tag_add("sel", "1.2", "1.4")
    window.on_bold()
    assert window.raw_text().split("\n")[:2] == ["# **請求**の原因", "# 結論"]
    # 本文の行で、選ばずに押しても何もしない
    window._load_text("本文。\n")
    window.text.mark_set("insert", "1.1")
    window.on_bold()
    assert window.raw_text().startswith("本文。")

def test_marks_wrapped_in_bold_in_editor(window):
    """「**:=: 準備書面**」の記号も青く示し、［中央］で付け替えられる。AI の回答で太字に囲まれても、
    記号が消えたとはみなさない（2026-10-24 班長指示）。"""
    window._load_text("**:=: 準備書面（１）**\n# 認否\n")
    window._highlight()
    # 「**」「:=: 」は青、「準備書面」は青でない（太字）
    assert all("mark" in window.text.tag_names(f"1.{c}") for c in range(6))
    assert "mark" not in window.text.tag_names("1.6") and "bold" in window.text.tag_names("1.6")
    window.text.mark_set("insert", "1.5")
    window.on_align(":-: ")
    assert window.text.get("1.0", "1.end") == ":-: **準備書面（１）**"
    r = vadm.review(vadm.parse_text("==== VA DocuMake 文書ID K7Q29XMD 版 1 ====\n**:=: 準備書面**\n"),
                     "K7Q29XMD", 1, [":=: 準備書面"], window.session.dictionary)
    assert not r.lost_marks


def test_highlight_button_and_tags(window):
    """［蛍光ペン］（Ctrl+Alt+H）で選んだ字を ==…== で囲み、もう一度で外す。エディターでは黄色の地で示す。"""
    window._load_text("# 認否\n主張は争う。\n")
    window.text.tag_add("sel", "2.0", "2.2")
    window.on_highlight()
    assert window.text.get("2.0", "2.end") == "==主張==は争う。"
    window._highlight()
    assert "highlight" in window.text.tag_names("2.2") and "mark" in window.text.tag_names("2.0")
    assert "highlight" not in window.text.tag_names("2.6")
    window.on_highlight()
    assert window.text.get("2.0", "2.end") == "主張は争う。"
    assert window.bind("<Control-Alt-Key-h>")


def test_dots_button_with_bold(window):
    """［傍点］で選んだ字を *…* で囲み、もう一度で外す。太字と重ねると ***…***、外すときは * の数で見分ける。
    エディターでは下線で示す（2026-10-24 班長指示）。"""
    window._load_text("# 認否\n主張は争う。\n")
    window.text.tag_add("sel", "2.0", "2.2")
    window.on_dots()
    assert window.text.get("2.0", "2.end") == "*主張*は争う。"
    window._highlight()
    assert "dots" in window.text.tag_names("2.1") and "mark" in window.text.tag_names("2.0")
    window.on_bold()                                     # 傍点に太字を重ねる
    assert window.text.get("2.0", "2.end") == "***主張***は争う。"
    window.on_dots()                                     # 傍点だけ外す
    assert window.text.get("2.0", "2.end") == "**主張**は争う。"
    window.on_dots()                                     # 太字に傍点を重ねる
    assert window.text.get("2.0", "2.end") == "***主張***は争う。"
    window.on_bold()                                     # 太字だけ外す
    assert window.text.get("2.0", "2.end") == "*主張*は争う。"
    window.on_dots()
    assert window.text.get("2.0", "2.end") == "主張は争う。"


def test_indent_button_and_shortcuts(window):
    """［インデント］（Ctrl+I）で +1 を付け、もう一度で外す（字数は手で直す）。字下げと一緒に使え、
    見出しの行には付けない。Ctrl+I でタブは入らない（2026-10-24 班長指示）。"""
    window._load_text("# 認否\n主張は争う。\n次の段落。\n")
    window.text.tag_add("sel", "2.0", "3.end")
    window.on_indent()
    assert window.raw_text().split("\n")[1:3] == ["+1 主張は争う。", "+1 次の段落。"]
    window.on_indent()                                   # もう一度で外す（選択は残る）
    assert window.raw_text().split("\n")[1:3] == ["主張は争う。", "次の段落。"]
    window.text.tag_remove("sel", "1.0", "end")
    window._load_text("# 認否\n+3 主張は争う。\n次の段落。\n")
    window.text.tag_add("sel", "2.0", "3.end")           # 一部の行に記号があれば、ない行に付ける（字数は変えない）
    window.on_indent()
    assert window.raw_text().split("\n")[1:3] == ["+3 主張は争う。", "+1 次の段落。"]
    window.text.tag_remove("sel", "1.0", "end")
    window.text.mark_set("insert", "2.5")
    window.on_align("-> ")                            # 字下げと一緒に使える（インデントは残る）
    assert window.text.get("2.0", "2.end") == "+3 -> 主張は争う。"
    window.on_align(":-: ")                            # 配置と字下げは付け替え、インデントは残す
    assert window.text.get("2.0", "2.end") == ":-: +3 主張は争う。"
    window.on_align(":-: ")
    window.text.mark_set("insert", "1.1")
    window.on_indent()                                   # 見出しの行には付けない
    assert window.text.get("1.0", "1.end") == "# 認否"
    window.text.mark_set("insert", "3.2")
    window.text.event_generate("<Control-Key-i>")
    assert window.text.get("3.0", "3.end") == "次の段落。"         # Ctrl+I で外れる。タブは入らない
    window.text.event_generate("<Control-Key-i>")
    assert window.text.get("3.0", "3.end") == "+1 次の段落。"
    window._highlight()
    assert all("mark" in window.text.tag_names(f"3.{c}") for c in range(3))
    window.on_plain()                                    # 標準（Ctrl+Shift+N）で記号を外す
    assert window.text.get("3.0", "3.end") == "次の段落。"

def test_header_footer_buttons(window):
    """［ヘッダー］：選んだ行の行頭に [HEADER] を付け、もう一度で外す（on_area は [FOOTER] にも使え、もう片方とは
    付け替える。フッターのボタンは置かない）。配置の記号は残す。見出しの行には付けない。記号は青い字で示し、確認表示では
    ヘッダーに組む（2026-10-25 班長指示）。"""
    assert not [b for b in _all_buttons(window) if str(b.cget("text")) == "フッター"]
    # ［ヘッダー］は「書式」の組の［インデント］の下（2026-10-25 班長指示）
    found = {str(b.cget("text")): b for b in _all_buttons(window)}
    head, indent = found["ヘッダー"], found["インデント"]
    assert head.master is indent.master is window.ribbon.groups[3].body
    assert head.grid_info()["column"] == indent.grid_info()["column"]
    assert int(head.grid_info()["row"]) == int(indent.grid_info()["row"]) + 1
    window._load_text("--: 事件番号\n担当\n# 認否\n主張は争う。")
    window.text.tag_add("sel", "1.0", "2.end")
    window.on_area("[HEADER] ")
    assert _lines(window, 1, 2) == ["[HEADER] --: 事件番号", "[HEADER] 担当"]
    window.on_align(":-: ")                                 # 配置は付け替え、ヘッダーの記号は残す
    assert _lines(window, 1, 2) == ["[HEADER] :-: 事件番号", "[HEADER] :-: 担当"]
    window.text.tag_remove("sel", "1.0", "end")
    window.text.mark_set("insert", "2.0")
    window.on_area("[FOOTER] ")                             # もう片方とは付け替える
    assert _lines(window, 2, 2) == ["[FOOTER] :-: 担当"]
    window.on_area("[FOOTER] ")                             # もう一度で外す
    assert _lines(window, 2, 2) == [":-: 担当"]
    window.text.mark_set("insert", "3.0")
    window.on_area("[HEADER] ")                             # 見出しの行には付けない
    assert _lines(window, 3, 3) == ["# 認否"]
    window.text.edit_undo()                                 # Ctrl+Z 1回で1回分戻る
    assert _lines(window, 2, 2) == ["[FOOTER] :-: 担当"]
    window._highlight()
    ranges = window.text.tag_ranges("mark")
    assert "[HEADER] :-: " in [window.text.get(a, b) for a, b in zip(ranges[0::2], ranges[1::2])]
    window.on_plain()                                       # 標準は配置を外し、置く場所の記号は残す
    assert _lines(window, 2, 2) == ["[FOOTER] 担当"]
    window.refresh()
    lines = window.session.layout_map.lines
    assert sorted((ln.area, "".join(g.ch for g in ln.glyphs)) for ln in lines if ln.area) == [
        ("footer", "担当"), ("header", "事件番号")]


def _all_buttons(w):
    from tkinter import ttk
    for c in w.winfo_children():
        if isinstance(c, ttk.Button):
            yield c
        yield from _all_buttons(c)


def test_header_overflow_is_shown_in_status(window):
    window._load_text("\n".join(["[HEADER] 行"] * 6 + ["本文"]))
    window.refresh()
    assert "ヘッダー" in str(window.status.cget("text"))
    window._load_text("本文")
    window.refresh()
    assert str(window.status.cget("text")) == ""


def test_distribute_button(window):
    """［均等割付］で選んだ字を [字]{N} の形で挟み（N は選んだ字の数。手で直す）、もう一度で外す。"""
    window._load_text("原告甲野太郎\n")
    window.text.tag_add("sel", "1.0", "1.2")
    window.on_distribute()
    assert window.text.get("1.0", "1.end") == "[原告]{2}〔人名Ａ〕"
    assert window.text.get("sel.first", "sel.last") == "原告"
    window._highlight()
    assert all("mark" in window.text.tag_names(f"1.{c}") for c in (0, 3, 4, 5, 6))       # 「[」と「]{2}」
    assert "mark" not in window.text.tag_names("1.1")
    window.on_distribute()
    assert window.text.get("1.0", "1.end") == "原告〔人名Ａ〕"
    window.text.edit_undo()
    assert window.text.get("1.0", "1.end") == "[原告]{2}〔人名Ａ〕"


def test_align_and_distribute_buttons_in_table_cells(window):
    """表のセルでは、［中央］［右］がセルの先頭の配置の記号を、［均等割付］がセルの字全体を挟む記号を付け外しする。
    区切りの行では列の配置を変える（2026-10-24 班長指示）。"""
    window._load_text("| 項目 | 金額 |\n|---|---|\n| 休業損害 | :-: 1,000 |\n本文。\n")

    def lines():
        return window.raw_text().split("\n")[:4]
    window.text.mark_set("insert", "1.4")                 # 「項目」のセル
    window.on_align("--: ")
    assert lines()[0] == "| --: 項目 | 金額 |"
    window.on_align("--: ")                               # もう一度で外す
    assert lines()[0] == "| 項目 | 金額 |"
    window.text.mark_set("insert", "3.13")                # 「1,000」のセル：:-: を --: に付け替える
    window.on_align("--: ")
    assert lines()[2] == "| 休業損害 | --: 1,000 |"
    window.text.tag_add("sel", "1.2", "3.4")              # 選んだ範囲にかかるセル（区切りの行は除く）
    window.on_align(":-: ")
    assert lines()[0] == "| :-: 項目 | :-: 金額 |" and lines()[1] == "|---|---|"
    assert lines()[2] == "| :-: 休業損害 | --: 1,000 |"
    window.text.edit_undo()                               # Ctrl+Z 1回で戻る
    assert lines()[0] == "| 項目 | 金額 |"
    window.text.tag_remove("sel", "1.0", "end")
    window.text.mark_set("insert", "3.4")                 # 均等割付：セルの字全体を挟む・外す
    window.on_distribute()
    assert lines()[2] == "| [休業損害]{4} | --: 1,000 |"
    window.text.tag_remove("sel", "1.0", "end")
    window.text.mark_set("insert", "3.6")
    window.on_distribute()
    assert lines()[2] == "| 休業損害 | --: 1,000 |"
    window.text.mark_set("insert", "3.14")                # 配置の記号の後から挟む
    window.on_distribute()
    assert lines()[2] == "| 休業損害 | --: [1,000]{3} |"
    window.text.tag_remove("sel", "1.0", "end")
    window.text.mark_set("insert", "3.end")               # 最後の | の後なら、最後のセル
    window.on_align(":-: ")
    assert lines()[2] == "| 休業損害 | :-: [1,000]{3} |"
    window.text.mark_set("insert", "2.2")                 # 区切りの行では、その列の配置を変える
    window.on_align("--: ")
    assert lines()[1] == "|---:|---|"
    window.text.mark_set("insert", "4.1")                 # 表の外の行は、これまでどおり段落の配置
    window.on_align("--: ")
    assert lines()[3] == "--: 本文。"


def test_align_buttons_on_separator_row_change_column(window):
    """区切りの行のセルで［中央］［右］を押すと、その列の配置（: の付け方）を変える。もう一度で左に戻す。
    - と = の種類と数は変えない（2026-10-24 班長指示）。"""
    window._load_text("| 項目 | 金額 |\n|===|===|\n| 休業損害 | 1,000 |\n")

    def sep():
        return window.raw_text().split("\n")[1]
    window.text.mark_set("insert", "2.6")                 # 2列目
    window.on_align("--: ")
    assert sep() == "|===|===:|"
    window.on_align(":-: ")
    assert sep() == "|===|:===:|"
    window.on_align(":-: ")                             # もう一度で左に戻す
    assert sep() == "|===|===|"
    window.text.tag_add("sel", "2.0", "2.end")            # 選んだ範囲にかかる列をまとめて
    window.on_align(":-: ")
    assert sep() == "|:===:|:===:|"
    window.text.edit_undo()
    assert sep() == "|===|===|"
    from va_documake.document import CENTER, parse_separator
    window.on_align(":-: ")
    assert parse_separator(sep()) == ([CENTER, CENTER], True)       # 2重線のまま


def test_naiyou_check_before_save(window, tmp_path, monkeypatch):
    """内容証明なら、保存する前に字数・行数を確かめる。ページ番号は「なし」にして知らせる。超えた所があれば
    カーソルをその行に動かして尋ね、「保存をやめて直す」なら保存しない（2026-10-24 班長指示）。"""
    shown, asked = [], []
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: shown.append(a[1]))

    class Stop:
        def __init__(self, parent, problem):
            asked.append(problem)
            self.ok = False
    monkeypatch.setattr(file_ops, "NaiyouDialog", Stop)
    window.doc_type_box.set("内容証明")
    window.page_number_box.set("中下")
    window.on_settings_changed()
    window._load_text("本文。\nABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij\n")
    window.refresh()
    window.session.pdf_path = tmp_path / "通知書.pdf"
    assert not window.on_save()
    assert window.page_number_box.get() == "なし" and "なし" in shown[0]
    assert asked and asked[0].kind == "chars"
    assert window.text.index("insert").startswith("2.")              # カーソルは超えた行に
    assert not (tmp_path / "通知書.pdf").exists()
    window._load_text("本文。\n")
    window.refresh()
    assert window.on_save() and (tmp_path / "通知書.pdf").exists()
    assert len(asked) == 1
    window.doc_type_box.set("裁判所提出書類")
    window.on_settings_changed()


def test_options_change_folder_and_editor(window, tmp_path, monkeypatch):
    """［オプション］で構文ファイルの保存場所と、エディターの書体・字の大きさ・行の間隔を変える。今の文書は、
    これまでの場所の構文ファイルを使い続ける（2026-10-24 班長指示）。"""
    window.session.pdf_path = tmp_path / "準備書面.pdf"
    assert window.on_save()
    old = window.session.vadm_path
    shared = tmp_path / "共有"
    shared.mkdir()
    family = (app.theme.editor_font_choices(window) or [""])[0]

    class Answer:
        def __init__(self, parent, cfg, choices, size_range, spacing_range, prompt, default_prompt):
            assert size_range == (8, 20) and spacing_range == (0, 20) and prompt == default_prompt
            self.result = {"vadm_folder": str(shared), "font_family": family, "font_size": 14, "line_spacing": 12,
                           "prompt": None}
    monkeypatch.setattr(app, "OptionsDialog", Answer)
    window.on_options()
    assert window.cfg.vadm_folder == str(shared) and window.cfg.editor_font_size == 14
    assert str(window.doc_id_label.cget("text")) == f"構文（VADM）ファイル：{window.session.doc_id}.vadm"   # 保存した文書
    assert str(window.pdf_name_label.cget("text")) == "書式付き（PDF）ファイル：準備書面.pdf"
    assert window.session.vadm_path == old                      # 今の文書は、これまでの構文ファイル
    from tkinter import font as tkfont
    assert tkfont.Font(window, font=window.text.cget("font")).actual("size") == 14
    assert int(str(window.text.cget("spacing2"))) == 12
    saved = app.config.load(app.config.config_path())
    assert (saved.editor_font_size, saved.editor_line_spacing, saved.vadm_folder) == (14, 12, str(shared))
    # 新しい文書は、新しい場所に保存する
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    assert window.on_close_document()
    assert window.session.vadm_path.parent == shared
    window.cfg.editor_font_size, window.cfg.editor_line_spacing, window.cfg.editor_font_family = 11, 8, ""
    window._apply_editor_prefs()


def test_close_document_starts_new_one(window, monkeypatch):
    """［閉じる］は今の文書を閉じて新しい文書にする（VA DocuMake は終わらない）。保存していない変更があれば尋ねる。"""
    asked = []
    monkeypatch.setattr(messagebox, "askyesnocancel", lambda *a, **k: asked.append(a[1]))
    old_id = window.session.doc_id
    window.text.insert("end", "追記。")
    window.on_text_modified()
    assert not window.on_close_document()                          # キャンセルなら閉じない
    assert asked and window.session.doc_id == old_id
    monkeypatch.setattr(messagebox, "askyesnocancel", lambda *a, **k: False)   # 保存しない
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    assert window.on_close_document()
    assert window.session.doc_id != old_id and window.raw_text() == "" and window.winfo_exists()
    # 閉じた後（エディターが空）は「開かれていません」、書いたが保存していなければ「保存していません」
    assert str(window.doc_id_label.cget("text")) == "構文（VADM）ファイル：（開かれていません）"
    assert str(window.pdf_name_label.cget("text")) == "書式付き（PDF）ファイル：（開かれていません）"
    window.text.insert("1.0", "本文。")
    window.on_text_modified()
    assert str(window.doc_id_label.cget("text")) == "構文（VADM）ファイル：（保存していません）"
    assert str(window.pdf_name_label.cget("text")) == "書式付き（PDF）ファイル：（保存していません）"
    assert not window.tree.get_children()


def test_config_rejects_out_of_range_options():
    cfg = app.config.AppConfig(editor_font_size=99, editor_line_spacing=-3, editor_font_family=5)
    assert (cfg.editor_font_size, cfg.editor_line_spacing, cfg.editor_font_family) == (11, 8, "")


def test_ai_prompt_in_options(window, tmp_path, monkeypatch):
    """AI への指示は、オプションで確かめ・直す。今の文書（保存してある構文ファイルの指示も書き直す）と、
    これから作る文書に使う。既定に戻すこともできる（2026-10-24 班長指示）。"""
    window.session.pdf_path = tmp_path / "準備書面.pdf"
    assert window.on_save()
    custom = vadm.PROMPT.rstrip() + "\n・短く書け。\n"

    def answer(prompt_text):
        class Answer:
            def __init__(self, parent, cfg, choices, size_range, spacing_range, prompt, default_prompt):
                self.result = {"vadm_folder": cfg.vadm_folder, "font_family": cfg.editor_font_family,
                               "font_size": cfg.editor_font_size, "line_spacing": cfg.editor_line_spacing,
                               "prompt": prompt_text}
        return Answer
    monkeypatch.setattr(app, "OptionsDialog", answer(custom))
    window.on_options()
    assert window.session.prompt == custom and window.cfg.ai_prompt == custom
    saved = window.session.vadm_path.read_text(encoding="utf-8")
    assert "・短く書け。" in saved and "版 1" in saved                    # 版は変えずに指示だけ書き直す
    assert not window.session.vadm_changed_outside()
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    assert window.on_close_document()
    assert window.session.prompt == custom                                 # 新しい文書にも使う
    monkeypatch.setattr(app, "OptionsDialog", answer(vadm.PROMPT))          # 既定に戻す
    window.on_options()
    assert window.session.prompt is None and window.cfg.ai_prompt == ""


def test_prompt_dialog_reset(window):
    from va_documake.dialogs import PromptDialog

    def run():
        d = [c for c in window.winfo_children() if isinstance(c, PromptDialog)][-1]
        d.text.insert("end", "\n・足した。")
        d.reset()
        assert d.text.get("1.0", "end-1c") == vadm.PROMPT.rstrip("\n")
        d.text.insert("end", "\n・足した。")
        d.accept()
    window.after(200, run)
    dlg = PromptDialog(window, vadm.PROMPT, vadm.PROMPT)
    assert dlg.result.endswith("・足した。\n")


def test_parse_pages():
    from va_documake.printing import parse_pages
    assert parse_pages("1-3, 5", 6) == [0, 1, 2, 4]
    assert parse_pages("２－３，２", 4) == [1, 2]
    assert parse_pages("4-", 6) == [3, 4, 5]
    for bad in ("", "0", "7", "3-2", "a"):
        with pytest.raises(ValueError):
            parse_pages(bad, 6)


@pytest.mark.skipif(app.os.name != "nt", reason="印刷は Windows だけ")
def test_print_dialog_choices(window):
    """印刷の画面：プリンター・ページ（すべて・確認表示のページ・指定）・部数を選ぶ。"""
    from va_documake.dialogs import PrintDialog
    results = []

    def run(setup):
        def go():
            d = [c for c in window.winfo_children() if isinstance(c, PrintDialog)][-1]
            setup(d)
            d.accept()
        window.after(200, go)
        return PrintDialog(window, 6, 2, ["A", "B"], "B", lambda *a: None).result
    results.append(run(lambda d: None))
    results.append(run(lambda d: (d.which.set("current"), d.copies.set("3"))))
    results.append(run(lambda d: (d.which.set("range"), d.range.set("1-2, 6"), d.printer.set("A"))))
    assert results == [("B", None, 1, [0, 1, 2, 3, 4, 5]), ("B", None, 3, [1]), ("A", None, 1, [0, 1, 5])]

def test_line_numbers_check(window, tmp_path):
    """「スタイル」の［行番号］のチェックで行番号を付ける。構文ファイルの区切りの行に残し、内容証明では付けない
    （VA公用文のセットアップと同じ。2026-10-24 班長指示）。"""
    from va_documake.doctypes import DOC_TYPES
    assert not window.line_numbers_var.get()
    window.line_numbers_check.invoke()
    assert window.session.settings.line_numbers and window.cfg.line_numbers
    window.session.pdf_path = tmp_path / "準備書面.pdf"
    assert window.on_save()
    assert "行番号 あり" in window.session.vadm_path.read_text(encoding="utf-8")
    window.doc_type_box.set(DOC_TYPES["Naiyou"].label)
    window.on_settings_changed()
    assert not window.session.settings.line_numbers and not window.line_numbers_var.get()
    assert str(window.line_numbers_check.cget("state")) == "disabled"
    window.doc_type_box.set(DOC_TYPES["Saiban"].label)
    window.on_settings_changed()
    assert str(window.line_numbers_check.cget("state")) == "normal" and not window.session.settings.line_numbers

def test_copy_vadm_path(window, tmp_path):
    """［パスをコピー］で構文ファイルのフルパスをコピーする（保存するまでは押せない。2026-10-24 班長指示）。"""
    assert str(window.copy_path_button.cget("state")) == "disabled"
    window.session.pdf_path = tmp_path / "準備書面.pdf"
    assert window.on_save()
    assert str(window.copy_path_button.cget("state")) == "normal"
    window.clipboard_clear()
    window.copy_path_button.invoke()
    assert window.clipboard_get() == str(window.session.vadm_path) and window.session.vadm_path.is_absolute()
    assert "パスをコピーしました" in str(window.status.cget("text"))


def test_no_commands_for_reusing_documents(window):
    """過去の文書を使い回す［コピーとして開く］［名前を付けて保存］（F12）と、［すべて解除］は置かない
    （2026-10-25 班長決定。仕様.md の9.4）。"""
    from tkinter import ttk

    def texts(w):
        for c in w.winfo_children():
            if isinstance(c, ttk.Button):
                yield str(c.cget("text")).replace("\n", "")
            yield from texts(c)
    found = set(texts(window))
    assert "開く" in found and "変更" in found and "解除" in found
    assert not found & {"コピーとして開く", "名前を付けて保存", "すべて解除"}
    assert not window.bind("<F12>")
    assert not hasattr(window, "on_save_as") and not hasattr(window, "on_open_copy") and not hasattr(window, "on_unregister_all")


def test_edit_entry_and_released_check(window, tmp_path, monkeypatch):
    """一覧の［変更］：元の語を直す（記号はそのまま）・記号を変える。解除した語の残りの確かめ（2026-10-25 班長決定）。"""
    from types import SimpleNamespace
    # 元の語を変える：記号はそのまま、文章の中の記号がすべて新しい語になる。新しい語を打ってあれば記号にする
    window.text.insert("end", "丙川次郎の陳述書。\n")
    window.tree.selection_set("〔人名Ａ〕")
    monkeypatch.setattr(ai_ops, "EditDialog", lambda parent, e, d: SimpleNamespace(result=("丙川次郎", "人名", "Ａ")))
    window.on_edit_entry()
    assert window.raw_text() == PSEUDO + "〔人名Ａ〕の陳述書。\n"
    assert window.real_text() == TEXT.replace("甲野太郎", "丙川次郎") + "丙川次郎の陳述書。\n"
    assert window.tree.item("〔人名Ａ〕", "values")[1] == "丙川次郎"
    assert "「甲野太郎」から「丙川次郎」に" in str(window.status.cget("text"))
    # 前の名前が残っていれば、保存するときに知らせ、その所を選んで見せる
    window.text.insert("end", "甲野太郎の陳述書。\n")
    window.session.pdf_path = tmp_path / "準備書面.pdf"
    asked = []
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: asked.append(a[1]) or False)
    assert not window.on_save()
    assert asked and "甲野太郎（1 か所）" in asked[0] and not window.session.pdf_path.exists()
    assert window.text.get("sel.first", "sel.last") == "甲野太郎"
    # 残してよいと答えれば保存し、次からは尋ねない
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: asked.append(a[1]) or True)
    assert window.on_save()
    n = len(asked)
    window.text.insert("end", "追記。\n")
    assert window.on_save() and len(asked) == n
    # 記号を変える：エディターの記号も変わる。前の記号は、ほかの語に使い直さない
    monkeypatch.setattr(ai_ops, "EditDialog", lambda parent, e, d: SimpleNamespace(result=("丙川次郎", "人名", "x")))
    window.tree.selection_set("〔人名Ａ〕")
    window.on_edit_entry()
    assert "〔人名Ａ〕" not in window.raw_text() and "〔人名Ｘ〕の陳述書。" in window.raw_text()
    assert window.tree.get_children() == ("〔人名Ｘ〕",) and "〔人名Ａ〕 から 〔人名Ｘ〕" in str(window.status.cget("text"))
    assert window.session.dictionary.next_letters("人名") == "Ｂ"


def test_register_dialog_requires_letters(window, monkeypatch):
    """仮名化の画面：記号の字は自動で入れず、利用者が必ず打つ（英字・数字・漢字など。2026-10-25 班長決定・班長指示）。
    今ほかの語に使っている記号・空・使えない字なら、理由を知らせて画面を閉じない。解除した記号を別の語に付けるときは
    確かめる。この文書で使っている記号・解除した記号を示す。"""
    from va_documake.dialogs import EditDialog, RegisterDialog
    d = window.session.dictionary                     # 甲野太郎＝〔人名Ａ〕
    d.register("丙川次郎", "人名", "B")
    d.unregister("丙川次郎")
    errors, asked, answers, seen = [], [], iter([False, True]), {}
    monkeypatch.setattr(messagebox, "showerror", lambda *a, **k: errors.append(a[1]))
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: asked.append(a[1]) or next(answers))

    def run():
        dlg = [c for c in window.winfo_children() if isinstance(c, RegisterDialog)][-1]
        assert dlg.letters.get() == ""
        seen["used"] = str(dlg.used_label.cget("text"))
        dlg.ok()                                       # 空のまま
        dlg.letters.set("a")
        dlg.ok()                                       # 今使っている記号
        dlg.letters.set("Ｘ Ｙ")
        dlg.ok()                                       # 空白は使えない
        dlg.letters.set("b")
        dlg.ok()                                       # 解除した記号：確かめて［いいえ］
        seen["after_no"] = dlg.winfo_exists()
        dlg.letters.set("相手方1")
        seen["preview"] = str(dlg.preview.cget("text"))
        dlg.letters.set("b")
        dlg.ok()                                       # 解除した記号：確かめて［はい］
    window.after(200, run)
    assert RegisterDialog(window, "丁野四郎", d).result == ("人名", "b")
    assert "〔人名Ａ〕（甲野太郎）" in seen["used"] and "〔人名Ｂ〕（丙川次郎）" in seen["used"]
    assert seen["preview"] == "記号：〔人名相手方１〕" and seen["after_no"]
    assert len(errors) == 3 and "入れて" in errors[0] and "使っています" in errors[1] and "数字だけ" in errors[2]
    assert len(asked) == 2 and "「丙川次郎」に使った記号" in asked[0]

    def run_edit():
        dlg = [c for c in window.winfo_children() if isinstance(c, EditDialog)][-1]
        assert dlg.letters.get() == "Ａ" and dlg.word.get() == "甲野太郎"
        assert "〔人名Ａ〕" not in str(dlg.used_label.cget("text"))      # 自分の記号は「使えない」に出さない
        dlg.word.set("甲野太朗")
        dlg.ok()
    window.after(200, run_edit)
    assert EditDialog(window, d.find("〔人名Ａ〕"), d).result == ("甲野太朗", "人名", "Ａ")
    assert len(asked) == 2                              # 自分の記号のままなら確かめない
    d.register("山田太郎", "人名", "yt")

    def run_edit2():
        dlg = [c for c in window.winfo_children() if isinstance(c, EditDialog)][-1]
        seen["edit"] = dlg.letters.get()
        dlg.cancel()
    window.after(200, run_edit2)
    assert EditDialog(window, d.find("〔人名ＹＴ〕"), d).result is None
    assert seen["edit"] == "ＹＴ"                       # 2字以上の記号も、その字を入れて開く

