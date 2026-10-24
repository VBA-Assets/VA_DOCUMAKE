# -*- mode: python ; coding: utf-8 -*-
# VA DocuMake の実行ファイル（dist\VA_DocuMake.exe）を作る（VA mints の mints_prep.spec と同じ作り）。
# 作り方：pyinstaller va_documake.spec --noconfirm


a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=[],
    # ・ボタンのアイコン（Fluent UI System Icons の SVG と LICENSE）。icons.py は va_documake\icons から読む
    # ・ウィンドウ（タイトルバー・タスクバー）のアイコン。exe そのもののアイコンは EXE(icon=...) で埋め込むが、
    #   Tk のウィンドウには、実行時にファイルとして読ませる必要があるため、展開先（sys._MEIPASS）に入れる
    datas=[('src/va_documake/icons', 'va_documake/icons'), ('assets/VA_DocuMake.ico', 'assets')],
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
    name='VA_DocuMake',
    icon='assets/VA_DocuMake.ico',
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
