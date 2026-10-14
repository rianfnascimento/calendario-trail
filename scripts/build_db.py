#!/usr/bin/env python3
"""
Constrói a base própria de eventos a partir dos arquivos brutos coletados.

Entradas (data/raw/):
  listing_<data>.tsv          listagem paginada do calendário Trail Run da Adventure Mag
  details_<data>.txt          um registro por página de evento (id<TAB>campos separados por |)
  complementos_oficiais.json  dados complementares de sites oficiais (opcional)

Saídas:
  data/events.json  base normalizada (fonte de verdade da aplicação)
  data/events.csv   mesma base em formato tabular
  data/build_report.json  contagens, alertas e verificações

Regra de segurança: se a validação falhar, nada é sobrescrito e a última
versão válida é preservada (o script sai com código 1).
"""
import csv
import glob
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT_JSON = os.path.join(ROOT, "data", "events.json")
OUT_CSV = os.path.join(ROOT, "data", "events.csv")
OUT_REPORT = os.path.join(ROOT, "data", "build_report.json")
OUT_NEWS = os.path.join(ROOT, "data", "novidades.json")
SUBMISSIONS_CSV = os.environ.get("SUBMISSOES_CSV") or os.path.join(RAW, "submissoes_aprovadas.csv")
NEW_BADGE_DAYS = 35  # selo "Nova" para provas incluídas nas últimas ~5 semanas

UF_INFO = {
    "AC": ("Acre", "Norte"), "AP": ("Amapá", "Norte"), "AM": ("Amazonas", "Norte"),
    "PA": ("Pará", "Norte"), "RO": ("Rondônia", "Norte"), "RR": ("Roraima", "Norte"),
    "TO": ("Tocantins", "Norte"),
    "AL": ("Alagoas", "Nordeste"), "BA": ("Bahia", "Nordeste"), "CE": ("Ceará", "Nordeste"),
    "MA": ("Maranhão", "Nordeste"), "PB": ("Paraíba", "Nordeste"), "PE": ("Pernambuco", "Nordeste"),
    "PI": ("Piauí", "Nordeste"), "RN": ("Rio Grande do Norte", "Nordeste"), "SE": ("Sergipe", "Nordeste"),
    "DF": ("Distrito Federal", "Centro-Oeste"), "GO": ("Goiás", "Centro-Oeste"),
    "MT": ("Mato Grosso", "Centro-Oeste"), "MS": ("Mato Grosso do Sul", "Centro-Oeste"),
    "ES": ("Espírito Santo", "Sudeste"), "MG": ("Minas Gerais", "Sudeste"),
    "RJ": ("Rio de Janeiro", "Sudeste"), "SP": ("São Paulo", "Sudeste"),
    "PR": ("Paraná", "Sul"), "RS": ("Rio Grande do Sul", "Sul"), "SC": ("Santa Catarina", "Sul"),
}
STATE_NAMES = {unicodedata.normalize("NFKD", v[0]).encode("ascii", "ignore").decode().lower() for v in UF_INFO.values()}

COUNTRY_CODES = {"AR": "Argentina", "CL": "Chile", "UY": "Uruguai", "MX": "México",
                 "PT": "Portugal", "NA": "Namíbia"}

# Domínios de plataformas de inscrição: o link é classificado como "inscrição".
TICKETING = [
    "ticketsports", "sympla", "giroingressos", "keepsporting", "apuracrono", "activesports",
    "races.com.br", "minhasinscricoes", "realtiming", "corridao", "centraldasinscricoes",
    "race83", "chipower", "soucorredor", "sporttimer", "cronoscariri", "atletis", "sprinta",
    "kmaisclube", "esportecorrida", "corridasjardelmoura", "maisinscricoes", "momentomajestoso",
    "ravelisports.com.br/evento", "correrenadar", "portaldascorridas", "clickaqui", "chipcarajas",
    "sportbro",
]
SOCIAL = ["instagram.com", "facebook.com", "linktr.ee", "beacons.ai", "lnk.bio"]

# Correções de grafia evidentes (registradas como alerta no evento).
CITY_FIXES = {"Campos de Goytacazes": "Campos dos Goytacazes"}


def strip_accents(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def norm_key(s):
    s = strip_accents(s or "").lower()
    s = re.sub(r"\b(19|20)\d{2}\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def parse_date(s):
    s = (s or "").strip()
    if s in ("", "-"):
        return None
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return date(int(m[3]), int(m[2]), int(m[1]))
    raise ValueError(f"data inválida: {s!r}")


def clean(v):
    v = (v or "").strip()
    return None if v in ("", "-", "STATUS", "a divulgar") else v


def clean_url(u):
    u = clean(u)
    if not u or u.rstrip("/") in ("http:", "https:", "http:/", "https:/"):
        return None
    u = re.sub(r"[?&](utm_[^&]+|_gl=[^&]+)", "", u)
    return u


def parse_distances(txt):
    """'80 km;50 km' / '7K' / '10 Milhas' -> lista de km (float), ordenada desc."""
    txt = clean(txt)
    if not txt:
        return [], []
    parts = [p.strip() for p in re.split(r"[;,|]", txt) if p.strip()]
    kms = []
    for p in parts:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(km|k|milhas|mi)\b", p, re.I)
        if not m:
            continue
        val = float(m[1].replace(",", "."))
        if m[2].lower() in ("milhas", "mi"):
            val = round(val * 1.609, 1)
        kms.append(val)
    return sorted(set(kms), reverse=True), parts


def latest(pattern):
    files = sorted(glob.glob(os.path.join(RAW, pattern)))
    if not files:
        raise SystemExit(f"arquivo bruto ausente: {pattern}")
    return files[-1]


def read_listing(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            m = re.search(r"/calendario/(\d+)/", r["url"])
            r["id"] = m[1]
            rows.append(r)
    return rows


def read_details(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            eid, payload = line.split("\t", 1)
            fields = payload.split("|")
            # Registros em que o extrator omitiu o campo STATUS (10 campos começando por data).
            if len(fields) == 10 and re.match(r"\d", fields[0]):
                fields = ["-"] + fields
            if len(fields) != 11:
                raise ValueError(f"detalhe malformado para {eid}: {payload}")
            keys = ["status", "inicio", "fim", "cidade", "uf", "organizador", "link",
                    "lat", "lng", "distancias", "altimetria"]
            out[eid] = dict(zip(keys, [x.strip() for x in fields]))
    return out


def in_brazil(lat, lng):
    return -33.8 <= lat <= 5.4 and -74.1 <= lng <= -28.6


def classify_link(url):
    if not url:
        return None
    low = url.lower()
    if any(t in low for t in TICKETING):
        return "inscricao"
    if any(t in low for t in SOCIAL):
        return "rede_social"
    return "site_oficial"


def build():
    listing_path = latest("listing_*.tsv")
    details_path = latest("details_*.txt")
    verified = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(listing_path))[1]
    listing = read_listing(listing_path)
    details = read_details(details_path)
    comp_path = os.path.join(RAW, "complementos_oficiais.json")
    complements = {}
    if os.path.exists(comp_path):
        for c in json.load(open(comp_path, encoding="utf-8"))["complementos"]:
            complements[c["adventuremag_id"]] = c

    records = []
    for r in listing:
        eid = r["id"]
        d = details.get(eid, {})
        alerts = [] if d else ["Página do evento não coletada nesta atualização; dados apenas da listagem"]
        name = r["name"].strip()
        list_date = parse_date(r["date"])
        start = parse_date(d.get("inicio")) or list_date
        end = parse_date(d.get("fim")) or start
        if d and parse_date(d.get("inicio")) and parse_date(d.get("inicio")) != list_date:
            alerts.append(f"Data divergente: listagem {list_date.isoformat()} × página {start.isoformat()}")
        if end < start:
            end = start

        # ---- localização -------------------------------------------------
        list_city = clean(r["city"])
        det_city = clean(d.get("cidade"))
        local = None
        city = None
        if det_city and "," in det_city:
            local, city = [x.strip() for x in det_city.split(",", 1)]
        else:
            city = det_city or list_city
        if list_city and city and norm_key(list_city) != norm_key(city) and not local:
            local = list_city
        # Só a listagem às vezes traz o nome do estado no lugar da cidade (ex.: "Alagoas").
        # Municípios homônimos (Rio de Janeiro, São Paulo, Amapá) são preservados quando
        # confirmados pela página do evento.
        if not det_city and city and strip_accents(city).lower() in STATE_NAMES and city not in ("Amapá", "Rio de Janeiro", "São Paulo"):
            alerts.append(f"Cidade não informada (fonte cita apenas '{city}')")
            city = None
        if city in CITY_FIXES:
            alerts.append(f"Grafia normalizada: '{city}' → '{CITY_FIXES[city]}'")
            city = CITY_FIXES[city]

        list_uf = clean(r["uf"])
        det_uf = clean(d.get("uf"))
        lat = lng = None
        try:
            lat, lng = float(d.get("lat")), float(d.get("lng"))
        except (TypeError, ValueError):
            pass

        country = "Brasil"
        uf = None
        if lat is not None and not in_brazil(lat, lng):
            country = COUNTRY_CODES.get(list_uf) or ("Marrocos" if list_uf == "MA" else "Exterior")
            if list_uf == "MA":
                alerts.append("A sigla 'MA' na fonte refere-se a Marrocos (confirmado pelas coordenadas), não ao Maranhão")
        elif list_uf in COUNTRY_CODES:
            country = COUNTRY_CODES[list_uf]
        else:
            uf = list_uf if list_uf in UF_INFO else (det_uf if det_uf in UF_INFO else None)
            if list_uf in UF_INFO and det_uf in UF_INFO and list_uf != det_uf:
                alerts.append(f"UF divergente: listagem {list_uf} × página {det_uf}")
        international = country != "Brasil"
        if not international and not uf:
            alerts.append("Estado não informado pela fonte")
        if not city:
            alerts.append("Local a divulgar")

        # ---- status -------------------------------------------------------
        tag = (r["tag"] or "").strip().lower()
        det_status = (clean(d.get("status")) or "").lower()
        if "cancel" in tag or "cancel" in det_status:
            status = "cancelado"
        elif "adiad" in tag or "adiad" in det_status:
            status = "adiado"
        elif "nova data" in tag or "nova data" in det_status:
            status = "data_alterada"
        else:
            status = "agendado"

        # ---- links --------------------------------------------------------
        link = clean_url(d.get("link"))
        link_type = classify_link(link)
        if link:
            years = [int(y) for y in re.findall(r"(?<![A-Za-z0-9])(20[12]\d)(?![A-Za-z0-9])", link)]
            if years and max(years) < start.year:
                alerts.append(f"Link aponta para edição anterior ({max(years)})")
        name_years = [int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", name)]
        if name_years and all(y not in (start.year, end.year) for y in name_years):
            alerts.append(f"Ano no nome ({name_years[0]}) difere da data publicada ({start.year})")

        kms, dist_txt = parse_distances(d.get("distancias"))
        dist_source = "Adventure Mag" if kms else None
        elev = clean(d.get("altimetria"))
        elev_m = None
        if elev:
            m = re.search(r"(\d[\d.]*)\s*m", elev)
            elev_m = int(m[1].replace(".", "")) if m else None

        rec = {
            "id": f"am-{eid}",
            "adventuremag_ids": [eid],
            "nome": name,
            "data_inicio": start.isoformat(),
            "data_fim": end.isoformat(),
            "ano": start.year,
            "mes": start.month,
            "cidade": city,
            "local": local,
            "uf": uf,
            "estado": UF_INFO[uf][0] if uf else None,
            "regiao": UF_INFO[uf][1] if uf else ("Exterior" if international else None),
            "pais": country,
            "internacional": international,
            "lat": lat, "lng": lng,
            "distancias_km": kms,
            "distancias_texto": dist_txt,
            "distancias_fonte": dist_source,
            "altimetria_m": elev_m,
            "altimetria_fonte": "Adventure Mag" if elev_m else None,
            "modalidade": "Trail Running",
            "organizador": clean(d.get("organizador")),
            "local_largada": None,
            "url_adventuremag": r["url"],
            "urls_adventuremag": [r["url"]],
            "link_oficial": link if link_type in ("site_oficial", "rede_social") else None,
            "link_oficial_tipo": link_type if link_type in ("site_oficial", "rede_social") else None,
            "link_inscricao": link if link_type == "inscricao" else None,
            "link_inscricao_fonte": "Adventure Mag" if link_type == "inscricao" else None,
            "status": status,
            "status_texto_fonte": r["tag"].strip() or None,
            "verificado_em": verified,
            "fonte": "Adventure Mag",
            "complemento_oficial": None,
            "alertas": alerts,
        }

        comp = complements.get(eid)
        if comp:
            rec["complemento_oficial"] = {"fonte_url": comp["fonte_url"], "verificado_em": comp["verificado_em"]}
            if comp.get("distancias_km") and not rec["distancias_km"]:
                rec["distancias_km"] = sorted(comp["distancias_km"], reverse=True)
                rec["distancias_fonte"] = "Site oficial"
            if comp.get("local_largada"):
                rec["local_largada"] = comp["local_largada"]
            if comp.get("link_inscricao") and not rec["link_inscricao"]:
                rec["link_inscricao"] = comp["link_inscricao"]
                rec["link_inscricao_fonte"] = "Site oficial"
            if comp.get("altimetria_m") and not rec["altimetria_m"]:
                rec["altimetria_m"] = comp["altimetria_m"]
                rec["altimetria_fonte"] = "Site oficial"
            rec["alertas"].extend(comp.get("divergencias", []))
        records.append(rec)

    # ---- duplicidades -----------------------------------------------------
    groups = defaultdict(list)
    for rec in records:
        groups[(norm_key(rec["nome"]), rec["data_inicio"], norm_key(rec["cidade"] or ""), rec["uf"])].append(rec)
    merged, dup_log = [], []
    for key, recs in groups.items():
        if len(recs) == 1:
            merged.append(recs[0])
            continue
        base = recs[0]
        for other in recs[1:]:
            base["adventuremag_ids"] += other["adventuremag_ids"]
            base["urls_adventuremag"] += other["urls_adventuremag"]
            for fld in ("link_inscricao", "link_oficial"):
                if other[fld] and other[fld] != base[fld]:
                    if base[fld]:
                        base["alertas"].append(f"Páginas duplicadas trazem links diferentes: {other[fld]}")
                    else:
                        base[fld] = other[fld]
        base["alertas"].append(f"Publicado {len(recs)}× na fonte (ids {', '.join(base['adventuremag_ids'])}); contado uma vez")
        dup_log.append({"nome": base["nome"], "ids": base["adventuremag_ids"]})
        merged.append(base)

    import geocode  # camada de localização (base local de municípios IBGE)
    geo_index = geocode.load(norm_key)
    for rec in merged:
        rec["alertas"].extend(geocode.locate(rec, geo_index, norm_key))

    # ---- provas enviadas pelo formulário e aprovadas na planilha ----
    import submissoes
    run_date = os.environ.get("BUILD_DATE") or date.today().isoformat()
    sub_rows = submissoes.read(SUBMISSIONS_CSV)
    sub_report = submissoes.apply(merged, sub_rows, {"norm_key": norm_key, "UF_INFO": UF_INFO,
                                                     "geo_index": geo_index, "today": run_date})
    sub_report["linhas_lidas"] = len(sub_rows)

    for rec in merged:
        n = 0
        n += bool(rec["cidade"]) + bool(rec["uf"] or rec["internacional"])
        n += bool(rec["link_inscricao"] or rec["link_oficial"])
        n += bool(rec["lat"] is not None)
        serious = any(a.startswith(("Data divergente", "UF divergente", "Link aponta", "Ano no nome", "Páginas duplicadas", "A página oficial", "Cidade divergente", "O link publicado")) for a in rec["alertas"])
        rec["confiabilidade"] = "alta" if n == 4 and not serious else ("media" if n >= 2 else "baixa")

    merged.sort(key=lambda x: (x["data_inicio"], x["nome"].lower()))
    return merged, listing, details, dup_log, verified, sub_report, run_date


def track_changes(records, run_date, verified):
    """Compara com a base anterior: data de inclusão, histórico de provas já realizadas e novidades."""
    prev = {}
    prev_meta = {}
    if os.path.exists(OUT_JSON):
        old = json.load(open(OUT_JSON, encoding="utf-8"))
        prev_meta = old.get("meta", {})
        prev = {e["id"]: e for e in old.get("eventos", [])}
    first = prev_meta.get("primeira_coleta") or prev_meta.get("coletado_em") or verified
    ids = {r["id"] for r in records}
    news = {"atualizado_em": run_date, "coleta_adventuremag": verified, "novas": [], "alteradas": [],
            "removidas_da_fonte": [], "mantidas_como_historico": 0}

    for r in records:
        old = prev.get(r["id"])
        r["incluido_em"] = (old or {}).get("incluido_em") or (first if old else run_date)
        if not old:
            news["novas"].append({"id": r["id"], "nome": r["nome"], "data": r["data_inicio"], "uf": r["uf"],
                                  "fonte": r["fonte"]})
            continue
        diff = [(f, old.get(f), r.get(f)) for f in ("data_inicio", "data_fim", "status", "cidade", "uf",
                                                    "link_inscricao", "distancias_km", "altimetria_m")
                if old.get(f) != r.get(f)]
        if diff:
            news["alteradas"].append({"id": r["id"], "nome": r["nome"],
                                      "mudancas": [{"campo": f, "de": a, "para": b} for f, a, b in diff]})

    for pid, old in prev.items():
        if pid in ids:
            continue
        if old["data_fim"] < run_date:
            # A fonte só lista provas futuras: as que já aconteceram ficam como histórico.
            old["historico"] = True
            records.append(old)
            news["mantidas_como_historico"] += 1
        else:
            news["removidas_da_fonte"].append({"id": pid, "nome": old["nome"], "data": old["data_inicio"], "uf": old.get("uf")})

    ref = date.fromisoformat(run_date)
    for r in records:
        inc = r.get("incluido_em") or first
        r["novo"] = inc > first and (ref - date.fromisoformat(inc)).days <= NEW_BADGE_DAYS
    records.sort(key=lambda x: (x["data_inicio"], x["nome"].lower()))
    return news, first


def validate(records, listing, details):
    errors = []
    ids = [r["id"] for r in records]
    if len(ids) != len(set(ids)):
        errors.append("ids duplicados na base")
    missing = [r["id"] for r in listing if r["id"] not in details]
    if len(missing) > 0.1 * len(listing):
        errors.append(f"{len(missing)} eventos sem página de detalhe coletada: {missing[:10]}")
    for r in records:
        if not r["nome"] or not r["data_inicio"]:
            errors.append(f"registro incompleto {r['id']}")
        if r["uf"] and r["uf"] not in UF_INFO:
            errors.append(f"UF inválida em {r['id']}")
        for f in ("link_oficial", "link_inscricao", "url_adventuremag"):
            if r[f] and not re.match(r"https?://[^/]+\.[^/]+", r[f]):
                errors.append(f"URL inválida em {r['id']}.{f}: {r[f]}")
    if os.path.exists(OUT_JSON):
        prev = json.load(open(OUT_JSON, encoding="utf-8"))
        prev_n = len(prev.get("eventos", []))
        if prev_n and len(records) < 0.7 * prev_n:
            errors.append(f"queda brusca de registros ({prev_n} → {len(records)}); possível falha de coleta")
    if len(records) < 20:
        errors.append("menos de 20 registros: coleta provavelmente falhou")
    return errors


def main():
    records, listing, details, dup_log, verified, sub_report, run_date = build()
    errors = validate(records, listing, details)
    if errors:
        print("VALIDAÇÃO FALHOU — base anterior preservada:")
        for e in errors:
            print(" -", e)
        sys.exit(1)

    news, first = track_changes(records, run_date, verified)
    news["envios"] = sub_report
    br = [r for r in records if not r["internacional"]]
    by_region = Counter(r["regiao"] or "Sem estado" for r in br)
    by_uf = Counter(r["uf"] or "—" for r in br)
    meta = {
        "fonte": "Adventure Mag — https://www.adventuremag.com.br/calendario/trail-run/",
        "coletado_em": verified,
        "atualizado_em": run_date,
        "primeira_coleta": first,
        "novas_nesta_atualizacao": len(news["novas"]),
        "envios_aprovados": len(sub_report["incluidas"]) + len(sub_report["complementadas"]),
        "paginas_listagem": max(int(r["page"]) for r in listing),
        "registros_na_fonte": len(listing),
        "eventos_unicos": len(records),
        "eventos_historico": sum(1 for r in records if r.get("historico")),
        "eventos_brasil": len(br),
        "eventos_exterior": len(records) - len(br),
        "periodo": [records[0]["data_inicio"], records[-1]["data_inicio"]],
        "anos": sorted({r["ano"] for r in records}),
        "por_regiao": dict(sorted(by_region.items())),
        "por_uf": dict(sorted(by_uf.items())),
        "por_status": dict(Counter(r["status"] for r in records)),
        "com_distancia": sum(1 for r in records if r["distancias_km"]),
        "com_altimetria": sum(1 for r in records if r["altimetria_m"]),
        "com_link": sum(1 for r in records if r["link_oficial"] or r["link_inscricao"]),
        "com_coordenadas": sum(1 for r in records if r["lat"] is not None),
        "no_mapa_estadual": sum(1 for r in br if r["mapa"]["tipo"] != "indisponivel"),
        "sem_localizacao_no_mapa": [r["id"] for r in br if r["mapa"]["tipo"] == "indisponivel"],
        "municipios_com_provas": len({r["municipio"]["ibge"] for r in br if r["municipio"]}),
        "fonte_municipios": "IBGE via kelvins/municipios-brasileiros (sede municipal)",
        "duplicidades_removidas": dup_log,
        "confiabilidade": dict(Counter(r["confiabilidade"] for r in records)),
    }
    tmp = OUT_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "eventos": records}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT_JSON)

    # Cópia consumida pela interface (script global, funciona até via file://).
    web_js = os.path.join(ROOT, "web", "data", "events.js")
    os.makedirs(os.path.dirname(web_js), exist_ok=True)
    with open(web_js + ".tmp", "w", encoding="utf-8") as f:
        f.write("window.TRAIL_DATA = " + json.dumps({"meta": meta, "eventos": records},
                ensure_ascii=False, separators=(",", ":")) + ";\n")
    os.replace(web_js + ".tmp", web_js)

    cols = ["id", "nome", "data_inicio", "data_fim", "cidade", "local", "uf", "regiao", "pais",
            "distancias_km", "altimetria_m", "organizador", "status", "link_oficial", "link_inscricao",
            "url_adventuremag", "confiabilidade", "alertas", "verificado_em"]
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in records:
            w.writerow([("; ".join(map(str, r[c])) if isinstance(r[c], list) else r[c]) for c in cols])

    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "alertas": {r["id"]: r["alertas"] for r in records if r["alertas"]}},
                  f, ensure_ascii=False, indent=1)
    with open(OUT_NEWS, "w", encoding="utf-8") as f:
        json.dump(news, f, ensure_ascii=False, indent=1)
    summary = news_markdown(news)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(summary + "\n")
    print(summary)
    print(json.dumps({k: v for k, v in meta.items() if k != "duplicidades_removidas"}, ensure_ascii=False, indent=1))
    print("duplicidades:", dup_log)


def news_markdown(n):
    e = n["envios"]
    lines = [f"## Atualização de {n['atualizado_em']}", "",
             f"- Coleta da Adventure Mag usada: {n['coleta_adventuremag']}",
             f"- Provas novas: **{len(n['novas'])}**",
             f"- Provas alteradas: **{len(n['alteradas'])}**",
             f"- Sumiram da fonte antes da data: **{len(n['removidas_da_fonte'])}**",
             f"- Já realizadas mantidas como histórico: {n['mantidas_como_historico']}",
             f"- Envios aprovados lidos da planilha: {e['linhas_lidas']} "
             f"(incluídos {len(e['incluidas'])}, complementaram provas existentes {len(e['complementadas'])}, "
             f"ignorados {len(e['ignoradas'])})"]
    for title, items, fmt in [
        ("Novas", n["novas"], lambda x: f"{x['data']} · {x['nome']} ({x['uf'] or '—'}) — {x['fonte']}"),
        ("Alteradas", n["alteradas"], lambda x: x["nome"] + ": " + "; ".join(f"{m['campo']} {m['de']} → {m['para']}" for m in x["mudancas"])),
        ("Sumiram da fonte (confira se foram canceladas)", n["removidas_da_fonte"], lambda x: f"{x['data']} · {x['nome']} ({x['uf'] or '—'})"),
        ("Envios ignorados (corrija na planilha)", e["ignoradas"], lambda x: f"linha {x['linha']}: {x['nome'] or '(sem nome)'} — {x['motivo']}"),
        ("Envios que complementaram provas existentes", e["complementadas"], lambda x: f"{x['nome']}: {', '.join(x['campos']) or 'sem mudanças'}"),
    ]:
        if items:
            lines += ["", f"### {title}"] + [f"- {fmt(x)}" for x in items[:200]]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
