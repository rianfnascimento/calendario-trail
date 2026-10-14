/* Testes da lógica de filtros com a base real: node tests/test_filters.js */
const path = require("path");
const F = require(path.join(__dirname, "..", "web", "js", "filters.js"));
global.window = {};
require(path.join(__dirname, "..", "web", "data", "events.js"));
const EV = window.TRAIL_DATA.eventos;
const SNAP = window.TRAIL_DATA.meta.coletado_em === "2026-10-14"; // casos conhecidos da coleta de 14/10/2026
const TODAY = SNAP ? "2026-10-14" : window.TRAIL_DATA.meta.atualizado_em;
let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) pass++; else fail++;
  console.log((cond ? "PASS " : "FAIL ") + name + (detail ? "  (" + detail + ")" : ""));
}
/* Verificação que depende de dados específicos da coleta de 14/10/2026. */
function snap(name, fn, detail) {
  if (!SNAP) return;
  let ok = false;
  try { ok = fn(); } catch (e) { detail = String(e); }
  check("[amostra] " + name, ok, detail);
}
function f(over) { return Object.assign(F.defaults(TODAY), over || {}); }

const all = F.apply(EV, f());
check("visão nacional exclui exterior por padrão", all.every(e => !e.internacional), all.length + " provas");
check("ordem cronológica", all.every((e, i) => i === 0 || all[i - 1].data_inicio <= e.data_inicio));

const pe = F.apply(EV, f({ uf: "PE" }));
check("estado PE só traz PE", pe.length > 0 && pe.every(e => e.uf === "PE"), pe.length + " provas");
check("contagem por UF bate com o filtro por UF",
  Object.entries(F.countBy(all, "uf")).every(([uf, n]) => F.apply(EV, f({ uf })).length === n));
for (const r of F.REGIONS) {
  const lst = F.apply(EV, f({ region: r }));
  check("região " + r + " consistente", lst.every(e => e.regiao === r), lst.length + " provas");
}
const sumRegions = F.REGIONS.reduce((s, r) => s + F.apply(EV, f({ region: r })).length, 0);
const noUf = all.filter(e => !e.uf).length;
check("regiões + sem estado = total nacional", sumRegions + noUf === all.length, sumRegions + " + " + noUf);

const combo = F.apply(EV, f({ region: "Nordeste", uf: "PE", year: "2026", month: "11", kmMin: 30 }));
check("filtro combinado Nordeste+PE+nov/2026+>30km executa", Array.isArray(combo), combo.length + " resultado(s)");
const combo2 = F.apply(EV, f({ region: "Nordeste", uf: "PE", year: "2026", month: "11" }));
check("Nordeste+PE+nov/2026 só traz PE em novembro de 2026",
  combo2.length > 0 && combo2.every(e => e.uf === "PE" && e.ano === 2026 && e.mes === 11), combo2.length + " provas");
const km30 = F.apply(EV, f({ kmMin: 30 }));
check("distância mínima 30 km exige alguma distância >= 30", km30.every(e => e.distancias_km.some(k => k >= 30)), km30.length + " provas");
const kmRange = F.apply(EV, f({ kmMin: 10, kmMax: 21, includeAbroad: true }));
check("faixa 10–21 km", kmRange.every(e => e.distancias_km.some(k => k >= 10 && k <= 21)), kmRange.length + " provas");
const elev = F.apply(EV, f({ withElevation: true }));
check("somente com altimetria", elev.every(e => e.altimetria_m > 0), elev.length + " provas");

const q = F.apply(EV, f({ q: "caruaru" }));
snap("busca por cidade (caruaru)", () => q.length >= 2 && q.every(e => F.norm(e.cidade).includes("caruaru")), q.length + " provas");
const qAcc = F.apply(EV, f({ q: "jalapao" }));
snap("busca ignora acentos (jalapao → Jalapão)", () => qAcc.length >= 1, qAcc.length + " provas");
const qNone = F.apply(EV, f({ q: "xyzprovainexistente" }));
check("busca sem resultado devolve lista vazia", qNone.length === 0);

const canc = F.apply(EV, f({ statuses: ["cancelado"] }));
check("status cancelado isolado",  canc.every(e => e.status === "cancelado"), canc.length + " prova(s)");
const noCanc = F.apply(EV, f({ statuses: ["agendado", "data_alterada", "adiado"] }));
check("ocultar canceladas remove só canceladas", noCanc.length + canc.length === all.length);

const range = F.apply(EV, f({ from: "2026-11-01", to: "2026-11-30" }));
check("intervalo de datas", range.every(e => e.data_fim >= "2026-11-01" && e.data_inicio <= "2026-11-30"), range.length + " provas");
const rr = F.apply(EV, f({ uf: "RR" }));
snap("estado sem provas (Roraima) devolve vazio sem erro", () => rr.length === 0);
const abroad = F.apply(EV, f({ region: "Exterior" }));
check("região Exterior lista só provas fora do Brasil",  abroad.every(e => e.internacional), abroad.length + " provas");
const past = F.apply(EV, f({ today: "2027-01-01" }));
check("provas já realizadas somem por padrão", past.every(e => e.data_fim >= "2027-01-01"));
check("…e voltam com includePast", F.apply(EV, f({ today: "2027-01-01", includePast: true })).length === all.length);

const multi = EV.find(e => e.data_fim > e.data_inicio && !e.internacional);
check("prova de vários dias aparece em cada dia", F.onDay([multi], multi.data_fim).length === 1, multi.nome);
const m = F.monthMatrix(2026, 11);
check("matriz de novembro/2026 começa num domingo", m[0][0] === "2026-11-01" && m.flat().filter(Boolean).length === 30);
check("navegação de mês atravessa o ano", JSON.stringify(F.shiftMonth(2026, 12, 1)) === '{"year":2027,"month":1}' &&
  JSON.stringify(F.shiftMonth(2027, 1, -1)) === '{"year":2026,"month":12}');
check("contador de filtros ativos", F.activeCount(f({ q: "x", kmMin: 30, month: "11" })) === 3);


// ---- cidades (nível 2) ----
const peAll = F.apply(EV, f({ uf: "PE" }));
const peCities = F.cities(peAll);
const car = peCities.list.find(c => c.nome === "Caruaru");
check("PE agrupa provas por município", peCities.list.length >= 1 && peCities.list.reduce((s, c) => s + c.count, 0) + peCities.unlocated.length === peAll.length,
  peCities.list.length + " cidades");
snap("Caruaru agrupa 2 provas num único marcador", () => car && car.count === 2 && car.events.every(e => e.cidade === "Caruaru"));
snap("filtro de cidade só traz o município", () => F.apply(EV, f({ uf: "PE", city: car.key })).length === 2);
snap("cidade + outros filtros (Caruaru, 2027, > 30 km)", () => F.apply(EV, f({ uf: "PE", city: car.key, from: "2027-01-01", to: "2027-06-30", kmMin: 30 })).length === 0);
snap("mapa usa o mesmo filtro sem a cidade (todas as cidades visíveis)", () => F.apply(EV, f({ uf: "PE", city: car.key }), { ignoreCity: true }).length === peAll.length);
const alAll = F.apply(EV, f({ uf: "AL" }));
const alC = F.cities(alAll);
snap("AL: provas sem localização ficam fora do mapa e na lista", () => alC.unlocated.length === 2 && alAll.length === alC.unlocated.length + alC.list.reduce((s, c) => s + c.count, 0));
snap("grupo 'sem localização' é filtrável", () => F.apply(EV, f({ uf: "AL", city: F.NO_CITY })).length === 2);
const sorted = F.sortCities(F.cities(F.apply(EV, f({ uf: "SP" }))).list, "count");
check("ordenação por número de provas", sorted.every((c, i) => i === 0 || sorted[i - 1].count >= c.count), sorted[0].nome + " " + sorted[0].count);
const alpha = F.sortCities(sorted, "alpha");
check("ordenação alfabética", alpha.every((c, i) => i === 0 || alpha[i - 1].nome.localeCompare(c.nome, "pt-BR") <= 0));
snap("Gravatá (PE) não consta na fonte", () => !peCities.list.some(c => F.norm(c.nome) === "gravata"));
console.log("\n" + pass + "/" + (pass + fail) + " verificações de filtros passaram");
process.exit(fail ? 1 : 0);
