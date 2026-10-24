# VA DocuMake — Word を使わずに、VA公用文と同じ書式の文書を作るツール

VA DocuMake は、裁判所提出書類・公用文・契約書などを、Word を使わずに、VA公用文（Word のアドイン）で整えたものと同じ書式の PDF にする、Windows 用の無料ツールです（Python 製）。文章の起案・推敲に AI（Claude など）を使うときは、依頼者などの名前を記号（〔人名Ａ〕など）に置き換えてから渡し、AI の回答を取り込むと元の名前に戻します。

- 配布：[VBAアセット](https://vba-assets.net/)（実行ファイルとインストーラーは、サイトの記事からダウンロードしてください）
- ライセンス：GNU Affero General Public License 第3版（[LICENSE](LICENSE)）。使っている部品のライセンスは [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt)
- 操作マニュアル：[docs/manual/VA_DocuMake_操作マニュアル.md](docs/manual/VA_DocuMake_操作マニュアル.md)
- 仕様：[仕様.md](仕様.md)

## フォルダの構成

| フォルダ・ファイル | 内容 |
|---|---|
| `src/va_documake/` | 本体のソース |
| `tests/` | テスト（pytest）。`tests/data/` は、VA公用文で整えた見本の文書と、その字の位置（正解） |
| `scripts/` | マニュアルの PDF・アイコン・ライセンスの表示・配布物を作るスクリプト |
| `assets/` | アプリのアイコン |
| `main.py` | ソースから起動するときの入口 |
| `va_documake.spec` | 実行ファイルを作る PyInstaller の設定 |

開発用の内部資料（検討のメモ、VA公用文の正解を作るために Word を操作する試作の道具）は、このリポジトリには含めていません。ソースのコメントでそれらを参照している箇所があります。

## ソースから動かす

Windows 10・11 と Python 3 で動かします（ＭＳ 明朝・ＭＳ ゴシックを使うため、Windows でだけ PDF を作れます）。

```
python -m pip install -r requirements.txt
python main.py
```

テストは `python -m pytest` で走ります。実行ファイルは `python -m PyInstaller va_documake.spec --noconfirm` で `dist\VA_DocuMake.exe` にできます。

## ライセンス

Copyright (C) 2026 VBAアセット

このプログラムはフリーソフトウェアです。Free Software Foundation が公表した GNU Affero General Public License 第3版の条件の下で、再配布・改変できます。このプログラムは有用であることを願って配布されますが、何の保証もありません（商品性や特定の目的への適合性の保証もありません）。詳しくは [LICENSE](LICENSE) をご覧ください。

PDF の表示・印刷・読み書きに、AGPL-3.0 で公開されている PyMuPDF を使っているため、このライセンスにしています。
