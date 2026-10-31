-- grão: uma linha = um par origem-destino (direcional: A→B e B→A são rotas diferentes), só voos tipo N
-- Responde: quais são as 20 rotas com mais voos realizados e qual a pontualidade de cada uma?
SELECT
    origem_icao,
    destino_icao,
    count(*) FILTER (WHERE situacao_voo = 'REALIZADO')                          AS voos_realizados,
    count(pontual_15)                                                           AS voos_avaliados,
    round(100.0 * count(*) FILTER (WHERE pontual_15) / count(pontual_15), 2)    AS pontualidade
FROM refined.voos
WHERE tipo_linha = 'N'
GROUP BY origem_icao, destino_icao
ORDER BY voos_realizados DESC, origem_icao, destino_icao
LIMIT 20
