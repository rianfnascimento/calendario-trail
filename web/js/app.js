/* Interface: estado da tela, renderização das três visões e do detalhe. */
(function () {
  "use strict";
  var F = window.Filters;
  var $ = function (id) { return document.getElementById(id); };

  var MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
    "setembro", "outubro", "novembro", "dezembro"];
  var MON = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  var WD = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
  var WDL = ["domingo", "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado"];
  var STATUS_LABEL = { agendado: "Agendada", data_alterada: "Nova data", adiado: "Adiada", cancelado: "Cancelada" };
  var CONF_LABEL = { alta: "Alta", media: "Média", baixa: "Baixa" };
  var VIEWS = { map: "view-map", cal: "view-cal", next: "view-next" };

  var DATA, EVENTS, GEO, UF_NAME = {}, today, state, mapApi, stateMap, lastCities = [];
  var isMobile = function () { return window.matchMedia("(max-width: 959px)").matches; };

  function fail(msg) {
    var e = $("error");
    e.hidden = false;
    e.innerHTML = "<strong>Não foi possível carregar o calendário.</strong> " + esc(msg) +
      " Recarregue a página; se o erro continuar, rode novamente <code>python3 scripts/build_db.py</code>.";
    ["view-map", "view-cal", "view-next"].forEach(function (v) { $(v).hidden = true; });
    $("sub").textContent = "Dados indisponíveis";
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function parts(iso) { var p = iso.split("-"); return { y: +p[0], m: +p[1], d: +p[2] }; }
  function weekday(iso) { var p = parts(iso); return new Date(Date.UTC(p.y, p.m - 1, p.d)).getUTCDay(); }
  function fmtLong(iso) { var p = parts(iso); return WDL[weekday(iso)] + ", " + p.d + " de " + MONTHS[p.m - 1] + " de " + p.y; }
  function fmtShort(iso) { var p = parts(iso); return p.d + " " + MON[p.m - 1] + " " + p.y; }
  function fmtKm(k) { return (Math.round(k * 10) / 10).toString().replace(".", ",") + " km"; }
  function plural(n, s, p) { return n + " " + (n === 1 ? s : p); }
  function store(k, v) { try { localStorage.setItem("trailbr." + k, v); } catch (e) { /* armazenamento indisponível */ } }
  function load(k) { try { return localStorage.getItem("trailbr." + k); } catch (e) { return null; } }

  function localToday() {
    var d = new Date();
    return F.iso(d.getFullYear(), d.getMonth() + 1, d.getDate());
  }

  /* ---------- inicialização ---------- */
  function init() {
    DATA = window.TRAIL_DATA; GEO = window.BR_STATES;
    if (!DATA || !Array.isArray(DATA.eventos) || !DATA.eventos.length) return fail("A base de eventos está vazia ou ausente.");
    if (!GEO || !GEO.states || GEO.states.length !== 27) return fail("O mapa dos estados não foi carregado.");
    if (!F || !window.TrailMap) return fail("Scripts da aplicação ausentes.");
    EVENTS = DATA.eventos;
    GEO.states.forEach(function (s) { UF_NAME[s.uf] = s.name; });
    today = localToday();
    state = { view: "map", f: F.defaults(today), cal: null, calDay: null, sub: "map", citySort: "count", hl: null };

    var m = DATA.meta;
    $("sub").textContent = plural(m.eventos_unicos, "prova", "provas") + " de trail running · " +
      fmtShort(m.periodo[0]) + " a " + fmtShort(m.periodo[1]) + " · verificado em " + fmtShort(m.coletado_em);
    $("foot-date").textContent = "verificados em " + fmtShort(m.coletado_em);

    setupFormLinks();
    fillSelects();
    mapApi = window.TrailMap.create($("map"), GEO, { onSelect: selectUf });
    if (!window.StateMap || !GEO.proj) return fail("O mapa interno dos estados não foi carregado.");
    stateMap = window.StateMap.create($("statemap"), GEO, {
      onCity: function (key) { selectCity(key, "map"); },
      onClearCity: clearCity,
      onShowEvents: function () { setSub("events"); }
    });
    bind();
    readHash();
    var cs = load("citySort");
    if (cs === "alpha" || cs === "count") state.citySort = cs;
    var v = load("view");
    if (!location.hash && v && VIEWS[v]) state.view = v;
    render();
  }

  /* Link do formulário de cadastro (web/config.js). Sem link configurado, nada aparece. */
  function formUrl() {
    var u = (window.TRAIL_CONFIG && window.TRAIL_CONFIG.formUrl || "").trim();
    return /^https:\/\/\S+$/.test(u) ? u : "";
  }
  function setupFormLinks() {
    var u = formUrl();
    document.querySelectorAll("[data-form-link]").forEach(function (a) { a.href = u || "#"; a.hidden = !u; });
    document.querySelectorAll("[data-form-block]").forEach(function (b) { b.hidden = !u; });
  }
  function formLinkHtml(text) {
    var u = formUrl();
    return u ? '<a class="link" href="' + esc(u) + '" target="_blank" rel="noopener">' + esc(text) + "</a>" : "";
  }

  function fillSelects() {
    var reg = $("f-region");
    F.REGIONS.concat(["Exterior"]).forEach(function (r) { reg.add(new Option(r === "Exterior" ? "Exterior" : r, r)); });
    var ufs = GEO.states.map(function (s) { return s; }).sort(function (a, b) { return a.name.localeCompare(b.name, "pt-BR"); });
    ufs.forEach(function (s) {
      $("f-uf").add(new Option(s.name + " (" + s.uf + ")", s.uf));
    });
    var years = {};
    EVENTS.forEach(function (e) { years[e.ano] = 1; });
    Object.keys(years).sort().forEach(function (y) { $("f-year").add(new Option(y, y)); });
    MONTHS.forEach(function (n, i) { $("f-month").add(new Option(n[0].toUpperCase() + n.slice(1), String(i + 1))); });
    var withKm = EVENTS.filter(function (e) { return e.distancias_km.length; }).length;
    var withEl = EVENTS.filter(function (e) { return e.altimetria_m; }).length;
    $("km-note").textContent = "Distância publicada em " + withKm + " de " + EVENTS.length +
      " provas. Com este filtro ativo, provas sem distância informada ficam de fora.";
    $("elev-note").textContent = "(" + withEl + " de " + EVENTS.length + " provas têm altimetria publicada)";
  }

  /* ---------- eventos de interface ---------- */
  function bind() {
    document.querySelectorAll(".tabs button").forEach(function (b) {
      b.addEventListener("click", function () { setView(b.dataset.view); });
      b.addEventListener("keydown", function (ev) {
        var order = ["map", "cal", "next"], i = order.indexOf(b.dataset.view);
        if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") {
          var n = order[(i + (ev.key === "ArrowRight" ? 1 : 2)) % 3];
          setView(n); document.querySelector('.tabs [data-view="' + n + '"]').focus();
        }
      });
    });
    var qTimer;
    $("q").addEventListener("input", function () {
      clearTimeout(qTimer);
      qTimer = setTimeout(function () { state.f.q = $("q").value.trim(); render(); }, 120);
    });
    $("btn-filters").addEventListener("click", function () { togglePanel(); });
    $("btn-close").addEventListener("click", function () { togglePanel(false); });
    $("filters").addEventListener("submit", function (ev) { ev.preventDefault(); togglePanel(false); });
    $("btn-clear").addEventListener("click", clearAll);
    $("btn-clear-inline").addEventListener("click", clearAll);

    $("f-region").addEventListener("change", function () { setRegion(this.value || null); });
    $("f-uf").addEventListener("change", function () { selectUf(this.value || null, true); });
    $("pick-uf").addEventListener("change", function () { selectUf(this.value || null, true); });
    $("f-year").addEventListener("change", function () { state.f.year = this.value || null; state.cal = null; render(); });
    $("f-month").addEventListener("change", function () { state.f.month = this.value || null; state.cal = null; render(); });
    $("f-from").addEventListener("change", function () { state.f.from = this.value || null; state.cal = null; render(); });
    $("f-to").addEventListener("change", function () { state.f.to = this.value || null; render(); });
    ["f-kmmin", "f-kmmax"].forEach(function (id) {
      $(id).addEventListener("input", function () {
        var v = $(id).value;
        state.f[id === "f-kmmin" ? "kmMin" : "kmMax"] = v === "" ? null : Math.max(0, Number(v));
        render();
      });
    });
    $("f-elev").addEventListener("change", function () { state.f.withElevation = this.checked; render(); });
    $("f-abroad").addEventListener("change", function () { state.f.includeAbroad = this.checked; render(); });
    $("f-past").addEventListener("change", function () { state.f.includePast = this.checked; render(); });
    F.STATUSES.forEach(function (s) {
      $("st-" + s).addEventListener("change", function () {
        state.f.statuses = F.STATUSES.filter(function (x) { return $("st-" + x).checked; });
        render();
      });
    });
    document.querySelectorAll(".regions button").forEach(function (b) {
      b.addEventListener("click", function () { setRegion(b.dataset.region || null); });
    });
    $("btn-national").addEventListener("click", goNational);
    document.querySelectorAll("#subtabs [data-sub]").forEach(function (b) {
      b.addEventListener("click", function () { setSub(b.dataset.sub); });
    });
    document.querySelectorAll(".seg [data-sort]").forEach(function (b) {
      b.addEventListener("click", function () { state.citySort = b.dataset.sort; store("citySort", b.dataset.sort); render(); });
    });
    $("f-city").addEventListener("change", function () { if (this.value) selectCity(this.value, "panel"); else clearCity(); });
    $("see-events").addEventListener("click", function () { setSub("events"); });
    $("cal-prev").addEventListener("click", function () { moveMonth(-1); });
    $("cal-next").addEventListener("click", function () { moveMonth(1); });
    $("cal-allmonth").addEventListener("click", function () { state.calDay = null; render(); });
    $("d-close").addEventListener("click", function () { $("detail").close(); });
    $("detail").addEventListener("click", function (ev) { if (ev.target === $("detail")) $("detail").close(); });
    document.addEventListener("click", function (ev) {
      var c = ev.target.closest("[data-event]");
      if (c) {
        var evt = EVENTS.find(function (x) { return x.id === c.dataset.event; });
        state.hl = evt && evt.municipio ? evt.municipio.ibge : null;
        if (state.f.uf && evt && evt.uf === state.f.uf) drawStateMap();
        openDetail(c.dataset.event, c);
      }
      var clr = ev.target.closest("[data-clear]");
      if (clr) clearAll();
      var nat = ev.target.closest("[data-national]");
      if (nat) goNational();
      var pick = ev.target.closest("[data-city-pick]");
      if (pick) selectCity(pick.dataset.cityPick, "list");
      var cc = ev.target.closest("[data-clear-city]");
      if (cc) clearCity();
      var cr = ev.target.closest("[data-crumb]");
      if (cr) crumb(cr.dataset.crumb);
      var onmap = ev.target.closest("[data-show-on-map]");
      if (onmap) {
        var key = onmap.dataset.showOnMap;
        var me = EVENTS.find(function (x) { return x.municipio && x.municipio.ibge === key; });
        $("detail").close();
        if (me) {
          state.f.uf = me.municipio.uf; state.f.region = window.TrailMap.UF_REGION[me.municipio.uf];
          state.sub = "map";
          selectCity(key, "map");
          scrollToHead();
        }
      }
    });
    window.addEventListener("hashchange", function () { readHash(); render(); });
  }

  function togglePanel(open) {
    var p = $("filters");
    var willOpen = open == null ? p.hidden : open;
    p.hidden = !willOpen;
    $("btn-filters").setAttribute("aria-expanded", String(willOpen));
    if (willOpen) $("f-region").focus();
  }

  function clearAll() {
    var keepView = state.view;
    state.f = F.defaults(today);
    state.cal = null; state.calDay = null;
    state.view = keepView;
    $("q").value = "";
    render();
  }

  function setView(v) {
    state.view = v;
    store("view", v);
    if (v === "map") syncHash();
    else { try { history.replaceState(null, "", "#" + (v === "cal" ? "calendario" : "proximas")); } catch (e) { /* sem histórico */ } }
    render();
  }

  function setRegion(r) {
    state.f.region = r;
    if (r === "Exterior") state.f.includeAbroad = true;
    if (state.f.uf && (!r || window.TrailMap.UF_REGION[state.f.uf] !== r)) state.f.uf = null;
    render();
  }

  function selectUf(uf, fromList) {
    if (!fromList && uf && state.f.uf === uf) uf = null; // segundo toque devolve à região
    state.f.uf = uf;
    state.f.city = null; state.hl = null;
    if (uf) state.f.region = window.TrailMap.UF_REGION[uf];
    state.sub = isMobile() ? "map" : "events";
    if (state.view !== "map") state.view = "map";
    syncHash();
    render();
    if (uf && isMobile()) scrollToHead();
  }

  function selectCity(key, from) {
    if (!state.f.uf) return;
    state.f.city = key;
    state.hl = null;
    if (from === "list" || from === "panel") state.sub = "events";
    if (state.view !== "map" && from !== "panel") state.view = "map";
    syncHash();
    render();
    if (from === "list" && isMobile()) scrollToHead();
  }

  function clearCity() {
    state.f.city = null; state.hl = null;
    syncHash();
    render();
  }

  function setSub(sub) {
    state.sub = sub;
    render();
    if (isMobile()) scrollToHead();
  }

  function goNational() {
    state.f.uf = null; state.f.region = null; state.f.city = null; state.hl = null;
    syncHash();
    render();
  }

  function crumb(level) {
    if (level === "br") return goNational();
    if (level === "region") { state.f.uf = null; state.f.city = null; state.hl = null; syncHash(); return render(); }
    if (level === "uf") { state.sub = isMobile() ? "map" : state.sub; return clearCity(); }
  }

  function scrollToHead() {
    var head = document.querySelector("#view-map .geo-head");
    if (head && head.scrollIntoView) head.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function syncHash() {
    var h = state.f.uf ? state.f.uf.toLowerCase() + (state.f.city ? "-" + state.f.city : "") : "";
    try { history.replaceState(null, "", h ? "#" + h : location.pathname + location.search); } catch (e) { /* sem histórico */ }
  }

  function readHash() {
    var raw = (location.hash || "").replace("#", "");
    var h = raw.split("-")[0].toUpperCase();
    if (UF_NAME[h]) {
      state.f.uf = h; state.f.region = window.TrailMap.UF_REGION[h]; state.view = "map";
      var city = raw.slice(3);
      state.f.city = city && (city === F.NO_CITY || EVENTS.some(function (e) { return e.municipio && e.municipio.ibge === city && e.uf === h; })) ? city : null;
      state.sub = isMobile() ? "map" : "events";
    }
    else if (h === "CALENDARIO") state.view = "cal";
    else if (h === "PROXIMAS") state.view = "next";
  }

  /* ---------- renderização ---------- */
  function render() {
    var f = state.f;
    var list = F.apply(EVENTS, f);
    var nonGeo = F.apply(EVENTS, f, { ignoreGeo: true });

    // abas
    Object.keys(VIEWS).forEach(function (k) {
      $(VIEWS[k]).hidden = k !== state.view;
      $("tab-" + k).setAttribute("aria-selected", String(k === state.view));
      $("tab-" + k).tabIndex = k === state.view ? 0 : -1;
    });

    // controles do painel
    $("f-region").value = f.region || "";
    $("f-uf").value = f.uf || "";
    fillCitySelect();
    $("pick-uf").value = f.uf || "";
    $("f-year").value = f.year || "";
    $("f-month").value = f.month || "";
    $("f-from").value = f.from || "";
    $("f-to").value = f.to || "";
    $("f-kmmin").value = f.kmMin == null ? "" : f.kmMin;
    $("f-kmmax").value = f.kmMax == null ? "" : f.kmMax;
    $("f-elev").checked = f.withElevation;
    $("f-abroad").checked = f.includeAbroad;
    $("f-past").checked = f.includePast;
    F.STATUSES.forEach(function (s) { $("st-" + s).checked = f.statuses.indexOf(s) !== -1; });

    var n = F.activeCount(f) + (f.region ? 1 : 0) + (f.uf ? 1 : 0) + (f.city ? 1 : 0);
    var badge = $("filter-count");
    badge.hidden = !n; badge.textContent = n;
    $("btn-clear-inline").hidden = !n;
    $("close-count").textContent = list.length;
    var where = f.city ? " em " + cityName(f.city) + ", " + f.uf : f.uf ? " em " + UF_NAME[f.uf] : f.region ? (f.region === "Exterior" ? " no exterior" : " na região " + f.region) : "";
    $("result-count").innerHTML = "<strong>" + list.length + "</strong> " + (list.length === 1 ? "prova encontrada" : "provas encontradas") + esc(where);

    renderMap(list, nonGeo);
    if (state.view === "cal") renderCal(list);
    if (state.view === "next") renderNext(list);
  }

  function renderMap(list, nonGeo) {
    var f = state.f;
    var counts = F.countBy(nonGeo, "uf");
    mapApi.update({ counts: counts, uf: f.uf, region: f.region });
    var rc = F.countBy(nonGeo, "regiao");
    document.querySelectorAll(".regions button").forEach(function (b) {
      var r = b.dataset.region;
      var c = r ? (rc[r] || 0) : nonGeo.filter(function (e) { return !e.internacional; }).length;
      b.setAttribute("aria-pressed", String((f.region || "") === r));
      b.innerHTML = esc(r || "Brasil") + '<span class="rc">' + c + "</span>";
    });
    // lista acessível de estados com contagem
    var pick = $("pick-uf");
    for (var i = 1; i < pick.options.length; i++) { /* reaproveita */ }
    if (pick.options.length === 1) {
      GEO.states.slice().sort(function (a, b) { return a.name.localeCompare(b.name, "pt-BR"); })
        .forEach(function (s) { pick.add(new Option(s.name, s.uf)); });
    }
    for (var j = 1; j < pick.options.length; j++) {
      var o = pick.options[j];
      o.textContent = UF_NAME[o.value] + " · " + (counts[o.value] || 0);
    }
    pick.value = f.uf || "";

    var section = $("view-map");
    var level = f.uf ? "state" : "br";
    section.setAttribute("data-level", level);
    section.setAttribute("data-sub", state.sub);
    $("map").hidden = level === "state";
    $("statemap").hidden = level !== "state";
    document.querySelector(".regions").hidden = level === "state";
    document.querySelector(".br-legend").hidden = level === "state";
    document.querySelector(".st-legend").hidden = level !== "state";
    $("subtabs").hidden = level !== "state";
    renderCrumbs();

    $("sel-eyebrow").textContent = f.city ? (UF_NAME[f.uf] + " · cidade") : f.uf ? "Região " + window.TrailMap.UF_REGION[f.uf] + " · " + f.uf : f.region ? (f.region === "Exterior" ? "Fora do Brasil" : "Região") : "Brasil";
    $("sel-title").textContent = f.city ? cityName(f.city) : f.uf ? UF_NAME[f.uf] : f.region ? f.region : "Todas as provas";
    $("btn-national").hidden = !(f.uf || f.region);
    var noUf = list.filter(function (e) { return !e.uf && !e.internacional; }).length;
    var note = $("sel-note");
    note.hidden = true;
    if (!f.uf && !f.region && noUf) {
      note.hidden = false;
      note.textContent = plural(noUf, "prova", "provas") + " sem estado definido pela fonte " + (noUf === 1 ? "aparece" : "aparecem") + " só nesta visão nacional.";
    }

    if (level === "state") renderStateLevel(list);
    fillCards($("list-map"), list, emptyMap());
  }

  function cityName(key) {
    if (key === F.NO_CITY) return "Sem localização no mapa";
    var e = EVENTS.find(function (x) { return x.municipio && x.municipio.ibge === key; });
    return e ? e.municipio.nome : key;
  }

  function fillCitySelect() {
    var sel = $("f-city"), f = state.f;
    sel.disabled = !f.uf;
    var opts = '<option value="">' + (f.uf ? "Todas" : "Escolha um estado") + "</option>";
    if (f.uf) {
      var c = F.cities(EVENTS.filter(function (e) { return e.uf === f.uf; }));
      F.sortCities(c.list, "alpha").forEach(function (x) { opts += '<option value="' + x.key + '">' + esc(x.nome) + "</option>"; });
      if (c.unlocated.length) opts += '<option value="' + F.NO_CITY + '">Sem localização no mapa</option>';
    }
    if (sel._opts !== opts) { sel.innerHTML = opts; sel._opts = opts; }
    sel.value = f.city || "";
  }

  function renderCrumbs() {
    var f = state.f, h = '<button type="button" data-crumb="br"' + (!f.region && !f.uf ? ' aria-current="page"' : "") + ">Brasil</button>";
    if (f.region && f.region !== "Exterior") h += '<span aria-hidden="true">›</span><button type="button" data-crumb="region"' + (!f.uf ? ' aria-current="page"' : "") + ">" + esc(f.region) + "</button>";
    if (f.uf) h += '<span aria-hidden="true">›</span><button type="button" data-crumb="uf"' + (!f.city ? ' aria-current="page"' : "") + ">" + esc(UF_NAME[f.uf]) + "</button>";
    if (f.city) h += '<span aria-hidden="true">›</span><span aria-current="page">' + esc(cityName(f.city)) + "</span>";
    $("crumbs").innerHTML = h;
  }

  /* Nível 2: cidades do estado (mesmos filtros, exceto a própria cidade). */
  function renderStateLevel(list) {
    var f = state.f;
    var pool = F.apply(EVENTS, f, { ignoreCity: true });
    var grouped = F.cities(pool);
    lastCities = grouped.list;
    drawStateMap();

    $("n-cities").textContent = grouped.list.length;
    $("n-events").textContent = list.length;
    document.querySelectorAll("#subtabs [data-sub]").forEach(function (b) {
      var on = b.dataset.sub === state.sub || (!isMobile() && state.sub === "map" && b.dataset.sub === "events");
      b.setAttribute("aria-selected", String(on));
    });
    document.querySelectorAll(".seg [data-sort]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.sort === state.citySort)); });
    var see = $("see-events");
    see.hidden = false;
    see.textContent = list.length ? "Ver " + plural(list.length, "prova", "provas") + (f.city ? " em " + cityName(f.city) : "") + " ›" : "Nenhuma prova com estes filtros";

    var rows = F.sortCities(grouped.list, state.citySort).map(function (c) {
      var on = f.city === c.key;
      return '<li><button type="button" class="city-row' + (on ? " sel" : "") + '" data-city-pick="' + c.key + '" aria-pressed="' + on + '">' +
        '<span class="cn">' + esc(c.nome) + ", " + c.uf + '</span><span class="cc">' + plural(c.count, "prova", "provas") + "</span></button></li>";
    });
    if (grouped.unlocated.length) {
      var on2 = f.city === F.NO_CITY;
      rows.push('<li><button type="button" class="city-row nomap' + (on2 ? " sel" : "") + '" data-city-pick="' + F.NO_CITY + '" aria-pressed="' + on2 + '">' +
        '<span class="cn">Sem localização no mapa</span><span class="cc">' + plural(grouped.unlocated.length, "prova", "provas") + "</span></button></li>");
    }
    $("city-list").innerHTML = rows.length ? rows.join("") : '<li><div class="empty"><strong>Nenhuma cidade com provas para estes filtros.</strong></div></li>';

    var chip = $("city-chip");
    chip.hidden = !f.city;
    if (f.city) {
      chip.innerHTML = "<span><strong>" + esc(cityName(f.city)) + "</strong>" + (f.city === F.NO_CITY ? "" : ", " + f.uf) + " · " + plural(list.length, "prova", "provas") +
        '</span><button type="button" class="link" data-clear-city>Todas as cidades de ' + esc(f.uf) + "</button>";
    }
    var unl = grouped.unlocated.length && f.city !== F.NO_CITY && !f.city;
    if (unl) {
      var note = $("sel-note");
      note.hidden = false;
      note.textContent = plural(grouped.unlocated.length, "prova", "provas") + " deste estado " + (grouped.unlocated.length === 1 ? "não tem" : "não têm") +
        " cidade identificada e " + (grouped.unlocated.length === 1 ? "aparece" : "aparecem") + " só na lista, sem marcador no mapa.";
    }
  }

  function drawStateMap() {
    if (!state.f.uf) return;
    var sel = state.f.city && state.f.city !== F.NO_CITY ? state.f.city : null;
    stateMap.show(state.f.uf, lastCities, sel, state.hl);
  }

  function emptyMap() {
    var f = state.f;
    var place = f.city ? cityName(f.city) : f.uf ? UF_NAME[f.uf] : f.region ? (f.region === "Exterior" ? "o exterior" : "a região " + f.region) : "o Brasil";
    var any = F.activeCount(f) > 0;
    return '<div class="empty"><strong>Nenhuma prova para ' + esc(place) + (any ? " com esses filtros." : " no calendário da fonte.") + "</strong>" +
      (any ? '<button type="button" class="primary" data-clear>Limpar filtros</button>' : "") +
      (f.city ? '<button type="button" class="link" data-clear-city>Ver todas as cidades de ' + esc(f.uf) + "</button>" : "") +
      (f.uf || f.region ? '<button type="button" class="link" data-national>Ver o Brasil inteiro</button>' : "") +
      formLinkHtml("Conhece uma prova aqui? Cadastre para avaliação") + "</div>";
  }

  function fillCards(ol, list, emptyHtml) {
    if (!list.length) { ol.innerHTML = "<li>" + emptyHtml + "</li>"; return; }
    ol.innerHTML = list.map(function (e) { return "<li>" + card(e) + "</li>"; }).join("");
  }

  function card(e) {
    var s = parts(e.data_inicio), multi = e.data_fim !== e.data_inicio;
    var en = parts(e.data_fim);
    var dayTxt = s.d;
    var until = multi ? "até " + en.d + (s.m === en.m ? "" : "/" + MON[en.m - 1]) : WD[weekday(e.data_inicio)];
    var place = e.internacional ? [e.cidade || e.local, e.pais].filter(Boolean).join(" · ")
      : [(e.local && e.cidade ? e.local + ", " + e.cidade : e.cidade || e.local || "Local a divulgar"), e.uf || "UF não informada"].join(" · ");
    var chips = e.distancias_km.map(function (k) { return '<span class="chip">' + fmtKm(k) + "</span>"; }).join("");
    if (e.altimetria_m) chips += '<span class="chip">D+ ' + e.altimetria_m + " m</span>";
    var pill = '<span class="pill ' + e.status + '">' + STATUS_LABEL[e.status] + "</span>";
    if (e.novo) pill = '<span class="pill nova">Nova</span> ' + pill;
    if (!e.cidade) pill += ' <span class="pill local">local a divulgar</span>';
    else if (!e.internacional && e.mapa && e.mapa.tipo === "indisponivel") pill += ' <span class="pill local">fora do mapa</span>';
    return '<button type="button" class="card ' + e.status + '" data-event="' + e.id + '" aria-label="' +
      esc(e.nome + ", " + fmtLong(e.data_inicio) + ", " + place + ", " + STATUS_LABEL[e.status]) + '">' +
      '<span class="date"><span class="d">' + dayTxt + '</span><span class="m">' + MON[s.m - 1] +
      (s.y !== parts(today).y ? " " + String(s.y).slice(2) : "") + '</span><span class="w">' + until + "</span></span>" +
      '<span class="c-main"><span class="c-name">' + esc(e.nome) + '</span><span class="c-place">' + esc(place) + "</span>" +
      '<span class="chips">' + pill + "</span>" +
      (chips ? '<span class="chips">' + chips + "</span>" : "") + "</span></button>";
  }

  /* ---------- calendário ---------- */
  function initialMonth(list) {
    var f = state.f;
    if (f.year && f.month) return { year: +f.year, month: +f.month };
    if (f.month) {
      var hit = list.find(function (e) { return e.mes === +f.month; });
      if (hit) return { year: hit.ano, month: hit.mes };
    }
    if (list.length) { var p = parts(list[0].data_inicio); return { year: p.y, month: p.m }; }
    var t = parts(today);
    return { year: f.year ? +f.year : t.y, month: t.m };
  }

  function moveMonth(d) {
    state.cal = F.shiftMonth(state.cal.year, state.cal.month, d);
    state.calDay = null;
    render();
  }

  function renderCal(list) {
    if (!state.cal) state.cal = initialMonth(list);
    var y = state.cal.year, m = state.cal.month;
    $("cal-title").textContent = MONTHS[m - 1] + " " + y;
    var first = list.length ? parts(list[0].data_inicio) : null;
    var last = list.length ? parts(list[list.length - 1].data_fim) : null;
    $("cal-prev").disabled = !first || (y * 12 + m) <= (first.y * 12 + first.m);
    $("cal-next").disabled = !last || (y * 12 + m) >= (last.y * 12 + last.m);

    var weeks = F.monthMatrix(y, m);
    var body = "";
    weeks.forEach(function (w) {
      body += "<tr>" + w.map(function (iso) {
        if (!iso) return "<td></td>";
        var evs = F.onDay(list, iso);
        var cls = "day" + (evs.length ? " has" : "") + (evs.length >= 4 ? " hi" : "") + (iso === today ? " today" : "") + (state.calDay === iso ? " sel" : "");
        var d = parts(iso).d;
        if (!evs.length) return '<td><span class="' + cls + '" aria-hidden="false">' + d + "</span></td>";
        return '<td><button type="button" class="' + cls + '" data-day="' + iso + '" aria-pressed="' + (state.calDay === iso) +
          '" aria-label="' + esc(fmtLong(iso) + ": " + plural(evs.length, "prova", "provas")) + '">' + d + '<span class="cnt">' + evs.length + "</span></button></td>";
      }).join("") + "</tr>";
    });
    $("cal-body").innerHTML = body;
    $("cal-body").querySelectorAll("[data-day]").forEach(function (b) {
      b.addEventListener("click", function () {
        state.calDay = state.calDay === b.dataset.day ? null : b.dataset.day;
        render();
        if (state.calDay && window.matchMedia("(max-width: 959px)").matches) {
          var h = document.querySelector("#view-cal .list-col");
          if (h && h.scrollIntoView) h.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    });

    var monthStart = F.iso(y, m, 1), monthEnd = F.iso(y, m, new Date(Date.UTC(y, m, 0)).getUTCDate());
    var shown;
    if (state.calDay) {
      shown = F.onDay(list, state.calDay);
      $("cal-eyebrow").textContent = WDL[weekday(state.calDay)];
      $("cal-list-title").textContent = parts(state.calDay).d + " de " + MONTHS[m - 1];
    } else {
      shown = list.filter(function (e) { return e.data_inicio <= monthEnd && e.data_fim >= monthStart; });
      $("cal-eyebrow").textContent = "Mês inteiro · " + plural(shown.length, "prova", "provas");
      $("cal-list-title").textContent = MONTHS[m - 1] + " de " + y;
    }
    $("cal-allmonth").hidden = !state.calDay;
    fillCards($("list-cal"), shown, '<div class="empty"><strong>Nenhuma prova neste mês com os filtros atuais.</strong>' +
      (list.length ? '<span>Use as setas para navegar até um mês com provas.</span>' : '<button type="button" class="primary" data-clear>Limpar filtros</button>') + "</div>");
  }

  /* ---------- próximas ---------- */
  function renderNext(list) {
    var box = $("list-next");
    if (!list.length) {
      box.innerHTML = '<div class="empty"><strong>Nenhuma prova com os filtros atuais.</strong><button type="button" class="primary" data-clear>Limpar filtros</button></div>';
      return;
    }
    var groups = [], cur = null;
    list.forEach(function (e) {
      var k = e.data_inicio.slice(0, 7);
      if (!cur || cur.k !== k) { cur = { k: k, items: [] }; groups.push(cur); }
      cur.items.push(e);
    });
    box.innerHTML = groups.map(function (g) {
      var p = g.k.split("-");
      return '<section class="month-group"><h3>' + MONTHS[+p[1] - 1] + " " + p[0] + " <small>" + plural(g.items.length, "prova", "provas") +
        '</small></h3><ol class="cards">' + g.items.map(function (e) { return "<li>" + card(e) + "</li>"; }).join("") + "</ol></section>";
    }).join("");
  }

  /* ---------- detalhe ---------- */
  function linkRow(href, label, note, main) {
    return '<a href="' + esc(href) + '" target="_blank" rel="noopener noreferrer"' + (main ? ' class="main"' : "") + ">" + esc(label) +
      " ↗<span>" + esc(note) + "</span></a>";
  }
  function mapInfo(e) {
    if (!e.mapa || e.mapa.tipo === "indisponivel") {
      return "Localização indisponível" + '<span class="src">' + esc(e.mapa && e.mapa.nota ? e.mapa.nota : "Cidade não identificada") + ". A prova continua na lista.</span>";
    }
    if (e.mapa.tipo === "exata") {
      var ll = e.mapa.largada_lat + "," + e.mapa.largada_lng;
      return "Ponto de largada informado pelo organizador" +
        '<span class="src">' + esc(ll) + " · " + '<a href="https://www.google.com/maps?q=' + encodeURIComponent(ll) + '" target="_blank" rel="noopener">abrir no mapa ↗</a>. ' +
        "No mapa do estado, a prova aparece agrupada na sede de " + esc(e.municipio.nome) + ".</span>" +
        '<button type="button" class="link" data-show-on-map="' + e.municipio.ibge + '">Ver ' + esc(e.municipio.nome) + " no mapa</button>";
    }
    return "Aproximada: sede de " + esc(e.municipio.nome) +
      '<span class="src">' + esc(e.mapa.nota) + " Base: IBGE " + esc(e.municipio.ibge) + ".</span>" +
      '<button type="button" class="link" data-show-on-map="' + e.municipio.ibge + '">Ver ' + esc(e.municipio.nome) + " no mapa</button>";
  }
  function host(u) { try { return new URL(u).hostname.replace(/^www\./, ""); } catch (e) { return u; } }

  function openDetail(id, opener) {
    var e = EVENTS.find(function (x) { return x.id === id; });
    if (!e) return;
    var multi = e.data_fim !== e.data_inicio;
    var when = multi ? fmtShort(e.data_inicio) + " → " + fmtShort(e.data_fim) : fmtLong(e.data_inicio);
    var loc = e.internacional ? [e.local, e.cidade, e.pais].filter(Boolean).join(", ")
      : [e.local, e.cidade, e.estado ? e.estado + " (" + e.uf + ")" : "Estado não informado"].filter(Boolean).join(", ");
    if (!e.cidade && !e.local) loc = "Local a divulgar" + (e.estado ? " · " + e.estado : "");
    var dist = e.distancias_km.length ? e.distancias_km.map(fmtKm).join(" · ") + '<span class="src">Fonte: ' + esc(e.distancias_fonte) + "</span>"
      : "Não informada pela fonte";
    var elev = e.altimetria_m ? e.altimetria_m + " m" + '<span class="src">Fonte: ' + esc(e.altimetria_fonte) + "</span>" : "Não informada pela fonte";

    var links = "";
    if (e.link_inscricao) links += linkRow(e.link_inscricao, "Inscrições", host(e.link_inscricao) + (e.link_inscricao_fonte === "Site oficial" ? " · via site oficial" : ""), true);
    if (e.link_oficial) links += linkRow(e.link_oficial, e.link_oficial_tipo === "rede_social" ? "Perfil oficial" : "Site oficial", host(e.link_oficial), !e.link_inscricao);
    if (e.complemento_oficial) links += linkRow(e.complemento_oficial.fonte_url, "Página oficial consultada", host(e.complemento_oficial.fonte_url), false);
    e.urls_adventuremag.forEach(function (u, i) {
      links += linkRow(u, "Página na Adventure Mag" + (e.urls_adventuremag.length > 1 ? " (" + (i + 1) + ")" : ""), "fonte original", false);
    });
    var noLink = !e.link_inscricao && !e.link_oficial ? '<p class="d-nolink">A fonte não publicou link oficial nem de inscrição para esta prova.</p>' : "";
    var alerts = e.alertas.length ? '<div class="alerts"><strong>Atenção aos dados</strong><ul>' +
      e.alertas.map(function (a) { return "<li>" + esc(a) + "</li>"; }).join("") + "</ul></div>" : "";

    $("d-body").innerHTML =
      '<span class="d-date">' + esc(when) + "</span>" +
      '<h2 class="d-name" id="d-name">' + esc(e.nome) + "</h2>" +
      '<span class="pill ' + e.status + '">' + STATUS_LABEL[e.status] + "</span>" +
      (e.status === "data_alterada" ? ' <small>A fonte marcou esta prova com "Nova data"; a data exibida é a atual.</small>' : "") +
      '<dl class="d-grid">' +
      "<dt>Local</dt><dd>" + esc(loc) + "</dd>" +
      (e.internacional ? "" : "<dt>No mapa</dt><dd>" + mapInfo(e) + "</dd>") +
      (e.local_largada ? "<dt>Largada</dt><dd>" + esc(e.local_largada) + '<span class="src">Fonte: ' + (e.envio ? "Envio do organizador" : "site oficial") + "</span></dd>" : "") +
      "<dt>Distâncias</dt><dd>" + dist + "</dd>" +
      "<dt>Altimetria</dt><dd>" + elev + "</dd>" +
      "<dt>Modalidade</dt><dd>" + esc(e.modalidade) + "</dd>" +
      "<dt>Organizador</dt><dd>" + esc(e.organizador || "Não informado pela fonte") + "</dd>" +
      "<dt>Confiabilidade</dt><dd>" + CONF_LABEL[e.confiabilidade] + '<span class="src">Fonte: ' + esc(e.fonte) +
      (e.complemento_oficial ? " + site oficial" : "") + " · verificado em " + fmtShort(e.verificado_em) + "</span></dd>" +
      "</dl>" + alerts + '<div class="d-links">' + links + "</div>" + noLink +
      '<p class="meta">Confirme data, percurso e valores no site do organizador antes de se inscrever.' +
      (e.incluido_em ? " Na base desde " + fmtShort(e.incluido_em) + "." : "") +
      (e.historico ? " Prova já realizada (mantida como histórico)." : "") + "</p>" +
      (formUrl() ? '<p class="meta">' + formLinkHtml("Organiza esta prova? Envie distâncias, altimetria ou correções") + "</p>" : "");
    var dlg = $("detail");
    dlg._opener = opener;
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
  }
  $("detail").addEventListener("close", function () { var o = $("detail")._opener; if (o && o.focus) o.focus(); });

  try { init(); } catch (err) { fail(err && err.message ? err.message : String(err)); }
})();
