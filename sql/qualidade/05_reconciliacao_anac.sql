-- Verifica: nosso atraso de chegada concorda com a classificação da ANAC em pelo menos 99,9%
-- dos voos com atraso calculado e situacao_chegada_anac preenchidos.
-- Por quê: a ANAC classifica a chegada com tolerância de 30 min; bater com ela prova que o cálculo
-- do atraso (chegada real − chegada prevista) está certo.
-- Regra: "não atrasado para a ANAC" (Antecipado ou Pontual) = atraso_chegada_min <= 30.
-- Medido em 2025: <= 30 concorda em 99,98% (202 divergências, todas "Pontual" com 31 min,
-- provavelmente porque a ANAC calcula com segundos, que não existem no arquivo público);
-- < 30 concorda em 99,64%. Limite com folga: 99,9%.
-- Devolve: uma linha com a concordância, só se ficar abaixo do limite.
WITH comparado AS (
    SELECT
        situacao_chegada_anac IN ('Antecipado', 'Pontual') = (atraso_chegada_min <= 30) AS concorda
    FROM refined.voos
    WHERE atraso_chegada_min IS NOT NULL AND situacao_chegada_anac IS NOT NULL
)
SELECT
    count(*) FILTER (WHERE NOT concorda)                                AS divergencias,
    count(*)                                                            AS voos_comparados,
    round(100.0 * count(*) FILTER (WHERE concorda) / count(*), 4)       AS concordancia_percentual,
    99.9                                                                AS limite_percentual
FROM comparado
HAVING 100.0 * count(*) FILTER (WHERE concorda) / count(*) < 99.9
