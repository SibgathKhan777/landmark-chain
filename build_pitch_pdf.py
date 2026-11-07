"""Builds PITCH.pdf (one page) from PITCH.md with the screenshots in docs/images/. Needs the `markdown` package and Google Chrome.

    python build_pitch_pdf.py
"""
import re
import subprocess
import sys
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CSS = """
@page { size: A4; margin: 9mm 11mm; }
body { font: 9.4pt/1.32 -apple-system, "Helvetica Neue", Arial, sans-serif; color: #15191f; margin: 0; }
h1 { font-size: 16pt; margin: 0 0 3px; } h2 { font-size: 10.5pt; margin: 7px 0 2px; color: #0b5d3b; }
p { margin: 2px 0; } ul { margin: 2px 0; padding-left: 16px; } li { margin: 0; }
pre { background: #f1f3f5; padding: 4px 6px; margin: 3px 0; font-size: 7.6pt; white-space: pre-wrap; }
code { font-size: 8.4pt; background: #f1f3f5; padding: 0 2px; }
img { display: block; width: 100%; border: 1px solid #cfd5dc; border-radius: 4px; margin: 3px 0 1px; }
.pair { display: flex; gap: 6px; } .pair > div { flex: 1; } .pair img { width: 100%; }
em { color: #4a5563; font-size: 7.9pt; }
"""
md = (HERE / "PITCH.md").read_text(encoding="utf-8")
html = markdown.markdown(md, extensions=["fenced_code"])
# put the two screenshots side by side, each with its caption
# one page: the first screenshot full width with its caption; the second screenshot stays in PITCH.md only
pat = re.compile(r'<p><img alt="([^"]*)" src="(docs/images/call_reply.png)" />\s*<em>(.*?)</em></p>', re.S)
html = pat.sub("", html)
page = HERE / "PITCH.html"
page.write_text(f'<!doctype html><meta charset="utf-8"><title>Landmark Chain: solution pitch</title><style>{CSS}</style>{html}', encoding="utf-8")
out = HERE / "PITCH.pdf"
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={out}", page.as_uri()], check=True, capture_output=True)
page.unlink()
pages = len(re.findall(rb"/Type\s*/Page[^s]", out.read_bytes()))
print(f"wrote {out.name}: {pages} page(s)")
sys.exit(0 if pages == 1 else 1)
