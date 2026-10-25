"""Word のリボンと同じ形のボタンの並び（2026-10-24 班長指示）。

・ボタンを組（ファイル・AI 連携・書式など）に分け、組の名前をボタンの下に小さく書く。組と組の間は縦の線で区切る。
・よく使うボタンは大きいアイコンの下に字（large）、ほかは小さいアイコンの右に字を縦に3つまで積む（small）。
・ボタンは、ふだんは枠も地もなく、マウスを重ねたときだけ淡い青の地と枠を出す（Word のリボンと同じ。班長の UI 方針の
  「ボタンには常時、細い枠線」の、このツールだけの例外。2026-10-24 班長決定）。スタイルは theme.py の Ribbon*。
・組の名前は、どの組も下端にそろえる（2026-10-24 班長指示）。
・入力欄の側の幅に組が入りきらないときは、入りきらない組を次の段に送る（Word のように組を畳んで隠すことはしない）。
  もとは、大きいボタンだけの組（AI 連携）を小さいボタンを積んだ形に縮めてもいたが、2026-10-25 に［コピー］［貼り付け］を
  小さいボタンにして縮める組がなくなったので、その仕組みは除いた。
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

    def _images(self, icon, large):
        if self.icons is None or not icon:
            return {}
        size = round(LARGE_ICON * self.icons.scale) if large else None
        images = (self.icons.image(icon, size=size), "disabled", self.icons.image(icon, disabled=True, size=size))
        return {"image": images, "compound": "top" if large else "left"}

    def large(self, text, command, icon=None, **kw):
        """大きいボタン（アイコンの下に字）。1列を使う。長い字は改行で2行に分ける（説明書きは、改行を除いた字で引く。
        tooltip.py）。"""
        self._column += 1
        self._row = ROWS
        b = ttk.Button(self.body, text=text, command=command, style="RibbonLarge.TButton",
                       **self._images(icon, True), **kw)
        b.grid(row=0, column=self._column, rowspan=ROWS, sticky="ns", padx=1)
        return b

    def small(self, text, command, icon=None, new_column=False, **kw):
        """小さいボタン（アイコンの右に字）。今の列に縦に積み、ROWS 個で次の列へ。"""
        widget = ttk.Button(self.body, text=text, command=command, style="Ribbon.TButton",
                            **self._images(icon, False), **kw)
        self.place_small(widget, new_column)
        return widget

    def place_small(self, widget, new_column=False, sticky="w"):
        """ほかの部品（ラベル付きの選択欄など）を、小さいボタンと同じく列に積む。"""
        if new_column or self._row >= ROWS:
            self._column += 1
            self._row = 0
        widget.grid(in_=self.body, row=self._row, column=self._column, sticky=sticky, padx=1, pady=0)
        self._row += 1

    def block(self, widget):
        """部品（選択欄の並びなど）を、新しい列の上から置く。"""
        self._column += 1
        self._row = ROWS
        widget.grid(in_=self.body, row=0, column=self._column, rowspan=ROWS, sticky="nw", padx=(1, 6), pady=(1, 0))


def set_accent(button, on):
    """リボンのボタンの枠をアクセント色にする・戻す（大きいボタンでも、小さいボタンでも）。"""
    base = str(button.cget("style")).removeprefix("Accent.") or "RibbonLarge.TButton"
    button.configure(style=("Accent." + base) if on else base)


class Ribbon(ttk.Frame):
    """組を左から並べる。幅に入りきらない組は次の段に送る。"""

    def __init__(self, master, icons):
        super().__init__(master, style="Ribbon.TFrame")
        self.icons = icons
        self.groups = []
        self._layout = None
        self.bind("<Configure>", lambda e: self.reflow(e.width))

    def group(self, title):
        g = RibbonGroup(self, title, self.icons)
        self.groups.append(g)
        self.reflow(self.winfo_width())
        return g

    def reflow(self, width):
        """幅 width に入るように、組を段に分けて置く（同じ並びなら置き直さない。Configure が続かないように）。"""
        if width <= 1:
            width = 10 ** 6
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

