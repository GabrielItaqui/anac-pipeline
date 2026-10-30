-- refined.aerodromos: um aeródromo público cadastrado na ANAC, tipado. Lê só de raw.aerodromos.
-- LATGEOPOINT/LONGEOPOINT já usam ponto decimal; Altitude usa vírgula decimal.
CREATE OR REPLACE TABLE refined.aerodromos AS
SELECT
    "Código OACI"                                   AS codigo_oaci,
    "CIAD"                                          AS ciad,
    "Nome"                                          AS nome,
    "Município"                                     AS municipio,
    "UF"                                            AS uf,
    "Situação"                                      AS situacao,
    CAST("LATGEOPOINT" AS DOUBLE)                   AS latitude,
    CAST("LONGEOPOINT" AS DOUBLE)                   AS longitude,
    CAST(replace("Altitude", ',', '.') AS DOUBLE)   AS altitude
FROM raw.aerodromos;
