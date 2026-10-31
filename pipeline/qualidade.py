"""Etapa de qualidade: checks de dados reais sobre a refined, antes dos marts.

Cada check é um arquivo sql/qualidade/NN_nome.sql cuja consulta devolve as linhas que violam a
regra: zero linhas = passou. Este módulo só executa os arquivos em ordem e loga o resultado.

Uso: uv run python -m pipeline.qualidade
"""

import logging
import sys
from pathlib import Path

import duckdb

from pipeline import config, db

log = logging.getLogger(__name__)

DIR_SQL_QUALIDADE = config.DIR_SQL / "qualidade"
MAX_EXEMPLOS = 5


def executar_check(con: duckdb.DuckDBPyConnection, arquivo: Path) -> tuple[int, list[tuple]]:
    """Executa um check; devolve (número de violações, até MAX_EXEMPLOS linhas de exemplo)."""
    consulta = arquivo.read_text(encoding="utf-8").strip().rstrip(";")
    # Quebra de linha antes do ")": a consulta pode terminar num comentário.
    violacoes = con.execute(f"SELECT count(*) FROM (\n{consulta}\n)").fetchone()[0]
    exemplos = con.execute(f"SELECT * FROM (\n{consulta}\n) LIMIT {MAX_EXEMPLOS}").fetchall()
    return violacoes, exemplos


def executar(con: duckdb.DuckDBPyConnection, dir_sql: Path = DIR_SQL_QUALIDADE) -> dict[str, tuple[int, list[tuple]]]:
    """Executa todos os checks em ordem de nome; devolve {nome do check: (violações, exemplos)}."""
    return {arquivo.stem: executar_check(con, arquivo) for arquivo in sorted(dir_sql.glob("*.sql"))}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        with db.conectar() as con:
            resultados = executar(con)
    except duckdb.Error as e:
        log.error("qualidade: FALHA ao executar os checks: %s", e)
        return 1

    for nome, (violacoes, exemplos) in resultados.items():
        if violacoes == 0:
            log.info("%s: PASSOU", nome)
        else:
            log.error("%s: FALHOU com %d violação(ões); exemplos: %s", nome, violacoes, exemplos)

    falhas = [nome for nome, (violacoes, _) in resultados.items() if violacoes]
    if falhas:
        log.error("qualidade: %d check(s) falharam (%s); pipeline parado antes dos marts", len(falhas), ", ".join(falhas))
        return 1
    log.info("qualidade: %d checks passaram", len(resultados))
    return 0


if __name__ == "__main__":
    sys.exit(main())
