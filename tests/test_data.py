#!/usr/bin/env python3
"""
Integridade da base gerada (data/events.json).

Verificações GERAIS valem para qualquer atualização (rodam no robô mensal).
Verificações de AMOSTRA conferem casos conhecidos da coleta de 14/10/2026 e só rodam
enquanto essa for a coleta usada (depois a fonte muda e esses casos deixam de existir).
"""
import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_db  # noqa: E402
import geocode  # noqa: E402

DB = json.load(open(os.path.join(ROOT, "data", "events.json"), encoding="utf-8"))
EV = DB["eventos"]
BY = {e["id"]: e for e in EV}
SNAPSHOT = DB["meta"]["coletado_em"] == "2026-10-14"
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


# ---------------- gerais ----------------
listing = build_db.read_listing(build_db.latest("listing_*.tsv"))
src_ids = {r["id"] for r in listing}
current = [e for e in EV if not e.get("historico")]
db_ids = {i for e in current for i in e["adventuremag_ids"]}
check("todos os registros da coleta atual estão na base", src_ids <= db_ids, f"fonte={len(src_ids)} base={len(db_ids)}")
check("provas da Adventure Mag fora da coleta atual são só histórico",
      all(e.get("historico") for e in EV if e["adventuremag_ids"] and not set(e["adventuremag_ids"]) & src_ids))
check("ids únicos", len({e['id'] for e in EV}) == len(EV))
check("nenhum id da fonte contado duas vezes", sum(len(e["adventuremag_ids"]) for e in current) == len(db_ids))
keys = [(build_db.norm_key(e["nome"]), e["data_inicio"], e["cidade"]) for e in EV]
check("sem duplicidade nome+data+cidade", len(keys) == len(set(keys)))
check("ordenação cronológica", [e["data_inicio"] for e in EV] == sorted(e["data_inicio"] for e in EV))
check("datas ISO válidas e fim >= início", all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["data_inicio"]) and e["data_fim"] >= e["data_inicio"] for e in EV))
check("ano/mês coerentes com a data", all(e["ano"] == int(e["data_inicio"][:4]) and e["mes"] == int(e["data_inicio"][5:7]) for e in EV))
check("UF válida ou ausente", all(e["uf"] in build_db.UF_INFO or e["uf"] is None for e in EV))
check("região coerente com a UF", all(not e["uf"] or build_db.UF_INFO[e["uf"]][1] == e["regiao"] for e in EV))
check("eventos no exterior sem UF brasileira", all(not e["internacional"] or e["uf"] is None for e in EV))
urls = [u for e in EV for u in [e["link_oficial"], e["link_inscricao"], *e["urls_adventuremag"]] if u]
check("links externos são http(s) absolutos", all(re.match(r"https?://[^/\s]+\.[^/\s]+", u) for u in urls))
check("nenhum link vazio 'http://'", all(u.rstrip("/") not in ("http:", "https:") for u in urls))
check("distância sem fonte nunca aparece", all(not e["distancias_km"] or e["distancias_fonte"] for e in EV))
check("altimetria sem fonte nunca aparece", all(not e["altimetria_m"] or e["altimetria_fonte"] for e in EV))
check("toda prova tem origem rastreável (página da fonte ou envio aprovado)",
      all(e["urls_adventuremag"] or (e.get("envio") and e["envio"]["aprovado"]) for e in EV))
check("toda prova tem data de inclusão na base", all(e.get("incluido_em") for e in EV))
check("meta.eventos_unicos confere", DB["meta"]["eventos_unicos"] == len(EV))
with open(os.path.join(ROOT, "data", "events.csv"), encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
check("CSV com o mesmo número de registros", len(rows) == len(EV))
news = json.load(open(os.path.join(ROOT, "data", "novidades.json"), encoding="utf-8"))
check("relatório de novidades gerado", news["atualizado_em"] == DB["meta"]["atualizado_em"])

before = open(os.path.join(ROOT, "data", "events.json"), "rb").read()
errs = build_db.validate([], listing, {})
check("validação rejeita coleta vazia", any("menos de 20" in e for e in errs))
check("arquivo anterior intacto após validação falha", open(os.path.join(ROOT, "data", "events.json"), "rb").read() == before)

# localização
idx = geocode.load(build_db.norm_key)
by_code = idx[0]
br = [e for e in EV if not e["internacional"]]
located = [e for e in br if e["mapa"]["tipo"] != "indisponivel"]
check("todo evento do Brasil tem status de localização", all(e["mapa"]["tipo"] in ("aproximada", "exata", "indisponivel") for e in br))
check("marcadores usam municípios IBGE existentes na UF do evento",
      all(e["municipio"]["ibge"] in by_code and by_code[e["municipio"]["ibge"]]["uf"] == e["uf"] for e in located), f"{len(located)} provas")
check("coordenada do marcador = sede do município (não o centroide do estado)",
      all(abs(e["mapa"]["lat"] - by_code[e["municipio"]["ibge"]]["lat"]) < 1e-9 and abs(e["mapa"]["lng"] - by_code[e["municipio"]["ibge"]]["lng"]) < 1e-9 for e in located))
check("nome da cidade confere com o município", all(build_db.norm_key(e["cidade"]) == build_db.norm_key(e["municipio"]["nome"]) for e in located))
check("localização aproximada sempre identificada como tal",
      all("sede" in e["mapa"]["nota"] and e["mapa"]["referencia"].startswith("Sede de") for e in located if e["mapa"]["tipo"] == "aproximada"))
check("ponto exato só com largada informada pelo organizador e perto do município",
      all(e.get("envio") and e["mapa"].get("largada_lat") is not None and
          geocode.haversine(e["mapa"]["largada_lat"], e["mapa"]["largada_lng"], e["municipio"]["lat"], e["municipio"]["lng"]) <= geocode.MAX_KM
          for e in EV if e["mapa"]["tipo"] == "exata"))
unl = [e for e in br if e["mapa"]["tipo"] == "indisponivel"]
check("provas sem localização continuam na base, com motivo", all(e["mapa"]["nota"] for e in unl), f"{len(unl)} provas")

# ---------------- amostra da coleta de 14/10/2026 ----------------
if SNAPSHOT:
    check("[amostra] 259 registros da fonte → 257 provas", len(src_ids) == 259 and len(current) == 257)
    check("[amostra] cancelado preservado (Corrida Mulungu)", BY["am-11223"]["status"] == "cancelado")
    check("[amostra] 'Nova data' preservada (WTR Campos do Jordão 2026)", BY["am-10673"]["status"] == "data_alterada")
    check("[amostra] Merzouga (sigla MA) = Marrocos, não Maranhão", BY["am-10912"]["pais"] == "Marrocos" and BY["am-10912"]["uf"] is None)
    check("[amostra] duplicidade da fonte unificada (PMMG Divinópolis)", set(BY["am-11184"]["adventuremag_ids"]) == {"11184", "11185"})
    check("[amostra] prova sem local mantém 'a divulgar'", BY["am-11226"]["cidade"] is None and "Local a divulgar" in BY["am-11226"]["alertas"])
    check("[amostra] Pernambuco tem 6 provas", len([e for e in current if e["uf"] == "PE"]) == 6)
    car = [e for e in EV if e["municipio"] and e["municipio"]["nome"] == "Caruaru"]
    check("[amostra] Caruaru: 2 provas no mesmo município IBGE 2604106", len(car) == 2 and all(e["municipio"]["ibge"] == "2604106" for e in car))
    tr = BY["am-10708"]
    check("[amostra] distrito associado com nota (Trancoso → Porto Seguro)", tr["municipio"]["nome"] == "Porto Seguro" and tr["local"] == "Trancoso")

ok = sum(1 for r in results if r[1])
for name, passed, det in results:
    print(("PASS " if passed else "FAIL ") + name + (f"  ({det})" if det else ""))
print(f"\n{ok}/{len(results)} verificações de dados passaram" + ("" if SNAPSHOT else " (sem amostra: coleta diferente de 14/10/2026)"))
sys.exit(0 if ok == len(results) else 1)
