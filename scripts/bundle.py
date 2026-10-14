#!/usr/bin/env python3
"""
Gera a versão distribuível da interface em um único arquivo:
  dist/index.html     página completa (abre direto no navegador ou em qualquer hospedagem estática)
  dist/artifact.html  mesmo conteúdo sem o esqueleto <html>/<head>, para publicação como Artifact
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
DIST = os.path.join(ROOT, "dist")


def read(rel):
    with open(os.path.join(WEB, rel), encoding="utf-8") as f:
        return f.read()


def main():
    html = read("index.html")
    html = html.replace('<link rel="stylesheet" href="css/app.css">', "<style>\n" + read("css/app.css") + "\n</style>")
    html = html.replace("<!--INLINE_CSS-->", "")

    def inline(m):
        src = m.group(1)
        return "<script>\n" + read(src).replace("</script", "<\\/script") + "\n</script>"

    html = re.sub(r'<script src="([^"]+)"></script>', inline, html)
    html = html.replace("<!--INLINE_JS-->", "")
    os.makedirs(DIST, exist_ok=True)
    with open(os.path.join(DIST, "artifact.html"), "w", encoding="utf-8") as f:
        f.write(html)
    head, _, body = html.partition('<div class="app" id="app">')
    full = ("<!doctype html>\n<html lang=\"pt-BR\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
            + head + "</head>\n<body>\n<div class=\"app\" id=\"app\">" + body + "\n</body>\n</html>\n")
    with open(os.path.join(DIST, "index.html"), "w", encoding="utf-8") as f:
        f.write(full)
    print("dist/index.html", os.path.getsize(os.path.join(DIST, "index.html")) // 1024, "KB")


if __name__ == "__main__":
    main()
