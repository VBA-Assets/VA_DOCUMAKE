"""Word のリボンと同じ形のボタンの並び（2026-10-24 班長指示）。

・ボタンを組（ファイル・AI 連携・書式など）に分け、組の名前をボタンの下に小さく書く。組と組の間は縦の線で区切る。
・よく使うボタンは大きいアイコンの下に字（large）、ほかは小さいアイコンの右に字を縦に3つまで積む（small）。
・ボタンは、ふだんは枠も地もなく、マウスを重ねたときだけ淡い青の地と枠を出す（Word のリボンと同じ。班長の UI 方針の
  「ボタンには常時、細い枠線」の、このツールだけの例外。2026-10-24 班長決定）。スタイルは theme.py の Ribbon*。
・組の名前は、どの組も下端にそろえる（2026-10-24 班長指示）。
・入力欄の側の幅に組が入りきらないときは、Word と同じく、大きいボタンだけの組（AI 連携）を小さいボタンを積んだ形に
  縮める。それでも入りきらない組は、次の段に送る（Word のように組を畳んで隠すことはしない）。
"""
from tkinter import ttk

ROWS = 3                # 小さいボタンを縦に積む数
LARGE_ICON = 32         # 大きいボタンのアイコンの大きさ（拡大率 100% のとき。画素）


class RibbonGroup(ttk.Frame):
    """リボンの1つの組。ボタンは左から列ごとに置く。"""

    def __init__(self, master, title, icons):
        super().__init__(master, style="Ribbon.TFrame")
        self.icons = icons
        self.body = ttk.Frame(self, style="Ribbon.TFrame")
        self.body.grid(row=0, column=0, sticky="nsew", padx=2, pady=(2, 0))
        ttk.Label(self, text=title, style="RibbonGroup.TLabel", anchor="center").grid(row=1, column=0, sticky="sew")
        ttk.Separator(self, orient="vertical").grid(row=0, column=1, rowspan=2, sticky="ns", pady=(4, 4))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)      # 組の高さがそろったとき、余りはボタンの側に回し、名前を下端にそろえる
        self._column = -1
        self._row = ROWS          # 今の列に積んだ数（ROWS なら次は新しい列）
        self._larges = []         # 大きいボタン [(ボタン, アイコン, 字, 大きいときの字)]
        self._has_small = False
        self.compact = False      # 大きいボタンを小さいボタンにして積んでいるか
        self._full_width = None   # 縮めていないときの幅

    def _images(self, icon, large):
        if self.icons is None or not icon:
            return {}
        size = round(LARGE_ICON * self.icons.scale) if large else None
        images = (self.icons.image(icon, size=size), "disabled", self.icons.image(icon, disabled=True, size=size))
        return {"image": images, "compound": "top" if large else "left"}

    def large(self, text, command, icon=None, label=None, **kw):
        """大きいボタン（アイコンの下に字）。1列を使う。label は大きいときの字（長い字を2行に分けるとき。
        縮めて小さいボタンにしたときは text の1行に戻す）。"""
        self._column += 1
        self._row = ROWS
        b = ttk.Button(self.body, text=label or text, command=command, style="RibbonLarge.TButton",
                       **self._images(icon, True), **kw)
        b.grid(row=0, column=self._column, rowspan=ROWS, sticky="ns", padx=1)
        self._larges.append((b, icon, text, label or text))
        return b

    def small(self, text, command, icon=None, new_column=False, **kw):
        """小さいボタン（アイコンの右に字）。今の列に縦に積み、ROWS 個で次の列へ。"""
        widget = ttk.Button(self.body, text=text, command=command, style="Ribbon.TButton",
                            **self._images(icon, False), **kw)
        self.place_small(widget, new_column)
        return widget

    def button(self, master, text, command, icon=None, **kw):
        """小さいボタンを、master（組の中の枠）に作る（置くのは呼ぶ側）。"""
        return ttk.Button(master, text=text, command=command, style="Ribbon.TButton", **self._images(icon, False), **kw)

    def place_small(self, widget, new_column=False, sticky="w"):
        """ほかの部品（ラベル付きの選択欄など）を、小さいボタンと同じく列に積む。"""
        self._has_small = True
        if new_column or self._row >= ROWS:
            self._column += 1
            self._row = 0
        widget.grid(in_=self.body, row=self._row, column=self._column, sticky=sticky, padx=1, pady=0)
        self._row += 1

    def block(self, widget):
        """部品（選択欄の並びなど）を、新しい列の上から置く。"""
        self._has_small = True
        self._column += 1
        self._row = ROWS
        widget.grid(in_=self.body, row=0, column=self._column, rowspan=ROWS, sticky="nw", padx=(1, 6), pady=(1, 0))

    @property
    def can_compact(self):
        """縮められる組か（大きいボタンが2つ以上で、ほかの部品がない組。縮めると幅が狭くなる）。"""
        return len(self._larges) >= 2 and not self._has_small

    def full_width(self):
        if not self.compact:
            self._full_width = self.winfo_reqwidth()
        return self._full_width

    def set_compact(self, compact):
        """大きいボタンを、小さいボタン（アイコンの右に字）にして縦に積む（compact が偽なら元に戻す）。"""
        if compact == self.compact:
            return
        self.full_width()
        self.compact = compact
        base = "Ribbon.TButton" if compact else "RibbonLarge.TButton"
        for k, (b, icon, text, label) in enumerate(self._larges):
            accent = str(b.cget("style")).startswith("Accent.")
            b.configure(style=("Accent." + base) if accent else base, text=text if compact else label,
                        **self._images(icon, not compact))
            b.grid_forget()
            if compact:
                b.grid(row=k % ROWS, column=k // ROWS, sticky="w", padx=1)
            else:
                b.grid(row=0, column=k, rowspan=ROWS, sticky="ns", padx=1)


def set_accent(button, on):
    """リボンのボタンの枠をアクセント色にする・戻す（大きいボタンでも、縮めた小さいボタンでも）。"""
    base = str(button.cget("style")).removeprefix("Accent.") or "RibbonLarge.TButton"
    button.configure(style=("Accent." + base) if on else base)


class Ribbon(ttk.Frame):
    """組を左から並べる。幅に入りきらない組は次の段に送る。"""

    def __init__(self, master, icons):
        super().__init__(master, style="Ribbon.TFrame")
        self.icons = icons
        self.groups = []
        self._layout = None
        self._busy = False
        self.bind("<Configure>", lambda e: self.reflow(e.width))

    def group(self, title):
        g = RibbonGroup(self, title, self.icons)
        self.groups.append(g)
        self.reflow(self.winfo_width())
        return g

    def reflow(self, width):
        """幅 width に入るように、組を段に分けて置く（同じ並びなら置き直さない。Configure が続かないように）。"""
        if self._busy:
            return
        if width <= 1:
            width = 10 ** 6
        # 入りきらなければ、大きいボタンだけの組を縮める
        compact = sum(g.full_width() for g in self.groups) > width
        if any(g.compact != (compact and g.can_compact) for g in self.groups):
            self._busy = True
            try:
                for g in self.groups:
                    g.set_compact(compact and g.can_compact)
                self.update_idletasks()
            finally:
                self._busy = False
        rows, used = [[]], 0
        for g in self.groups:
            w = g.winfo_reqwidth()
            if rows[-1] and used + w > width:
                rows.append([])
                used = 0
            rows[-1].append(g)
            used += w
        layout = [[id(g) for g in row] for row in rows]
        if layout == self._layout:
            return
        self._layout = layout
        for r, row in enumerate(rows):
            for c, g in enumerate(row):
                g.grid(row=r, column=c, sticky="nsw")


def labeled_rows(parent, rows):
    """ラベル付きの部品を縦に並べた枠（「文書の種類 [選択欄]」「ページ番号 [選択欄]」）。部品の左端をそろえる
    （2026-10-24 班長指示）。rows は [(ラベル, 部品を作る関数)]。(枠, [部品]) を返す。"""
    frame = ttk.Frame(parent, style="Ribbon.TFrame")
    widgets = []
    for r, (text, factory) in enumerate(rows):
        ttk.Label(frame, text=text, style="Ribbon.TLabel").grid(row=r, column=0, sticky="w", padx=(2, 6), pady=1)
        widget = factory(frame)
        widget.grid(row=r, column=1, sticky="w", pady=1)
        widgets.append(widget)
    return frame, widgets

