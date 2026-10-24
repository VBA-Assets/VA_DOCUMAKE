"""確認の画面（種別の選択・外で書き換えられた・記号の元の語・内容証明・オプション）。"""
import tkinter as tk
from tkinter import ttk

from . import theme
from .pseudonym import KINDS




class _Dialog(tk.Toplevel):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.configure(background=theme.WINDOW_BG)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda e: self.cancel())

    def run(self):
        self.update_idletasks()
        parent = self.master
        x = parent.winfo_rootx() + max((parent.winfo_width() - self.winfo_reqwidth()) // 2, 0)
        y = parent.winfo_rooty() + max((parent.winfo_height() - self.winfo_reqheight()) // 3, 0)
        self.geometry(f"+{x}+{y}")
        self.grab_set()
        self.wait_window()

    def cancel(self):
        self.destroy()

    def buttons(self, ok_text, ok_command, cancel_text="やめる"):
        bar = ttk.Frame(self, padding=(12, 8, 12, 12))
        bar.pack(side="bottom", fill="x")
        ttk.Button(bar, text=cancel_text, command=self.cancel).pack(side="right")
        ok = ttk.Button(bar, text=ok_text, style="Accent.TButton", command=ok_command)
        ok.pack(side="right", padx=(0, 8))
        return bar


class KindDialog(_Dialog):
    """仮名化する語の種別を選ぶ。"""

    def __init__(self, parent, word):
        super().__init__(parent, "種別を選ぶ")
        self.result = None
        self.kind = tk.StringVar(value=KINDS[0])
        body = ttk.Frame(self, padding=(16, 14, 16, 4))
        body.pack(fill="both")
        ttk.Label(body, text=f"「{word}」を仮名化します。種別を選んでください。").pack(anchor="w", pady=(0, 8))
        for k in KINDS:
            ttk.Radiobutton(body, text=k, value=k, variable=self.kind).pack(anchor="w", pady=1)
        self.buttons("仮名化する", self.ok)
        self.bind("<Return>", lambda e: self.ok())
        self.run()

    def ok(self):
        self.result = self.kind.get()
        self.destroy()


class RenameDialog(_Dialog):
    """仮名化した語の元の語を変える（記号はそのまま。2026-10-25 班長指示）。"""

    def __init__(self, parent, entry):
        super().__init__(parent, "元の語を変える")
        self.result = None
        body = ttk.Frame(self, padding=(16, 14, 16, 4))
        body.pack(fill="both")
        ttk.Label(body, text=f"{entry.token} の元の語を変えます。文章の中の {entry.token} は、すべて新しい語になります。"
                  ).pack(anchor="w", pady=(0, 8))
        ttk.Label(body, text=f"今の語：{entry.word}", style="Note.TLabel").pack(anchor="w", pady=(0, 4))
        self.word = tk.StringVar(value=entry.word)
        box = ttk.Entry(body, textvariable=self.word, width=40)
        box.pack(anchor="w", fill="x")
        box.select_range(0, "end")
        box.focus_set()
        self.buttons("変える", self.ok)
        self.bind("<Return>", lambda e: self.ok())
        self.run()

    def ok(self):
        self.result = self.word.get()
        self.destroy()


class ChangedOutsideDialog(_Dialog):
    """構文ファイルが外で書き換えられたことを知らせ、どうするかを尋ねる。result は "import"・"overwrite"・None。"""

    def __init__(self, parent, at_save):
        super().__init__(parent, "構文ファイルが書き換えられています")
        self.result = None
        body = ttk.Frame(self, padding=(16, 14, 16, 4))
        body.pack(fill="both")
        msg = ("構文ファイル（VADM）が、VA DocuMakeの外で書き換えられています"
               "（テキストエディターで直した、AI の回答を上書き保存した、など）。\n")
        if at_save:
            msg += ("このまま保存すると、外で書き換えた中身は消えます。\n"
                    "［取り込む］：外で書き換えた中身をエディターに取り込んでから保存します（変わった段落は右の青い線で示します）。\n"
                    "［上書きする］：外で書き換えた中身を捨てて、エディターの文章で保存します。")
        else:
            msg += "外で書き換えた中身を、エディターに取り込みますか？（変わった段落は右の青い線で示し、Ctrl+Z で元に戻せます）"
        ttk.Label(body, text=msg, justify="left").pack(anchor="w")
        bar = ttk.Frame(self, padding=(12, 10, 12, 12))
        bar.pack(side="bottom", fill="x")
        ttk.Button(bar, text="やめる" if at_save else "取り込まない", command=self.cancel).pack(side="right")
        if at_save:
            ttk.Button(bar, text="上書きする", command=lambda: self.choose("overwrite")).pack(side="right", padx=(0, 8))
        ttk.Button(bar, text="取り込む", style="Accent.TButton",
                   command=lambda: self.choose("import")).pack(side="right", padx=(0, 8))
        self.run()

    def choose(self, value):
        self.result = value
        self.destroy()


class MissingDialog(_Dialog):
    """元の語が求まらなかった記号の、元の語を利用者に尋ねる（仕様.md の7）。"""

    def __init__(self, parent, session, result):
        super().__init__(parent, "記号の元の語")
        self.answers = {}
        r = result.recovery
        head = ttk.Frame(self, padding=(12, 12, 12, 4))
        head.pack(fill="x")
        ttk.Label(head, text="次の記号の元の語が、PDF から求まりませんでした。分かるものは入力してください。\n"
                             "空のままにした記号は、記号のまま入力欄に入ります（後から［選択範囲を仮名化］で仮名化できます）。",
                  justify="left").pack(anchor="w")
        grid = ttk.Frame(self, padding=(12, 4))
        grid.pack(fill="both", expand=True)
        self.entries = {}
        for n, tok in enumerate(result.unresolved):
            ttk.Label(grid, text=tok).grid(row=n, column=0, sticky="w", padx=(0, 8), pady=2)
            e = ttk.Entry(grid, width=40)
            e.grid(row=n, column=1, sticky="we", pady=2)
            if tok in r.conflicts:
                best = max(r.conflicts[tok].items(), key=lambda kv: kv[1])[0]
                e.insert(0, best)
                ttk.Label(grid, style="Note.TLabel",
                          text="候補：" + "、".join(r.conflicts[tok])).grid(row=n, column=2, sticky="w", padx=(8, 0))
            self.entries[tok] = e
        self.buttons("決める", self.accept, "空のまま開く")
        self.run()

    def accept(self):
        self.answers = {tok: e.get() for tok, e in self.entries.items()}
        self.destroy()


class NaiyouDialog(_Dialog):
    """内容証明の字数・行数を超えた所を知らせ、保存するかを尋ねる（2026-10-24 班長指示）。ok が真なら保存する。"""

    def __init__(self, parent, problem):
        super().__init__(parent, "内容証明の字数・行数")
        self.ok = False
        body = ttk.Frame(self, padding=(16, 14, 16, 4))
        body.pack(fill="both")
        ttk.Label(body, text=problem.message() + "\n\nエディターのカーソルを、その行に動かしました。"
                             "このまま保存すると、内容証明として出せないことがあります。",
                  justify="left", wraplength=520).pack(anchor="w")
        bar = ttk.Frame(self, padding=(12, 10, 12, 12))
        bar.pack(side="bottom", fill="x")
        ttk.Button(bar, text="このまま保存する", command=self.accept).pack(side="right")
        stop = ttk.Button(bar, text="保存をやめて直す", style="Accent.TButton", command=self.cancel)
        stop.pack(side="right", padx=(0, 8))
        stop.focus_set()
        self.bind("<Return>", lambda e: self.cancel())
        self.run()

    def accept(self):
        self.ok = True
        self.destroy()


class OptionsDialog(_Dialog):
    """オプション（構文ファイルの保存場所、エディターの書体・字の大きさ・行の間隔。2026-10-24 班長指示）。
    result は {"vadm_folder", "font_family", "font_size", "line_spacing"}（やめたら None）。"""

    def __init__(self, parent, cfg, font_choices, size_range, spacing_range, prompt, default_prompt):
        super().__init__(parent, "オプション")
        self.result = None
        self.size_range, self.spacing_range = size_range, spacing_range
        self.prompt, self.default_prompt, self.new_prompt = prompt, default_prompt, None
        body = ttk.Frame(self, padding=(16, 14, 16, 4))
        body.pack(fill="both", expand=True)
        box = ttk.Labelframe(body, text="構文ファイル（.vadm）の保存場所", padding=(10, 6))
        box.pack(fill="x")
        self.folder = tk.StringVar(value=cfg.vadm_folder)
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.folder, width=60).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="参照", command=self.browse).pack(side="left", padx=(6, 0))
        # 注意書きは文ごとに改行する（Tk の折り返しは語の途中で切れるため）
        ttk.Label(box, style="Note.TLabel", justify="left",
                  text="共有フォルダも選べます（ほかの人と文書を共有するとき）。\n"
                       "このフォルダには構文ファイル（仮名化済み）だけを置き、書式付きファイル（PDF）や事件の資料（実名入り）は"
                       "置かないでください。\n"
                       "ほかの人が構文ファイルを開いて実名に戻すには、同じ文書の書式付きファイル（PDF）も必要です。").pack(anchor="w", pady=(6, 0))
        box = ttk.Labelframe(body, text="エディター", padding=(10, 6))
        box.pack(fill="x", pady=(10, 0))
        self.family = tk.StringVar(value=cfg.editor_font_family or "（既定）")
        self.size = tk.StringVar(value=str(cfg.editor_font_size))
        self.spacing = tk.StringVar(value=str(cfg.editor_line_spacing))
        ttk.Label(box, text="書体").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Combobox(box, textvariable=self.family, state="readonly", width=20,
                     values=["（既定）"] + list(font_choices)).grid(row=0, column=1, sticky="w", pady=2)
        for r, (label, var, rng, unit) in enumerate((("字の大きさ", self.size, size_range, "ポイント"),
                                                     ("行の間隔", self.spacing, spacing_range,
                                                      "画素（行の上と下に足す間隔）")), start=1):
            ttk.Label(box, text=label).grid(row=r, column=0, sticky="w", padx=(0, 8), pady=2)
            cell = ttk.Frame(box)
            cell.grid(row=r, column=1, sticky="w", pady=2)
            ttk.Spinbox(cell, textvariable=var, from_=rng[0], to=rng[1], width=5).pack(side="left")
            ttk.Label(cell, text=unit, style="Note.TLabel").pack(side="left", padx=(6, 0))
        ttk.Label(box, style="Note.TLabel", justify="left",
                  text="書体は、全角と半角の幅がそろうものから選べます。\n"
                       "書体・字の大きさ・行の間隔は、エディターの見た目だけで、PDF には関係しません。").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        box = ttk.Labelframe(body, text="AI への指示（構文ファイルの上の部分）", padding=(10, 6))
        box.pack(fill="x", pady=(10, 0))
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.prompt_note = ttk.Label(row, style="Note.TLabel")
        self.prompt_note.pack(side="left")
        ttk.Button(row, text="確認・修正", command=self.edit_prompt).pack(side="right")
        self._show_prompt_state()
        self.buttons("OK", self.accept, "キャンセル")
        self.run()

    def _show_prompt_state(self):
        current = self.new_prompt if self.new_prompt is not None else self.prompt
        same = current.rstrip() == self.default_prompt.rstrip()
        self.prompt_note.configure(text="既定の指示を使っています。" if same else "直した指示を使っています。")

    def edit_prompt(self):
        current = self.new_prompt if self.new_prompt is not None else self.prompt
        dlg = PromptDialog(self, current, self.default_prompt)
        if dlg.result is not None:
            self.new_prompt = dlg.result
            self._show_prompt_state()

    def browse(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(parent=self, title="構文ファイルの保存場所", initialdir=self.folder.get(),
                                         mustexist=True)
        if folder:
            self.folder.set(folder)

    def accept(self):
        from pathlib import Path
        from tkinter import messagebox
        folder = self.folder.get().strip()
        if not folder or not Path(folder).is_dir():
            messagebox.showerror("オプション", "構文ファイルの保存場所のフォルダが見つかりません。", parent=self)
            return
        try:
            size, spacing = int(self.size.get()), int(self.spacing.get())
        except ValueError:
            messagebox.showerror("オプション", "字の大きさと行の間隔は、数字で入れてください。", parent=self)
            return
        if not (self.size_range[0] <= size <= self.size_range[1] and self.spacing_range[0] <= spacing <= self.spacing_range[1]):
            messagebox.showerror("オプション", f"字の大きさは {self.size_range[0]}〜{self.size_range[1]}、行の間隔は "
                                 f"{self.spacing_range[0]}〜{self.spacing_range[1]} の数字にしてください。", parent=self)
            return
        family = self.family.get()
        self.result = {"vadm_folder": folder, "font_family": "" if family == "（既定）" else family,
                       "font_size": size, "line_spacing": spacing, "prompt": self.new_prompt}
        self.destroy()


class PromptDialog(_Dialog):
    """AI への指示（構文ファイルの区切りの行より上の部分）を確かめ、直す（2026-10-24 班長指示）。
    result は直した指示（やめたら None）。"""

    def __init__(self, parent, prompt, default_prompt):
        super().__init__(parent, "AI への指示")
        self.result = None
        self.default_prompt = default_prompt
        head = ttk.Frame(self, padding=(12, 12, 12, 4))
        head.pack(fill="x")
        ttk.Label(head, justify="left",
                  text="構文ファイルの上に付ける、AI への指示です。今の文書と、これから作る文書に使います。\n"
                       "記号（〔人名Ａ〕など）や区切りの行を残すよう求める部分は、消さないでください。").pack(anchor="w")
        frame = ttk.Frame(self, padding=(12, 0))
        frame.pack(fill="both", expand=True)
        self.text = tk.Text(frame, wrap="char", height=24, width=90, font=theme.editor_font(parent), padx=6, pady=6,
                            undo=True)
        ys = ttk.Scrollbar(frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=ys.set)
        ys.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.insert("1.0", prompt.rstrip("\n"))
        bar = self.buttons("OK", self.accept, "キャンセル")
        ttk.Button(bar, text="既定に戻す", command=self.reset).pack(side="left")
        self.run()

    def reset(self):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self.default_prompt.rstrip("\n"))

    def accept(self):
        self.result = self.text.get("1.0", "end-1c").rstrip() + "\n"
        self.destroy()


class PrintDialog(_Dialog):
    """VA DocuMake の「印刷」画面（プリンター・部数・ページ。2026-10-24 班長決定。Windows 11 の新しい印刷画面は、
    プレビューの欄に「このアプリは印刷プレビューをサポートしていません」と出て紛らわしいため）。
    result は (プリンターの名前, DEVMODE〔プロパティで直さなければ None〕, 部数, ページ〔0 から〕のリスト)。やめたら None。"""

    def __init__(self, parent, pages, current_page, printer_names, chosen, show_properties):
        super().__init__(parent, "印刷")
        self.result = None
        self.pages, self.current_page, self.show_properties = pages, current_page, show_properties
        self.modes = {}             # プリンター → プロパティで直した設定
        body = ttk.Frame(self, padding=(16, 14, 16, 4))
        body.pack(fill="both")
        box = ttk.Labelframe(body, text="プリンター", padding=(10, 6))
        box.pack(fill="x")
        self.printer = tk.StringVar(value=chosen if chosen in printer_names else
                                    (printer_names[0] if printer_names else ""))
        ttk.Combobox(box, textvariable=self.printer, values=printer_names, state="readonly", width=40).pack(
            side="left")
        ttk.Button(box, text="プロパティ", command=self.properties).pack(side="left", padx=(8, 0))
        box = ttk.Labelframe(body, text="印刷するページ", padding=(10, 6))
        box.pack(fill="x", pady=(10, 0))
        self.which = tk.StringVar(value="all")
        ttk.Radiobutton(box, text=f"すべて（{pages} ページ）", value="all", variable=self.which).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=1)
        ttk.Radiobutton(box, text=f"確認表示のページ（{current_page} ページ目）", value="current",
                        variable=self.which).grid(row=1, column=0, columnspan=2, sticky="w", pady=1)
        ttk.Radiobutton(box, text="ページを指定", value="range", variable=self.which).grid(
            row=2, column=0, sticky="w", pady=1)
        self.range = tk.StringVar()
        entry = ttk.Entry(box, textvariable=self.range, width=20)
        entry.grid(row=2, column=1, sticky="w", padx=(6, 0))
        entry.bind("<FocusIn>", lambda e: self.which.set("range"))
        ttk.Label(box, text="例：1-3, 5", style="Note.TLabel").grid(row=2, column=2, sticky="w", padx=(6, 0))
        row = ttk.Frame(body)
        row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, text="部数").pack(side="left")
        self.copies = tk.StringVar(value="1")
        ttk.Spinbox(row, textvariable=self.copies, from_=1, to=99, width=5).pack(side="left", padx=(8, 0))
        ttk.Label(body, style="Note.TLabel", justify="left",
                  text="確認表示と同じページを、A4 の実際の大きさで印刷します。\n"
                       "用紙のトレイ・両面などは、［プロパティ］で決めてください。").pack(anchor="w", pady=(10, 0))
        self.buttons("印刷", self.accept, "キャンセル")
        self.bind("<Return>", lambda e: self.accept())
        self.run()

    def properties(self):
        from tkinter import messagebox
        name = self.printer.get()
        if not name:
            return
        try:
            mode = self.show_properties(int(self.wm_frame(), 16), name, self.modes.get(name))
        except Exception as e:
            messagebox.showerror("印刷", f"プリンターの設定の画面を開けませんでした。\n{e}", parent=self)
            return
        if mode is not None:
            self.modes[name] = mode

    def accept(self):
        from tkinter import messagebox
        from .printing import parse_pages
        name = self.printer.get()
        if not name:
            messagebox.showerror("印刷", "プリンターを選んでください。", parent=self)
            return
        try:
            copies = int(self.copies.get())
            if not 1 <= copies <= 99:
                raise ValueError
        except ValueError:
            messagebox.showerror("印刷", "部数は 1〜99 の数字にしてください。", parent=self)
            return
        which = self.which.get()
        if which == "all":
            pages = list(range(self.pages))
        elif which == "current":
            pages = [self.current_page - 1]
        else:
            try:
                pages = parse_pages(self.range.get(), self.pages)
            except ValueError:
                messagebox.showerror("印刷", f"ページの指定を読めません（1〜{self.pages} の数字を、「1-3, 5」のように"
                                     "書いてください）。", parent=self)
                return
        self.result = (name, self.modes.get(name), copies, pages)
        self.destroy()

