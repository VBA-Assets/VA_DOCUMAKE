"""印刷の色（2026-10-30 班長決定）：字だけのページは灰色、画像のあるページはカラーで送る。カラーのページは、上から
BAND_ROWS 行ずつに分けて送り、帯の間がすかないこと。Microsoft Print to PDF に印刷して確かめる（Windows だけ）。"""
import time

import fitz
import pytest

from va_document import printing


def color_pdf():
    """1ページ目は字だけ、2ページ目は字と、帯の切れ目をまたぐ高さのカラーの画像。"""
    doc = fitz.open()
    for k in range(2):
        page = doc.new_page(width=595.3, height=841.9)
        page.insert_text((72, 72), f"page {k + 1}", fontsize=12)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 200), False)
    pix.set_rect(pix.irect, (220, 40, 40))
    doc[1].insert_image(fitz.Rect(100, 100, 300, 700), pixmap=pix)
    return doc.tobytes()


def test_page_colorspace():
    with fitz.open(stream=color_pdf(), filetype="pdf") as doc:
        assert printing.page_colorspace(doc[0]) is fitz.csGRAY
        assert printing.page_colorspace(doc[1]) is fitz.csRGB


@pytest.fixture
def quiet_faulthandler():
    """Microsoft Print to PDF のドライバーは、中で Windows の例外を起こして中で処理する（test_app.py と同じ）。"""
    import faulthandler
    was = faulthandler.is_enabled()
    faulthandler.disable()
    yield
    if was:
        faulthandler.enable()


@pytest.mark.skipif(not printing.available(), reason="印刷は Windows だけ")
def test_color_page_is_printed_in_color_without_gaps(tmp_path, quiet_faulthandler):
    if "Microsoft Print to PDF" not in printing.printers():
        pytest.skip("Microsoft Print to PDF がない")
    out = tmp_path / "印刷.pdf"
    hdc = printing.make_dc("Microsoft Print to PDF")
    assert printing.print_pdf(color_pdf(), hdc, "色の試験", output=str(out)) == 2
    for _ in range(50):
        if out.exists() and out.stat().st_size:
            break
        time.sleep(0.2)
    time.sleep(0.5)
    with fitz.open(out) as doc:
        assert len(doc) == 2
        gray = doc[0].get_pixmap(dpi=72)
        assert gray.n == 3 or gray.n == 1
        assert all(len(set(gray.pixel(x, y)[:3])) == 1 for x in range(0, gray.width, 7) for y in range(0, gray.height, 7))
        # 2ページ目の画像は赤いまま。画像の上から下まで（帯の切れ目をまたいで）、白い行がない
        pix = doc[1].get_pixmap(dpi=150)
        z = 150 / 72
        x = round(200 * z)
        reds = [pix.pixel(x, y)[:3] for y in range(round(105 * z), round(695 * z))]
        assert all(r > 150 and g < 120 and b < 120 for r, g, b in reds), [c for c in reds if c[0] <= 150 or c[1] >= 120][:3]
        # 送った解像度（600 dpi）でも、帯の切れ目（BAND_ROWS 行ごと）の前後に、白い行がない
        fine = doc[1].get_pixmap(dpi=600, clip=fitz.Rect(195, 100, 205, 700))
        z = 600 / 72
        cut_rows = [r - round(100 * z) for r in range(printing.BAND_ROWS, round(700 * z), printing.BAND_ROWS)]
        assert cut_rows
        for r in cut_rows:
            for y in range(max(0, r - 3), min(fine.height, r + 3)):
                cr, cg, cb = fine.pixel(fine.width // 2, y)[:3]
                assert cr > 150 and cg < 120, (r, y, (cr, cg, cb))
