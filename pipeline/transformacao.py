"""Etapa de transformação: cria a camada refined a partir da raw.

Toda regra fica em sql/refined/*.sql; este módulo só executa os arquivos em ordem e
loga as contagens.

Uso: uv run python -m pipeline.transformacao
"""

import logging
import sys
from pathlib import Path

import duckdb

from pipeline import config, db

log = logging.getLogger(__name__)

DIR_SQL_REFINED = config.DIR_SQL / "refined"

# Arquivo .sql -> (tabela de origem na raw, tabela criada na refined)
ETAPAS = (
    ("voos.sql", "raw.vra", "refined.voos"),
    ("aerodromos.sql", "raw.aerodromos", "refined.aerodromos"),
)


def contar(con: duckdb.DuckDBPyConnection, tabela: str) -> int:
    return con.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]


def executar_sql(con: duckdb.DuckDBPyConnection, arquivo: Path) -> None:
    """Executa um arquivo .sql inteiro na conexão."""
    con.execute(arquivo.read_text(encoding="utf-8"))


def executar(con: duckdb.DuckDBPyConnection, dir_sql: Path = DIR_SQL_REFINED) -> dict[str, tuple[int, int]]:
    """Executa os .sql da refined em ordem; devolve {tabela refined: (linhas raw, linhas refined)}."""
    contagens = {}
    for nome, origem, destino in ETAPAS:
        executar_sql(con, dir_sql / nome)
        contagens[destino] = (contar(con, origem), contar(con, destino))
    return contagens


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        with db.conectar() as con:
            contagens = executar(con)
    except duckdb.Error as e:
        log.error("transformação: FALHA: %s", e)
        return 1

    for tabela, (raw, refined) in contagens.items():
        log.info("%s: %d linhas (raw: %d; removidas: %d)", tabela, refined, raw, raw - refined)
    return 0


if __name__ == "__main__":
    sys.exit(main())
