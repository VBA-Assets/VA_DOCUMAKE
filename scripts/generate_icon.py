"""実行ファイル・ウィンドウ用のアイコン（assets/VA_DocuMake.ico）を作るスクリプト。

VA mints・VA FAX と同じ作り（角丸の四角に白い太字。角の丸み・左右の余白は同じ）にしたうえで、
1行目に「VA」を小さく、2行目に「Docu」を大きく書き、背景は紫（#5C2D91。Microsoft の紫）にする
（紫は 2026-10-23 班長決定。VA mints の青と見分けるため。字は 2026-10-24、名前を VA DocuMake に改めたときの班長決定。
それまでは「VA 公用文」「AI」）。字は Segoe UI Bold。2行目は、左右の余白に収まるいちばん大きい字にする。

アイコンのファイルはリポジトリに入れ、作り方もコードとして残す（VA mints の scripts/generate_icon.py と同じ方針）。

実行のしかた：
    python scripts\\generate_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ICON_PATH = ROOT / "assets" / "VA_DocuMake.ico"

BACKGROUND = "#5C2D91"
TEXT_COLOR = "#ffffff"
CANVAS = 256            # 元の画像の一辺（ここから各大きさへ縮める）
CORNER_RADIUS = 28      # VA mints・VA FAX と同じ
SIDE_PADDING = 30       # 同じ
TOP_TEXT, TOP_SIZE = "VA", 56          # 1行目（小さく）
MAIN_TEXT, MAIN_MAX = "Docu", 128      # 2行目（大きく。この大きさから、余白に収まるまで小さくする）
LINE_GAP = 14
SEGOE = r"C:\Windows\Fonts\segoeuib.ttf"
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def font(path, size):
    if not Path(path).is_file():
        raise FileNotFoundError(f"書体が見つかりません：{path}")
    return ImageFont.truetype(path, size)


def build_image():
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, CANVAS - 1, CANVAS - 1), radius=CORNER_RADIUS, fill=BACKGROUND)
    width = CANVAS - SIDE_PADDING * 2
    top = font(SEGOE, TOP_SIZE)
    size = MAIN_MAX
    while size > 10:
        main = font(SEGOE, size)
        box = main.getbbox(MAIN_TEXT, anchor="ls")
        if box[2] - box[0] <= width:
            break
        size -= 2
    # 高さは、ベースラインからの上端・下端で測る
    top_box = top.getbbox(TOP_TEXT, anchor="ls")
    ascent1, descent1 = -top_box[1], top_box[3]
    ascent2 = -box[1]
    y = (CANVAS - (ascent1 + descent1 + LINE_GAP + ascent2)) / 2
    base1 = y + ascent1
    base2 = base1 + descent1 + LINE_GAP + ascent2
    draw.text(((CANVAS - (top_box[2] - top_box[0])) / 2 - top_box[0], base1), TOP_TEXT, font=top,
              fill=TEXT_COLOR, anchor="ls")
    draw.text(((CANVAS - (box[2] - box[0])) / 2 - box[0], base2), MAIN_TEXT, font=main, fill=TEXT_COLOR, anchor="ls")
    return image


def build():
    ICON_PATH.parent.mkdir(parents=True, exist_ok=True)
    build_image().save(ICON_PATH, format="ICO", sizes=ICO_SIZES)
    print(f"作りました：{ICON_PATH}")


if __name__ == "__main__":
    build()
