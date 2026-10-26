"""IME の入力中の文字（変換前の文字）の書体を、エディターの書体に合わせる（Windows だけ）。

Tk のエディター（Text）では、IME が入力中の文字を、エディターの書体ではなく Windows の既定の小さい書体で
表示する。エディターに入るたびに、IME の入力中の書体（ImmSetCompositionFontW）をエディターの書体と大きさに
する（2026-10-23 班長指摘）。うまくいかなくても、入力そのものには差し支えないので、失敗は無視する。
"""
import os

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    class LOGFONTW(ctypes.Structure):
        _fields_ = [("lfHeight", wintypes.LONG), ("lfWidth", wintypes.LONG), ("lfEscapement", wintypes.LONG),
                    ("lfOrientation", wintypes.LONG), ("lfWeight", wintypes.LONG), ("lfItalic", wintypes.BYTE),
                    ("lfUnderline", wintypes.BYTE), ("lfStrikeOut", wintypes.BYTE), ("lfCharSet", wintypes.BYTE),
                    ("lfOutPrecision", wintypes.BYTE), ("lfClipPrecision", wintypes.BYTE),
                    ("lfQuality", wintypes.BYTE), ("lfPitchAndFamily", wintypes.BYTE),
                    ("lfFaceName", wintypes.WCHAR * 32)]

    _imm32 = ctypes.windll.imm32
    _user32 = ctypes.windll.user32
    _imm32.ImmGetContext.argtypes = [wintypes.HWND]
    _imm32.ImmGetContext.restype = wintypes.HANDLE
    _imm32.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
    _imm32.ImmSetCompositionFontW.argtypes = [wintypes.HANDLE, ctypes.POINTER(LOGFONTW)]
    _imm32.ImmGetCompositionFontW.argtypes = [wintypes.HANDLE, ctypes.POINTER(LOGFONTW)]
    _user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetAncestor.restype = wintypes.HWND
    _user32.GetFocus.restype = wintypes.HWND
    _GA_ROOT = 2
    _DEFAULT_CHARSET = 1


def _windows(widget):
    """IME の文脈を持ちうるウィンドウ（エディター自身・入力の場所・いちばん外のウィンドウ）。"""
    hwnd = widget.winfo_id()
    found = [hwnd, _user32.GetFocus(), _user32.GetAncestor(hwnd, _GA_ROOT)]
    return [h for k, h in enumerate(found) if h and h not in found[:k]]


def set_composition_font(widget, family, size_pt):
    """widget（Tk の Text など）の IME の入力中の書体を、family・size_pt（ポイント）にする。

    合わせられたウィンドウの数を返す（Windows 以外・失敗したときは 0）。
    """
    if os.name != "nt":
        return 0
    try:
        dpi = widget.winfo_fpixels("1i")
        lf = LOGFONTW()
        lf.lfHeight = -round(size_pt * dpi / 72)
        lf.lfWeight = 400
        lf.lfCharSet = _DEFAULT_CHARSET
        lf.lfFaceName = family[:31]
        done = 0
        for hwnd in _windows(widget):
            himc = _imm32.ImmGetContext(hwnd)
            if not himc:
                continue
            try:
                if _imm32.ImmSetCompositionFontW(himc, ctypes.byref(lf)):
                    done += 1
            finally:
                _imm32.ImmReleaseContext(hwnd, himc)
        return done
    except Exception:
        return 0


def composition_font(widget):
    """確かめるため：widget の IME の入力中の書体 (書体名, 高さ) を返す（取れなければ None）。"""
    if os.name != "nt":
        return None
    for hwnd in _windows(widget):
        himc = _imm32.ImmGetContext(hwnd)
        if not himc:
            continue
        try:
            lf = LOGFONTW()
            if _imm32.ImmGetCompositionFontW(himc, ctypes.byref(lf)):
                return lf.lfFaceName, lf.lfHeight
        finally:
            _imm32.ImmReleaseContext(hwnd, himc)
    return None
