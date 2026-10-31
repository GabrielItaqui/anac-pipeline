-- grão: uma linha = uma hora do dia (0–23) da partida prevista, só voos tipo N
-- Responde: a pontualidade piora ao longo do dia?
-- Voos sem partida prevista não têm hora e ficam de fora (também não entram na pontualidade).
-- Atraso mediano de chegada só sobre os voos avaliados (mesma base da pontualidade); mediana e não
-- média porque há atrasos extremos que distorcem a média.
SELECT
    hora_partida_prevista                                                       AS hora,
    count(pontual_15)                                                           AS voos_avaliados,
    round(100.0 * count(*) FILTER (WHERE pontual_15) / count(pontual_15), 2)    AS pontualidade,
    round(median(atraso_chegada_min) FILTER (WHERE pontual_15 IS NOT NULL), 1)  AS atraso_mediano_chegada_min
FROM refined.voos
WHERE tipo_linha = 'N' AND hora_partida_prevista IS NOT NULL
GROUP BY hora_partida_prevista
ORDER BY hora_partida_prevista
