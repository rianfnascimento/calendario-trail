/* Mapa vetorial dos estados (SVG gerado por scripts/build_map.py). */
(function (root) {
  "use strict";

  var UF_REGION = {
    AC: "Norte", AP: "Norte", AM: "Norte", PA: "Norte", RO: "Norte", RR: "Norte", TO: "Norte",
    AL: "Nordeste", BA: "Nordeste", CE: "Nordeste", MA: "Nordeste", PB: "Nordeste", PE: "Nordeste",
    PI: "Nordeste", RN: "Nordeste", SE: "Nordeste",
    DF: "Centro-Oeste", GO: "Centro-Oeste", MT: "Centro-Oeste", MS: "Centro-Oeste",
    ES: "Sudeste", MG: "Sudeste", RJ: "Sudeste", SP: "Sudeste",
    PR: "Sul", RS: "Sul", SC: "Sul"
  };
  var BUCKETS = [0, 1, 3, 6, 11, 21]; // limites inferiores das classes c0..c5
  var SVGNS = "http://www.w3.org/2000/svg";

  function bucket(n) {
    var b = 0;
    for (var i = 0; i < BUCKETS.length; i++) if (n >= BUCKETS[i]) b = i;
    return b;
  }

  function el(tag, attrs) {
    var e = document.createElementNS(SVGNS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }

  function create(container, geo, handlers) {
    var svg = el("svg", { viewBox: geo.viewBox, class: "br-map", role: "group",
      "aria-label": "Mapa do Brasil por estado. Selecione um estado para ver as provas." });
    var gStates = el("g", { class: "states" });
    var gLabels = el("g", { class: "labels", "aria-hidden": "true" });
    svg.appendChild(gStates);
    svg.appendChild(gLabels);
    var nodes = {};

    geo.states.forEach(function (s) {
      var p = el("path", { d: s.d, class: "state c0", tabindex: "0", role: "button", "data-uf": s.uf });
      var title = el("title", {});
      p.appendChild(title);
      p.addEventListener("click", function () { handlers.onSelect(s.uf); });
      p.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); handlers.onSelect(s.uf); }
      });
      gStates.appendChild(p);

      var lg = el("g", { class: "label" });
      var moved = s.lx !== s.cx || s.ly !== s.cy;
      if (moved) {
        lg.appendChild(el("line", { x1: s.cx, y1: s.cy, x2: s.lx, y2: s.ly, class: "leader" }));
        lg.appendChild(el("circle", { cx: s.cx, cy: s.cy, r: 2.5, class: "anchor" }));
      }
      var t = el("text", { x: s.lx, y: s.ly, class: moved ? "lbl out" : "lbl", "dominant-baseline": "central" });
      var uf = el("tspan", { class: "uf" });
      uf.textContent = s.uf;
      var n = el("tspan", { class: "n", dx: "4" });
      t.appendChild(uf);
      t.appendChild(n);
      lg.appendChild(t);
      gLabels.appendChild(lg);
      nodes[s.uf] = { path: p, title: title, count: n, name: s.name, label: lg };
    });
    container.appendChild(svg);

    function update(state) {
      Object.keys(nodes).forEach(function (uf) {
        var nd = nodes[uf];
        var c = state.counts[uf] || 0;
        var inRegion = !state.region || UF_REGION[uf] === state.region;
        var cls = "state c" + bucket(c);
        if (!inRegion) cls += " dim";
        if (state.uf === uf) cls += " sel";
        nd.path.setAttribute("class", cls);
        nd.path.setAttribute("aria-pressed", state.uf === uf ? "true" : "false");
        var label = nd.name + ": " + c + (c === 1 ? " prova" : " provas");
        nd.path.setAttribute("aria-label", label);
        nd.title.textContent = label;
        nd.count.textContent = c ? String(c) : "";
        nd.label.setAttribute("class", "label" + (inRegion ? "" : " dim") + (state.uf === uf ? " sel" : "") + (c ? "" : " zero"));
      });
    }

    return { update: update, svg: svg };
  }

  root.TrailMap = { create: create, UF_REGION: UF_REGION, BUCKETS: BUCKETS, bucket: bucket };
})(this);
