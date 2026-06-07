"""Convert report.md -> report.pdf using Python-Markdown + Chrome headless.

中文走 Windows 系统字体（Microsoft YaHei），表格用 tables 扩展。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import markdown

REPORT_DIR = Path(r"Q:\Cosmetic\docs\rag_eval\2026-05-28-agent-rag-vs-raw-10q")
MD_PATH = REPORT_DIR / "report.md"
HTML_PATH = REPORT_DIR / "report.html"
PDF_PATH = REPORT_DIR / "report.pdf"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
* { box-sizing: border-box; }
body {
  font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
  font-size: 11pt;
  line-height: 1.55;
  color: #222;
  max-width: 100%;
  margin: 0;
}
h1 { font-size: 20pt; margin: 0 0 12px; border-bottom: 2px solid #333; padding-bottom: 6px; }
h2 { font-size: 15pt; margin: 22px 0 10px; color: #1a3a6c; }
h3 { font-size: 12.5pt; margin: 16px 0 6px; color: #2a4d80; }
p { margin: 6px 0 10px; }
ul, ol { margin: 6px 0 10px 22px; padding: 0; }
li { margin: 2px 0; }
code {
  font-family: "Cascadia Mono", Consolas, Menlo, monospace;
  font-size: 10pt;
  background: #f3f4f6;
  padding: 1px 4px;
  border-radius: 3px;
}
pre { background: #f6f8fa; padding: 10px; border-radius: 5px; overflow-x: auto; }
pre code { background: transparent; padding: 0; }
table {
  border-collapse: collapse;
  width: 100%;
  margin: 10px 0;
  font-size: 10pt;
  page-break-inside: avoid;
}
th, td {
  border: 1px solid #cfd6dd;
  padding: 6px 8px;
  text-align: left;
  vertical-align: top;
}
th { background: #eef2f7; font-weight: 600; }
tr:nth-child(even) td { background: #fafbfc; }
blockquote {
  border-left: 3px solid #888;
  margin: 10px 0;
  padding: 4px 12px;
  color: #555;
  background: #f9f9f9;
}
hr { border: none; border-top: 1px solid #ddd; margin: 18px 0; }
"""

HTML_TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>{css}</style>
</head>
<body>
{body}
</body>
</html>
"""


def main() -> int:
    md_text = MD_PATH.read_text(encoding="utf-8")
    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
        output_format="html5",
    )
    title = MD_PATH.stem
    HTML_PATH.write_text(HTML_TPL.format(title=title, css=CSS, body=body), encoding="utf-8")
    print(f"[1/2] HTML written: {HTML_PATH}")

    file_url = HTML_PATH.as_uri()
    cmd = [
        CHROME,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={PDF_PATH}",
        file_url,
    ]
    print(f"[2/2] Chrome headless print -> {PDF_PATH}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if not PDF_PATH.exists() or PDF_PATH.stat().st_size < 1000:
        print("STDOUT:", result.stdout[-500:])
        print("STDERR:", result.stderr[-500:])
        return 1
    print(f"OK: {PDF_PATH} ({PDF_PATH.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
