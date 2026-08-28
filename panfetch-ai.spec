# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

system32 = (Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32').resolve()
clean_path = []
for directory in os.environ.get('PATH', '').split(os.pathsep):
    candidate = Path(directory)
    if (candidate / 'icuuc.dll').is_file() and candidate.resolve() != system32:
        continue
    clean_path.append(directory)
os.environ['PATH'] = os.pathsep.join(clean_path)

truststore_datas, truststore_binaries, truststore_hiddenimports = collect_all('truststore')
agent_hiddenimports = (
    collect_submodules('langchain_core')
    + collect_submodules('langgraph')
    + collect_submodules('langsmith')
)

a = Analysis(
    ['panfetch_ai_launcher.py'],
    pathex=[],
    binaries=truststore_binaries,
    datas=truststore_datas,
    hiddenimports=truststore_hiddenimports + agent_hiddenimports + ['win32crypt'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'test', 'unittest', 'PyQt6'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PanFetch AI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
