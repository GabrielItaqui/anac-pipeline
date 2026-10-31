-- grão: uma linha = uma empresa aérea (empresa_icao), só voos tipo N
-- Responde: quais empresas mais cancelam voos? (por empresa: a Justificativa vem 100% vazia)
-- Só empresas com pelo menos 1.000 voos programados no ano: uma empresa com 20 voos e 1
-- cancelamento distorceria o ranking.
SELECT
    empresa_icao,
    any_value(empresa_nome)                                                     AS empresa_nome,
    count(*)                                                                    AS voos_programados,
    count(*) FILTER (WHERE cancelado)                                           AS voos_cancelados,
    round(100.0 * count(*) FILTER (WHERE cancelado) / count(*), 2)              AS taxa_cancelamento
FROM refined.voos
WHERE tipo_linha = 'N'
GROUP BY empresa_icao
HAVING count(*) >= 1000
ORDER BY taxa_cancelamento DESC, empresa_icao
