-- grão: uma linha = o ano de 2025 inteiro (resumo), só voos tipo N
-- Responde: qual o retrato geral da aviação doméstica em 2025?
-- Atraso mediano de chegada só sobre os voos avaliados (mesma base da pontualidade); mediana e não
-- média porque há atrasos extremos que distorcem a média.
SELECT
    count(*)                                                                    AS voos_programados,
    count(*) FILTER (WHERE situacao_voo = 'REALIZADO')                          AS voos_realizados,
    count(*) FILTER (WHERE cancelado)                                           AS voos_cancelados,
    round(100.0 * count(*) FILTER (WHERE cancelado) / count(*), 2)              AS taxa_cancelamento,
    count(*) FILTER (WHERE sem_previsao)                                        AS voos_sem_previsao,
    count(pontual_15)                                                           AS voos_avaliados,
    round(100.0 * count(*) FILTER (WHERE pontual_15) / count(pontual_15), 2)    AS pontualidade,
    round(median(atraso_chegada_min) FILTER (WHERE pontual_15 IS NOT NULL), 1)  AS atraso_mediano_chegada_min,
    count(DISTINCT empresa_icao)                                                AS empresas,
    count(DISTINCT origem_icao)                                                 AS aeroportos_origem
FROM refined.voos
WHERE tipo_linha = 'N'
