#!/usr/bin/env python3
"""
Converte data/geo/brazil-states.geojson (limites estaduais, fonte: projeto
click_that_hood / Code for Germany, a partir de dados do IBGE) em caminhos SVG
simplificados para o mapa interativo.

Saída: web/data/br-states.js  ->  window.BR_STATES = {viewBox, states:[{uf,name,d,cx,cy,lx,ly}]}
"""
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "geo", "brazil-states.geojson")
OUT = os.path.join(ROOT, "web", "data", "br-states.js")

WIDTH = 1000.0
TOL = 0.02  # graus — tolerância do Douglas-Peucker (mapa nacional)
TOL_DETAIL = 0.004  # graus — contorno mais fino para o mapa interno do estado
MIN_RING_AREA = 0.0008  # graus² — descarta ilhotas invisíveis no mapa

# Estados pequenos têm o rótulo deslocado para o mar, ligado por uma linha.
LABEL_POS = {  # posição absoluta (x, y) no viewBox; os demais ficam no centroide
    "RN": (852, 215), "PB": (852, 255), "PE": (852, 295), "AL": (852, 335), "SE": (852, 375),
    "ES": (770, 520), "RJ": (705, 625), "DF": (560, 412), "GO": (488, 470),
}


def merc(lng, lat):
    x = math.radians(lng)
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


def dp(points, tol):
    if len(points) < 3:
        return points
    (x1, y1), (x2, y2) = points[0], points[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = math.hypot(dx, dy) or 1e-12
    best, idx = 0, 0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        d = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / norm
        if d > best:
            best, idx = d, i
    if best > tol:
        return dp(points[: idx + 1], tol)[:-1] + dp(points[idx:], tol)
    return [points[0], points[-1]]


def ring_area(r):
    a = 0
    for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]):
        a += x1 * y2 - x2 * y1
    return a / 2


def centroid(r):
    a = ring_area(r) or 1e-12
    cx = cy = 0
    for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]):
        f = x1 * y2 - x2 * y1
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    return cx / (6 * a), cy / (6 * a)


def main():
    gj = json.load(open(SRC, encoding="utf-8"))
    states = []
    for f in gj["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        rings, rings_d = [], []
        for poly in polys:
            for ring in poly:
                pts = [tuple(p[:2]) for p in ring]
                if abs(ring_area(pts)) < MIN_RING_AREA:
                    continue
                if pts[0] == pts[-1]:
                    pts = pts[:-1]
                # Anel fechado: simplifica as duas metades separadamente.
                h = len(pts) // 2
                s = dp(pts[: h + 1], TOL)[:-1] + dp(pts[h:] + [pts[0]], TOL)[:-1]
                sd = dp(pts[: h + 1], TOL_DETAIL)[:-1] + dp(pts[h:] + [pts[0]], TOL_DETAIL)[:-1]
                if len(s) >= 4:
                    rings.append(s)
                if len(sd) >= 4:
                    rings_d.append(sd)
        states.append({"uf": f["properties"]["sigla"], "name": f["properties"]["name"], "rings": rings, "rings_d": rings_d})

    allpts = [merc(*p) for s in states for r in s["rings"] for p in r]
    minx, maxx = min(p[0] for p in allpts), max(p[0] for p in allpts)
    miny, maxy = min(p[1] for p in allpts), max(p[1] for p in allpts)
    pad = 0.012
    scale = WIDTH / (maxx - minx + 2 * pad) * 0.86  # deixa margem à direita para rótulos
    height = (maxy - miny + 2 * pad) * scale

    def proj(lng, lat):
        x, y = merc(lng, lat)
        return (x - minx + pad) * scale, (maxy - y + pad) * scale

    out = []
    for s in states:
        parts, biggest, big_area = [], None, 0
        for r in s["rings"]:
            pr = [proj(*p) for p in r]
            area = abs(ring_area(pr))
            if area > big_area:
                big_area, biggest = area, pr
            parts.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pr) + "Z")
        cx, cy = centroid(biggest)
        bx = [p[0] for p in biggest]
        by = [p[1] for p in biggest]
        detail = "".join("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in (proj(*p) for p in r)) + "Z" for r in s["rings_d"])
        lx, ly = LABEL_POS.get(s["uf"], (cx, cy))
        out.append({"uf": s["uf"], "name": s["name"], "d": "".join(parts),
                    "cx": round(cx, 1), "cy": round(cy, 1),
                    "lx": round(lx, 1), "ly": round(ly, 1), "dd": detail,
                    "bbox": [round(min(bx), 1), round(min(by), 1), round(max(bx), 1), round(max(by), 1)]})
    out.sort(key=lambda s: s["uf"])
    data = {"viewBox": f"0 0 {WIDTH:.0f} {height:.0f}", "states": out,
            # Parâmetros da projeção (Mercator) para posicionar municípios no mesmo sistema de coordenadas.
            "proj": {"minx": minx, "maxy": maxy, "pad": pad, "scale": scale},
            "fonte": "Limites estaduais: click_that_hood (Code for Germany), derivado de dados do IBGE"}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.BR_STATES = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print(f"{len(out)} estados, {os.path.getsize(OUT)/1024:.0f} KB, viewBox {data['viewBox']}")


if __name__ == "__main__":
    main()
