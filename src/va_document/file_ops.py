"""ファイルの操作：開く・保存（PDF と構文ファイルを同じ版で）・閉じる・印刷。

メインの画面（app.MainWindow）の部品（mixin）。
"""
from pathlib import Path
from tkinter import filedialog, messagebox

import fitz  # PyMuPDF

from . import APP_NAME, config, naiyou, printing, vamd
from .dialogs import ChangedOutsideDialog, MissingDialog, NaiyouDialog, PrintDialog
from .doctypes import PAGE_NUMBER_LABELS, PAGE_NUMBER_NONE
from .pdfwriter import FontNotEmbeddable
from .pseudonym import TOKEN_RE
from .recover import PdfMismatch

# ［開く］の画面のファイルの種類。最初のものが既定。開けるものをまとめて出し、Word・Excel など開けないファイル
# （テキストとして読むと文字化けする）は出さない（2026-10-27 班長決定。「すべてのファイル」を既定にする案と比べた）
OPEN_FILETYPES = [
    ("開けるファイル（構文ファイル・書式付きファイル・テキスト・マークダウン）", f"*{vamd.EXTENSION} *.pdf *.txt *.md"),
    ("VA Document（構文ファイル・書式付きファイル）", f"*{vamd.EXTENSION} *.pdf"), ("テキスト・マークダウン", "*.txt *.md"),
    ("すべてのファイル", "*.*")]


class FileMixin:
    """ファイルの操作（MainWindow に混ぜて使う）。"""

    def on_open(self):
        if not self._confirm_discard():
            return
        path = filedialog.askopenfilename(parent=self, title="開く", filetypes=OPEN_FILETYPES)
        if path:
            self.open_path(Path(path))

    def open_path(self, path):
        try:
            suffix = path.suffix.lower()
            if suffix == vamd.EXTENSION:
                result = self._open_vamd(path)
            elif suffix == ".pdf":
                result = self.session.open_pdf(path)
            else:
                result = self.session.open_text(path)
        except vamd.NoSeparator as e:
            messagebox.showerror(APP_NAME, f"構文ファイルとして読めません。\n{e}", parent=self)
            return
        except (PdfMismatch, OSError, ValueError) as e:
            messagebox.showerror(APP_NAME, f"開けませんでした。\n{e}", parent=self)
            return
        if result is None:
            return
        text = result.text
        if result.unresolved:
            answers = MissingDialog(self, self.session, result).answers
            text = self.session.resolve(answers)
        self._load_text(text)
        self._layout_pages(keep=False)     # 開いた文書は、1ページ目の上から表示する
        for m in result.messages:
            messagebox.showinfo(APP_NAME, m, parent=self)
        self.status.configure(text=f"開きました：{path.name}")

    def _open_vamd(self, path):
        try:
            return self.session.open_vamd(path)
        except FileNotFoundError:
            pass
        choice = messagebox.askyesnocancel(
            APP_NAME, "この構文ファイルと同じ文書ID の書式付きファイル（PDF）が、これまでに保存したフォルダに見つかりません。\n"
            "PDF を選びますか？\n（［いいえ］：PDF なしで開き、記号の元の語を入力します）", parent=self)
        if choice is None:
            return None
        if choice:
            pdf = filedialog.askopenfilename(parent=self, title="PDF を選ぶ", filetypes=[("PDF", "*.pdf")])
            if not pdf:
                return None
            return self.session.open_vamd(path, Path(pdf))
        return self.session.open_vamd(path, False)

    def _confirm_discard(self):
        """保存していない変更があれば、保存するかを尋ねる。続けてよければ True。"""
        text = self.real_text()
        if not self.session.is_modified(text):
            return True
        answer = messagebox.askyesnocancel(APP_NAME, "保存していない変更があります。保存しますか？", parent=self)
        if answer is None:
            return False
        return self.on_save() if answer else True

    def on_close_document(self):
        """今の文書を閉じて、新しい文書にする（Word の「閉じる」。VA Document は終わらない。2026-10-24 班長指示）。
        保存していない変更があれば尋ねる。仮名化した語の一覧（実名と記号の対応）が消えることは確かめない（保存した
        文書は、開き直せば構文ファイルと PDF を突き合わせて作り直せる。2026-10-27 班長指示）。"""
        if not self._confirm_discard():
            return False
        self.session.new()
        self._load_text("")             # 設定の欄・仮名化した語の一覧・題も、ここで新しい文書のものにする
        self._layout_pages(keep=False)
        self.status.configure(text="文書を閉じました。新しい文書です。")
        return True

    def on_save(self, check_outside=True, allow_unknown=False):
        """PDF と構文ファイルを、同じ版で保存する。保存できたら True。

        構文ファイルが外で書き換えられていれば（テキストエディターで直した、AI の回答を上書き保存した、など）、
        黙って上書きせず、取り込むか・上書きするかを尋ねる（2026-10-23 班長了承）。
        エディターは常に仮名で、見えているものがそのまま構文ファイルに書かれるので、保存の前の確認画面
        （構文ファイルに書く中身の確認）は出さない（2026-10-24 班長決定）。
        """
        text = self.real_text()
        if check_outside and self.session.vamd_changed_outside():
            choice = ChangedOutsideDialog(self, at_save=True).result
            if choice is None:
                return False
            if choice == "import":
                return self._import_outside()
        pdf = self.session.pdf_path
        if pdf is None:
            pdf = self._ask_pdf_path()
            if pdf is None:
                return False
        text = self._guard_tokens(text, allow_unknown)
        if text is None:
            return False
        if not self._check_released(text):
            return False
        if self.session.settings.doc_type == naiyou.DOC_TYPE and not self._check_naiyou(text):
            return False
        try:
            self.session.save(text, pdf)
        except PermissionError:
            messagebox.showerror(APP_NAME, f"PDF を保存できませんでした。PDF をほかのソフトで開いていれば、閉じてから"
                                 f"もう一度保存してください。\n{pdf}", parent=self)
            return False
        except (OSError, FontNotEmbeddable) as e:
            messagebox.showerror(APP_NAME, f"保存できませんでした。\n{e}", parent=self)
            return False
        config.save(self.cfg)
        self._update_title()
        self.status.configure(text=f"版 {self.session.version} を保存しました。書式付き（PDF）：{self.session.pdf_path.name}　"
                                   f"構文（VAMD）：{self.session.vamd_path.name}")
        return True

    def _check_released(self, text):
        """仮名化を解除した語・変える前の元の語が、構文ファイル（AI に渡すもの）に実名のまま残っていれば知らせ、
        保存するかを尋ねる（2026-10-25 班長指示）。保存してよければ True。
        残してよいと答えた語は、もう知らせない。"""
        found = self.session.released_in(text)
        if not found:
            return True
        lines = "\n".join(f"　{w}（{n} か所）" for w, n in list(found.items())[:10])
        more = f"\n　ほか {len(found) - 10} 語" if len(found) > 10 else ""
        if messagebox.askyesno(APP_NAME, "仮名化を解除した語（または、変える前の元の語）が、文章に残っています：\n"
                               f"{lines}{more}\n\nこのまま保存すると、構文ファイル（AI に渡すもの）に実名のまま書かれます。"
                               "仮名化するはずの語であれば、直してから保存してください。"
                               "仮名化するときは、語を選んで［選択範囲を仮名化］を押してください。\n\n"
                               "このまま保存しますか？", parent=self):
            self.session.accept_released(found)
            return True
        # 最初に残っている所を選んで見せる（エディターは仮名なので、残った語はエディターにもそのままある）
        word = next(iter(found))
        first = self.text.search(word, "1.0", stopindex="end")
        if first:
            self.text.tag_remove("sel", "1.0", "end")
            self.text.tag_add("sel", first, f"{first}+{len(word)}c")
            self.text.mark_set("insert", first)
            self.text.see(first)
            self.text.focus_set()
        return False

    def _check_naiyou(self, text):
        """内容証明なら、保存する前に VA内容証明郵便と同じ字数・行数のチェックをする（2026-10-24 班長指示）。
        ページ番号が「なし」でなければ「なし」にして知らせる（VA内容証明郵便がヘッダー・フッターを消すのと同じ）。
        超えた所があれば、エディターのカーソルをその行に動かし、保存するかを尋ねる。保存してよければ True。"""
        if self.session.settings.page_number != PAGE_NUMBER_NONE:
            self.page_number_box.set(PAGE_NUMBER_LABELS[PAGE_NUMBER_NONE])
            self.on_settings_changed()
            messagebox.showinfo(APP_NAME, "内容証明にはページ番号を付けないため、ページ番号を「なし」にしました。",
                                parent=self)
        ts, lines = self.session.typeset(text)
        problem = naiyou.check(ts, lines)
        if problem is None:
            return True
        hit = self.session.layout_map.hit(problem.page - 1, problem.x, problem.y)
        if hit is not None:
            self._move_cursor(*hit)
        return NaiyouDialog(self, problem).ok

    def _guard_tokens(self, text, allow_unknown=False):
        """保存する実名の文章に、構文ファイルの区切りの行や、仮名化した語にない記号が残っていないかを確かめる。

        区切りの行があれば保存しない（仮名の文章が紛れ込んでいる）。仮名化した語にない記号（AI が作った〔人名Ｃ〕など）
        があれば、PDF に記号のまま出ることを知らせて、保存するかを尋ねる（仮名化した語の記号は、実名に戻してある）。
        返すのは保存する文章（やめたら None）。allow_unknown なら尋ねない（AI の回答の取り込みで、すでに知らせているため）。
        """
        if vamd.has_separator(text):
            messagebox.showerror(APP_NAME, "実名の文章の中に、構文ファイルの区切りの行（==== VA Document …）があります。"
                                 "仮名の文章が紛れ込んでいるおそれがあるため、保存しません。\n\n"
                                 "AI の回答を Ctrl+V で貼り付けた場合は、Ctrl+Z で貼り付ける前に戻してから、"
                                 "「AI 連携」の［貼り付け］で取り込んでください（区切りの行を外し、文書ID と版を確かめ、"
                                 "記号を実名に戻して、変わった段落に印を付けます）。\n"
                                 "そうでない場合は、区切りの行とその上（AI への指示）を消してから保存してください。", parent=self)
            return None
        unknown = list(dict.fromkeys(m.group(0) for m in TOKEN_RE.finditer(text)))
        if not unknown or allow_unknown:
            return text
        if not messagebox.askyesno(APP_NAME, "仮名化した語にない記号があります（AI が作った記号など）：\n"
                                   + "、".join(unknown) + "\n\nこのまま保存すると、PDF には記号のまま出ます。"
                                   "元の語が分かれば、エディターで直すか、元の語を選んで仮名化してください。\n"
                                   "このまま保存しますか？", parent=self):
            return None
        return text

    def _ask_pdf_path(self):
        # 画面の題は、画面の「書式付き（PDF）ファイル」の呼び方にそろえる（2026-10-26 班長指示）
        while True:
            path = filedialog.asksaveasfilename(parent=self, title="書式付き（PDF）ファイルの保存先", defaultextension=".pdf",
                                                filetypes=[("PDF", "*.pdf")])
            if not path:
                return None
            path = Path(path)
            if path.parent.resolve() == Path(self.cfg.vamd_folder).resolve():
                messagebox.showwarning(APP_NAME, "構文ファイルのフォルダには、書式付きファイル（PDF。実名入り）を保存しないでください。"
                                       "AI がフォルダの中を読むと、実名の PDF に届いてしまいます。", parent=self)
                continue
            return path

    def on_print(self):
        """確認表示と同じページを、プリンターに実際のサイズ（A4）で印刷する。保存していない変更があれば、先に保存する
        （印刷したものと、保存した書式付きファイル〔PDF〕が違わないように。2026-10-26 班長指示。それまでは保存しなくても
        印刷できた）。保存をやめたら印刷しない。"""
        if not printing.available():
            # Windows だけ（Mac などでは［印刷］を押せない。Ctrl+P も効かせない）。保存した PDF を、PDF のソフトで印刷する
            messagebox.showinfo(APP_NAME, "この PC では、VA Document から印刷できません。保存した PDF を開いて印刷してください。",
                                parent=self)
            return
        text = self.real_text()
        saved = ""
        if self.session.is_modified(text):
            if not self.on_save():                      # 記号・区切りの行の確かめも、保存のときに行う
                return
            text = self.real_text()
            # 保存したことは、印刷の知らせと一緒に下の欄に出す（印刷の途中の知らせで上書きされるため。2026-10-26 班長指摘）
            saved = f"版 {self.session.version} を保存し、"
        elif self._guard_tokens(text) is None:
            return
        try:
            data = self.session.preview_pdf(text)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"印刷するページを組めませんでした。\n{e}", parent=self)
            return
        with fitz.open(stream=data, filetype="pdf") as doc:
            pages = len(doc)
        # VA Document の「印刷」画面で選ぶ（2026-10-24 班長決定。Windows の新しい印刷画面の紛らわしい知らせを避ける）
        choice = PrintDialog(self, pages, self._preview_page + 1, printing.printers(),
                             self._last_printer or printing.default_printer(), printing.show_properties).result
        if choice is None:
            return
        name, mode, copies, page_list = choice
        self._last_printer = name
        try:
            hdc = printing.make_dc(name, mode, copies)
        except printing.PrintError as e:
            messagebox.showerror(APP_NAME, f"印刷できませんでした。\n{e}", parent=self)
            return

        def progress(done, total):
            self.status.configure(text=f"印刷しています（{done} / {total} ページ）…")
            self.update_idletasks()
        self.configure(cursor="watch")
        try:
            # 印刷の文書の名前は、Word と同じく PDF のファイル名（保存していなければ「VA Document」）。
            # 2026-10-23 班長決定（文書ID にしていたが、Microsoft Print to PDF で作った PDF の題名にもなるため改めた）
            doc_name = self.session.pdf_path.stem if self.session.pdf_path else APP_NAME
            n = printing.print_pdf(data, hdc, doc_name, page_list, progress=progress)
        except (printing.PrintError, OSError) as e:
            messagebox.showerror(APP_NAME, f"印刷できませんでした。\n{e}", parent=self)
            self.status.configure(text="印刷できませんでした。")
            return
        finally:
            self.configure(cursor="")
        self.status.configure(text=f"{saved}{n} ページをプリンターに送りました。")

