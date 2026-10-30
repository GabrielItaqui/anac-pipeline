-- refined.voos: um voo (etapa origem → destino) do VRA, tipado, com atrasos e flags.
-- Lê só de raw.vra. Horários em horário de Brasília, sem conversão de fuso.
-- strptime (e não try_strptime): formato inesperado derruba a etapa; vazio (NULL) segue NULL.
CREATE OR REPLACE TABLE refined.voos AS
WITH tipado AS (
    SELECT
        "Sigla ICAO Empresa Aérea"                          AS empresa_icao,
        "Empresa Aérea"                                     AS empresa_nome,
        "Número Voo"                                        AS numero_voo,
        "Código DI"                                         AS codigo_di,
        "Código Tipo Linha"                                 AS tipo_linha,
        "Modelo Equipamento"                                AS modelo_equipamento,
        CAST("Número de Assentos" AS INTEGER)               AS assentos,
        "Sigla ICAO Aeroporto Origem"                       AS origem_icao,
        "Descrição Aeroporto Origem"                        AS origem_descricao,
        "Sigla ICAO Aeroporto Destino"                      AS destino_icao,
        "Descrição Aeroporto Destino"                       AS destino_descricao,
        strptime("Partida Prevista", '%d/%m/%Y %H:%M')      AS partida_prevista,
        strptime("Partida Real", '%d/%m/%Y %H:%M')          AS partida_real,
        strptime("Chegada Prevista", '%d/%m/%Y %H:%M')      AS chegada_prevista,
        strptime("Chegada Real", '%d/%m/%Y %H:%M')          AS chegada_real,
        "Situação Voo"                                      AS situacao_voo,
        CAST(strptime("Referência", '%d/%m/%Y %H:%M:%S') AS DATE) AS referencia,
        "Situação Partida"                                  AS situacao_partida_anac,
        "Situação Chegada"                                  AS situacao_chegada_anac,
        "Codeshare"                                         AS codeshare,
        _arquivo_origem
    FROM raw.vra
),

-- Deduplicação só nas linhas com partida prevista; em empate fica a do arquivo de nome menor,
-- depois a de partida real e chegada real mais cedo (NULL por último) e, por fim, a de
-- Referência mais cedo (há duplicata que só difere no dia da Referência). As duplicatas reais
-- estão todas no mesmo arquivo, então só o arquivo não decidia qual linha fica.
-- Linhas sem partida prevista passam todas: a chave apagaria voos reais diferentes.
deduplicado AS (
    SELECT *
    FROM tipado
    WHERE partida_prevista IS NOT NULL
    QUALIFY row_number() OVER (
        PARTITION BY empresa_icao, numero_voo, origem_icao, partida_prevista
        ORDER BY _arquivo_origem, partida_real NULLS LAST, chegada_real NULLS LAST, referencia
    ) = 1
    UNION ALL
    SELECT *
    FROM tipado
    WHERE partida_prevista IS NULL
),

calculado AS (
    SELECT
        *,
        -- Mês do voo = Referência (voos vazam para o mês seguinte; a partida pode vir vazia).
        CAST(date_trunc('month', referencia) AS DATE)                AS mes_referencia,
        CAST(hour(partida_prevista) AS INTEGER)                      AS hora_partida_prevista,
        -- Real − prevista; negativo = antecipado.
        CAST(date_diff('minute', partida_prevista, partida_real) AS INTEGER) AS atraso_partida_min,
        CAST(date_diff('minute', chegada_prevista, chegada_real) AS INTEGER) AS atraso_chegada_min,
        situacao_voo = 'CANCELADO'                                   AS cancelado,
        situacao_voo = 'REALIZADO'
            AND (partida_prevista IS NULL OR chegada_prevista IS NULL) AS sem_previsao
    FROM deduplicado
)

SELECT
    empresa_icao, empresa_nome, numero_voo, codigo_di, tipo_linha, modelo_equipamento,
    assentos, origem_icao, origem_descricao, destino_icao, destino_descricao,
    partida_prevista, partida_real, chegada_prevista, chegada_real,
    referencia, mes_referencia, hora_partida_prevista,
    atraso_partida_min, atraso_chegada_min,
    situacao_voo, situacao_partida_anac, situacao_chegada_anac, codeshare,
    cancelado, sem_previsao,
    -- NULL tira o voo do denominador da pontualidade nos marts.
    CASE
        WHEN cancelado OR sem_previsao OR chegada_real IS NULL THEN NULL
        ELSE atraso_chegada_min <= 15
    END AS pontual_15,
    _arquivo_origem
FROM calculado;
