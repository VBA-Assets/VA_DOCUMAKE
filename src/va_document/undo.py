"""エディター（tk.Text）の書き換えを、Ctrl+Z（元に戻す）1回で戻せる1つの操作として記録する。"""
from contextlib import contextmanager


@contextmanager
def undoable(text):
    """with の中の書き換え（消す・入れる）を、1つの操作として記録する。

    Tk は「消す」と「入れる」の間に自動で区切りを入れるので、そのままでは Ctrl+Z 1回で文章が空になったり、
    何行かのうち1行だけ戻ったりする（2026-10-23）。配置の記号の付け替え・見出しのレベル・AI の回答の取り込み・
    置換で使う。with を入れ子にしたときは、いちばん外側の with の全体を1つの操作にする（［見出し］で記号を付けた後、
    直前の同じ段の見出しにならって太字・前の空行を付けるのも、Ctrl+Z 1回で戻すため）。
    """
    depth = getattr(text, "_undoable_depth", 0)
    text._undoable_depth = depth + 1
    if not depth:
        text.configure(autoseparators=False)
        text.edit_separator()
    try:
        yield
    finally:
        text._undoable_depth = depth
        if not depth:
            text.edit_separator()
            text.configure(autoseparators=True)
