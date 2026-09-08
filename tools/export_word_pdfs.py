from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WINCOM = ROOT / "tmp" / "wincom"
sys.path.insert(0, str(WINCOM))
sys.path.insert(0, str(WINCOM / "win32"))
sys.path.insert(0, str(WINCOM / "win32" / "lib"))
sys.path.insert(0, str(WINCOM / "win32com"))
os.add_dll_directory(str(WINCOM / "pywin32_system32"))

import pythoncom
import win32com.client


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manual-only", action="store_true")
    args = parser.parse_args()
    out = ROOT / "output" / "softcopyright"
    pairs = [
        (out / "炼数DataForge_V1.0_源代码示例文件.docx", out / "炼数DataForge_V1.0_源代码示例文件.pdf"),
        (out / "炼数DataForge_V1.0_用户手册_含目录.docx", out / "炼数DataForge_V1.0_用户手册_含目录.pdf"),
    ]
    if args.manual_only:
        pairs = pairs[-1:]
    pythoncom.CoInitialize()
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        for source, target in pairs:
            document = word.Documents.Open(str(source.resolve()), ReadOnly=True, AddToRecentFiles=False)
            try:
                pages = document.ComputeStatistics(2)
                document.ExportAsFixedFormat(
                    OutputFileName=str(target.resolve()),
                    ExportFormat=17,
                    OpenAfterExport=False,
                    OptimizeFor=0,
                    Range=0,
                    Item=0,
                    IncludeDocProps=True,
                    KeepIRM=True,
                    CreateBookmarks=1,
                    DocStructureTags=True,
                    BitmapMissingFonts=True,
                    UseISO19005_1=False,
                )
                print(f"{source.name}: {pages} pages -> {target.name}")
            finally:
                document.Close(False)
    finally:
        word.Quit()
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
