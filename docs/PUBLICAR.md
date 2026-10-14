# Como colocar o Calendário Trail Brasil no ar

São três peças, todas gratuitas:

| Peça | Para quê |
|---|---|
| **GitHub** (repositório + Actions + Pages) | Guarda o projeto, roda o robô mensal e hospeda o site |
| **Google Formulários + Planilhas** | Recebe os cadastros de provas; você aprova na planilha |
| **Adventure Mag** | Fonte principal das provas (varredura no dia 1 de cada mês) |

Tempo estimado: 30 a 40 minutos na primeira vez.

> Antes de divulgar o site, vale pedir autorização à Adventure Mag (página de contato do site
> deles). O rodapé do site diz "Proibida a reprodução total ou parcial do conteúdo" e o
> robots.txt bloqueia robôs de IA na seção /calendario/ desde 08/09/2026.

---

## 1. Criar o repositório no GitHub

1. Crie uma conta em https://github.com (se ainda não tiver).
2. Clique em **New repository**. Nome sugerido: `calendario-trail`. Marque **Public**
   (o GitHub Pages gratuito exige repositório público). Clique em **Create repository**.
3. Na página do repositório vazio, clique em **uploading an existing file**.
4. Descompacte `calendario-trail-brasil.zip` no computador, abra a pasta `trail-calendario`
   e arraste **todo o conteúdo** dela (não a pasta em si) para a página. Clique em **Commit changes**.
5. Confira se a pasta `.github/workflows` subiu. No Mac ela fica oculta e costuma ficar de fora.
   Se não aparecer na lista de arquivos do repositório:
   **Add file > Create new file**, digite o nome `.github/workflows/atualizar.yml`,
   cole o conteúdo do arquivo `atualizar.yml` (abra no Bloco de Notas/TextEdit) e salve.

## 2. Ligar o site e o robô

1. **Settings > Pages > Build and deployment > Source**: escolha **GitHub Actions**.
2. **Settings > Actions > General > Workflow permissions**: marque **Read and write permissions** e salve.
3. Aba **Actions** > **Atualizar calendário** > **Run workflow** > modo **envios** > **Run workflow**.
4. Em uns 2 minutos o site estará em `https://SEU-USUARIO.github.io/calendario-trail/`
   (o endereço aparece no resumo da execução e em Settings > Pages).

A partir daí:

- **Dia 1 de cada mês, 06:00:** o robô lê a listagem da Adventure Mag, baixa só as páginas de provas
  novas ou alteradas, atualiza a base e publica. O resumo da execução mostra o que entrou, o que mudou
  e o que sumiu da fonte.
- **Toda segunda, 07:00:** o robô lê só a planilha de envios aprovados (não acessa a Adventure Mag).
  Se não houver aprovação nova, não publica nada.
- **Se algo falhar:** o GitHub manda um e-mail e o site continua com a última versão boa.

## 3. Criar o formulário e a planilha de aprovação

1. Crie uma planilha nova em https://sheets.google.com. Nome sugerido: `Calendário Trail · Envios`.
2. Menu **Extensões > Apps Script**. Apague o que estiver lá, cole o arquivo `formulario/Codigo.gs`
   inteiro e clique em salvar.
3. No seletor de funções, escolha **configurar** e clique em **Executar**. O Google pede autorização
   (é o seu próprio script); aceite.
4. Volte à planilha. Agora existem as abas:
   - **Leia-me:** link do formulário e instruções.
   - **Respostas:** cada envio, com as colunas **Status** (Pendente / Aprovada / Recusada) e
     **Observação interna**.
   - **Publicar:** só as provas aprovadas e só as colunas públicas. Nome e contato de quem enviou
     nunca vão para essa aba.
5. **Arquivo > Compartilhar > Publicar na Web** > escolha a aba **Publicar** e o formato
   **Valores separados por vírgula (.csv)** > **Publicar**. Copie o link gerado.
6. No GitHub: **Settings > Secrets and variables > Actions > aba Variables > New repository variable**.
   Nome: `SUBMISSOES_CSV_URL`. Valor: o link copiado.

### Perguntas do formulário (criadas pelo script)

| Pergunta | Obrigatória | Vira no site |
|---|---|---|
| Nome da prova | sim | nome |
| Data de início | sim | data em destaque, calendário |
| Data de término | não | provas de mais de um dia |
| Estado (UF) | sim | estado, região, mapa do Brasil |
| Cidade (município) | sim | marcador no mapa do estado |
| Local de largada | não | detalhe da prova |
| Coordenadas da largada | não | ponto exato da largada (se ficar a menos de 60 km do município) |
| Distâncias (km) | sim | etiquetas de distância e filtro por km |
| Altimetria (D+) da maior distância | não | etiqueta D+ e filtro "com altimetria" |
| Tipo de prova | sim | modalidade |
| Situação da prova | sim | Agendada / Adiada / Cancelada |
| Organizador | sim | detalhe da prova |
| Site oficial ou perfil | não | botão "Site oficial" / "Perfil oficial" |
| Link de inscrição | não | botão "Inscrições" |
| Seu nome · E-mail ou WhatsApp · Relação com a prova | sim | **não publicado** |
| Autorização de publicação | sim | **não publicado** |

## 4. Colocar o botão "Cadastrar prova" no site

1. Na aba **Leia-me** da planilha, copie o link do formulário.
2. No GitHub, abra `web/config.js`, clique no lápis (editar) e cole o link entre as aspas:
   `formUrl: "https://docs.google.com/forms/d/e/.../viewform"`.
3. **Commit changes.** O site é refeito sozinho em ~2 minutos e passa a mostrar:
   - o botão **+ Cadastrar prova** no topo;
   - a faixa "Sua prova não está aqui?" no fim da página;
   - o link "Conhece uma prova aqui? Cadastre" quando um estado ou cidade não tem provas;
   - o link "Organiza esta prova? Envie distâncias, altimetria ou correções" no detalhe de cada prova.

## 5. Rotina de aprovação

1. Chega um e-mail "Nova prova para avaliar".
2. Na aba **Respostas**, confira os dados (site, inscrição, data, cidade).
3. Troque o **Status** para **Aprovada** ou **Recusada**. A aba **Publicar** se atualiza sozinha.
4. Para publicar na hora: GitHub > **Actions > Atualizar calendário > Run workflow** > modo **envios**.
   Ou espere a execução automática de segunda-feira.

O que acontece com um envio aprovado:

- **Prova nova:** entra no calendário e no mapa com o selo **Nova** e a fonte "Envio do organizador".
- **Prova que já existe** (mesma data, mesmo município, nome parecido): não duplica; completa a prova
  existente com distâncias, D+, largada e links. Se algum dado divergir da Adventure Mag, aparece um
  alerta no detalhe.
- **Envio com problema** (sem estado ou data válida): é ignorado e aparece no resumo da execução no
  GitHub, com o motivo, para você corrigir na planilha.
- **Recusada ou volta a Pendente:** sai do site na próxima atualização.

Atenção: o Google leva alguns minutos para atualizar o CSV publicado depois que você muda o Status.
Se rodar o robô logo em seguida e a prova não entrar, espere 5 minutos e rode de novo.

## Testar no computador (opcional)

```bash
python3 scripts/build_db.py && python3 scripts/bundle.py   # gera dist/index.html
python3 tests/test_data.py && node tests/test_filters.js && python3 tests/test_atualizacao.py
python3 tests/test_ui.py                                    # precisa de Playwright + Chromium
```
