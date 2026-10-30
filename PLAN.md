# PLAN.md – Plano de execução

Cada etapa = um commit (Conventional Commits). Uma etapa só começa quando os critérios
de aceite da anterior passam. Regras gerais: ver CLAUDE.md. Decisões: ver README.md.

## Etapa 0 – Estrutura e documentação
- [x] Pastas `pipeline/`, `sql/{refined,qualidade,marts}/`, `tests/`; remover `src/`
- [x] README.md, CLAUDE.md, PLAN.md, .gitignore
- **Aceite:** `uv sync` roda sem erro; `git status` não mostra nada de `data/`
- **Commit:** `chore: estrutura inicial, README, CLAUDE.md e plano`

## Etapa 1 – Download idempotente
- [x] `pipeline/config.py` com as URLs (12 meses do VRA + aeródromos)
- [x] Download com retry/backoff para `data/raw/`
- [x] `data/manifesto.json` com URL, data do download, tamanho e SHA-256
- **Aceite:** 13 arquivos baixados; rodar de novo não baixa nada (hash confere)
- **Commit:** `feat(ingestao): download idempotente com manifesto e retry`

## Etapa 2 – Carga da raw
- [x] `raw.vra` e `raw.aerodromos`, tudo VARCHAR, com `_arquivo_origem` e `_carregado_em`
- [x] Leitura conforme o "Formato real" do CLAUDE.md (cabeçalho, encoding, separador)
- **Aceite:** linhas de `raw.vra` = soma das linhas dos 12 CSVs; `raw.aerodromos`
  com 496 linhas e 18 colunas + linhagem
- **Commit:** `feat(ingestao): carga da camada raw com linhagem`

## Etapa 3 – Testes da ingestão
- [x] CSVs inventados em `tmp_path`: cabeçalho na linha 1 (VRA) e na linha 2
  (aeródromos), Latin-1, zero à esquerda preservado, idempotência pelo hash
- **Aceite:** `uv run pytest` verde, sem rede e sem abrir o banco real
- **Commit:** `test(ingestao): testes de leitura, linhagem e idempotência`

## Etapa 4 – Refined
- [ ] `refined.voos`: tipos, datas, `mes_referencia`, atraso de partida e de chegada
  (min), flags `cancelado`, `sem_previsao`, `pontual_15`, deduplicação
- [ ] `refined.aerodromos`: tipos, altitude com vírgula → número
- **Aceite:** nenhuma linha some sem explicação (raw − duplicatas = refined);
  `Número Voo` mantém o zero à esquerda
- **Commit:** `feat(refined): voos e aeródromos tipados e deduplicados`

## Etapa 5 – Testes da refined
- [ ] Atraso calculado, virada da meia-noite, voo sem previsão, cancelado, dedup que
  preserva voos sem previsão
- **Commit:** `test(refined): regras de atraso, flags e deduplicação`

## Etapa 6 – Qualidade de dados
- [ ] `Situação Voo` só tem REALIZADO ou CANCELADO
- [ ] `Código OACI` é único em aeródromos
- [ ] Sem duplicata pela chave natural no ano inteiro (vazamento entre arquivos)
- [ ] Voos N sem aeródromo cadastrado ≤ 1%
- [ ] Reconciliação: nossa classificação com 30 min × `Situação Chegada` da ANAC
  (limite de concordância definido após medir, e escrito no README)
- **Aceite:** `pipeline.qualidade` para o pipeline com mensagem clara se um check falhar
- **Commit:** `feat(qualidade): checks de dados antes dos marts`

## Etapa 7 – Marts 01 a 04
- [ ] 01_voos_mensais, 02_pontualidade_por_empresa, 03_cancelamento_por_empresa,
  04_atraso_por_aeroporto. Grão na primeira linha de cada .sql
- **Commit:** `feat(marts): volume, pontualidade, cancelamento e atraso por aeroporto`

## Etapa 8 – Marts 05 a 08
- [ ] 05_rotas_mais_voadas, 06_pontualidade_por_hora, 07_pontualidade_por_uf (JOIN),
  08_kpis
- **Commit:** `feat(marts): rotas, horário, UF e KPIs`

## Etapa 9 – Testes dos marts
- [ ] Base inventada pequena com resultado calculado à mão (ex.: 2 de 3 pontuais = 66.67)
- [ ] Cancelados e sem previsão fora do denominador; UF "Não cadastrado" no mart 07
- **Aceite:** coverage ≥ 60%
- **Commit:** `test(marts): indicadores com dados inventados`

## Etapa 10 – CI
- [ ] `.github/workflows/ci.yml`: uv sync + pytest --cov a cada push
- **Aceite:** badge verde no GitHub
- **Commit:** `ci: testes automáticos no GitHub Actions`

## Etapa 11 – README final
- [ ] Rodar tudo do zero num clone limpo e corrigir o "Como rodar"
- [ ] Resultados principais (números dos marts) e seção da IA completa
- **Commit:** `docs: README final com resultados e erros da IA`

## Cronograma (sexta, 30/10)
- Manhã: etapas 1 a 5
- Tarde: etapas 6 a 10
- Fim da tarde: etapa 11