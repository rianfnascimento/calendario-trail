# Calendário Trail Brasil

Calendário geográfico interativo de provas de trail running no Brasil, construído a partir do
calendário público da Adventure Mag (https://www.adventuremag.com.br/calendario/trail-run/).

## Como abrir

O site é estático e não depende de servidor nem de consultas à Adventure Mag durante o uso.

- Abra `dist/index.html` direto no navegador, ou
- Sirva a pasta: `cd dist && python3 -m http.server 8000` e acesse http://localhost:8000
- Para publicar, copie `dist/index.html` para qualquer hospedagem estática (GitHub Pages, Netlify, S3…).

Atalhos de link: `index.html#pe` abre Pernambuco no mapa; `#pe-2604106` abre Caruaru (código IBGE do
município); `#calendario` e `#proximas` abrem as outras visões.

## Navegação geográfica em dois níveis

1. **Brasil e estados**: mapa nacional por estado, regiões e contagem de provas (como antes).
2. **Estado e cidades**: ao escolher um estado, aparece o mapa do estado com um marcador por município
   que tem provas (número = provas). Cidades próximas viram um grupo que se abre ao ampliar
   (+/−, roda do mouse, arrastar ou pinça). Tocar num marcador mostra o resumo da cidade e filtra a lista.
   A aba **Cidades** lista os municípios (ordem por número de provas ou A–Z); escolher um atualiza mapa e lista.
   A trilha `Brasil › Região › Estado › Cidade` volta um nível sem perder os demais filtros.
   No celular, Mapa / Cidades / Provas ficam em subabas; no computador, mapa e lista ficam lado a lado.

## Estrutura

| Camada | Arquivo |
|---|---|
| Coleta / importação | `scripts/collect.py` (automática) ou arquivos em `data/raw/` |
| Base de dados | `scripts/build_db.py` → `data/events.json`, `data/events.csv`, `data/build_report.json` |
| Complementos oficiais | `data/raw/complementos_oficiais.json` (separados dos dados da Adventure Mag) |
| Lógica dos filtros | `web/js/filters.js` (funções puras, testáveis em Node) |
| Localização das cidades | `scripts/geocode.py` + `data/geo/municipios.csv` + `data/geo/localidades_municipios.json` |
| Mapa | `scripts/build_map.py` (GeoJSON IBGE → SVG) e `web/js/map.js` (Brasil), `web/js/statemap.js` (estado/cidades) |
| Interface | `web/index.html`, `web/css/app.css`, `web/js/app.js` |
| Empacotamento | `scripts/bundle.py` → `dist/index.html` (arquivo único) |
| Envios aprovados | `formulario/Codigo.gs` (Google) e `scripts/submissoes.py` |
| Rotina de atualização | `.github/workflows/atualizar.yml` (GitHub Actions + Pages) |
| Testes | `tests/test_data.py`, `tests/test_filters.js`, `tests/test_atualizacao.py`, `tests/test_ui.py` |

## Publicar e atualizar

Passo a passo completo (GitHub Pages, robô mensal, formulário e aprovação): **[docs/PUBLICAR.md](docs/PUBLICAR.md)**.

Resumo do robô (`.github/workflows/atualizar.yml`):
- **dia 1 de cada mês:** varredura incremental da Adventure Mag + envios aprovados → publica;
- **toda segunda:** só envios aprovados (publica apenas se houver novidade);
- **sob demanda:** botão *Run workflow* (modo `envios` ou `completo`).

Manualmente:

```bash
python3 scripts/collect.py      # incremental: listagem completa + só páginas novas/alteradas (--full baixa tudo)
python3 scripts/build_db.py     # normaliza, junta envios aprovados, valida e grava a base + data/novidades.json
python3 scripts/bundle.py       # gera dist/index.html
python3 tests/test_data.py && node tests/test_filters.js && python3 tests/test_atualizacao.py && python3 tests/test_ui.py
```

Proteções:
- `collect.py` grava em arquivos temporários e só os confirma se a coleta parecer completa
  (≥ 20 eventos e no máximo 10% de páginas de evento com falha). Coletas antigas nunca são apagadas.
- `build_db.py` valida antes de escrever (ids únicos, UFs válidas, URLs válidas, queda brusca de
  registros > 30%). Se a validação falhar, sai com código 1 e a última base válida é mantida.
- Provas que já aconteceram e saíram da fonte ficam como histórico; provas futuras que somem da fonte
  são listadas no relatório para conferência.

Envios de provas: `data/raw/submissoes_aprovadas.csv` (aba "Publicar" da planilha, baixada pelo robô).
Regras em `scripts/submissoes.py`; formulário e planilha criados por `formulario/Codigo.gs`.

Coleta manual (alternativa): se o coletor parar de funcionar por mudança no site, preencha
`data/raw/listing_<data>.tsv` (página, data, tag, nome, cidade, UF, URL) e
`data/raw/details_<data>.txt` (`id<TAB>status|início|fim|cidade|UF|organizador|link|lat|lng|distâncias|altimetria`)
no mesmo formato dos arquivos de 14/10/2026 e rode `build_db.py`. Foi assim que a base atual foi montada.

## Regras de dados

- Nada é inventado: campos ausentes ficam vazios e a interface diz "não informado pela fonte".
- Cada evento guarda a URL de origem na Adventure Mag; eventos publicados duas vezes viram um só,
  com as duas URLs.
- Status da fonte é preservado ("Cancelado", "Nova data").
- Dados de sites oficiais ficam em `complemento_oficial`, com fonte e data, e divergências entre
  fontes viram alertas visíveis no detalhe da prova, sem escolher um lado.
- Links classificados automaticamente: plataformas de inscrição → "Inscrições"; Instagram/Facebook/
  Linktree → "Perfil oficial"; demais → "Site oficial".
- Confiabilidade: alta (cidade, UF, link e coordenadas presentes, sem divergência), média, baixa.

## Como as cidades são localizadas

- Base local de municípios com código IBGE e coordenadas da sede (`data/geo/municipios.csv`, projeto
  kelvins/municipios-brasileiros, licença MIT). Nenhum serviço externo de geocodificação é consultado,
  então não há limite de uso nem consultas repetidas; as coordenadas ficam gravadas em `data/events.json`.
- Cidade + UF do evento são comparadas ao nome do município (sem acentos/caixa).
- Distritos, praias e parques citados pela fonte (Trancoso, Praia do Forte, Sana…) só são associados
  pela tabela `data/geo/localidades_municipios.json`, e apenas se as coordenadas publicadas pela fonte
  estiverem a menos de 60 km da sede do município indicado.
- Todo marcador fica na **sede do município** e é rotulado como **localização aproximada**. Não há ponto
  de largada exato na fonte; o campo `mapa.tipo = "exata"` está previsto, mas nunca é usado sem esse dado.
- Sem cidade identificável (local "a divulgar", "Jalapão", "Rota Imperial"): a prova continua na lista,
  aparece no grupo "Sem localização no mapa" e tem o motivo explicado no detalhe.
- Ilhas distantes do continente (Fernando de Noronha) aparecem num atalho "fora de escala" no mapa do estado.

## Limitações conhecidas

- A Adventure Mag publica só provas futuras; não há histórico de 2026 anterior a 16/10.
- As páginas da fonte raramente trazem distâncias e nunca traziam altimetria na coleta de 14/10/2026.
  Distâncias vieram da fonte em 5 provas e de sites oficiais em mais 9; altimetria: nenhuma.
- Muitos sites de inscrição carregam o conteúdo via JavaScript e não puderam ser lidos.
- `collect.py` foi escrito a partir da estrutura observada das páginas, mas não pôde ser executado
  contra o site real no ambiente de desenvolvimento (rede bloqueada). Na primeira execução, confira
  o resumo impresso e o relatório `data/build_report.json`.
- Limites estaduais: GeoJSON do projeto click_that_hood (Code for Germany), derivado do IBGE,
  simplificado para o mapa.
