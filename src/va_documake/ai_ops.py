"""AI 連携：仮名化（選択範囲を仮名化・解除・一覧）、構文ファイルのコピー、AI の回答の取り込み、
外で書き換えられた構文ファイルの取り込み。

メインの画面（app.MainWindow）の部品（mixin）。保存（on_save）は file_ops.FileMixin が持つ。
"""
import tkinter as tk
from tkinter import messagebox

from . import APP_NAME, vadm
from .dialogs import ChangedOutsideDialog, KindDialog
from .pseudonym import KINDS, NotRegistrable, trim_selection


class AiMixin:
    """AI 連携の操作（MainWindow に混ぜて使う）。"""

    def _refresh_dictionary(self):
        self.tree.delete(*self.tree.get_children())
        for e in sorted(self.session.dictionary.entries.values(), key=lambda e: (KINDS.index(e.kind), e.token)):
            self.tree.insert("", "end", iid=e.token, values=(e.token, e.word, e.kind))

    def on_register(self):
        word = trim_selection(self._selection())
        if not word:
            messagebox.showinfo(APP_NAME, "入力欄で、仮名化する語を選んでから押してください。", parent=self)
            return
        found = self.session.dictionary.find(word)
        if found is not None:
            if messagebox.askyesno(APP_NAME, f"「{found.word}」は {found.token} として仮名化しています。仮名化を解除しますか？",
                                   parent=self):
                self._unregister(found.token)
            return
        try:
            self.session.dictionary.check(word)
        except NotRegistrable as e:
            messagebox.showerror(APP_NAME, str(e), parent=self)
            return
        kind = KindDialog(self, word).result
        if kind is None:
            return
        token = self.session.dictionary.register(word, kind)
        self._refresh_dictionary()
        self._tokenize_editor()          # エディターの同じ語を、すべて記号に置き換える
        self._highlight()
        self._render_preview()
        self._update_title()
        self.status.configure(text=f"「{word}」を {token} として仮名化しました。")

    def on_unregister(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "左の一覧で、解除する語を選んでから押してください。", parent=self)
            return
        e = self.session.dictionary.find(sel[0])
        if e and messagebox.askyesno(APP_NAME, f"「{e.word}」（{e.token}）の仮名化を解除しますか？\n"
                                     "解除した記号の英字は、ほかの語に使い直しません。", parent=self):
            self._unregister(e.token)

    def _unregister(self, token):
        e = self.session.dictionary.find(token)
        if e:
            # エディターの記号を、先に元の語に戻す（解除した語が記号のまま残らないように）
            self._replace_in_editor(token, e.word)
        e = self.session.dictionary.unregister(token)
        self._refresh_dictionary()
        self._highlight()
        self._render_preview()
        self._update_title()
        if e:
            self.status.configure(text=f"「{e.word}」（{e.token}）の仮名化を解除しました。")

    def on_copy_vadm(self):
        """構文ファイルの中身をクリップボードに写す（直していれば、先に保存する）。"""
        text = self.real_text()
        if self.session.is_modified(text) or self.session.version == 0 or not self.session.vadm_path.exists():
            if not messagebox.askyesno(APP_NAME, "構文ファイルをコピーする前に、書式付きファイル（PDF）と構文ファイルを保存します。"
                                       "よろしいですか？", parent=self):
                return
            if not self.on_save():
                return
        data = self.session.vadm_path.read_text(encoding="utf-8")
        self.clipboard_clear()
        self.clipboard_append(data)
        self.status.configure(text="AI に渡す構文ファイル（仮名化済み）の中身をコピーしました。AI のチャット画面に貼り付けてください。")

    def on_copy_path(self):
        """構文ファイルのフルパスをクリップボードに写す（2026-10-24 班長指示）。保存していなければ写さない。"""
        if not self.session.version:
            return
        path = str(self.session.vadm_path)
        self.clipboard_clear()
        self.clipboard_append(path)
        self.status.configure(text=f"構文ファイルのパスをコピーしました：{path}")

    def on_import(self):
        """［貼り付け］：クリップボードの AI の回答を、確認の画面なしでエディターに取り込む（2026-10-23 班長決定）。"""
        try:
            clip = self.clipboard_get()
        except tk.TclError:
            clip = ""
        if not vadm.SEPARATOR_RE.search(clip) and "==== VA DocuMake" not in clip:
            messagebox.showinfo(APP_NAME, "クリップボードに AI の回答がありません。\n"
                                "AI の画面で、回答のコードブロックのコピーボタンを押してから、［貼り付け］を押してください"
                                "（回答の最初の行に「==== VA DocuMake 文書ID …」の区切りの行が要ります）。", parent=self)
            return
        self.take_in(clip, "回答")

    def take_in(self, answer_text, origin, check_outside=True):
        """AI の回答（または外で書き換えられた構文ファイル）を、記号を実名に戻してエディターに入れ、保存する。

        ・文書ID が違う・区切りの行がないときは、入れずに知らせる。
        ・変わった段落・増えた段落は、エディターの右端に青い線を付けて示す（次に取り込むまで残る）。
        ・記号・配置の記号の問題と、消えた段落は、あるときだけ知らせる。Ctrl+Z 1回で元に戻せる。
        取り込んで保存できたら True。
        """
        text = self.real_text()
        try:
            content, r = self.session.review_answer(answer_text, text)
        except (vadm.NoSeparator, vadm.OtherDocument) as e:
            messagebox.showerror(APP_NAME, f"取り込めません。\n{e}", parent=self)
            return False
        new_text = self.session.apply_answer(content, text)
        self._replace_undoable(self.session.body(new_text))      # エディターは仮名のまま
        self.text.tag_remove("changed", "1.0", "end")
        for k in r.changed_lines:
            self.text.tag_add("changed", f"{k + 1}.0", f"{k + 1}.end+1c")
        if r.changed_lines:
            self.text.see(f"{r.changed_lines[0] + 1}.0")
        problems = []
        if r.unknown_tokens:
            problems.append("仮名化した語にない記号（記号のまま入れました）：" + "、".join(r.unknown_tokens))
        if r.lost_tokens:
            problems.append("前の文章にあって、なくなった記号：" + "、".join(r.lost_tokens))
        if r.lost_marks:
            problems.append("なくなった配置などの記号：\n" + "\n".join(f"　{m}　{ln[:40]}" for m, ln in r.lost_marks[:10]))
        if r.removed:
            restored = [self.session.dictionary.restore(ln)[0] for ln in r.removed]
            more = f"\n　ほか {len(restored) - 10} 段落" if len(restored) > 10 else ""
            problems.append(f"消えた段落（{len(restored)}）：\n" + "\n".join(f"　{ln[:50]}" for ln in restored[:10]) + more)
        if problems:
            messagebox.showwarning(APP_NAME, f"AI の{origin}を取り込みました。次の点を確かめてください。\n\n"
                                   + "\n\n".join(problems) + "\n\n取り込む前に戻すときは、Ctrl+Z を押してください。",
                                   parent=self)
        saved = self.on_save(check_outside=check_outside, allow_unknown=True)
        notes = [f"変わった・増えた段落 {len(r.changed_lines)}（右の青い線）"]
        if r.removed:
            notes.append(f"消えた段落 {len(r.removed)}")
        if r.older:
            notes.append(f"前の版（版 {content.version}）をもとにした回答")
        head = f"AI の{origin}を取り込み、版 {self.session.version} を保存しました。" if saved else \
            f"AI の{origin}を取り込みました（まだ保存していません）。"
        self.status.configure(text=head + "　" + "、".join(notes) + "。Ctrl+Z で取り込む前に戻せます。")
        return saved

    def _import_outside(self):
        """外で書き換えられた構文ファイルの中身を、［貼り付け］と同じく取り込み、保存する。"""
        self._declined_stamp = self.session.outside_stamp()
        return self.take_in(self.session.outside_vadm_text(), "用ファイル（外で書き換えたもの）", check_outside=False)

    def _on_focus_in(self, event=None):
        """VA DocuMakeの画面に戻ったとき、構文ファイルが外で書き換えられていれば、取り込むかを尋ねる
        （取り込まないと答えた中身については、もう一度は尋ねない。保存するときには、改めて尋ねる）。"""
        if self._focus_job is None:
            self._focus_job = self.after(300, self._check_outside)

    def _check_outside(self):
        self._focus_job = None
        if self._checking_outside or self.grab_current() is not None:
            return
        try:
            if not self.session.vadm_changed_outside() or self.session.outside_stamp() == self._declined_stamp:
                return
        except OSError:
            return
        self._checking_outside = True
        try:
            choice = ChangedOutsideDialog(self, at_save=False).result
            self._declined_stamp = self.session.outside_stamp()
            if choice == "import":
                self._import_outside()
        finally:
            self._checking_outside = False
