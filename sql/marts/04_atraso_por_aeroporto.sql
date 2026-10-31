-- grão: uma linha = um aeroporto de origem (origem_icao), só voos tipo N
-- Responde: quais aeroportos de origem são mais pontuais e quanto atrasam tipicamente na partida?
-- Só aeroportos com pelo menos 1.000 voos avaliados no ano: um aeroporto com 20 voos e 100% pontual
-- distorceria o ranking. LEFT JOIN com aeródromos: origem sem cadastro vira UF "Não cadastrado".
-- Atraso mediano de partida só sobre os voos avaliados (mesma base da pontualidade); mediana e não
-- média porque há atrasos extremos que distorcem a média.
SELECT
    v.origem_icao,
    a.nome                                                                      AS aeroporto_nome,
    coalesce(a.uf, 'Não cadastrado')                                            AS uf,
    count(v.pontual_15)                                                         AS voos_avaliados,
    round(100.0 * count(*) FILTER (WHERE v.pontual_15) / count(v.pontual_15), 2) AS pontualidade,
    round(median(v.atraso_partida_min) FILTER (WHERE v.pontual_15 IS NOT NULL), 1) AS atraso_mediano_partida_min
FROM refined.voos AS v
LEFT JOIN refined.aerodromos AS a ON a.codigo_oaci = v.origem_icao
WHERE v.tipo_linha = 'N'
GROUP BY v.origem_icao, a.nome, a.uf
HAVING count(v.pontual_15) >= 1000
ORDER BY pontualidade DESC, v.origem_icao
