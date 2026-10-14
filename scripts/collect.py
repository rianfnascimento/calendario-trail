#!/usr/bin/env python3
"""
Coleta automatizada do calendário de Trail Run da Adventure Mag.

Gera os mesmos arquivos brutos usados por build_db.py:
  data/raw/listing_<AAAA-MM-DD>.tsv
  data/raw/details_<AAAA-MM-DD>.txt

Uso:
  python3 scripts/collect.py              # incremental: listagem completa + só páginas novas/alteradas
  python3 scripts/collect.py --full       # baixa de novo todas as páginas de evento
  python3 scripts/collect.py --max-pages 3

Modo incremental (padrão): a listagem (≈9 páginas) é sempre lida inteira, porque é ela que traz
data, cidade e marcações como "Cancelado" ou "Nova data". A página individual só é baixada para
provas que ainda não estão na base ou cuja data/marcação mudou. Numa varredura mensal típica isso
significa ~10 páginas de listagem + algumas dezenas de páginas de evento.

Comportamento seguro:
  * Escreve em arquivos temporários e só os renomeia no fim, se a coleta parecer completa.
  * Nunca apaga coletas anteriores; build_db.py usa a mais recente e valida antes de publicar.
  * Respeita o site: 1 requisição por vez, pausa entre páginas, User-Agent identificado.
  * Usa apenas páginas públicas; não faz login nem tenta contornar bloqueios.

Limitação conhecida: este coletor foi escrito com base na estrutura observada das páginas em
14/10/2026 (via leitura do conteúdo publicado), mas não pôde ser executado contra o site real
no ambiente em que o projeto foi criado, porque a rede desse ambiente bloqueava o domínio.
Na primeira execução, confira o resumo impresso e o relatório do build_db.py.
"""
import argparse
import html
import os
import re
import sys
import time
import urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
BASE = "https://www.adventuremag.com.br/calendario/trail-run/"
UA = "CalendarioTrailBrasil/1.0 (+coleta pública do calendário; contato no README)"
MONTHS = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7,
          "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}
STATUS_WORDS = ("Nova data", "Cancelado", "Cancelada", "Adiado", "Adiada", "Data a confirmar")


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise RuntimeError(f"falha ao baixar {url}: {e}")
            time.sleep(2 * (i + 1))


def tokens(page):
    """Sequência de ('text', s) e ('a', href, texto) na ordem do documento."""
    out = []
    pos = 0
    for m in re.finditer(r"<a\b[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", page, re.S | re.I):
        out += [("text", t) for t in split_text(page[pos:m.start()])]
        out.append(("a", html.unescape(m.group(1)), clean_text(m.group(2))))
        pos = m.end()
    out += [("text", t) for t in split_text(page[pos:])]
    return out


def clean_text(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return " ".join(html.unescape(s).split())


def split_text(chunk):
    chunk = re.sub(r"<script.*?</script>|<style.*?</style>", " ", chunk, flags=re.S | re.I)
    parts = re.split(r"<[^>]+>", chunk)
    return [" ".join(html.unescape(p).split()) for p in parts if p.strip()]


def parse_listing(page, page_no):
    rows, cur_date, pending_tag = [], None, ""
    toks = tokens(page)
    texts_window = []
    for t in toks:
        if t[0] == "text":
            texts_window = (texts_window + [t[1]])[-3:]
            if len(texts_window) == 3:
                mo, d, y = texts_window
                if mo[:3].lower() in MONTHS and d.isdigit() and re.fullmatch(r"20\d\d", y):
                    cur_date = date(int(y), MONTHS[mo[:3].lower()], int(d))
            if t[1] in STATUS_WORDS:
                pending_tag = t[1]
            continue
        href, text = t[1], t[2]
        m = re.search(r"/calendario/(\d+)/1/", href)
        if not m or "»" not in text or cur_date is None:
            continue
        name, _, place = text.rpartition("»")
        pm = re.match(r"\s*(.*?)\s*\((\w{0,2})\)\s*$", place)
        city, uf = (pm.group(1), pm.group(2)) if pm else (place.strip(), "")
        url = href if href.startswith("http") else "https://www.adventuremag.com.br" + href
        rows.append([str(page_no), cur_date.strftime("%d/%m/%Y"), pending_tag, name.strip(), city, uf, url])
        pending_tag = ""
    last = max([int(x) for x in re.findall(r"[?&]page=(\d+)", page)] or [page_no])
    return rows, last


def parse_detail(page):
    def find(rx, default="-", flags=re.S | re.I):
        m = re.search(rx, page, flags)
        return html.unescape(m.group(1)).strip() if m else default

    dates = find(r"dates=(\d{8})/(\d{8})", None)
    start = end = "-"
    m = re.search(r"dates=(\d{8})/(\d{8})", page)
    if m:
        s, e = m.group(1), m.group(2)
        start, end = f"{s[:4]}-{s[4:6]}-{s[6:]}", f"{e[:4]}-{e[4:6]}-{e[6:]}"
    loc = find(r"[?&]location=([^&\"]+)", "")
    loc = urllib.request.unquote(loc.replace("+", " ")).split(",") if loc else []
    city = loc[1].strip() if len(loc) >= 3 else "-"
    uf = loc[2].strip() if len(loc) >= 3 else "-"
    org = find(r"href=\"[^\"]*/calendario/organizador/[^\"]*\"[^>]*>(.*?)</a>")
    org = clean_text(org) or "-"
    link = "-"
    for a in re.finditer(r"<a\b[^>]*href=\"(https?://[^\"]+)\"[^>]*>(.*?)</a>", page, re.S | re.I):
        if "inscri" in clean_text(a.group(2)).lower() and "adventuremag" not in a.group(1):
            link = html.unescape(a.group(1))
            break
    lat = find(r"lat=(-?\d+\.\d+)")
    lng = find(r"lng=(-?\d+\.\d+)")
    text = clean_text(page)
    status = next((w for w in STATUS_WORDS if w in text[:4000]), "-")
    _ = dates
    return "|".join([status, start, end, city, uf, org, link, lat, lng, "-", "-"])


def previous_raw():
    """Última coleta já gravada: {id: (data, tag)} da listagem e {id: linha} dos detalhes."""
    import glob
    lst = sorted(glob.glob(os.path.join(RAW, "listing_*.tsv")))
    det = sorted(glob.glob(os.path.join(RAW, "details_*.txt")))
    plist, pdet = {}, {}
    if lst:
        with open(lst[-1], encoding="utf-8") as f:
            next(f, None)
            for line in f:
                c = line.rstrip("\n").split("\t")
                if len(c) >= 7:
                    m = re.search(r"/calendario/(\d+)/", c[6])
                    if m:
                        plist[m.group(1)] = (c[1], c[2])
    if det:
        with open(det[-1], encoding="utf-8") as f:
            for line in f:
                if "\t" in line:
                    eid, payload = line.rstrip("\n").split("\t", 1)
                    pdet[eid] = payload
    return plist, pdet


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="baixa todas as páginas de evento de novo")
    ap.add_argument("--max-pages", type=int, default=50)
    ap.add_argument("--pause", type=float, default=1.5)
    a = ap.parse_args()
    stamp = date.today().isoformat()
    os.makedirs(RAW, exist_ok=True)

    rows, page_no, last = [], 1, 1
    while page_no <= min(last, a.max_pages):
        url = BASE if page_no == 1 else f"{BASE}?page={page_no}"
        got, last_seen = parse_listing(get(url), page_no)
        print(f"página {page_no}: {len(got)} eventos")
        if not got:
            break
        rows += got
        last = max(last, last_seen)
        page_no += 1
        time.sleep(a.pause)

    if len(rows) < 20:
        sys.exit(f"Coleta suspeita: apenas {len(rows)} eventos. Nada foi gravado.")

    listing_tmp = os.path.join(RAW, f"listing_{stamp}.tsv.tmp")
    with open(listing_tmp, "w", encoding="utf-8") as f:
        f.write("page\tdate\ttag\tname\tcity\tuf\turl\n")
        for r in rows:
            f.write("\t".join(x.replace("\t", " ") for x in r) + "\n")

    details_tmp = os.path.join(RAW, f"details_{stamp}.txt.tmp")
    fails = 0
    plist, pdet = ({}, {}) if a.full else previous_raw()
    reused = fetched = 0
    with open(details_tmp, "w", encoding="utf-8") as f:
        for i, r in enumerate(rows, 1):
            eid = re.search(r"/calendario/(\d+)/", r[6]).group(1)
            if eid in pdet and plist.get(eid) == (r[1], r[2]):
                f.write(eid + "\t" + pdet[eid] + "\n")
                reused += 1
                continue
            try:
                f.write(eid + "\t" + parse_detail(get(r[6])) + "\n")
                fetched += 1
            except Exception as e:  # noqa: BLE001
                fails += 1
                print(f"  aviso: detalhe {eid} falhou ({e})")
                if eid in pdet:  # mantém os dados da coleta anterior em vez de perder a prova
                    f.write(eid + "\t" + pdet[eid] + "\n")
            if fetched and fetched % 25 == 0:
                print(f"  {fetched} páginas de evento baixadas")
            time.sleep(a.pause)
    if fails > len(rows) * 0.1:
        sys.exit(f"{fails} páginas de evento falharam; arquivos temporários mantidos para inspeção.")
    os.replace(listing_tmp, listing_tmp[:-4])
    os.replace(details_tmp, details_tmp[:-4])
    print(f"OK: {len(rows)} eventos na listagem; {fetched} páginas de evento baixadas, {reused} reaproveitadas "
          f"da coleta anterior, {fails} falhas. Agora rode: python3 scripts/build_db.py")


if __name__ == "__main__":
    main()
