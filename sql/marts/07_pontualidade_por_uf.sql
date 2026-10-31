-- grão: uma linha = uma UF de origem (por extenso, como no cadastro de aeródromos), só voos tipo N
-- Responde: quais estados têm os voos mais pontuais?
-- LEFT JOIN com aeródromos para não perder voos: origem sem cadastro vira UF "Não cadastrado".
SELECT
    coalesce(a.uf, 'Não cadastrado')                                            AS uf,
    count(*)                                                                    AS voos_programados,
    count(v.pontual_15)                                                         AS voos_avaliados,
    round(100.0 * count(*) FILTER (WHERE v.pontual_15) / count(v.pontual_15), 2) AS pontualidade
FROM refined.voos AS v
LEFT JOIN refined.aerodromos AS a ON a.codigo_oaci = v.origem_icao
WHERE v.tipo_linha = 'N'
GROUP BY coalesce(a.uf, 'Não cadastrado')
ORDER BY pontualidade DESC, uf
