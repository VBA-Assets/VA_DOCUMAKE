"""エディターへの画像の挿入（［画像］・クリップボードの画像の貼り付け。[IMAGE 1]{30}。2026-10-29 班長決定。検討_画像の挿入.md）。

メインの画面（app.MainWindow）の部品（mixin。editor_ops.EditorMixin が混ぜる）。self.text（tk.Text）・self.session は
MainWindow が持つ。画像のデータは session.images（メモリの中だけ）に入れ、エディターには記号の行だけを入れる。
"""
from tkinter import filedialog, messagebox

from . import APP_NAME, images
from .document import is_table_line
from .layout import Typesetter
from .undo import undoable


class ImageMixin:
    """画像の挿入（MainWindow に混ぜて使う）。"""

    def on_image(self):
        """［画像］：画像ファイルを選び、カーソルのある行の次に [IMAGE n]{幅} の行を入れる（2026-10-29 班長決定）。
        ファイルを選ぶ画面の最初のフォルダは覚えない（設定ファイルに画像のフォルダを書かない）。"""
        paths = filedialog.askopenfilenames(parent=self, title="画像を入れる", filetypes=images.FILE_TYPES)
        pictures, failed = [], 0
        for path in paths:
            try:
                pictures.append(images.from_file(path))
            except (OSError, images.NotImage):
                failed += 1
        if failed:
            messagebox.showerror(APP_NAME, f"画像として読めないファイルが {failed} つありました（入れていません）。", parent=self)
        if pictures:
            self.insert_pictures(pictures)

    def insert_pictures(self, pictures):
        """画像を文書に加え、カーソルのある行の次（カーソルの行が空ならその行。表の中なら表の後）に、1つずつ
        [IMAGE n]{幅} の行を入れる。幅は、画像を 96dpi で置いた幅を字数に切り上げたもの（1行の字数まで）。
        Ctrl+Z 1回で戻せる（画像のデータは閉じるまでメモリに残り、行のある画像だけを PDF に入れる）。"""
        chars = self.session.doc_type.chars_lines[0]
        pitch = Typesetter(self.session.doc_type).pitch
        lines = []
        for pic in pictures:
            try:
                n = self.session.add_picture(pic, self.raw_text())
            except ValueError as e:
                messagebox.showerror(APP_NAME, str(e), parent=self)
                break
            lines.append(f"[IMAGE {n}]{{{min(images.natural_chars(pic, pitch), chars)}}}")
        if not lines:
            return
        n = int(self.text.index("insert").split(".")[0])
        last = int(self.text.index("end-1c").split(".")[0])
        while n < last and is_table_line(self.text.get(f"{n}.0", f"{n}.end")) \
                and is_table_line(self.text.get(f"{n + 1}.0", f"{n + 1}.end")):
            n += 1
        block = "\n".join(lines)
        with undoable(self.text):
            if not self.text.get(f"{n}.0", f"{n}.end").strip():
                self.text.delete(f"{n}.0", f"{n}.end")
                self.text.insert(f"{n}.0", block)
                end = n + len(lines) - 1
            else:
                self.text.insert(f"{n}.end", "\n" + block)
                end = n + len(lines)
        self.text.mark_set("insert", f"{end}.end")
        self.text.see("insert")
        self.status.configure(text=f"画像を {len(lines)} つ入れました（{'、'.join(lines)}）。幅は、エディターで"
                                   "{ } の中の字数を直して変えられます。Ctrl+Z で入れる前に戻せます。")
        self.refresh()

    def paste_pictures(self):
        """Ctrl+V で、クリップボードに字がないとき（editor_ops._on_paste から呼ぶ）：クリップボードの画像（エクスプローラーで
        コピーした画像ファイルも）を入れる。入れたら True。Win+V で選んだ画像も、Windows が置き直してから Ctrl+V を送るので、
        ここを通る。クリップボードは、利用者が Ctrl+V を押したときだけ読む。"""
        pictures = images.from_clipboard()
        if not pictures:
            return False
        self.insert_pictures(pictures)
        return True
