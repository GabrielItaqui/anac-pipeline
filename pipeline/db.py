"""Conexão com o banco DuckDB do pipeline."""

from pathlib import Path

import duckdb

from pipeline import config

SCHEMAS = ("raw", "refined", "marts")


def conectar(caminho: Path | str = config.CAMINHO_BANCO) -> duckdb.DuckDBPyConnection:
    """Abre o banco (`":memory:"` para um banco em memória) e garante os schemas."""
    if str(caminho) != ":memory:":
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(caminho))
    for schema in SCHEMAS:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    return con
