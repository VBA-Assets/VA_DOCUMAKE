"""組んだ結果を PDF に書き出し、ファイル識別子に文書ID と版を入れる（仕様.md の9.1・9.3）。

・書体は PDF に埋め込む。埋め込む前に、書体ファイルの埋め込みの許可（OS/2 の fsType）を確かめ、
  埋め込みが禁止されている書体（fsType の 2）は使わない（Windows の書体の再配布の条件）。
・PDF の文書情報（作成ソフト・作成者・日時など）と XMP は入れない（VA mints のメタデータ検出で
  「メタデータなし」になるようにするため）。
・ファイル識別子（トレーラーの /ID）の1つ目に「VAMD:<文書ID>:<版>」を入れる。2つ目は保存し直すと
  作り直されるので使わない（2026-10-23、PyMuPDF・pikepdf で確認）。
"""
import io
import os
import re
import sys
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
from fontTools.ttLib import TTCollection, TTFont as FTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .doctypes import (FW_DIGITS, PAGE_NUMBER_BOTTOM_CENTER, PAGE_NUMBER_BOTTOM_CENTER_DECORATED,
                       PAGE_NUMBER_BOTTOM_RIGHT, PAGE_NUMBER_NONE, PAGE_NUMBER_TOP_RIGHT)
from .layout import (DOT_RADIUS, DOT_RISE, DOUBLE_RULE_GAP, FONT_SIZE, FOOTER_BASELINE_OFFSET, FOOTER_DISTANCE,
                     HEADER_DISTANCE, PAGE_H, PAGE_W, RULE_WIDTH)

def _font_dir():
    """同梱の書体（assets/fonts）の場所。exe（PyInstaller）では展開先（Windows の exe には入れない）。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / "assets" / "fonts"
    return Path(__file__).resolve().parents[2] / "assets" / "fonts"


# 書体の組（本文の明朝、太字のゴシック）。各書体は (ファイル, ttc の中の番号)。太字はゴシックで描く（VAスタイルの
# 太字と同じ。字の幅は明朝と同じ）
MS_FONTS = ((r"C:\Windows\Fonts\msmincho.ttc", 0), (r"C:\Windows\Fonts\msgothic.ttc", 0))   # ＭＳ 明朝・ＭＳ ゴシック
# Mac など、ＭＳ 明朝のない PC では、同梱の IPA明朝・IPAゴシック（IPAフォントライセンス v1.0。再配布できる）を使う。
# IPAex ではなく IPA を使うのは、ＭＳ 明朝と同じく英数字も含めてすべての字が等幅（半角は全角の半分）で、ページ番号の
# 中央寄せと行番号の数字の送りが同じになるため。Mac のヒラギノは、reportlab が読めない形（CFF）なので使えない
# （2026-10-25 班長決定）。字は1字ずつ位置を決めて置くので、本文の字の位置は書体によらない
IPA_FONTS = ((str(_font_dir() / "ipam.ttf"), 0), (str(_font_dir() / "ipag.ttf"), 0))


def _default_fonts():
    return MS_FONTS if os.name == "nt" and os.path.exists(MS_FONTS[0][0]) else IPA_FONTS


DEFAULT_FONTS = _default_fonts()
HIGHLIGHT_COLOR = (1, 1, 0)     # 蛍光ペンの黄（Word の蛍光ペンの黄と同じ）。確認表示だけで塗る
# 仮名化した語の地の色（確認表示だけ。エディターの記号の地と同じ薄い緑。theme.REGISTERED_BG と同じ値。2026-10-24 班長指示）
PSEUDONYM_COLOR = (0xd9 / 255, 0xf2 / 255, 0xd9 / 255)
# 行番号（VA公用文 basSetup.ConfigPage・cstSettings.sngLineNo）。位置と大きさは、班長が VA公用文で作った PDF
# （裁判所提出書類・行番号を表示）で測った値（2026-10-24）：字の大きさ（Word の PDF では 8.04pt）、増分、
# 数字の送り（半角の数字の幅より広い）、本文の左端から最後の数字の左端まで（ポイント）。基準線は本文の行と同じ
LINE_NUMBER_SIZE = 8.04
LINE_NUMBER_STEP = 5
LINE_NUMBER_PITCH = 4.2
LINE_NUMBER_LAST_X = 22.14
ID_PREFIX = "VAMD"


class FontNotEmbeddable(Exception):
    """書体ファイルが、文書への埋め込みを許していない。"""


def check_embeddable(path, index=0):
    """書体ファイルの埋め込みの許可（fsType）を確かめる。許されていなければ FontNotEmbeddable を出す。"""
    font = TTCollection(path).fonts[index] if path.lower().endswith(".ttc") else FTFont(path)
    fs_type = font["OS/2"].fsType
    if fs_type & 0x0002:
        raise FontNotEmbeddable(f"{os.path.basename(path)} は、文書への埋め込みが許されていない書体です（fsType={fs_type}）。")
    return fs_type


def register_font(path, index=0):
    """書体を登録し、登録した名前を返す。名前は書体ファイルごとに替える（reportlab は、登録した名前に別の書体を
    登録し直せない。試験では書体の組を替えて書き出す）。PDF に入る書体の名前は、書体そのものの名前（MS-Mincho など）。"""
    name = f"VAMD-{Path(path).stem}-{index}"
    if name not in pdfmetrics.getRegisteredFontNames():
        check_embeddable(path, index)
        pdfmetrics.registerFont(TTFont(name, path, subfontIndex=index))
    return name


def _has_bold(ts, lines):
    return any(g.bold for ln in lines for g in ln.glyphs) or any(
        g.bold for piece in getattr(ts, "tables", []) for g in piece.glyphs)


def _draw_glyph(c, x, y, g):
    """字を描く。太字の字はゴシック（ＭＳ ゴシック、Mac などでは IPAゴシック）で描き、書体を戻す。横の倍率のある字
    （複合見出しの外側の括弧の番号）は、倍率を掛けて描く。"""
    if g.bold:
        c.setFont(c.vamd_fonts[1], FONT_SIZE)
        c.drawString(x, y, g.ch)
        c.setFont(c.vamd_fonts[0], FONT_SIZE)
    elif getattr(g, "scale", 1.0) != 1.0:     # 表の字（TableGlyph）には倍率がない
        t = c.beginText(x, y)
        t.setHorizScale(g.scale * 100)
        t.textOut(g.ch)
        t.setHorizScale(100)            # 倍率は BT〜ET の外にも残るので、後の字のために戻す
        c.drawText(t)
    else:
        c.drawString(x, y, g.ch)


def page_number_text(style, page, pages):
    """ページ番号の文字列（VA公用文 basSetup.ConfigHeaderFooter と同じ形）。"""
    if style == PAGE_NUMBER_TOP_RIGHT:
        # 右上：全角数字。最後のページには「」」を付ける（VA公用文の blnPageNumberEnd）
        s = "".join(FW_DIGITS[int(d)] for d in str(page))
        return s + ("」" if page == pages else "")
    if style == PAGE_NUMBER_BOTTOM_CENTER_DECORATED:
        return f"- {page} -"
    if style == PAGE_NUMBER_BOTTOM_RIGHT:
        return f"{page}/{pages}"
    return str(page)


def write_pdf(ts, lines, path, doc_id=None, version=None, page_number=PAGE_NUMBER_BOTTOM_CENTER,
              fonts=None, line_numbers=False):
    """Typesetter（ts）で組んだ行（lines）を PDF に書き出す。doc_id があれば識別子に文書ID と版を入れる。

    書き出し先と同じフォルダの一時ファイルに書いてから置き換える（途中で止まっても前の版が壊れない）。
    """
    data = pdf_bytes(ts, lines, doc_id, version, page_number, fonts, line_numbers=line_numbers)
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def pdf_bytes(ts, lines, doc_id=None, version=None, page_number=PAGE_NUMBER_BOTTOM_CENTER, fonts=None,
              highlight=False, line_numbers=False):
    """組んだ結果の PDF を、メモリの中で作って返す（画面の確認表示も、これを使う。文章を一時ファイルに書かない）。

    highlight が真なら、蛍光ペン（==文字==）の字の後ろを黄色に塗る（確認表示だけ。保存する PDF と印刷には塗らない。
    2026-10-24 班長指示）。line_numbers が真なら、行番号を付ける（_draw_line_numbers）。fonts は書体の組
    （None は DEFAULT_FONTS）。
    """
    mincho, gothic = fonts or DEFAULT_FONTS
    pages = max((ln.page for ln in lines), default=1)
    pages = max([pages] + [p.page for p in getattr(ts, "tables", [])])
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H), invariant=1)
    # 描くときに使う書体の名前（本文、太字）。描く関数は、ここから読む
    c.vamd_fonts = (register_font(*mincho), register_font(*gothic) if _has_bold(ts, lines) else None)
    text_center = ts.margin_left + ts.text_w / 2
    for pg in range(1, pages + 1):
        c.setFont(c.vamd_fonts[0], FONT_SIZE)
        # 本文の行と表を、上から（文書の順に）描く。PDF の字の並びが文書の順になり、
        # 構文ファイルとの突き合わせ（recover.py）で、表の前後の本文を取り違えない。ヘッダー・フッターの行も
        # 上から描き、ページ番号はページの最後に描く（突き合わせで、余白の字からページ番号を除くため）
        items = [(ts.line_baseline(ln), 0, ln) for ln in lines if ln.page == pg]
        items += [(piece.rows[0].top if piece.rows else 0, 1, piece)
                  for piece in getattr(ts, "tables", []) if piece.page == pg]
        for _, is_table, item in sorted(items, key=lambda t: (t[0], t[1])):
            if is_table:
                draw_table(c, ts, item, highlight)
                c.setFont(c.vamd_fonts[0], FONT_SIZE)
                continue
            y = PAGE_H - ts.line_baseline(item)
            if highlight:
                _draw_highlight(c, [(ts.margin_left + g.x, y, ts.advance(g.ch), g.pseudonym) for g in item.glyphs],
                                PSEUDONYM_COLOR)
                _draw_highlight(c, [(ts.margin_left + g.x, y, ts.advance(g.ch), g.highlight) for g in item.glyphs])
            for g in item.glyphs:
                _draw_glyph(c, ts.margin_left + g.x, y, g)
            _draw_dots(c, [(ts.margin_left + g.x, y, ts.advance(g.ch), g) for g in item.glyphs])
        if line_numbers:
            _draw_line_numbers(c, ts, lines, pg)
        if page_number != PAGE_NUMBER_NONE:
            s = page_number_text(page_number, pg, pages)
            # 基準線は下中央・下右が「フッターの位置＋FOOTER_BASELINE_OFFSET」、右上が「ヘッダーの位置＋字の上端から
            # 基準線まで」（右上の位置は VA公用文の PDF と比べていない。仕様.md の6.4。要確認）。ヘッダー・フッターが
            # 余白に入りきらないときは、ずらした位置（layout.Typesetter.area_baselines）
            y = PAGE_H - ts.page_number_baseline(pg, page_number)
            if page_number in (PAGE_NUMBER_BOTTOM_CENTER, PAGE_NUMBER_BOTTOM_CENTER_DECORATED):
                c.drawCentredString(text_center, y, s)
            elif page_number in (PAGE_NUMBER_BOTTOM_RIGHT, PAGE_NUMBER_TOP_RIGHT):
                c.drawRightString(ts.margin_left + ts.text_w, y, s)
        c.showPage()
    c.save()
    with fitz.open(stream=buf.getvalue(), filetype="pdf") as doc:
        _clean_and_mark(doc, doc_id, version)
        return doc.tobytes(garbage=3, deflate=True)


def _draw_highlight(c, items, color=HIGHLIGHT_COLOR):
    """蛍光ペンの字の後ろを黄色に塗る。items は [(x, 基準線の y, 字の幅, 蛍光ペンか)]（描く順）。同じ行で続いた字は、
    字の間も含めて1つにつなげて塗る（表の隣のセルのように、半字より離れた字はつなげない）。"""
    c.saveState()
    c.setFillColorRGB(*color)
    run = None
    for x, y, w, on in items + [(0, None, 0, False)]:
        if on and run and run[1] == y and x - run[2] <= FONT_SIZE / 2:
            run[2] = x + w
            continue
        if run:
            c.rect(run[0], run[1] - FONT_SIZE * 36 / 256, run[2] - run[0], FONT_SIZE, stroke=0, fill=1)
        run = [x, y, x + w] if on else None
    c.restoreState()


def _draw_line_numbers(c, ts, lines, page):
    """行番号（VA公用文 basSetup.ConfigPage と同じ：ページごとに 1 から数え、LINE_NUMBER_STEP 行ごとに番号を出す）。
    数えるのは本文の行と空の段落の行（Word の空の段落も1行に数える）で、表の中の行は数えない。番号は右をそろえ
    （最後の数字を本文の左端から LINE_NUMBER_LAST_X の所に置き、前の数字を LINE_NUMBER_PITCH ずつ左に置く）、
    行の字と基準線をそろえる。"""
    rows = sorted({ln.row for ln in lines if ln.page == page and not ln.area}      # ヘッダー・フッターは数えない
                  | {r % ts.lines_page for r in ts.blank_rows if r // ts.lines_page + 1 == page})
    c.setFont(c.vamd_fonts[0], LINE_NUMBER_SIZE)
    for k, row in enumerate(rows, start=1):
        if k % LINE_NUMBER_STEP == 0:
            # 1つの字の並びとして描く（PDF の字を読むと「10」になるように）。字の間隔で送りを広げる
            s = str(k)
            c.drawString(ts.margin_left - LINE_NUMBER_LAST_X - (len(s) - 1) * LINE_NUMBER_PITCH, PAGE_H - ts.baseline(row), s,
                         charSpace=LINE_NUMBER_PITCH - LINE_NUMBER_SIZE / 2)
    c.setFont(c.vamd_fonts[0], FONT_SIZE)


def _draw_dots(c, items):
    """傍点：字の上の中央に黒丸を描く。字ではなく図形で描く（PDF の字の並びに入れない。構文ファイルとの突き合わせ
    〔recover.py〕と、PDF の字の検索を乱さないため）。items は [(x, 基準線の y, 字の幅, 字)]。空白には付けない。"""
    dots = [(x + w / 2, y + DOT_RISE) for x, y, w, g in items if g.dot and not g.ch.isspace()]
    if not dots:
        return
    c.saveState()
    c.setFillColorRGB(0, 0, 0)
    for x, y in dots:
        c.circle(x, y, DOT_RADIUS, stroke=0, fill=1)
    c.restoreState()


def draw_table(c, ts, piece, highlight=False):
    """表の1ページ分（TablePiece）の字と罫線を描く。"""
    if highlight:
        _draw_highlight(c, [(ts.margin_left + g.x, PAGE_H - g.y, ts.advance(g.ch), g.pseudonym) for g in piece.glyphs],
                        PSEUDONYM_COLOR)
        _draw_highlight(c, [(ts.margin_left + g.x, PAGE_H - g.y, ts.advance(g.ch), g.highlight) for g in piece.glyphs])
    for g in piece.glyphs:
        _draw_glyph(c, ts.margin_left + g.x, PAGE_H - g.y, g)
    _draw_dots(c, [(ts.margin_left + g.x, PAGE_H - g.y, ts.advance(g.ch), g) for g in piece.glyphs])
    if not piece.rows:
        return
    c.setLineWidth(RULE_WIDTH)
    x0, x1 = ts.margin_left + piece.col_x[0], ts.margin_left + piece.col_x[-1]
    top, bottom = piece.rows[0].top, piece.rows[-1].bottom
    # 横の罫線：各行の上の端と、最後の行の下の端。見出しの行の下が2重線なら、もう1本足す
    for r in piece.rows:
        c.line(x0, PAGE_H - r.top, x1, PAGE_H - r.top)
        if r.double_below:
            c.line(x0, PAGE_H - (r.bottom - DOUBLE_RULE_GAP), x1, PAGE_H - (r.bottom - DOUBLE_RULE_GAP))
    c.line(x0, PAGE_H - bottom, x1, PAGE_H - bottom)
    # 縦の罫線：列の境目
    for x in piece.col_x:
        c.line(ts.margin_left + x, PAGE_H - top, ts.margin_left + x, PAGE_H - bottom)


def _clean_and_mark(doc, doc_id, version):
    """文書情報と XMP を取り除き、識別子に文書ID と版を入れる。"""
    doc.set_metadata({})
    doc.del_xml_metadata()
    if doc_id is not None:
        first = f"{ID_PREFIX}:{doc_id}:{int(version):06d}".encode("ascii").hex()
        doc.xref_set_key(-1, "ID", f"[<{first}><{first}>]")


def read_id(path):
    """PDF の識別子から (文書ID, 版) を読み出す。VA Documentの識別子でなければ None を返す。"""
    with fitz.open(path) as doc:
        kind, val = doc.xref_get_key(-1, "ID")
    if kind != "array":
        return None
    # 1つ目の要素は、文字列（(…)）か16進（<…>）のどちらかの形で返る
    m = re.match(r"\[\s*(?:\((?P<lit>[^)]*)\)|<(?P<hex>[0-9A-Fa-f]*)>)", val)
    if not m:
        return None
    try:
        text = m.group("lit") if m.group("lit") is not None else bytes.fromhex(m.group("hex")).decode("ascii")
        prefix, doc_id, version = text.split(":")
        return (doc_id, int(version)) if prefix == ID_PREFIX else None
    except (ValueError, UnicodeDecodeError):
        return None
