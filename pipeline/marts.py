"""Etapa de marts: cria as tabelas de indicadores a partir da refined.

Cada mart é um arquivo sql/marts/NN_nome.sql com um único SELECT; este módulo roda a qualidade
antes e, se todos os checks passarem, cria marts.<nome> para cada arquivo, em ordem.

Uso: uv run python -m pipeline.marts
"""

import logging
import sys
from pathlib import Path

import duckdb

from pipeline import config, db, qualidade

log = logging.getLogger(__name__)

DIR_SQL_MARTS = config.DIR_SQL / "marts"


class QualidadeFalhou(Exception):
    """Algum check de qualidade falhou; nenhum mart foi criado."""


def nome_tabela(arquivo: Path) -> str:
    """`01_voos_mensais.sql` -> `marts.voos_mensais`."""
    return "marts." + arquivo.stem.split("_", 1)[1]


def criar_mart(con: duckdb.DuckDBPyConnection, arquivo: Path) -> str:
    """Cria a tabela do mart a partir do SELECT do arquivo; devolve o nome da tabela."""
    consulta = arquivo.read_text(encoding="utf-8").strip().rstrip(";")
    tabela = nome_tabela(arquivo)
    # Quebra de linha antes do ")": a consulta pode terminar num comentário.
    con.execute(f"CREATE OR REPLACE TABLE {tabela} AS (\n{consulta}\n)")
    return tabela


def executar(
    con: duckdb.DuckDBPyConnection,
    dir_sql: Path = DIR_SQL_MARTS,
    dir_qualidade: Path = qualidade.DIR_SQL_QUALIDADE,
) -> dict[str, int]:
    """Roda a qualidade e, se passar, cria todos os marts numa transação; devolve {tabela: linhas}."""
    falhas = {nome: v for nome, (v, _) in qualidade.executar(con, dir_qualidade).items() if v}
    if falhas:
        raise QualidadeFalhou(falhas)

    # Uma transação: se um mart quebrar, nenhum é criado ou substituído pela metade.
    con.execute("BEGIN TRANSACTION")
    try:
        tabelas = [criar_mart(con, arquivo) for arquivo in sorted(dir_sql.glob("*.sql"))]
        con.execute("COMMIT")
    except duckdb.Error:
        con.execute("ROLLBACK")
        raise
    return {tabela: con.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0] for tabela in tabelas}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        with db.conectar() as con:
            contagens = executar(con)
    except QualidadeFalhou as e:
        log.error("marts: qualidade falhou %s; nenhum mart criado (detalhes: python -m pipeline.qualidade)", e)
        return 1
    except duckdb.Error as e:
        log.error("marts: FALHA: %s", e)
        return 1

    for tabela, linhas in contagens.items():
        log.info("%s: %d linhas", tabela, linhas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
