/* Mapa interno do estado: contorno detalhado + marcadores por município, com zoom,
   arrasto, pinça e agrupamento de cidades próximas conforme o nível de zoom. */
(function (root) {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";
  var CLUSTER_PX = 28;   // distância na tela abaixo da qual cidades viram um grupo
  var MAX_ZOOM = 14;

  function el(tag, attrs) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function create(container, geo, handlers) {
    var P = geo.proj;
    function project(lng, lat) {
      var x = lng * Math.PI / 180;
      var y = Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360));
      return [(x - P.minx + P.pad) * P.scale, (P.maxy - y + P.pad) * P.scale];
    }

    container.innerHTML =
      '<div class="sm-stage"><svg class="sm-svg" role="group" aria-label="Mapa do estado com as cidades que têm provas"></svg>' +
      '<div class="sm-zoom" role="group" aria-label="Zoom do mapa">' +
      '<button type="button" data-z="in" aria-label="Aproximar">+</button>' +
      '<button type="button" data-z="out" aria-label="Afastar">−</button>' +
      '<button type="button" data-z="fit" aria-label="Ver o estado inteiro">⤢</button></div>' +
      '<div class="sm-remote" hidden></div>' +
      '<div class="sm-pop" role="dialog" aria-live="polite" hidden></div></div>';
    var stage = container.querySelector(".sm-stage");
    var svg = container.querySelector(".sm-svg");
    var pop = container.querySelector(".sm-pop");
    var remoteBox = container.querySelector(".sm-remote");
    var gCtx = el("g", { class: "sm-ctx" });
    var focus = el("path", { class: "sm-focus" });
    var gMark = el("g", { class: "sm-marks" });
    svg.appendChild(gCtx); svg.appendChild(focus); svg.appendChild(gMark);
    var byUf = {};
    geo.states.forEach(function (s) {
      byUf[s.uf] = s;
      gCtx.appendChild(el("path", { d: s.d, "data-ctx": s.uf, class: "sm-other" }));
    });

    var cur = { uf: null, cities: [], remote: [], sel: null, hi: null };
    var base = null, vb = null;

    function setVB() { svg.setAttribute("viewBox", vb.x + " " + vb.y + " " + vb.w + " " + vb.h); }
    function upp() { // unidades do viewBox por pixel de tela (preserveAspectRatio meet)
      var r = svg.getBoundingClientRect();
      if (!r.width || !r.height) return vb.w / 340;
      return Math.max(vb.w / r.width, vb.h / r.height);
    }

    function fit() {
      var s = byUf[cur.uf];
      var x0 = s.bbox[0], y0 = s.bbox[1], x1 = s.bbox[2], y1 = s.bbox[3];
      var w = x1 - x0, h = y1 - y0, pad = Math.max(w, h) * 0.08 + 4;
      return { x: x0 - pad, y: y0 - pad, w: w + 2 * pad + w * 0.1, h: h + 2 * pad }; // folga à direita para os botões de zoom
    }

    function zoomAt(factor, px, py) {
      var nw = Math.min(base.w, Math.max(base.w / MAX_ZOOM, vb.w / factor));
      var k = nw / vb.w;
      if (px == null) { px = vb.x + vb.w / 2; py = vb.y + vb.h / 2; }
      vb = { x: px - (px - vb.x) * k, y: py - (py - vb.y) * k, w: nw, h: vb.h * k };
      clamp(); setVB(); draw();
    }
    function zoomTo(box) {
      var aspect = base.w / base.h;
      var w = Math.max(box.w, base.w / MAX_ZOOM), h = Math.max(box.h, w / aspect);
      w = Math.max(w, h * aspect);
      vb = { x: box.x + box.w / 2 - w / 2, y: box.y + box.h / 2 - h / 2, w: w, h: h };
      clamp(); setVB(); draw();
    }
    function clamp() {
      var mx = base.w * 0.5, my = base.h * 0.5;
      vb.x = Math.min(Math.max(vb.x, base.x - mx), base.x + base.w + mx - vb.w);
      vb.y = Math.min(Math.max(vb.y, base.y - my), base.y + base.h + my - vb.h);
    }
    function toSvg(cx, cy) {
      var pt = svg.createSVGPoint(); pt.x = cx; pt.y = cy;
      var m = svg.getScreenCTM();
      return m ? pt.matrixTransform(m.inverse()) : { x: vb.x + vb.w / 2, y: vb.y + vb.h / 2 };
    }

    /* Agrupamento guloso em espaço de tela: cidades com mais provas viram âncoras. */
    function clusters() {
      var r = CLUSTER_PX * upp();
      var out = [];
      cur.cities.filter(function (c) { return !c.remote; }).sort(function (a, b) { return b.count - a.count; }).forEach(function (c) {
        var hit = null;
        for (var i = 0; i < out.length; i++) {
          var dx = out[i].x - c.x, dy = out[i].y - c.y;
          if (dx * dx + dy * dy < r * r) { hit = out[i]; break; }
        }
        if (hit && c.key !== cur.sel && hit.members[0].key !== cur.sel) {
          hit.members.push(c); hit.count += c.count;
        } else out.push({ x: c.x, y: c.y, members: [c], count: c.count });
      });
      return out;
    }

    function draw() {
      var u = upp();
      while (gMark.firstChild) gMark.removeChild(gMark.firstChild);
      focus.setAttribute("stroke-width", 1.6 * u);
      gCtx.setAttribute("stroke-width", 1 * u);
      clusters().forEach(function (cl) {
        var single = cl.members.length === 1, c = cl.members[0];
        var rpx = single ? 11 + Math.min(10, 3.2 * Math.sqrt(cl.count)) : 15 + Math.min(10, 2.5 * Math.sqrt(cl.count));
        var sel = single && (c.key === cur.sel), hi = single && (c.key === cur.hi);
        var g = el("g", {
          class: "sm-mark" + (single ? " city" : " cluster") + (sel ? " sel" : "") + (hi ? " hi" : ""),
          transform: "translate(" + cl.x + "," + cl.y + ")", tabindex: "0", role: "button",
          "data-city": single ? c.key : "", "data-count": cl.count,
          "aria-label": single
            ? c.nome + ": " + cl.count + (cl.count === 1 ? " prova" : " provas") + " (localização aproximada, sede do município)"
            : cl.members.length + " cidades próximas, " + cl.count + " provas. Ampliar"
        });
        if (!single) g.appendChild(el("circle", { r: (rpx + 4) * u, class: "halo" }));
        g.appendChild(el("circle", { r: rpx * u, class: "dot" }));
        var t = el("text", { class: "cnt", "font-size": 12.5 * u, "dominant-baseline": "central" });
        t.textContent = cl.count;
        g.appendChild(t);
        if (sel || hi) {
          var lbl = el("text", { class: "name", x: (rpx + 5) * u, "font-size": 14 * u, "dominant-baseline": "central" });
          lbl.textContent = c.nome;
          g.appendChild(lbl);
        }
        var title = el("title", {});
        title.textContent = single ? c.nome + " · " + cl.count + " provas" : cl.members.map(function (m) { return m.nome; }).join(", ");
        g.appendChild(title);
        function act(ev) {
          ev.stopPropagation();
          if (single) { handlers.onCity(c.key); }
          else {
            var xs = cl.members.map(function (m) { return m.x; }), ys = cl.members.map(function (m) { return m.y; });
            var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs), y0 = Math.min.apply(null, ys), y1 = Math.max.apply(null, ys);
            var pad = 40 * u;
            zoomTo({ x: x0 - pad, y: y0 - pad, w: (x1 - x0) / 0.5 + 2 * pad, h: (y1 - y0) / 0.5 + 2 * pad });
          }
        }
        g.addEventListener("click", act);
        g.addEventListener("keydown", function (ev) { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); act(ev); } });
        gMark.appendChild(g);
      });
      gMark.setAttribute("class", "sm-marks" + (cur.sel ? " has-sel" : ""));
      var rem = cur.cities.filter(function (c) { return c.remote; });
      remoteBox.hidden = !rem.length;
      remoteBox.innerHTML = rem.map(function (c) {
        return '<button type="button" class="sm-mark-r' + (c.key === cur.sel || c.key === cur.hi ? " sel" : "") + '" data-city="' + c.key + '" data-count="' + c.count +
          '" aria-label="' + esc(c.nome + ": " + c.count + (c.count === 1 ? " prova" : " provas") + " (ilha fora da escala do mapa)") + '">' +
          '<span class="b">' + c.count + "</span>" + esc(c.nome) + ' <small>fora de escala</small></button>';
      }).join("");
      Array.prototype.forEach.call(remoteBox.querySelectorAll("[data-city]"), function (b) {
        b.addEventListener("click", function () { handlers.onCity(b.dataset.city); });
      });
      placePop();
    }

    /* Resumo da cidade: painel ancorado na parte de baixo do mapa, sem cobrir o marcador. */
    function placePop() {
      var c = cur.sel && cur.cities.find(function (x) { return x.key === cur.sel; });
      pop.hidden = !c;
      if (!c) return;
      pop.style.bottom = (remoteBox.hidden ? 8 : remoteBox.offsetHeight + 16) + "px";
      // garante que o marcador selecionado não fique escondido atrás do painel
      if (!c.remote) {
        var m = svg.getScreenCTM(), sr = stage.getBoundingClientRect();
        if (!m) return;
        var pt = svg.createSVGPoint(); pt.x = c.x; pt.y = c.y;
        var sy = pt.matrixTransform(m).y - sr.top;
        var limit = sr.height - pop.offsetHeight - parseFloat(pop.style.bottom) - 24;
        if (sy > limit && !placePop.busy) {
          placePop.busy = true;
          vb.y += (sy - limit + 20) * upp(); clamp(); setVB(); draw();
          placePop.busy = false;
        }
      }
    }

    function setPop(c) {
      pop.innerHTML = '<button type="button" class="sm-pop-x" aria-label="Fechar resumo">×</button>' +
        "<strong>" + esc(c.nome) + ", " + esc(c.uf) + "</strong>" +
        '<span class="sm-pop-n">' + c.count + (c.count === 1 ? " prova" : " provas") + "</span>" +
        '<span class="sm-pop-note">Localização aproximada: sede do município</span>' +
        '<button type="button" class="primary sm-pop-go">Ver ' + (c.count === 1 ? "a prova" : "as " + c.count + " provas") + "</button>";
      pop.querySelector(".sm-pop-x").addEventListener("click", function () { handlers.onClearCity(); });
      pop.querySelector(".sm-pop-go").addEventListener("click", function () { handlers.onShowEvents(c.key); });
    }

    /* Interações: arrasto, pinça e roda do mouse. */
    var pointers = {}, last = null, pinch = null, moved = false;
    svg.addEventListener("pointerdown", function (ev) {
      pointers[ev.pointerId] = { x: ev.clientX, y: ev.clientY };
      var ids = Object.keys(pointers);
      if (ids.length === 1) { last = { x: ev.clientX, y: ev.clientY }; moved = false; }
      if (ids.length === 2) {
        var a = pointers[ids[0]], b = pointers[ids[1]];
        pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2 };
      }
    });
    svg.addEventListener("pointermove", function (ev) {
      if (!pointers[ev.pointerId]) return;
      pointers[ev.pointerId] = { x: ev.clientX, y: ev.clientY };
      var ids = Object.keys(pointers);
      if (ids.length === 2 && pinch) {
        var a = pointers[ids[0]], b = pointers[ids[1]];
        var d = Math.hypot(a.x - b.x, a.y - b.y);
        if (d > 0 && Math.abs(d / pinch.d - 1) > 0.04) {
          var p = toSvg(pinch.cx, pinch.cy);
          zoomAt(d / pinch.d, p.x, p.y);
          pinch.d = d; moved = true;
        }
        return;
      }
      if (ids.length === 1 && last) {
        var dx = ev.clientX - last.x, dy = ev.clientY - last.y;
        if (!moved && Math.abs(dx) + Math.abs(dy) < 5) return;
        if (!moved) { moved = true; try { svg.setPointerCapture(ev.pointerId); } catch (e) { /* ok */ } }
        var u = upp();
        vb.x -= dx * u; vb.y -= dy * u;
        last = { x: ev.clientX, y: ev.clientY };
        clamp(); setVB(); placePop();
      }
    });
    function up(ev) {
      delete pointers[ev.pointerId];
      if (Object.keys(pointers).length < 2) pinch = null;
      if (!Object.keys(pointers).length) { if (moved) draw(); last = null; }
    }
    svg.addEventListener("pointerup", up);
    svg.addEventListener("pointercancel", up);
    svg.addEventListener("click", function (ev) { if (moved) { ev.stopPropagation(); ev.preventDefault(); } }, true);
    svg.addEventListener("wheel", function (ev) {
      ev.preventDefault();
      var p = toSvg(ev.clientX, ev.clientY);
      zoomAt(ev.deltaY < 0 ? 1.25 : 0.8, p.x, p.y);
    }, { passive: false });
    container.querySelector(".sm-zoom").addEventListener("click", function (ev) {
      var b = ev.target.closest("[data-z]");
      if (!b) return;
      if (b.dataset.z === "in") zoomAt(1.6);
      else if (b.dataset.z === "out") zoomAt(1 / 1.6);
      else { vb = Object.assign({}, base); setVB(); draw(); }
    });
    window.addEventListener("resize", function () { if (cur.uf) draw(); });

    function show(uf, cities, sel, hi) {
      var changedUf = uf !== cur.uf;
      cur.uf = uf;
      cur.cities = cities.map(function (c) {
        var p = project(c.lng, c.lat);
        return Object.assign({}, c, { x: p[0], y: p[1] });
      });
      var prevSel = cur.sel;
      cur.sel = sel || null; cur.hi = hi || null;
      if (changedUf) {
        var s = byUf[uf];
        focus.setAttribute("d", s.dd || s.d);
        Array.prototype.forEach.call(gCtx.childNodes, function (p) {
          p.setAttribute("class", "sm-other" + (p.getAttribute("data-ctx") === uf ? " me" : ""));
        });
        base = fit();
        // Altura da área acompanha o formato do estado (estados "deitados" não deixam faixas vazias).
        var wpx = stage.getBoundingClientRect().width || 360;
        var hpx = Math.round(wpx * base.h / base.w);
        var maxH = Math.round(window.innerHeight * (window.innerWidth < 960 ? 0.6 : 0.72));
        stage.style.height = Math.max(280, Math.min(maxH, hpx)) + "px";
        vb = Object.assign({}, base);
        setVB();
        svg.setAttribute("aria-label", "Mapa de " + s.name + " com " + cur.cities.length + " cidades com provas");
      }
      // Municípios muito distantes do continente (ex.: Fernando de Noronha) ficam num atalho à parte.
      var mx = base.w * 0.1, my = base.h * 0.1;
      cur.cities.forEach(function (c) {
        c.remote = c.x < base.x - mx || c.x > base.x + base.w + mx || c.y < base.y - my || c.y > base.y + base.h + my;
      });
      var target = cur.sel || cur.hi;
      if (target) {
        var c = cur.cities.find(function (x) { return x.key === target; });
        if (c && !c.remote && (c.x < vb.x || c.x > vb.x + vb.w || c.y < vb.y || c.y > vb.y + vb.h)) {
          vb.x = c.x - vb.w / 2; vb.y = c.y - vb.h / 2; clamp(); setVB();
        }
      }
      if (cur.sel) {
        var cs = cur.cities.find(function (x) { return x.key === cur.sel; });
        if (cs) setPop(cs);
      }
      if (cur.sel !== prevSel || changedUf) pop.scrollTop = 0;
      draw();
    }

    return {
      show: show,
      redraw: function () { if (cur.uf) draw(); },
      zoomIn: function () { zoomAt(1.6); },
      markerCount: function () { return gMark.childNodes.length; }
    };
  }

  root.StateMap = { create: create };
})(this);
