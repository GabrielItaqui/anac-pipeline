-- grão: uma linha = uma empresa aérea (empresa_icao), só voos tipo N
-- Responde: quais empresas são mais pontuais (OTP15) e quanto atrasam tipicamente na chegada?
-- Só empresas com pelo menos 1.000 voos avaliados no ano: uma empresa com 20 voos e 100% pontual
-- distorceria o ranking. Atraso mediano de chegada só sobre os voos avaliados (mesma base da
-- pontualidade); mediana e não média porque há atrasos extremos que distorcem a média.
SELECT
    empresa_icao,
    any_value(empresa_nome)                                                     AS empresa_nome,
    count(pontual_15)                                                           AS voos_avaliados,
    count(*) FILTER (WHERE pontual_15)                                          AS voos_pontuais,
    round(100.0 * count(*) FILTER (WHERE pontual_15) / count(pontual_15), 2)    AS pontualidade,
    round(median(atraso_chegada_min) FILTER (WHERE pontual_15 IS NOT NULL), 1)  AS atraso_mediano_chegada_min
FROM refined.voos
WHERE tipo_linha = 'N'
GROUP BY empresa_icao
HAVING count(pontual_15) >= 1000
ORDER BY pontualidade DESC, empresa_icao
