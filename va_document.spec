# -*- mode: python ; coding: utf-8 -*-
# VA Document の実行ファイル（dist\VA_Document.exe）を作る（VA mints の mints_prep.spec と同じ作り）。
# 作り方：pyinstaller va_document.spec --noconfirm


a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=[],
    # ・ボタンのアイコン（Fluent UI System Icons の SVG と LICENSE）。icons.py は va_document\icons から読む
    # ・ウィンドウ（タイトルバー・タスクバー）のアイコン。exe そのもののアイコンは EXE(icon=...) で埋め込むが、
    #   Tk のウィンドウには、実行時にファイルとして読ませる必要があるため、展開先（sys._MEIPASS）に入れる
    # ・同梱の IPA書体（assets/fonts。Mac などで使う）は入れない（Windows ではＭＳ 明朝を使う。pdfwriter.DEFAULT_FONTS）
    datas=[('src/va_document/icons', 'va_document/icons'), ('assets/VA_Document.ico', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 使わない大きな部品を入れない（試験の部品・ほかの GUI）
    excludes=['pytest', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'matplotlib', 'numpy'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='VA_Document',
    icon='assets/VA_Document.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
