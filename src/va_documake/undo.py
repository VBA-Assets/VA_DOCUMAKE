"""エディター（tk.Text）の書き換えを、Ctrl+Z（元に戻す）1回で戻せる1つの操作として記録する。"""
from contextlib import contextmanager


@contextmanager
def undoable(text):
    """with の中の書き換え（消す・入れる）を、1つの操作として記録する。

    Tk は「消す」と「入れる」の間に自動で区切りを入れるので、そのままでは Ctrl+Z 1回で文章が空になったり、
    何行かのうち1行だけ戻ったりする（2026-10-23）。配置の記号の付け替え・見出しのレベル・AI の回答の取り込み・
    置換で使う。
    """
    text.configure(autoseparators=False)
    text.edit_separator()
    try:
        yield
    finally:
        text.edit_separator()
        text.configure(autoseparators=True)
