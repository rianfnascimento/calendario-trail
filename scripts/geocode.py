"""
Localização das provas no mapa estadual.

Fonte cartográfica: base de municípios brasileiros com código IBGE e coordenadas da sede
municipal (data/geo/municipios.csv, projeto kelvins/municipios-brasileiros, licença MIT).
Nenhum serviço de geocodificação externo é consultado: a base é local, então não há limite
de uso nem consulta repetida. O resultado fica gravado em data/events.json.

Regras:
  * Cidade do evento + UF -> município IBGE (comparação sem acentos/caixa).
  * Localidades que não são municípios (distritos, praias, parques) só são associadas por
    data/geo/localidades_municipios.json, e apenas se as coordenadas publicadas pela fonte
    ficarem a menos de MAX_KM da sede do município indicado.
  * O marcador fica na sede municipal e é sempre rotulado como localização APROXIMADA.
    Um ponto "exato" só existiria se a fonte publicasse coordenadas da largada (não há hoje).
  * Sem cidade identificável: o evento continua na base, com mapa.tipo = "indisponivel".
"""
import csv
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO = os.path.join(ROOT, "data", "geo")
MAX_KM = 60.0


def haversine(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load(norm_key):
    with open(os.path.join(GEO, "estados.csv"), encoding="utf-8-sig") as f:
        uf_by_code = {r["codigo_uf"]: r["uf"] for r in csv.DictReader(f)}
    by_code, by_name = {}, {}
    with open(os.path.join(GEO, "municipios.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            m = {"ibge": r["codigo_ibge"], "nome": r["nome"], "uf": uf_by_code[r["codigo_uf"]],
                 "lat": float(r["latitude"]), "lng": float(r["longitude"])}
            by_code[m["ibge"]] = m
            by_name[(m["uf"], norm_key(m["nome"]))] = m
    with open(os.path.join(GEO, "localidades_municipios.json"), encoding="utf-8") as f:
        loc = json.load(f)
    aliases = {(a["uf"], norm_key(a["localidade"])): a for a in loc["localidades"]}
    unresolved = {(a["uf"], norm_key(a["localidade"])): a for a in loc["nao_resolvidas"]}
    return by_code, by_name, aliases, unresolved


def locate(rec, index, norm_key):
    """Preenche rec['municipio'] e rec['mapa']; devolve alertas novos."""
    by_code, by_name, aliases, unresolved = index
    alerts = []
    rec["municipio"] = None
    rec["mapa"] = {"tipo": "indisponivel", "lat": None, "lng": None, "referencia": None, "nota": None}
    if rec["internacional"]:
        rec["mapa"]["nota"] = "Prova fora do Brasil"
        return alerts
    if not rec["uf"] or not rec["cidade"]:
        rec["mapa"]["nota"] = "Cidade não informada pela fonte"
        alerts.append("Localização indisponível no mapa: cidade não informada pela fonte")
        return alerts

    key = (rec["uf"], norm_key(rec["cidade"]))
    mun, via = by_name.get(key), "nome"
    alias = aliases.get(key)
    if not mun and alias:
        mun, via = by_code.get(alias["municipio_ibge"]), "localidade"
    if not mun:
        why = unresolved.get(key, {}).get("motivo", "local não corresponde a um município do IBGE")
        rec["mapa"]["nota"] = f"'{rec['cidade']}' não identificado com segurança ({why})"
        alerts.append(f"Localização indisponível no mapa: {rec['mapa']['nota']}")
        return alerts

    # Conferência com as coordenadas publicadas pela fonte, quando existem.
    dist = None
    if rec.get("lat") is not None:
        dist = haversine(rec["lat"], rec["lng"], mun["lat"], mun["lng"])
        if dist > MAX_KM:
            if via == "localidade":
                rec["mapa"]["nota"] = (f"Associação '{rec['cidade']}' → {mun['nome']} descartada: coordenadas da fonte "
                                       f"a {dist:.0f} km da sede")
                alerts.append("Localização indisponível no mapa: " + rec["mapa"]["nota"])
                return alerts
            alerts.append(f"Coordenadas publicadas pela fonte ficam a {dist:.0f} km da sede de {mun['nome']}; "
                          "marcador mantido na sede do município informado")

    rec["municipio"] = dict(mun)
    nota = "Local exato de largada não informado; marcador na sede do município (IBGE)."
    if via == "localidade":
        rec["local"] = rec["local"] or rec["cidade"]
        rec["cidade"] = mun["nome"]
        nota = f"{alias['nota']}. Marcador na sede de {mun['nome']} (IBGE); local exato não informado."
    rec["mapa"] = {"tipo": "aproximada", "lat": mun["lat"], "lng": mun["lng"],
                   "referencia": f"Sede de {mun['nome']} ({mun['uf']}), IBGE {mun['ibge']}",
                   "nota": nota, "distancia_coord_fonte_km": None if dist is None else round(dist, 1)}
    return alerts
