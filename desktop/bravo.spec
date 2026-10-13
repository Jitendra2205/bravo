# PyInstaller recipe for the installable Bravo.exe (one folder: dist/Bravo/).
# Built on Windows by .github/workflows/windows-installer.yml; run locally with:  pyinstaller --noconfirm bravo.spec
import os
from PyInstaller.utils.hooks import collect_all

here = SPECPATH
datas = [(os.path.join(here, "ui"), "ui"),
         (os.path.join(here, "..", "skills", "daily-brief", "brief.py"), os.path.join("skills", "daily-brief"))]
binaries, hiddenimports = [], []
# Packages with DLLs, model assets or a bundled driver that static analysis alone misses.
for pkg in ("faster_whisper", "ctranslate2", "onnxruntime", "webview", "playwright"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis([os.path.join(here, "app.py")], pathex=[here], datas=datas, binaries=binaries,
             hiddenimports=hiddenimports, excludes=["tkinter", "matplotlib", "pytest"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Bravo", icon=os.path.join(here, "ui", "bravo.ico"),
          console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Bravo", upx=False)
