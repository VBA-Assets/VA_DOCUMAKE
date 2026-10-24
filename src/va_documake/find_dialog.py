"""エディターの検索と置換（Ctrl+F・Ctrl+H）。"""
import tkinter as tk
from tkinter import ttk

from . import theme
from .undo import undoable


class FindDialog(tk.Toplevel):
    """エディターの検索と置換（メモ帳と同じく、開いたまま使える。2026-10-23 班長指示）。

    エディターは常に仮名なので、仮名化した語（実名）を入れると記号を探す・記号にする。［すべて置換］は、Ctrl+Z 1回で元に戻せる。
    """

    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.text = main.text
        self.title("検索と置換")
        self.transient(main)
        self.resizable(False, False)
        self.configure(background=theme.WINDOW_BG)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.close())
        self.find_var = tk.StringVar()
        self.replace_var = tk.StringVar()
        self.case_var = tk.BooleanVar(value=False)
        body = ttk.Frame(self, padding=(12, 12, 12, 4))
        body.pack(fill="both")
        ttk.Label(body, text="検索する文字列").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=2)
        self.find_entry = ttk.Entry(body, textvariable=self.find_var, width=36)
        self.find_entry.grid(row=0, column=1, sticky="we", pady=2)
        ttk.Label(body, text="置換後の文字列").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=2)
        self.replace_entry = ttk.Entry(body, textvariable=self.replace_var, width=36)
        self.replace_entry.grid(row=1, column=1, sticky="we", pady=2)
        tk.Checkbutton(body, text="大文字と小文字を区別する", variable=self.case_var,
                       command=self.mark_all).grid(row=2, column=1, sticky="w", pady=(4, 0))
        buttons = ttk.Frame(body, padding=(12, 0, 0, 0))
        buttons.grid(row=0, column=2, rowspan=4, sticky="n")
        for label, command, style in (("次を検索", lambda: self.find(True), "Accent.TButton"),
                                      ("前を検索", lambda: self.find(False), "TButton"),
                                      ("置換", self.replace_one, "TButton"),
                                      ("すべて置換", self.replace_all, "TButton"),
                                      ("閉じる", self.close, "TButton")):
            ttk.Button(buttons, text=label, style=style, command=command, width=12).pack(fill="x", pady=(0, 4))
        self.message = ttk.Label(self, style="Note.TLabel", padding=(12, 0, 12, 10))
        self.message.pack(fill="x")
        self.find_entry.bind("<Return>", lambda e: self.find(True))
        self.replace_entry.bind("<Return>", lambda e: self.replace_one())
        self.find_var.trace_add("write", lambda *a: self.mark_all())

    def show(self, initial, replace):
        if initial:
            self.find_var.set(initial)
        self.deiconify()
        self.lift()
        self.update_idletasks()
        if not getattr(self, "_placed", False):
            m = self.main
            x = m.winfo_rootx() + m.winfo_width() - self.winfo_reqwidth() - 40
            y = m.winfo_rooty() + 120
            self.geometry(f"+{max(x, 0)}+{y}")
            self._placed = True
        entry = self.replace_entry if replace and self.find_var.get() else self.find_entry
        entry.focus_set()
        entry.select_range(0, "end")
        self.mark_all()

    def _nocase(self):
        return not self.case_var.get()

    def _pattern(self):
        """検索する文字列。仮名化した語（実名）で検索したときは、エディターの記号を探す（エディターは常に仮名。
        2026-10-24）。"""
        return self.main.session.dictionary.pseudonymize(self.find_var.get())

    def _matches(self):
        """見つかった箇所 [(始め, 終わり)] を、文書の初めから順に返す。"""
        pattern = self._pattern()
        out = []
        if not pattern:
            return out
        start = "1.0"
        while True:
            count = tk.IntVar()
            pos = self.text.search(pattern, start, stopindex="end", nocase=self._nocase(), count=count)
            if not pos or count.get() == 0:
                break
            end = f"{pos}+{count.get()}c"
            out.append((pos, end))
            start = end
        return out

    def mark_all(self):
        self.text.tag_remove("found", "1.0", "end")
        self.text.tag_remove("found_current", "1.0", "end")
        matches = self._matches()
        for a, b in matches:
            self.text.tag_add("found", a, b)
        if self.find_var.get():
            self.message.configure(text=f"{len(matches)} 件見つかりました。" if matches else "見つかりません。")
        else:
            self.message.configure(text="")
        return matches

    def find(self, forward=True):
        pattern = self._pattern()
        if not pattern:
            return False
        count = tk.IntVar()
        if forward:
            start = self.text.index("sel.last") if self.text.tag_ranges("sel") else self.text.index("insert")
            pos = self.text.search(pattern, start, stopindex="end", nocase=self._nocase(), count=count) or \
                self.text.search(pattern, "1.0", stopindex="end", nocase=self._nocase(), count=count)
        else:
            start = self.text.index("sel.first") if self.text.tag_ranges("sel") else self.text.index("insert")
            pos = self.text.search(pattern, start, stopindex="1.0", backwards=True, nocase=self._nocase(),
                                   count=count) or \
                self.text.search(pattern, "end", stopindex="1.0", backwards=True, nocase=self._nocase(), count=count)
        if not pos:
            self.message.configure(text="見つかりません。")
            return False
        end = f"{pos}+{count.get()}c"
        self.text.tag_remove("sel", "1.0", "end")
        self.text.tag_add("sel", pos, end)
        # 検索の画面に入力の場所があるとエディターの選択の色が薄くなるので、今の1か所に別の色を付ける
        self.text.tag_remove("found_current", "1.0", "end")
        self.text.tag_add("found_current", pos, end)
        self.text.mark_set("insert", end if forward else pos)
        self.text.see(pos)
        return True

    def _selection_matches(self):
        if not self.text.tag_ranges("sel"):
            return False
        selected = self.text.get("sel.first", "sel.last")
        pattern = self._pattern()
        return selected == pattern if self.case_var.get() else selected.lower() == pattern.lower()

    def replace_one(self):
        """選んでいる箇所が検索する文字列なら置き換え、次を検索する。"""
        if not self.find_var.get():
            return
        if self._selection_matches():
            first = self.text.index("sel.first")
            with undoable(self.text):
                self.text.delete("sel.first", "sel.last")
                self.text.insert(first, self._replacement())
            self.text.mark_set("insert", f"{first}+{len(self._replacement())}c")
        self.find(True)
        self.mark_all()

    def replace_all(self):
        matches = self._matches()
        if not matches:
            self.message.configure(text="見つかりません。")
            return
        new = self._replacement()
        with undoable(self.text):          # Ctrl+Z 1回で、すべて元に戻る
            for a, b in reversed(matches):
                self.text.delete(a, b)
                self.text.insert(a, new)
        self.mark_all()
        self.message.configure(text=f"{len(matches)} 件を置換しました（Ctrl+Z で元に戻せます）。")

    def _replacement(self):
        """置き換える文字列（仮名化した語なら記号にする。エディターは常に仮名）。"""
        return self.main.session.dictionary.pseudonymize(self.replace_var.get())

    def close(self):
        self.text.tag_remove("found", "1.0", "end")
        self.text.tag_remove("found_current", "1.0", "end")
        self.withdraw()
        self.main.text.focus_set()
