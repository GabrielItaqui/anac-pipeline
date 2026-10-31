-- Verifica: empresa + número do voo + origem + partida prevista é único em refined.voos,
-- só nas linhas com partida prevista.
-- Por quê: prova que a deduplicação da refined funcionou no ano inteiro, inclusive entre arquivos.
-- Devolve: as chaves repetidas, com quantas vezes aparecem.
SELECT empresa_icao, numero_voo, origem_icao, partida_prevista, count(*) AS repeticoes
FROM refined.voos
WHERE partida_prevista IS NOT NULL
GROUP BY empresa_icao, numero_voo, origem_icao, partida_prevista
HAVING count(*) > 1
ORDER BY repeticoes DESC, empresa_icao, numero_voo, origem_icao, partida_prevista
