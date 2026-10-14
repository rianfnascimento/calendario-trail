/**
 * Calendário Trail Brasil — formulário de cadastro de provas + planilha de aprovação.
 *
 * Como usar (uma vez só):
 *   1. Crie uma planilha nova no Google Planilhas.
 *   2. Menu Extensões > Apps Script. Apague o conteúdo e cole este arquivo inteiro. Salve.
 *   3. Escolha a função "configurar" e clique em Executar. Autorize o acesso pedido.
 *   4. Volte à planilha: o formulário foi criado e as abas "Respostas" e "Publicar" estão prontas.
 *      O link do formulário fica na aba "Leia-me".
 *
 * No dia a dia:
 *   - Cada envio chega na aba "Respostas" com Status = "Pendente" e você recebe um e-mail.
 *   - Avalie e troque o Status para "Aprovada" ou "Recusada".
 *   - A aba "Publicar" é refeita sozinha com as aprovadas, só com as colunas públicas
 *     (nome e contato de quem enviou NUNCA vão para lá). É essa aba que o site lê.
 */

var TITULO_FORM = "Cadastro de prova · Calendário Trail Brasil";
var ABA_RESPOSTAS = "Respostas";
var ABA_PUBLICAR = "Publicar";
var COL_STATUS = "Status";
var COL_OBS = "Observação interna";
var STATUS = ["Pendente", "Aprovada", "Recusada"];

var UFS = ["AC — Acre", "AL — Alagoas", "AP — Amapá", "AM — Amazonas", "BA — Bahia", "CE — Ceará",
  "DF — Distrito Federal", "ES — Espírito Santo", "GO — Goiás", "MA — Maranhão", "MT — Mato Grosso",
  "MS — Mato Grosso do Sul", "MG — Minas Gerais", "PA — Pará", "PB — Paraíba", "PR — Paraná",
  "PE — Pernambuco", "PI — Piauí", "RJ — Rio de Janeiro", "RN — Rio Grande do Norte",
  "RS — Rio Grande do Sul", "RO — Rondônia", "RR — Roraima", "SC — Santa Catarina", "SP — São Paulo",
  "SE — Sergipe", "TO — Tocantins"];

/* Perguntas públicas: [chave no site, título da pergunta]. A ordem das colunas na planilha não importa:
   a aba Publicar procura cada pergunta pelo título. */
var PUBLICAS = [
  ["enviado_em", "Carimbo de data/hora"],
  ["nome", "Nome da prova"],
  ["data_inicio", "Data de início"],
  ["data_fim", "Data de término"],
  ["uf", "Estado (UF)"],
  ["cidade", "Cidade (município)"],
  ["local_largada", "Local de largada"],
  ["coordenadas", "Coordenadas da largada"],
  ["distancias", "Distâncias (km)"],
  ["altimetria", "Altimetria (D+) da maior distância, em metros"],
  ["modalidade", "Tipo de prova"],
  ["situacao", "Situação da prova"],
  ["organizador", "Organizador"],
  ["site", "Site oficial ou perfil da prova"],
  ["inscricao", "Link de inscrição"]
];

function configurar() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  if (ss.getSheetByName(ABA_RESPOSTAS)) {
    throw new Error("Esta planilha já foi configurada (a aba '" + ABA_RESPOSTAS + "' existe).");
  }
  var form = FormApp.create(TITULO_FORM);
  form.setDescription(
    "Envie uma prova de trail running, corrida de montanha ou ultra trail para o Calendário Trail Brasil. " +
    "Cada envio é avaliado antes de ser publicado. Os dados de contato servem só para tirar dúvidas e não são publicados.\n\n" +
    "Se a prova já aparece no calendário, envie mesmo assim para completar distâncias, altimetria ou links: " +
    "o envio aprovado complementa a prova existente.");
  form.setCollectEmail(false);
  form.setAllowResponseEdits(false);
  form.setConfirmationMessage("Recebido! Sua prova será avaliada e, se aprovada, entra no calendário na próxima atualização.");

  var url = FormApp.createTextValidation().requireTextIsUrl()
    .setHelpText("Cole o endereço completo, começando com https://").build();

  // --- Seção 1: a prova ---
  form.addTextItem().setTitle("Nome da prova").setRequired(true)
    .setHelpText("Como aparece na divulgação, com o ano. Ex.: Ultra Trail Serra Azul 2027");
  form.addDateItem().setTitle("Data de início").setRequired(true);
  form.addDateItem().setTitle("Data de término")
    .setHelpText("Preencha só se a prova durar mais de um dia.");
  form.addListItem().setTitle("Estado (UF)").setRequired(true).setChoiceValues(UFS);
  form.addTextItem().setTitle("Cidade (município)").setRequired(true)
    .setHelpText("Nome oficial do município. Se a largada for num distrito, praia ou parque, escreva aqui o município e o lugar no campo seguinte.");
  form.addTextItem().setTitle("Local de largada")
    .setHelpText("Opcional. Ex.: Praça da Matriz; distrito de Trancoso; Parque Estadual X.");
  form.addTextItem().setTitle("Coordenadas da largada")
    .setHelpText("Opcional, mas coloca a prova no ponto exato. No Google Maps, toque e segure no ponto e copie os números (ex.: -8.2836, -35.9761), ou cole o link do local.");
  form.addTextItem().setTitle("Distâncias (km)").setRequired(true)
    .setHelpText("Separe por vírgula. Ex.: 50, 25, 12");
  form.addTextItem().setTitle("Altimetria (D+) da maior distância, em metros")
    .setHelpText("Opcional. Só o número. Ex.: 2500");
  form.addListItem().setTitle("Tipo de prova").setRequired(true)
    .setChoiceValues(["Trail run", "Corrida de montanha", "Ultra trail", "Skyrunning", "Vertical"]);
  form.addMultipleChoiceItem().setTitle("Situação da prova").setRequired(true)
    .setChoiceValues(["Confirmada", "Adiada (nova data a definir)", "Cancelada"]);

  // --- Seção 2: organização e links ---
  form.addPageBreakItem().setTitle("Organização e links");
  form.addTextItem().setTitle("Organizador").setRequired(true)
    .setHelpText("Empresa, assessoria ou pessoa responsável pela prova.");
  form.addTextItem().setTitle("Site oficial ou perfil da prova").setValidation(url)
    .setHelpText("Opcional. Site ou Instagram da prova (link completo).");
  form.addTextItem().setTitle("Link de inscrição").setValidation(url)
    .setHelpText("Opcional. Página onde o atleta se inscreve.");

  // --- Seção 3: contato (não publicado) ---
  form.addPageBreakItem().setTitle("Seu contato (não será publicado)");
  form.addTextItem().setTitle("Seu nome").setRequired(true);
  form.addTextItem().setTitle("E-mail ou WhatsApp").setRequired(true);
  form.addMultipleChoiceItem().setTitle("Qual sua relação com a prova?").setRequired(true)
    .setChoiceValues(["Sou da organização", "Sou atleta", "Assessoria ou divulgação"]);
  form.addCheckboxItem().setTitle("Autorização").setRequired(true)
    .setChoiceValues(["Confirmo que as informações são verdadeiras e autorizo a publicação no Calendário Trail Brasil."]);

  // --- Planilha: respostas, status e aba pública ---
  form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());
  SpreadsheetApp.flush();
  Utilities.sleep(2000);
  var resp = null;
  ss.getSheets().forEach(function (sh) { if (sh.getFormUrl()) resp = sh; });
  if (!resp) throw new Error("A aba de respostas não foi criada. Rode 'configurar' de novo numa planilha nova.");
  resp.setName(ABA_RESPOSTAS);

  var lastCol = resp.getLastColumn();
  resp.getRange(1, lastCol + 1, 1, 2).setValues([[COL_STATUS, COL_OBS]]).setFontWeight("bold").setBackground("#fff3c4");
  var rule = SpreadsheetApp.newDataValidation().requireValueInList(STATUS, true).setAllowInvalid(false).build();
  resp.getRange(2, lastCol + 1, resp.getMaxRows() - 1, 1).setDataValidation(rule);
  resp.setFrozenRows(1);

  var pub = ss.getSheetByName(ABA_PUBLICAR) || ss.insertSheet(ABA_PUBLICAR);
  pub.getRange(1, 1, 1, PUBLICAS.length).setValues([PUBLICAS.map(function (p) { return p[0]; })]).setFontWeight("bold");
  pub.setFrozenRows(1);

  var leia = ss.insertSheet("Leia-me", 0);
  leia.getRange("A1:B6").setValues([
    ["Link do formulário (cole em web/config.js)", form.getPublishedUrl()],
    ["Editar o formulário", form.getEditUrl()],
    ["Como aprovar", "Na aba Respostas, troque o Status para Aprovada ou Recusada."],
    ["O que o site lê", "Somente a aba Publicar (aprovadas, sem dados de contato)."],
    ["Publicar a aba para o site", "Arquivo > Compartilhar > Publicar na Web > aba Publicar > CSV > Publicar."],
    ["Atualizar a aba Publicar à mão", "Menu Calendário Trail > Atualizar aba Publicar."]
  ]);
  leia.setColumnWidth(1, 300).setColumnWidth(2, 600);
  leia.getRange("A1:A6").setFontWeight("bold");

  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger("aoReceberEnvio").forSpreadsheet(ss).onFormSubmit().create();
  ScriptApp.newTrigger("aoEditar").forSpreadsheet(ss).onEdit().create();
  atualizarPublicar();
  Logger.log("Formulário: " + form.getPublishedUrl());
}

function onOpen() {
  SpreadsheetApp.getUi().createMenu("Calendário Trail")
    .addItem("Atualizar aba Publicar", "atualizarPublicar")
    .addToUi();
}

/* Novo envio: marca como Pendente e avisa por e-mail o dono da planilha. */
function aoReceberEnvio(e) {
  var sh = e.range.getSheet();
  if (sh.getName() !== ABA_RESPOSTAS) return;
  var head = cabecalho(sh);
  var row = e.range.getRow();
  sh.getRange(row, head[COL_STATUS] + 1).setValue("Pendente");
  var v = e.namedValues || {};
  var nome = (v["Nome da prova"] || [""])[0];
  var quando = (v["Data de início"] || [""])[0];
  var onde = (v["Cidade (município)"] || [""])[0] + " / " + (v["Estado (UF)"] || [""])[0];
  try {
    MailApp.sendEmail(Session.getEffectiveUser().getEmail(),
      "Nova prova para avaliar: " + nome,
      nome + "\n" + quando + " · " + onde + "\n\nAvalie na planilha: " + SpreadsheetApp.getActiveSpreadsheet().getUrl());
  } catch (err) { /* sem permissão de e-mail: segue sem aviso */ }
}

/* Mudou o Status? Refaz a aba Publicar. */
function aoEditar(e) {
  var sh = e.range.getSheet();
  if (sh.getName() !== ABA_RESPOSTAS) return;
  var head = cabecalho(sh);
  if (e.range.getColumn() <= head[COL_STATUS] + 1 && e.range.getLastColumn() >= head[COL_STATUS] + 1) {
    atualizarPublicar();
  }
}

function cabecalho(sh) {
  var h = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  var idx = {};
  h.forEach(function (t, i) { idx[String(t).trim()] = i; });
  return idx;
}

function atualizarPublicar() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var resp = ss.getSheetByName(ABA_RESPOSTAS);
  var pub = ss.getSheetByName(ABA_PUBLICAR);
  var tz = ss.getSpreadsheetTimeZone();
  var head = cabecalho(resp);
  if (head[COL_STATUS] === undefined) throw new Error("Coluna '" + COL_STATUS + "' não encontrada na aba Respostas.");
  var data = resp.getLastRow() > 1 ? resp.getRange(2, 1, resp.getLastRow() - 1, resp.getLastColumn()).getValues() : [];
  var out = [];
  data.forEach(function (row) {
    if (String(row[head[COL_STATUS]]).trim() !== "Aprovada") return;
    out.push(PUBLICAS.map(function (p) {
      var i = p[0] === "enviado_em" ? 0 : head[p[1]]; // 1ª coluna = data/hora do envio (nome varia com o idioma)
      if (i === undefined) return "";
      var v = row[i];
      if (v instanceof Date) {
        return Utilities.formatDate(v, tz, p[0] === "enviado_em" ? "yyyy-MM-dd'T'HH:mm:ss" : "yyyy-MM-dd");
      }
      return String(v).trim();
    }));
  });
  pub.getRange(2, 1, Math.max(pub.getMaxRows() - 1, 1), PUBLICAS.length).clearContent();
  if (out.length) pub.getRange(2, 1, out.length, PUBLICAS.length).setNumberFormat("@").setValues(out);
}
