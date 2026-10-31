-- grão: uma linha = um mês (mes_referencia) de 2025, só voos tipo N
-- Responde: como volume, cancelamento e pontualidade evoluem ao longo do ano?
-- Programados = todos os voos N do mês (realizados + cancelados); o mês vem da Referência.
SELECT
    mes_referencia                                                              AS mes,
    count(*)                                                                    AS voos_programados,
    count(*) FILTER (WHERE situacao_voo = 'REALIZADO')                          AS voos_realizados,
    count(*) FILTER (WHERE cancelado)                                           AS voos_cancelados,
    count(*) FILTER (WHERE sem_previsao)                                        AS voos_sem_previsao,
    round(100.0 * count(*) FILTER (WHERE cancelado) / count(*), 2)              AS taxa_cancelamento,
    count(pontual_15)                                                           AS voos_avaliados,
    round(100.0 * count(*) FILTER (WHERE pontual_15) / count(pontual_15), 2)    AS pontualidade
FROM refined.voos
WHERE tipo_linha = 'N'
GROUP BY mes_referencia
ORDER BY mes_referencia
