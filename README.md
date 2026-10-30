# Pontualidade da aviação doméstica brasileira em 2025

Pipeline de dados em três camadas (raw → refined → marts) com dados abertos da ANAC,
construído com Python 3.13, uv e DuckDB. Desafio final do curso Pipeline Olist.

**Pergunta de negócio:** quais empresas, aeroportos, horários e estados têm os voos
mais pontuais (e os mais cancelados) na aviação doméstica brasileira em 2025?

## Fonte dos dados

| Tabela | Origem | Formato |
|---|---|---|
| VRA – Voo Regular Ativo (jan–dez/2025) | https://siros.anac.gov.br/siros/registros/diversos/vra/2025/ | 12 CSVs mensais (~310 MB) |
| Lista de aeródromos públicos | https://sistemas.anac.gov.br/dadosabertos/Aerodromos/Aer%C3%B3dromos%20P%C3%BAblicos/Lista%20de%20aer%C3%B3dromos%20p%C3%BAblicos/AerodromosPublicos.csv | 1 CSV |

- **Licença:** dados abertos publicados pela ANAC. TODO: confirmar a licença exata no portal.
- **Tipo de ingestão:** download batch via HTTP de arquivos publicados (não é uma API).
  Os dados **não são versionados** no repositório; são reproduzidos a partir da fonte
  oficial a cada execução.
- **A fonte muda depois de publicada:** o arquivo de jan/2025 foi republicado pela ANAC
  em 22/10/2026. Por isso a ingestão registra um manifesto com o SHA-256 de cada arquivo.

## O que é uma linha de cada tabela

- **VRA:** um voo (uma etapa de origem para destino) programado ou realizado, com
  horários previstos e reais. Chave natural: empresa + número do voo + aeroporto de
  origem + partida prevista.
- **Aeródromos:** um aeródromo público cadastrado na ANAC. Chave: `Código OACI`
  (496 linhas, 496 códigos únicos).
- **Ligação:** `VRA.Sigla ICAO Aeroporto Origem = Aeródromos.Código OACI` (LEFT JOIN).

## Camadas

| Camada | O que faz | Regra |
|---|---|---|
| raw | CSV carregado como está, todas as colunas em VARCHAR, mais `_arquivo_origem` e `_carregado_em` | Nunca é alterada |
| refined | Tipagem, conversão de datas, deduplicação, cálculo de atraso, flags | Só lê a raw |
| qualidade | Checks de dados que rodam antes dos marts e param o pipeline se falharem | Separada dos testes unitários |
| marts | Um `.sql` por indicador, com o grão na primeira linha | Só lê a refined |

Carga validada por contagem independente: 1.005.807 linhas no VRA 2025, iguais
arquivo a arquivo à contagem direta das quebras de linha dos CSVs.

## Indicadores (marts)

| Mart | Grão (uma linha = ...) |
|---|---|
| 01_voos_mensais | um mês |
| 02_pontualidade_por_empresa | uma empresa aérea |
| 03_cancelamento_por_empresa | uma empresa aérea |
| 04_atraso_por_aeroporto | um aeroporto de origem |
| 05_rotas_mais_voadas | um par origem-destino |
| 06_pontualidade_por_hora | uma hora do dia (partida prevista) |
| 07_pontualidade_por_uf | uma UF de origem (usa o JOIN com aeródromos) |
| 08_kpis | uma linha só (resumo do ano) |

## Definições e decisões

Números medidos no arquivo de jan/2025 (89.616 linhas).

| Decisão | Motivo |
|---|---|
| **Voo pontual = chegada com até 15 min de atraso (OTP15)** | Padrão internacional de pontualidade |
| Cancelados ficam fora do denominador da pontualidade | Voo que não voou não pode chegar atrasado |
| Realizados sem horário previsto (2.253, 2,6%) ficam fora da pontualidade e são contados à parte em `voos_sem_previsao` | Sem horário previsto não há atraso calculável. A própria ANAC também não os classifica |
| Pontualidade calculada só para voos tipo `N` (doméstico); a refined guarda todos os tipos | Escopo da pergunta. O JOIN com aeródromos cobre 99,7% dos voos N, contra cerca de metade nos internacionais |
| Mês do voo = coluna `Referência` | É a atribuição da própria ANAC, nunca vem vazia e resolve os 21 voos que vazam para fevereiro |
| Horários tratados como horário de Brasília, inclusive em aeroportos estrangeiros | Evidência: Miami → Galeão 01:10 → 09:25 só dá a duração real da rota (~8h) se os dois horários estiverem no mesmo fuso |
| Raw toda em VARCHAR | `Número Voo` tem zero à esquerda (`0904`); ler como número apagaria o zero |
| Leitura com `quote=''` e `escape=''` | Nenhum arquivo usa aspas como delimitador; as aspas existentes são parte do dado (ex.: 09°52'06"S). Fixado no código para não depender da detecção automática |
| Antes da carga, toda linha de dados de cada arquivo (VRA e aeródromos) precisa ter o mesmo número de `;` que o cabeçalho; senão a carga para com arquivo, linha e contagens | O DuckDB tolera um `;` sobrando no fim da linha: como toda linha do VRA termina em `;` (Codeshare vazio), uma linha com um campo a mais entrava com as colunas deslocadas, sem erro. Com `quote=''` todo `;` é separador, então a contagem é exata |
| `_carregado_em` em UTC | É metadado técnico da carga, igual ao manifesto; a regra "horário de Brasília" vale só para os horários dos voos |
| Deduplicação por empresa + voo + origem + partida prevista, só para voos com previsão | No ano inteiro há 59 chaves duplicadas, todas dentro do mesmo arquivo. O desempate é determinístico: arquivo de origem, depois partida real e chegada real mais cedo (vazio por último) e, por fim, a `Referência` mais cedo (uma duplicata só difere no dia da `Referência`). Aplicar a chave nos voos sem previsão apagaria voos reais diferentes |
| Aeródromos sem cadastro aparecem como UF "Não cadastrado" | 5 aeródromos (provavelmente privados) somam 206 voos N (0,29%). LEFT JOIN para não perder voos |
| Check de qualidade reconcilia nosso cálculo com a coluna `Situação Chegada` da ANAC (tolerância de 30 min) | A ANAC classifica com 30 min. Bater com ela prova que o cálculo de atraso está correto |
| Cancelamento por empresa, não por justificativa | A coluna `Justificativa` vem 100% vazia, inclusive nos cancelados |

## Como rodar do zero

TODO: confirmar ao final do projeto.

```powershell
git clone https://github.com/<usuario>/anac-pipeline.git
cd anac-pipeline
uv sync
uv run python -m pipeline.ingestao
uv run python -m pipeline.transformacao
uv run python -m pipeline.qualidade
uv run python -m pipeline.marts
uv run pytest --cov
```

## Onde a IA errou ou assumiu algo (e como descobrimos)

| # | O que a IA assumiu | O que era verdade | Como foi descoberto |
|---|---|---|---|
| 1 | O VRA começa com uma linha `Atualizado em:` e o cabeçalho está na linha 2 | No arquivo do SIROS o cabeçalho está na linha 1 (a premissa vinha de outro portal da ANAC) | Lendo os bytes crus com `Get-Content` antes de escrever qualquer parser |
| 2 | Horários ausentes vêm como o texto literal `null` | Vêm como campo vazio (0 ocorrências do texto `null`) | Consulta contando vazios × texto `null` por coluna |
| 3 | Existe uma coluna de justificativa preenchida para os cancelamentos | `Justificativa` vem 100% vazia | Consulta agrupando por justificativa; o mart 03 foi redesenhado |
| 4 | Filtrar `LIKE 'S%'` isola aeroportos brasileiros | Toda a América do Sul começa com S (SC = Chile, SA = Argentina...) | Lendo a descrição dos aeroportos no resultado |
| 5 | A spec pedia "3 tentativas" com três esperas (2 s → 4 s → 8 s) | Três tentativas no total só têm duas esperas; a spec era internamente contraditória | O Claude Code apontou a ambiguidade na lista de premissas e implementou 1 tentativa + 3 novas |
| 6 | No script de verificação da Etapa 2, o Claude Code usou `con.sql(...).fetchone()`, API de versões antigas do DuckDB | No DuckDB 2.0 as relations não têm mais `fetchone()`; é preciso usar `con.execute(...).fetchone()` | O script falhou com `AttributeError` na primeira execução; o código do pipeline já usava `execute` e não foi afetado |
| 7 | Na Etapa 2, a IA testou um único tipo de linha malformada e concluiu que toda linha malformada derrubava a carga | Uma linha com um campo a mais e Codeshare vazio entrava com as colunas deslocadas, sem erro | Teste da Etapa 3 com um campo a mais no meio da linha; corrigido com a conferência do número de `;` por linha |
| 8 | O plano afirmava zero duplicatas pela chave de deduplicação, com base só em janeiro | A refined do ano inteiro mostrou 59 chaves duplicadas, e o desempate por arquivo não decidia nada porque as duplicatas estão no mesmo arquivo | Contagem de chaves duplicadas na refined do ano inteiro; corrigido com desempate por partida real e chegada real (vazio por último) e, por fim, `Referência` (uma duplicata só difere no dia da `Referência`) |