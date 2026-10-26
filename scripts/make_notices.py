"""VA Document が使っている部品のライセンスの表示（THIRD_PARTY_NOTICES.txt）を作る。

exe に入る部品（Python・Tcl/Tk・PyMuPDF・ReportLab・fontTools・Pillow・PyInstaller のブートローダー）と、
ボタンのアイコン（Fluent UI System Icons）のライセンスの全文を、いま入っている部品のファイルから集める。
部品の版を上げたら、作り直してコミットする。

実行のしかた：
    python scripts\\make_notices.py
"""

from __future__ import annotations

import importlib.metadata as metadata
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "THIRD_PARTY_NOTICES.txt"
PY_HOME = Path(sys.base_prefix)

# (表示する名前, 配布の名前〔版を読む。None は Python〕, 用途, ライセンス, 全文のファイル)
COMPONENTS = [
    ("Python", None, "プログラムの言語（exe に入る）", "PSF License Version 2", [PY_HOME / "LICENSE.txt"]),
    ("Tcl/Tk", None, "画面", "Tcl/Tk License（BSD 形式）", [PY_HOME / "tcl" / "tk8.6" / "license.terms"]),
    ("PyMuPDF", "pymupdf", "PDF の表示・印刷・読み書き", "GNU Affero General Public License 第3版（AGPL-3.0）",
     []),
    ("ReportLab", "reportlab", "PDF の作成", "BSD License", ["licenses/LICENSE"]),
    ("fontTools", "fonttools", "書体の埋め込みの許可の確かめ", "MIT License",
     ["licenses/LICENSE", "licenses/LICENSE.external"]),
    ("Pillow", "pillow", "アイコンの画像", "MIT-CMU License", ["licenses/LICENSE"]),
    ("PyInstaller", "pyinstaller", "実行ファイルの作成（ブートローダーが exe に入る）",
     "GNU General Public License 第2版以降（ブートローダーの例外条項付き）", ["licenses/COPYING.txt"]),
    ("Fluent UI System Icons", None, "ボタンのアイコン（［傍点］のアイコンを除く）", "MIT License",
     [ROOT / "src" / "va_document" / "icons" / "LICENSE"]),
    ("IPAフォント（IPA明朝・IPAゴシック）Ver.003.03", None,
     "Mac など、ＭＳ 明朝のない PC で PDF に埋め込む書体（ソースの assets/fonts に同梱。exe には入らない）",
     "IPAフォントライセンス v1.0", [ROOT / "assets" / "fonts" / "IPA_Font_License_Agreement_v1.0.txt"]),
]


def _license_files(dist: str | None, files: list) -> list[tuple[str, str]]:
    out = []
    for f in files:
        if isinstance(f, Path):
            path = f
        else:
            path = Path(metadata.distribution(dist).locate_file(f"{dist}-{metadata.version(dist)}.dist-info/{f}"))
            if not path.exists():
                matches = [p for p in metadata.distribution(dist).files or [] if str(p).replace("\\", "/").endswith(f)]
                path = Path(metadata.distribution(dist).locate_file(matches[0])) if matches else path
        out.append((path.name, path.read_text(encoding="utf-8-sig", errors="replace")))
    return out


def build() -> Path:
    parts = [
        "VA Document が使っている部品のライセンスの表示",
        "",
        "VA Document そのものは、GNU Affero General Public License 第3版（AGPL-3.0）で公開しています（LICENSE）。",
        "VA Document の実行ファイル（VA_Document.exe）には、次の部品が入っています（IPAフォントは、ソースにだけ入っています）。",
        "ＭＳ 明朝・ＭＳ ゴシックは入っていません（Windows に入っているものを、埋め込みの許可の範囲で PDF に埋め込みます）。",
        "",
    ]
    for name, dist, use, lic, files in COMPONENTS:
        version = sys.version.split()[0] if name == "Python" else (metadata.version(dist) if dist else "")
        parts += ["=" * 78, f"{name} {version}".rstrip(), f"用途：{use}", f"ライセンス：{lic}"]
        if name == "PyMuPDF":
            parts.append("ライセンスの全文は、VA Document の LICENSE（AGPL-3.0）と同じです。"
                         "PyMuPDF の表示：" + (Path(metadata.distribution(dist).locate_file(
                             f"{dist}-{version}.dist-info/COPYING")).read_text(encoding="utf-8").strip()))
        parts.append("=" * 78)
        for fname, text in _license_files(dist, files):
            parts += [f"--- {fname} ---", text.rstrip(), ""]
        parts.append("")
    OUTPUT.write_text("\n".join(parts) + "\n", encoding="utf-8", newline="\n")
    return OUTPUT


if __name__ == "__main__":
    print(f"作りました：{build()}")
