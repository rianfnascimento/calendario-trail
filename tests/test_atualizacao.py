#!/usr/bin/env python3
"""
Simula atualizações numa CÓPIA do projeto (a base real não é tocada):
  1. envios aprovados da planilha (tests/fixtures/submissoes_exemplo.csv);
  2. uma varredura mensal posterior em que provas já realizadas saem da fonte;
  3. o coletor incremental reaproveitando páginas já baixadas.
"""
import csv
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "submissoes_exemplo.csv")
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


tmp = tempfile.mkdtemp()
proj = os.path.join(tmp, "p")
shutil.copytree(ROOT, proj, ignore=shutil.ignore_patterns("dist", "__pycache__", ".git", "node_modules"))


def build(date_, csv_path=None):
    env = dict(os.environ, BUILD_DATE=date_, SUBMISSOES_CSV=csv_path or os.path.join(proj, "nao-existe.csv"))
    env.pop("GITHUB_STEP_SUMMARY", None)
    r = subprocess.run([sys.executable, "scripts/build_db.py"], cwd=proj, env=env, capture_output=True, text=True)
    db = json.load(open(os.path.join(proj, "data", "events.json"), encoding="utf-8"))
    news = json.load(open(os.path.join(proj, "data", "novidades.json"), encoding="utf-8"))
    return r, db, news


# ---------- 1. envios aprovados ----------
r, db, news = build("2026-10-20", FIX)
check("build com envios conclui", r.returncode == 0, r.stderr[-300:])
ev = db["eventos"]
by = {e["id"]: e for e in ev}
env = [e for e in ev if e["id"].startswith("env-")]
grav = next((e for e in env if "Gravatá" in e["nome"]), None)
check("envio novo vira prova (Gravatá)", grav is not None)
check("Gravatá: município IBGE e região corretos", grav and grav["municipio"]["ibge"] == "2606408" and grav["regiao"] == "Nordeste")
check("Gravatá: ponto de largada exato informado pelo organizador", grav and grav["mapa"]["tipo"] == "exata" and grav["mapa"]["largada_lat"] == -8.205)
check("Gravatá: distâncias, D+ e fonte do organizador",
      grav and grav["distancias_km"] == [42, 21, 10] and grav["altimetria_m"] == 1850 and grav["distancias_fonte"] == "Envio do organizador")
check("Gravatá: links classificados (site e inscrição)",
      grav and grav["link_oficial"] == "https://exemplo-trail.com.br" and grav["link_inscricao"].startswith("https://www.ticketsports"))
check("Gravatá: prova de dois dias", grav and grav["data_fim"] == "2027-03-21")
check("envio aprovado ganha selo 'Nova'", grav and grav["novo"] is True)
check("provas antigas não ganham selo 'Nova'", not any(e["novo"] for e in ev if not e["id"].startswith("env-")))
mat = by["am-11160"]
check("envio de prova existente complementa em vez de duplicar (Matutos)",
      sum(1 for e in ev if "Matutos" in e["nome"]) == 1 and mat["distancias_km"] == [21, 10, 5] and mat["altimetria_m"] == 650)
check("complemento normaliza link sem https", mat["link_inscricao"] == "https://sympla.com.br/evento/matutos-exemplo")
check("complemento mantém a página da Adventure Mag", mat["url_adventuremag"].endswith("matutos-trail-run-2026") and "Envio do organizador".lower() in mat["fonte"].lower())
bon = next((e for e in env if "Bonito" in e["nome"]), None)
check("coordenadas longe do município não viram ponto exato (Bonito)",
      bon and bon["mapa"]["tipo"] == "aproximada" and any("km de Bonito" in a for a in bon["alertas"]))
vila = next((e for e in env if "Inexistente" in e["nome"]), None)
check("cidade não identificada: fica na lista, fora do mapa", vila and vila["mapa"]["tipo"] == "indisponivel")
ign = news["envios"]["ignoradas"]
check("envio sem UF é ignorado e explicado no relatório", len(ign) == 1 and "UF inválida" in ign[0]["motivo"], str(ign))
check("linha vazia da planilha é descartada", news["envios"]["linhas_lidas"] == 5)
check("relatório lista envios incluídos e complementados",
      len(news["envios"]["incluidas"]) == 3 and news["envios"]["complementadas"][0]["id"] == "am-11160")
check("novidades: 3 provas novas", len(news["novas"]) == 3, str([n["nome"] for n in news["novas"]]))

r2, db2, news2 = build("2026-10-21", FIX)
check("rodar de novo sem mudanças: nenhuma novidade", len(news2["novas"]) == 0 and len(news2["alteradas"]) == 0)
check("data de inclusão preservada entre execuções", {e["id"]: e["incluido_em"] for e in db2["eventos"]}[grav["id"]] == "2026-10-20")

# ---------- 2. varredura mensal posterior ----------
raw = os.path.join(proj, "data", "raw")
rows = list(csv.DictReader(open(os.path.join(raw, "listing_2026-10-14.tsv"), encoding="utf-8"), delimiter="\t"))
keep = [r_ for r_ in rows if r_["date"][3:] not in ("10/2026",) and "11306" not in r_["url"]]
with open(os.path.join(raw, "listing_2026-11-01.tsv"), "w", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys(), delimiter="\t")
    w.writeheader()
    w.writerows(keep)
shutil.copy(os.path.join(raw, "details_2026-10-14.txt"), os.path.join(raw, "details_2026-11-01.txt"))
r3, db3, news3 = build("2026-11-02", FIX)
check("varredura mensal conclui", r3.returncode == 0, r3.stderr[-300:])
by3 = {e["id"]: e for e in db3["eventos"]}
octo = [e for e in db3["eventos"] if e["data_inicio"].startswith("2026-10") and e["adventuremag_ids"]]
check("provas de outubro saem da fonte e ficam como histórico", octo and all(e.get("historico") for e in octo), f"{len(octo)} provas")
check("prova futura que sumiu da fonte é avisada no relatório",
      any(x["id"] == "am-11306" for x in news3["removidas_da_fonte"]) and "am-11306" not in by3)
check("envios aprovados continuam após a varredura", grav["id"] in by3)
check("relatório em Markdown gerado", "Atualização de 2026-11-02" in r3.stdout)

# ---------- 3. coletor incremental (sem acessar a internet) ----------
sys.path.insert(0, os.path.join(proj, "scripts"))
collect = importlib.import_module("collect")
collect.RAW = raw
listing_rows = [[r_["page"], r_["date"], r_["tag"], r_["name"], r_["city"], r_["uf"], r_["url"]] for r_ in keep]
listing_rows[0][2] = "Cancelado"           # uma prova mudou de situação
listing_rows.append(["9", "10/12/2027", "", "EXEMPLO Prova Nova", "Recife", "PE",
                     "https://www.adventuremag.com.br/calendario/99999/1/exemplo-prova-nova"])
fetched = []
collect.get = lambda url, tries=3: url
collect.time.sleep = lambda s: None
pages = {1: (listing_rows, 1)}
collect.parse_listing = lambda page, n: pages.get(n, ([], 1))
collect.parse_detail = lambda page: fetched.append(page) or "-|2027-12-10|-|Recife|PE|-|-|-8.05|-34.88|-|-"
collect.date = type("D", (), {"today": staticmethod(lambda: __import__("datetime").date(2026, 12, 1))})
sys.argv = ["collect.py"]
try:
    collect.main()
    ok = True
except SystemExit as e:
    ok = e.code in (None, 0)
check("coletor incremental conclui", ok)
check("baixa só as páginas novas ou alteradas", len(fetched) == 2, f"{len(fetched)} de {len(listing_rows)}")
det = open(os.path.join(raw, "details_2026-12-01.txt"), encoding="utf-8").read().splitlines()
check("reaproveita as demais da coleta anterior", len(det) == len(listing_rows))

shutil.rmtree(tmp)
ok = sum(1 for r_ in results if r_[1])
for name, passed, d in results:
    print(("PASS " if passed else "FAIL ") + name + (f"  ({d})" if d else ""))
print(f"\n{ok}/{len(results)} verificações de atualização passaram")
sys.exit(0 if ok == len(results) else 1)
