"""エディターへの画像の挿入（［画像］・クリップボードの画像の貼り付け。[IMAGE 1]{30}。2026-10-29 班長決定。検討_画像の挿入.md）。

メインの画面（app.MainWindow）の部品（mixin。editor_ops.EditorMixin が混ぜる）。self.text（tk.Text）・self.session は
MainWindow が持つ。画像のデータは session.images（メモリの中だけ）に入れ、エディターには記号の行だけを入れる。
"""
from tkinter import filedialog, messagebox

from . import APP_NAME, images
from .document import IMAGE_RE, image_mark
from .layout import Typesetter
from .undo import undoable


class ImageMixin:
    """画像の挿入（MainWindow に混ぜて使う）。"""

    def on_image(self):
        """［画像］：画像ファイルを選び、カーソルのある行の次に [IMAGE n]{幅} の行を入れる（2026-10-29 班長決定）。
        ファイルを選ぶ画面の最初のフォルダは覚えない（設定ファイルに画像のフォルダを書かない）。カーソルが画像の行に
        あれば、差し替え・幅のメニューを出す（［表］と同じ作り。2026-10-31 班長決定）。"""
        mark = image_mark(self._line(self._cursor()[0]))
        if mark:
            self._post_image_menu(mark[0])
            return
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

    def _post_image_menu(self, number):
        self._post_button_menu(self.image_button, self._image_menu_items(number))

    def _image_menu_items(self, number):
        """画像の行の［画像］のメニュー [(字, 働き)]。データのない画像は、元の大きさが分からない。"""
        items = [("別の画像に差し替える", self.on_image_replace)]
        if number in self.session.images:
            items.append(("元の大きさにする", self.on_image_natural_width))
        return items + [("本文の幅いっぱいにする", self.on_image_full_width)]

    def _natural_width(self, picture):
        """画像を入れたときの幅（字数。画像を 96dpi で置いた幅を字数に切り上げたもの。1行の字数まで）。"""
        return min(images.natural_chars(picture, Typesetter(self.session.doc_type).pitch), self.session.doc_type.chars_lines[0])

    def _set_image_mark(self, number=None, width=None):
        """カーソルの行の画像の記号の番号・幅を書き換える（None はそのまま）。行のほかの字（配置の記号など）は変えない。
        Ctrl+Z 1回で戻せる。"""
        n = self._cursor()[0]
        m = IMAGE_RE.search(self._line(n))
        if not m:
            return
        kept = m.group(2)
        mark = f"[IMAGE {number or m.group(1)}]" + (f"{{{width or kept}}}" if width or kept else "")
        with undoable(self.text):
            self.text.delete(f"{n}.{m.start()}", f"{n}.{m.end()}")
            self.text.insert(f"{n}.{m.start()}", mark)
        self._go(n, len(self._line(n)))
        self.text.focus_set()
        self.refresh()

    def on_image_replace(self):
        """カーソルの行の画像を、選んだファイルの画像に差し替える（幅と配置はそのまま）。新しい番号を振って行の番号を
        書き換えるので、Ctrl+Z 1回で元の画像に戻せる（元の画像のデータは閉じるまでメモリに残る。同じ番号の行がほかに
        あっても、この行だけが替わる）。"""
        path = filedialog.askopenfilename(parent=self, title="差し替える画像", filetypes=images.FILE_TYPES)
        if not path:
            return
        try:
            picture = images.from_file(path)
            number = self.session.add_picture(picture, self.raw_text())
        except (OSError, images.NotImage):
            messagebox.showerror(APP_NAME, "画像として読めないファイルです（差し替えていません）。", parent=self)
            return
        except ValueError as e:
            messagebox.showerror(APP_NAME, str(e), parent=self)
            return
        self._set_image_mark(number=number)
        self.status.configure(text="画像を差し替えました。Ctrl+Z で元の画像に戻せます。")

    def on_image_natural_width(self):
        """カーソルの行の画像の幅を、入れたときの幅に戻す。"""
        mark = image_mark(self._line(self._cursor()[0]))
        if mark and mark[0] in self.session.images:
            self._set_image_mark(width=self._natural_width(self.session.images[mark[0]]))

    def on_image_full_width(self):
        """カーソルの行の画像の幅を、1行の字数にする（組むときに、置ける幅に収める。layout_blocks.image_size）。"""
        self._set_image_mark(width=self.session.doc_type.chars_lines[0])

    def insert_pictures(self, pictures):
        """画像を文書に加え、カーソルのある行の次（カーソルの行が空ならその行。表の中なら表の後）に、1つずつ
        [IMAGE n]{幅} の行を入れる。幅は、画像を 96dpi で置いた幅を字数に切り上げたもの（1行の字数まで）。
        Ctrl+Z 1回で戻せる（画像のデータは閉じるまでメモリに残り、行のある画像だけを PDF に入れる）。"""
        lines = []
        for pic in pictures:
            try:
                n = self.session.add_picture(pic, self.raw_text())
            except ValueError as e:
                messagebox.showerror(APP_NAME, str(e), parent=self)
                break
            lines.append(f"[IMAGE {n}]{{{self._natural_width(pic)}}}")
        if not lines:
            return
        end = self._insert_block(lines) + len(lines) - 1
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
