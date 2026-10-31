-- Verifica: codigo_oaci é único em refined.aerodromos.
-- Por quê: o JOIN dos voos com aeródromos multiplicaria os voos de um código repetido.
-- Devolve: os códigos repetidos, com quantas vezes aparecem.
SELECT codigo_oaci, count(*) AS repeticoes
FROM refined.aerodromos
GROUP BY codigo_oaci
HAVING count(*) > 1
ORDER BY repeticoes DESC, codigo_oaci
