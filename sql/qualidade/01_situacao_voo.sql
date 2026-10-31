-- Verifica: situacao_voo só tem REALIZADO ou CANCELADO.
-- Por quê: as flags cancelado e sem_previsao e o denominador da pontualidade só conhecem esses dois
-- valores; um valor novo (ou vazio) sumiria das contas sem erro.
-- Devolve: os valores fora do domínio, com quantos voos têm cada um.
SELECT situacao_voo, count(*) AS voos
FROM refined.voos
WHERE situacao_voo IS NULL OR situacao_voo NOT IN ('REALIZADO', 'CANCELADO')
GROUP BY situacao_voo
ORDER BY voos DESC
