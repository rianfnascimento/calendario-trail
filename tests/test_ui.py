#!/usr/bin/env python3
"""
Testes de interface em navegador real (Chromium headless via Playwright) sobre dist/index.html.
Uso: python3 tests/test_ui.py   (rode antes: build_db.py, build_map.py, bundle.py)
SHOTS_DIR=/pasta python3 tests/test_ui.py  também salva capturas de tela.
"""
import asyncio
import os
import shutil
import sys
import tempfile
from datetime import datetime

from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = "file://" + os.path.join(ROOT, "dist", "index.html")
SHOTS = os.environ.get("SHOTS_DIR")
results = []
CARUARU = "2604106"


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


async def shot(pg, name):
    if SHOTS:
        await pg.screenshot(path=os.path.join(SHOTS, name + ".png"))


async def tap_state(pg, uf):
    """Toque com ponteiro real num ponto interior do estado (centroide) no mapa nacional."""
    await pg.evaluate("document.querySelector('.br-map').scrollIntoView({block: 'center'})")
    await pg.wait_for_timeout(300)
    pt = await pg.evaluate("""uf => {
      const s = window.BR_STATES.states.find(x => x.uf === uf);
      const svg = document.querySelector('.br-map');
      const p = svg.createSVGPoint(); p.x = s.cx; p.y = s.cy;
      const r = p.matrixTransform(svg.getScreenCTM());
      return {x: r.x, y: r.y};
    }""", uf)
    await pg.mouse.click(pt["x"], pt["y"])
    await pg.wait_for_timeout(250)


async def tap_marker(pg, sel):
    """Toque real no centro do marcador do mapa estadual."""
    loc = pg.locator(sel).first
    await loc.scroll_into_view_if_needed()
    box = await loc.locator("circle.dot").bounding_box()
    await pg.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    await pg.wait_for_timeout(250)


async def reveal_city(pg, key):
    """Toca nos grupos até o marcador individual da cidade aparecer (agrupamento por zoom)."""
    clicks = 0
    for _ in range(6):
        if await pg.locator(f'.sm-mark.city[data-city="{key}"]').count():
            return clicks
        # grupo que contém a cidade: o mais próximo da posição dela
        idx = await pg.evaluate("""key => {
          const P = window.BR_STATES.proj, e = window.TRAIL_DATA.eventos.find(x => x.municipio && x.municipio.ibge === key);
          const x = (e.municipio.lng*Math.PI/180 - P.minx + P.pad) * P.scale;
          const y = (P.maxy - Math.log(Math.tan(Math.PI/4 + e.municipio.lat*Math.PI/360)) + P.pad) * P.scale;
          const cl = [...document.querySelectorAll('.sm-mark.cluster')];
          let best = -1, bd = Infinity;
          cl.forEach((g, i) => { const m = g.getAttribute('transform').match(/translate\\(([-\\d.]+),([-\\d.]+)\\)/);
            const d = Math.hypot(+m[1]-x, +m[2]-y); if (d < bd) { bd = d; best = i; } });
          return best;
        }""", key)
        if idx < 0:
            return clicks
        await tap_marker(pg, f".sm-mark.cluster >> nth={idx}")
        clicks += 1
    return clicks


async def card_ids(pg, sel):
    return await pg.eval_on_selector_all(sel + " .card", "els => els.map(e => e.dataset.event)")


async def run(p, label, viewport, mobile):
    b = await p.chromium.launch()
    ctx = await b.new_context(viewport=viewport, is_mobile=mobile, has_touch=mobile, locale="pt-BR",
                              color_scheme="light" if mobile else "dark")
    pg = await ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    await pg.clock.set_fixed_time(datetime(2026, 10, 14, 12, 0))
    await pg.route("**/fonts.googleapis.com/**", lambda r: r.abort())
    await pg.goto(PAGE)
    await pg.wait_for_selector(".br-map path")
    ev = await pg.evaluate("window.TRAIL_DATA.eventos.map(e => ({id:e.id, uf:e.uf, d:e.data_inicio, st:e.status, mun: e.municipio && e.municipio.ibge, nome: e.nome}))")
    byid = {e["id"]: e for e in ev}
    t = f"[{label}] "

    # ---------- Nível 1: Brasil ----------
    check(t + "mapa nacional com 27 unidades federativas", await pg.locator(".br-map path.state").count() == 27)
    check(t + "filtros recolhidos ao abrir", await pg.locator("#filters").is_hidden())
    check(t + "sem rolagem horizontal (Brasil)", await pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
    await shot(pg, f"{label}-1-brasil")

    await pg.click(".regions button[data-region='Sul']")
    ids = await card_ids(pg, "#list-map")
    check(t + "região Sul filtra lista", ids and all(byid[i]["uf"] in ("PR", "SC", "RS") for i in ids), f"{len(ids)} provas")
    check(t + "estados fora da região esmaecidos", "dim" in await pg.get_attribute('.br-map path[data-uf="BA"]', "class"))
    await pg.click(".regions button[data-region='']")

    # ---------- Brasil → Pernambuco (toque no mapa) ----------
    await tap_state(pg, "PE")
    check(t + "toque em PE abre o nível estadual", await pg.text_content("#sel-title") == "Pernambuco")
    check(t + "mapa estadual visível e nacional oculto", await pg.locator("#statemap").is_visible() and await pg.locator("#map").is_hidden())
    crumbs = await pg.text_content("#crumbs")
    check(t + "trilha Brasil › Nordeste › Pernambuco", "Brasil" in crumbs and "Nordeste" in crumbs and "Pernambuco" in crumbs, crumbs)
    pe_ev = [e for e in ev if e["uf"] == "PE"]
    located = [e for e in pe_ev if e["mun"]]
    total = await pg.evaluate("[...document.querySelectorAll('.sm-mark, .sm-mark-r')].reduce((s, g) => s + +g.dataset.count, 0)")
    check(t + "marcadores somam as provas localizadas de PE", total == len(located), f"{total} de {len(pe_ev)}")
    if mobile:
        check(t + "celular: subabas Mapa | Cidades | Provas", await pg.locator("#sub-map").is_visible() and await pg.locator("#sub-cities").is_visible())
        check(t + "celular: botão para ver as provas abaixo do mapa", await pg.locator("#see-events").is_visible())
        check(t + "celular: zoom + − disponível", await pg.locator(".sm-zoom [data-z='in']").is_visible())
    else:
        check(t + "computador: mapa e lista lado a lado", await pg.locator("#statemap").is_visible() and await pg.locator("#list-map").is_visible())
    check(t + "sem rolagem horizontal (estado)", await pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
    await shot(pg, f"{label}-2-pernambuco")

    # posição dos marcadores = coordenadas reais dos municípios (projetadas)
    pos_ok = await pg.evaluate("""() => {
      const P = window.BR_STATES.proj, ev = window.TRAIL_DATA.eventos;
      return [...document.querySelectorAll('.sm-mark.city')].every(g => {
        const e = ev.find(x => x.municipio && x.municipio.ibge === g.dataset.city);
        const x = (e.municipio.lng*Math.PI/180 - P.minx + P.pad) * P.scale;
        const y = (P.maxy - Math.log(Math.tan(Math.PI/4 + e.municipio.lat*Math.PI/360)) + P.pad) * P.scale;
        const m = g.getAttribute('transform').match(/translate\\(([-\\d.]+),([-\\d.]+)\\)/);
        return Math.abs(+m[1]-x) < 0.01 && Math.abs(+m[2]-y) < 0.01 && e.uf === 'PE';
      });
    }""")
    check(t + "marcadores posicionados nas coordenadas dos municípios de PE", pos_ok)
    remote = await pg.locator(".sm-mark-r").all_text_contents()
    check(t + "Fernando de Noronha fora de escala, em atalho próprio", any("Fernando de Noronha" in r for r in remote))

    # ---------- agrupamento por zoom e toque em Caruaru ----------
    n_before = await pg.locator(".sm-mark").count()
    vb_before = await pg.get_attribute(".sm-svg", "viewBox")
    clicks = await reveal_city(pg, CARUARU)
    vb_after = await pg.get_attribute(".sm-svg", "viewBox")
    check(t + "cidades próximas agrupadas conforme o zoom", clicks == 0 or (vb_before != vb_after), f"{clicks} toque(s) em grupos, {n_before} marcadores iniciais")
    cnt = await pg.get_attribute(f'.sm-mark.city[data-city="{CARUARU}"]', "data-count")
    check(t + "Caruaru: 2 provas num único marcador", cnt == "2", cnt)
    await tap_marker(pg, f'.sm-mark.city[data-city="{CARUARU}"]')
    pop = await pg.text_content(".sm-pop")
    check(t + "toque no marcador abre resumo da cidade", await pg.locator(".sm-pop").is_visible() and "Caruaru" in pop and "2 provas" in pop, pop.strip()[:60])
    check(t + "resumo identifica localização aproximada", "aproximada" in pop)
    check(t + "marcador selecionado destacado", "sel" in await pg.get_attribute(f'.sm-mark.city[data-city="{CARUARU}"]', "class"))
    ids = await card_ids(pg, "#list-map")
    check(t + "lista filtrada pela cidade do marcador", len(ids) == 2 and all(byid[i]["mun"] == CARUARU for i in ids))
    await shot(pg, f"{label}-3-caruaru-mapa")

    await pg.click(".sm-pop-go")
    await pg.wait_for_timeout(200)
    check(t + "'Ver as provas' mostra a lista da cidade", await pg.locator("#list-map").is_visible() and await pg.locator("#city-chip").is_visible())
    ordered = [byid[i]["d"] for i in ids]
    check(t + "provas de Caruaru em ordem cronológica", ordered == sorted(ordered))
    await shot(pg, f"{label}-4-caruaru-lista")

    # ---------- detalhes de um evento ----------
    await pg.click(f"#list-map .card[data-event='{ids[0]}']")
    await pg.wait_for_selector("#detail[open]")
    body = await pg.text_content("#d-body")
    check(t + "detalhe abre a partir da lista da cidade", byid[ids[0]]["nome"] in body)
    check(t + "detalhe informa localização aproximada (sede IBGE)", "Aproximada: sede de Caruaru" in body and "2604106" in body)
    hrefs = await pg.eval_on_selector_all("#d-body .d-links a", "els => els.map(a => [a.href, a.target])")
    check(t + "links externos abrem em nova aba", hrefs and all(h.startswith("https://") and tg == "_blank" for h, tg in hrefs))
    await shot(pg, f"{label}-5-detalhe")
    await pg.keyboard.press("Escape")
    await pg.wait_for_timeout(100)
    check(t + "detalhe fecha com Esc", not await pg.locator("#detail[open]").count())

    # ---------- volta ao estado sem perder filtros ----------
    await pg.click("#btn-filters")
    await pg.select_option("#f-year", "2026")
    await pg.click("#btn-close")
    await pg.click("#crumbs [data-crumb='uf']")
    check(t + "trilha volta a Pernambuco (cidade limpa)", await pg.text_content("#sel-title") == "Pernambuco")
    check(t + "filtro de ano preservado ao voltar ao estado", await pg.input_value("#f-year") == "2026")
    ids = await card_ids(pg, "#list-map")
    check(t + "lista do estado respeita o ano", ids and all(byid[i]["uf"] == "PE" and byid[i]["d"].startswith("2026") for i in ids), f"{len(ids)} provas")
    total = await pg.evaluate("[...document.querySelectorAll('.sm-mark, .sm-mark-r')].reduce((s, g) => s + +g.dataset.count, 0)")
    check(t + "mapa e lista mostram o mesmo conjunto (2026)", total == len([i for i in ids if byid[i]["mun"]]), f"mapa {total} × lista {len(ids)}")

    # ---------- lista de cidades ----------
    if not mobile:
        await pg.click("#sub-cities")
    else:
        await pg.click("#sub-cities")
    rows = await pg.eval_on_selector_all("#city-list .city-row .cc", "els => els.map(e => parseInt(e.textContent))")
    check(t + "cidades ordenadas por número de provas", rows == sorted(rows, reverse=True), str(rows))
    await pg.click(".seg [data-sort='alpha']")
    names = await pg.eval_on_selector_all("#city-list .city-row .cn", "els => els.map(e => e.textContent)")
    check(t + "ordenação alfabética", names == sorted(names, key=lambda s: s.lower()), ", ".join(names))
    check(t + "Gravatá não aparece (não há prova em Gravatá na fonte)", not any("Gravat" in n for n in names))
    await pg.click("#city-list [data-city-pick]:has-text('Abreu e Lima')")
    await pg.wait_for_timeout(200)
    ids = await card_ids(pg, "#list-map")
    check(t + "escolher cidade na lista mostra só as provas dela", ids and all(byid[i]["mun"] == "2600054" for i in ids), f"{len(ids)} prova(s)")
    check(t + "cidade da lista destacada no mapa", "sel" in (await pg.get_attribute('.sm-mark[data-city="2600054"]', "class") or ""))
    await pg.click("#city-chip [data-clear-city]")
    check(t + "limpar cidade volta a todas as cidades do estado", await pg.locator("#city-chip").is_hidden())

    # ---------- filtros combinados (cidade + período + distância) ----------
    await pg.click("#btn-filters")
    await pg.select_option("#f-year", "")
    await pg.select_option("#f-city", CARUARU)
    await pg.fill("#f-from", "2027-01-01")
    await pg.fill("#f-to", "2027-06-30")
    await pg.fill("#f-kmmin", "30")
    await pg.wait_for_timeout(150)
    c = (await pg.text_content("#result-count")).strip()
    check(t + "Caruaru + 1º semestre 2027 + >30 km: 0 provas, sem erro", c.startswith("0") and "Caruaru" in c, c)
    await pg.click("#btn-clear")
    await pg.click("#btn-close")
    check(t + "limpar filtros volta ao Brasil", await pg.text_content("#sel-title") == "Todas as provas")

    # ---------- estado com provas sem localização ----------
    await pg.select_option("#pick-uf", "AL")
    await pg.click("#sub-cities")
    txt = await pg.text_content("#city-list")
    check(t + "AL: grupo 'Sem localização no mapa' na lista de cidades", "Sem localização no mapa" in txt)
    await pg.click("#sub-events")
    ids = await card_ids(pg, "#list-map")
    no_loc = [i for i in ids if not byid[i]["mun"]]
    check(t + "AL: provas sem coordenadas continuam na lista", len(no_loc) == 2 and len(ids) == 4)
    check(t + "AL: aviso de provas fora do mapa", "sem marcador no mapa" in await pg.text_content("#sel-note"))
    total = await pg.evaluate("[...document.querySelectorAll('.sm-mark, .sm-mark-r')].reduce((s, g) => s + +g.dataset.count, 0)")
    check(t + "AL: marcadores só para provas localizadas", total == 2)

    # ---------- estado sem provas ----------
    await pg.goto(PAGE + "#rr")
    await pg.wait_for_timeout(300)
    await pg.click("#sub-events") if mobile else None
    check(t + "Roraima: aviso de nenhuma prova", "Nenhuma prova" in await pg.text_content("#list-map"))
    check(t + "Roraima: mapa estadual sem marcadores", await pg.locator(".sm-mark").count() == 0)

    # ---------- link direto para cidade ----------
    await pg.goto(PAGE + "#pe-" + CARUARU)
    await pg.wait_for_timeout(400)
    check(t + "link #pe-2604106 abre Caruaru", await pg.text_content("#sel-title") == "Caruaru")

    # ---------- São Paulo: agrupamento e zoom ----------
    await pg.goto(PAGE + "#sp")
    await pg.wait_for_timeout(400)
    n_cities = await pg.evaluate("new Set(window.TRAIL_DATA.eventos.filter(e => e.uf==='SP' && e.municipio && e.data_fim >= '2026-10-14').map(e => e.municipio.ibge)).size")
    n0 = await pg.locator(".sm-mark").count()
    for _ in range(3):
        await pg.click(".sm-zoom [data-z='in']")
    vbw = float((await pg.get_attribute(".sm-svg", "viewBox")).split()[2])
    await pg.click(".sm-zoom [data-z='fit']")
    vbw0 = float((await pg.get_attribute(".sm-svg", "viewBox")).split()[2])
    check(t + "SP: grupos reduzem marcadores na visão do estado", n0 < n_cities, f"{n0} marcadores para {n_cities} cidades")
    check(t + "SP: botões de zoom ampliam e restauram", vbw < vbw0)
    await shot(pg, f"{label}-6-sao-paulo")

    # ---------- outras visões (compartilham filtros) ----------
    await pg.goto(PAGE)
    await pg.wait_for_timeout(300)
    await pg.click("#tab-cal")
    check(t + "calendário abre no primeiro mês com provas", await pg.text_content("#cal-title") == "outubro 2026")
    await pg.click("#cal-body [data-day='2026-10-25']")
    ids = await card_ids(pg, "#list-cal")
    check(t + "toque no dia lista provas daquele dia", ids and all(byid[i]["d"] <= "2026-10-25" for i in ids), f"{len(ids)} provas")
    for _ in range(3):
        await pg.click("#cal-next")
    check(t + "navegação de meses atravessa o ano", await pg.text_content("#cal-title") == "janeiro 2027")
    await pg.click("#tab-next")
    ids = await card_ids(pg, "#list-next")
    check(t + "próximas provas em ordem cronológica", [byid[i]["d"] for i in ids] == sorted(byid[i]["d"] for i in ids), f"{len(ids)} provas")
    await pg.fill("#q", "mulungu")
    await pg.wait_for_timeout(300)
    check(t + "prova cancelada sinalizada", "Cancelada" in await pg.text_content("#list-next"))

    # detalhe aberto fora do mapa → "ver no mapa" leva ao estado e cidade
    await pg.fill("#q", "matutos")
    await pg.wait_for_timeout(300)
    await pg.click("#list-next .card")
    await pg.click("#d-body [data-show-on-map]")
    await pg.wait_for_timeout(300)
    check(t + "'Ver no mapa' no detalhe leva a Caruaru no mapa estadual",
          await pg.text_content("#sel-title") == "Caruaru" and await pg.locator("#statemap").is_visible())

    check(t + "sem erros de JavaScript", not errors, "; ".join(errors))
    await b.close()


async def error_case(p):
    tmp = tempfile.mkdtemp()
    src = open(os.path.join(ROOT, "dist", "index.html"), encoding="utf-8").read()
    path = os.path.join(tmp, "index.html")
    open(path, "w", encoding="utf-8").write(src.replace("window.TRAIL_DATA = ", "window.TRAIL_DATA_X = ", 1))
    b = await p.chromium.launch()
    pg = await b.new_page()
    await pg.route("**/fonts.googleapis.com/**", lambda r: r.abort())
    await pg.goto("file://" + path)
    check("[erro] base ausente mostra mensagem clara", await pg.locator("#error").is_visible() and "Não foi possível carregar" in await pg.text_content("#error"))
    await b.close()
    shutil.rmtree(tmp)


async def main():
    async with async_playwright() as p:
        await run(p, "celular", {"width": 390, "height": 844}, True)
        await run(p, "desktop", {"width": 1280, "height": 900}, False)
        await error_case(p)
    ok = sum(1 for r in results if r[1])
    for name, passed, det in results:
        print(("PASS " if passed else "FAIL ") + name + (f"  ({det})" if det else ""))
    print(f"\n{ok}/{len(results)} verificações de interface passaram")
    sys.exit(0 if ok == len(results) else 1)


asyncio.run(main())
