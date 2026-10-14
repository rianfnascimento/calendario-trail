"""
Provas enviadas pelo formulário e APROVADAS por você na planilha.

Entrada: data/raw/submissoes_aprovadas.csv — a aba "Publicar" da planilha do formulário,
publicada na Web como CSV (o robô baixa esse arquivo a cada atualização). Essa aba só contém
linhas com Status = "Aprovada" e só as colunas públicas: nome e contato de quem enviou nunca
saem da planilha.

Colunas esperadas (cabeçalho exato; ordem livre):
  enviado_em, nome, data_inicio, data_fim, uf, cidade, local_largada, coordenadas,
  distancias, altimetria, modalidade, situacao, organizador, site, inscricao

Regras:
  * Uma linha aprovada que corresponde a uma prova já publicada pela Adventure Mag (mesmo
    município, mesma data e nome parecido) COMPLEMENTA essa prova: distâncias, D+, largada,
    links. Valores divergentes viram alerta; nada da fonte é apagado.
  * Sem correspondência: vira uma prova nova, com fonte "Envio do organizador".
  * Linhas inválidas (sem nome, data ou UF válidos) são ignoradas e listadas no relatório.
"""
import csv
import hashlib
import os
import re
from datetime import date

import geocode

STATUS_MAP = {"confirmada": "agendado", "adiada": "adiado", "cancelada": "cancelado"}
STOP = {"de", "da", "do", "das", "dos", "e", "trail", "run", "running", "corrida", "etapa", "the"}
FONTE = "Envio do organizador"


def _date(s):
    s = (s or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return date(int(m[3]), int(m[2]), int(m[1]))
    return None


def _kms(s):
    out = []
    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(milhas|mi)?", s or "", re.I):
        v = float(m[1].replace(",", "."))
        if m[2]:
            v = round(v * 1.609, 1)
        if 0 < v <= 500:
            out.append(int(v) if v == int(v) else v)
    return sorted(set(out), reverse=True)


def _int(s):
    m = re.search(r"\d[\d.]*", (s or "").replace(" ", ""))
    if not m:
        return None
    v = int(m[0].replace(".", ""))
    return v if 0 < v < 20000 else None


def _coords(s):
    """Aceita 'lat, long' decimal ou link do Google Maps (@lat,lng / q=lat,lng)."""
    s = (s or "").strip()
    m = re.search(r"(-?\d{1,2}\.\d{3,})\s*[, ]\s*(-?\d{1,3}\.\d{3,})", s)
    if not m:
        return None
    lat, lng = float(m[1]), float(m[2])
    return (lat, lng) if -34 <= lat <= 6 and -75 <= lng <= -28 else None


def _url(s):
    s = (s or "").strip()
    if s and not re.match(r"https?://", s, re.I) and re.match(r"[\w.-]+\.[a-z]{2,}", s, re.I):
        s = "https://" + s
    return s if re.match(r"https?://[^/\s]+\.[^/\s]+", s) else None


def _tokens(name, norm_key):
    return {t for t in norm_key(name).split() if t not in STOP and len(t) > 1}


def similar(a, b, norm_key):
    ta, tb = _tokens(a, norm_key), _tokens(b, norm_key)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def read(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in rows
            if any((v or "").strip() and (v or "").strip() != "#N/A" for v in r.values())]


def apply(records, rows, ctx):
    """Incorpora as linhas aprovadas a `records` (lista do build). Devolve o relatório."""
    norm_key, UF_INFO, geo_index, today = ctx["norm_key"], ctx["UF_INFO"], ctx["geo_index"], ctx["today"]
    rep = {"incluidas": [], "complementadas": [], "ignoradas": []}
    by_code = geo_index[0]

    for i, r in enumerate(rows, 2):
        nome = r.get("nome", "")
        ini = _date(r.get("data_inicio"))
        fim = _date(r.get("data_fim")) or ini
        uf = (r.get("uf", "")[:2] or "").upper()
        problems = []
        if not nome:
            problems.append("sem nome")
        if not ini:
            problems.append(f"data de início inválida ('{r.get('data_inicio', '')}')")
        if uf not in UF_INFO:
            problems.append(f"UF inválida ('{r.get('uf', '')}')")
        if problems:
            rep["ignoradas"].append({"linha": i, "nome": nome, "motivo": "; ".join(problems)})
            continue
        if fim < ini:
            fim = ini

        sub_id = "env-" + hashlib.sha1((r.get("enviado_em", "") + "|" + nome).encode()).hexdigest()[:8]
        kms = _kms(r.get("distancias"))
        dplus = _int(r.get("altimetria"))
        start = _coords(r.get("coordenadas"))
        site, insc = _url(r.get("site")), _url(r.get("inscricao"))
        status = STATUS_MAP.get((r.get("situacao") or "confirmada").split()[0].lower(), "agendado")

        probe = {"internacional": False, "uf": uf, "cidade": r.get("cidade") or None, "lat": None, "lng": None, "local": None}
        geocode.locate(probe, geo_index, norm_key)
        mun = probe["municipio"]

        # ---- correspondência com prova já publicada ----
        match, best = None, 0.0
        for rec in records:
            if rec["data_inicio"] != ini.isoformat() or rec["uf"] != uf:
                continue
            same_city = mun and rec.get("municipio") and rec["municipio"]["ibge"] == mun["ibge"]
            sim = similar(nome, rec["nome"], norm_key)
            if (same_city and sim >= 0.34) or sim >= 0.6:
                if sim > best:
                    match, best = rec, sim
        if match:
            changed = complement(match, kms, dplus, start, site, insc, r, status, sub_id, ctx)
            rep["complementadas"].append({"id": match["id"], "nome": match["nome"], "envio": sub_id, "campos": changed})
            continue

        alerts = []
        if not mun:
            alerts.append("Localização indisponível no mapa: " + (probe["mapa"]["nota"] or "cidade não identificada"))
        rec = {
            "id": sub_id, "adventuremag_ids": [], "nome": nome,
            "data_inicio": ini.isoformat(), "data_fim": fim.isoformat(), "ano": ini.year, "mes": ini.month,
            "cidade": mun["nome"] if mun else (r.get("cidade") or None),
            "local": r.get("local_largada") or None,
            "uf": uf, "estado": UF_INFO[uf][0], "regiao": UF_INFO[uf][1], "pais": "Brasil", "internacional": False,
            "lat": None, "lng": None,
            "distancias_km": kms, "distancias_texto": [r.get("distancias", "")] if kms else [],
            "distancias_fonte": FONTE if kms else None,
            "altimetria_m": dplus, "altimetria_fonte": FONTE if dplus else None,
            "modalidade": r.get("modalidade") or "Trail Running",
            "organizador": r.get("organizador") or None,
            "local_largada": r.get("local_largada") or None,
            "url_adventuremag": None, "urls_adventuremag": [],
            "link_oficial": site, "link_oficial_tipo": ("rede_social" if site and re.search(r"instagram|facebook|linktr", site) else "site_oficial") if site else None,
            "link_inscricao": insc, "link_inscricao_fonte": FONTE if insc else None,
            "status": status, "status_texto_fonte": r.get("situacao") or None,
            "verificado_em": today, "fonte": FONTE, "complemento_oficial": None,
            "envio": {"id": sub_id, "enviado_em": r.get("enviado_em") or None, "aprovado": True},
            "alertas": alerts,
        }
        rec["municipio"] = mun
        rec["mapa"] = probe["mapa"]
        set_start(rec, start)
        records.append(rec)
        rep["incluidas"].append({"id": sub_id, "nome": nome, "data": ini.isoformat(), "cidade": rec["cidade"], "uf": uf})
    return rep


def set_start(rec, start):
    """Ponto exato só quando o organizador informou a largada e ela fica perto do município."""
    if not start or not rec.get("municipio"):
        if start and not rec.get("municipio"):
            rec["alertas"].append("Coordenadas de largada informadas, mas o município não foi identificado; ponto não exibido")
        return
    dist = geocode.haversine(start[0], start[1], rec["municipio"]["lat"], rec["municipio"]["lng"])
    if dist > geocode.MAX_KM:
        rec["alertas"].append(f"Coordenadas de largada informadas ficam a {dist:.0f} km de {rec['municipio']['nome']}; ponto não exibido")
        return
    rec["mapa"].update({"tipo": "exata", "largada_lat": start[0], "largada_lng": start[1],
                        "nota": "Ponto de largada informado pelo organizador. O marcador do mapa agrupa as provas na sede do município."})


def complement(rec, kms, dplus, start, site, insc, r, status, sub_id, ctx):
    changed = []
    rec.setdefault("envio", {"id": sub_id, "enviado_em": r.get("enviado_em") or None, "aprovado": True, "tipo": "complemento"})
    if kms:
        if rec["distancias_km"] and sorted(rec["distancias_km"]) != sorted(kms):
            rec["alertas"].append(f"Distâncias divergentes: {rec['distancias_fonte']} {rec['distancias_km']} × organizador {kms}; exibindo as do organizador")
        if sorted(rec["distancias_km"]) != sorted(kms):
            rec["distancias_km"], rec["distancias_fonte"] = kms, FONTE
            changed.append("distâncias")
    if dplus and rec.get("altimetria_m") != dplus:
        rec["altimetria_m"], rec["altimetria_fonte"] = dplus, FONTE
        changed.append("altimetria")
    if r.get("local_largada") and not rec.get("local_largada"):
        rec["local_largada"] = r["local_largada"]
        changed.append("local de largada")
    if insc and not rec.get("link_inscricao"):
        rec["link_inscricao"], rec["link_inscricao_fonte"] = insc, FONTE
        changed.append("link de inscrição")
    elif insc and rec.get("link_inscricao") != insc:
        rec["alertas"].append(f"Organizador informou outro link de inscrição: {insc}")
    if site and not rec.get("link_oficial"):
        rec["link_oficial"] = site
        rec["link_oficial_tipo"] = "rede_social" if re.search(r"instagram|facebook|linktr", site) else "site_oficial"
        changed.append("site oficial")
    if r.get("organizador") and not rec.get("organizador"):
        rec["organizador"] = r["organizador"]
        changed.append("organizador")
    if status != "agendado" and rec["status"] != status:
        rec["alertas"].append(f"Situação informada pelo organizador ({r.get('situacao')}) difere da fonte ({rec['status']}); exibindo a do organizador")
        rec["status"] = status
        changed.append("situação")
    if start:
        before = rec["mapa"]["tipo"]
        set_start(rec, start)
        if rec["mapa"]["tipo"] != before:
            changed.append("ponto de largada")
    if changed:
        rec["fonte"] = rec["fonte"] + " + " + FONTE.lower()
    return changed
