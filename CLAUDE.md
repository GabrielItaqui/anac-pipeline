# CLAUDE.md – Regras do projeto anac-pipeline

Pipeline de dados (raw → refined → qualidade → marts) sobre pontualidade da aviação
doméstica brasileira em 2025, com dados abertos da ANAC. O README.md é a fonte da
verdade para decisões de negócio: **não mude uma decisão do README sem perguntar.**

## Stack e comandos

- Python 3.13, uv, DuckDB. Sem pandas: o DuckDB lê os CSVs direto.
- Banco único: `data/anac.duckdb`, com schemas `raw`, `refined` e `marts`.
- Etapas: `uv run python -m pipeline.ingestao | transformacao | qualidade | marts`
- Testes: `uv run pytest --cov=pipeline` (meta: 60% de coverage)

## Estrutura

```
pipeline/   config.py (URLs, caminhos, meses), db.py, ingestao.py,
            transformacao.py, qualidade.py, marts.py
sql/        refined/, qualidade/, marts/ (um .sql por indicador)
tests/      testes unitários
data/       gerado em runtime, NUNCA versionado (está no .gitignore)
```

## Formato real dos arquivos (medido, não suposto)

**VRA** (`VRA_2025_MM.csv`)
- Separador `;`, UTF-8 puro (**sem BOM**), **cabeçalho na linha 1**.
- O `;` no fim de cada linha é o `Codeshare` vazio, não uma 22ª coluna (21 colunas).
- Ausência de valor = campo vazio (não existe o texto literal `null`); na raw, campo
  vazio vira NULL.
- Aspas são texto literal (ex.: nomes como `"DIAGORAS"`), nunca delimitador de campo:
  a leitura usa `quote=''` e `escape=''`.
- Datas: `%d/%m/%Y %H:%M`; `Referência` usa `%d/%m/%Y %H:%M:%S`.
- `Número Voo` tem zero à esquerda (`0904`).
- `Justificativa` vem 100% vazia: não construa nada sobre ela.

**Aeródromos** (`AerodromosPublicos.csv`)
- Separador `;`, **Latin-1**, linha 1 = `Atualizado em: AAAA-MM-DD`, **cabeçalho na
  linha 2** (`skip=1`).
- `LATGEOPOINT`/`LONGEOPOINT` usam ponto decimal; `Altitude` usa vírgula decimal.
- `UF` vem por extenso ("Acre"), não como sigla.
- Aspas são texto literal (segundos das coordenadas, ex.: `09°52'06"S`), nunca
  delimitador de campo: a leitura usa `quote=''` e `escape=''`.

## Regras por camada

**Raw**
- Todas as colunas em VARCHAR (`all_varchar=true`). Motivo: tipar na leitura apaga
  zeros à esquerda e esconde erros de formato.
- Adicione `_arquivo_origem` e `_carregado_em` em toda linha. Motivo: linhagem.
- A raw nunca é alterada depois de carregada; recarregar = recriar a tabela inteira.
- O download é idempotente: pula se o arquivo existe e o SHA-256 bate com o manifesto
  (data/manifesto.json: URL, data, tamanho, SHA-256, Last-Modified). Retry com backoff em falha de
  rede. Motivo: a ANAC republica arquivos antigos.

**Refined**
- Lê só da raw. Toda transformação fica em `sql/refined/*.sql`; o Python só orquestra.
- Colunas em snake_case, sem acento.
- Mês do voo = `Referência` (não a partida prevista). Motivo: voos vazam para o mês
  seguinte e a partida prevista pode vir vazia.
- Atraso de chegada em minutos = chegada real − chegada prevista.
- Deduplicação por empresa + número do voo + origem + partida prevista, **só para
  linhas com partida prevista**. Motivo: aplicada aos voos sem previsão, a chave
  apagaria voos reais diferentes.
- Horários = horário de Brasília (premissa documentada no README).

**Qualidade**
- Checks em `sql/qualidade/`, executados antes dos marts. Falha = pipeline para.
- São checks de dados reais, separados dos testes unitários.

**Marts**
- Leem só da refined. Um arquivo por indicador: `sql/marts/NN_nome.sql`.
- **A primeira linha de todo mart é o grão**: `-- grão: uma linha = ...`
- Pontual = atraso de chegada ≤ 15 min (OTP15), só voos tipo `N`.
- Fora do denominador da pontualidade: cancelados e realizados sem horário previsto.
- O JOIN com aeródromos é LEFT JOIN; origem sem cadastro vira UF `Não cadastrado`.

## Testes

- pytest com **dados inventados** pequenos e `tmp_path`.
- **Nunca** abrir `data/anac.duckdb` nem baixar da internet nos testes.
- Todo teste tem pelo menos um `assert` com valor esperado explícito.
- Percentuais comparados com valor exato arredondado (ex.: `round(x, 2) == 66.67`),
  sem `pytest.approx`.

## Git

- Conventional Commits (`feat(ingestao): ...`, `test(refined): ...`, `docs: ...`).
- Um commit por etapa, na ordem do PLANO.md. Nunca commitar arquivos de `data/`.

## Quando estiver em dúvida

- Não invente colunas nem formatos: consulte a seção "Formato real" acima.
- Se precisar assumir algo sobre os dados, **diga explicitamente** antes de codar,
  para registrarmos na seção "Onde a IA errou ou assumiu algo" do README.