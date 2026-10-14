/* Lógica de filtros — funções puras, sem DOM. Usada pela interface e pelos testes (Node). */
(function (root) {
  "use strict";

  var REGIONS = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"];
  var STATUSES = ["agendado", "data_alterada", "adiado", "cancelado"];
  var NO_CITY = "sem-local"; // chave usada para "provas sem localização no mapa"

  function norm(s) {
    return String(s || "")
      .normalize("NFD").replace(/[̀-ͯ]/g, "")
      .toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  }

  function defaults(today) {
    return {
      region: null, uf: null, city: null, year: null, month: null,
      from: null, to: null, kmMin: null, kmMax: null,
      withElevation: false, statuses: STATUSES.slice(),
      q: "", includeAbroad: false, includePast: false,
      today: today
    };
  }

  /* Quantos filtros (além da geografia) estão ativos — exibido no botão "Filtros". */
  function activeCount(f) {
    var n = 0;
    if (f.year) n++;
    if (f.month) n++;
    if (f.from || f.to) n++;
    if (f.kmMin != null || f.kmMax != null) n++;
    if (f.withElevation) n++;
    if (f.statuses.length !== STATUSES.length) n++;
    if (f.q) n++;
    if (f.includeAbroad) n++;
    if (f.includePast) n++;
    return n;
  }

  function matches(e, f, opts) {
    opts = opts || {};
    if (!f.includePast && f.today && e.data_fim < f.today) return false;
    if (e.internacional && !f.includeAbroad && f.region !== "Exterior") return false;
    if (!opts.ignoreGeo) {
      if (f.region && e.regiao !== f.region) return false;
      if (f.uf && e.uf !== f.uf) return false;
      if (f.city && !opts.ignoreCity && (cityKey(e) || NO_CITY) !== f.city) return false;
    }
    if (f.year && e.ano !== Number(f.year)) return false;
    if (f.month && e.mes !== Number(f.month)) return false;
    if (f.from && e.data_fim < f.from) return false;
    if (f.to && e.data_inicio > f.to) return false;
    if (f.kmMin != null || f.kmMax != null) {
      var lo = f.kmMin == null ? -Infinity : Number(f.kmMin);
      var hi = f.kmMax == null ? Infinity : Number(f.kmMax);
      var ok = (e.distancias_km || []).some(function (k) { return k >= lo && k <= hi; });
      if (!ok) return false;
    }
    if (f.withElevation && !e.altimetria_m) return false;
    if (f.statuses.indexOf(e.status) === -1) return false;
    if (f.q) {
      var hay = norm([e.nome, e.cidade, e.local, e.estado, e.uf, e.organizador, e.pais].join(" "));
      var terms = norm(f.q).split(" ");
      for (var i = 0; i < terms.length; i++) if (hay.indexOf(terms[i]) === -1) return false;
    }
    return true;
  }

  /* Chave da cidade: código IBGE do município (ou null quando a localização é indisponível). */
  function cityKey(e) { return e.municipio ? e.municipio.ibge : null; }

  /* Agrupa eventos por município: [{key, nome, uf, lat, lng, count, events}], + sem localização. */
  function cities(events) {
    var map = {}, none = [];
    events.forEach(function (e) {
      var k = cityKey(e);
      if (!k) { none.push(e); return; }
      if (!map[k]) map[k] = { key: k, nome: e.municipio.nome, uf: e.municipio.uf, lat: e.municipio.lat, lng: e.municipio.lng, count: 0, events: [] };
      map[k].count++;
      map[k].events.push(e);
    });
    return { list: Object.keys(map).map(function (k) { return map[k]; }), unlocated: none };
  }

  function sortCities(list, mode) {
    return list.slice().sort(function (a, b) {
      if (mode === "alpha") return a.nome.localeCompare(b.nome, "pt-BR");
      return b.count - a.count || a.nome.localeCompare(b.nome, "pt-BR");
    });
  }

  function byDate(a, b) {
    return a.data_inicio < b.data_inicio ? -1 : a.data_inicio > b.data_inicio ? 1 :
      a.nome.localeCompare(b.nome, "pt-BR");
  }

  function apply(events, f, opts) {
    return events.filter(function (e) { return matches(e, f, opts); }).sort(byDate);
  }

  function countBy(events, key) {
    var out = {};
    events.forEach(function (e) { var k = e[key]; if (k) out[k] = (out[k] || 0) + 1; });
    return out;
  }

  /* Eventos que ocorrem em um dia (inclui provas de vários dias). */
  function onDay(events, iso) {
    return events.filter(function (e) { return e.data_inicio <= iso && e.data_fim >= iso; });
  }

  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function iso(y, m, d) { return y + "-" + pad(m) + "-" + pad(d); }

  /* Matriz do mês (semanas começando no domingo); dias fora do mês = null. */
  function monthMatrix(year, month) {
    var first = new Date(Date.UTC(year, month - 1, 1)).getUTCDay();
    var days = new Date(Date.UTC(year, month, 0)).getUTCDate();
    var cells = [];
    for (var i = 0; i < first; i++) cells.push(null);
    for (var d = 1; d <= days; d++) cells.push(iso(year, month, d));
    while (cells.length % 7) cells.push(null);
    var weeks = [];
    for (var j = 0; j < cells.length; j += 7) weeks.push(cells.slice(j, j + 7));
    return weeks;
  }

  function shiftMonth(year, month, delta) {
    var m = month - 1 + delta;
    return { year: year + Math.floor(m / 12), month: ((m % 12) + 12) % 12 + 1 };
  }

  var api = {
    REGIONS: REGIONS, STATUSES: STATUSES, norm: norm, defaults: defaults,
    activeCount: activeCount, matches: matches, apply: apply, countBy: countBy,
    cityKey: cityKey, cities: cities, sortCities: sortCities, NO_CITY: NO_CITY,
    onDay: onDay, monthMatrix: monthMatrix, shiftMonth: shiftMonth, iso: iso
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Filters = api;
})(this);
