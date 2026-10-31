-- Verifica: no máximo 1% dos voos tipo N tem origem sem cadastro em refined.aerodromos.
-- Por quê: esses voos vão para a UF "Não cadastrado" no mart por UF; acima de 1% o mart deixa
-- de representar as UFs (medido: 5 aeródromos, 0,29% dos voos N).
-- Devolve: uma linha com o percentual, só se passar do limite.
WITH n AS (
    SELECT v.origem_icao, a.codigo_oaci IS NULL AS sem_cadastro
    FROM refined.voos AS v
    LEFT JOIN refined.aerodromos AS a ON a.codigo_oaci = v.origem_icao
    WHERE v.tipo_linha = 'N'
)
SELECT
    count(*) FILTER (WHERE sem_cadastro)                                    AS voos_sem_cadastro,
    count(*)                                                                AS voos_n,
    round(100.0 * count(*) FILTER (WHERE sem_cadastro) / count(*), 2)       AS percentual,
    1.0                                                                     AS limite_percentual
FROM n
HAVING 100.0 * count(*) FILTER (WHERE sem_cadastro) / count(*) > 1.0
