"""Testes dos checks de qualidade: os próprios arquivos sql/qualidade/*.sql sobre uma refined inventada.

Todos os dados são inventados; o banco é sempre `:memory:`.
"""

import pytest

from pipeline import db, qualidade


def check(nome: str):
    return qualidade.DIR_SQL_QUALIDADE / f"{nome}.sql"


def criar_refined(con, voos, aerodromos=("SBGR", "SBRJ")):
    """`voos`: tuplas (situacao, empresa, numero, origem, partida, tipo, atraso_chegada, situacao_anac)."""
    con.execute("""
        CREATE OR REPLACE TABLE refined.voos (
            situacao_voo VARCHAR, empresa_icao VARCHAR, numero_voo VARCHAR, origem_icao VARCHAR,
            partida_prevista TIMESTAMP, tipo_linha VARCHAR, atraso_chegada_min INTEGER,
            situacao_chegada_anac VARCHAR)""")
    con.executemany("INSERT INTO refined.voos VALUES (?, ?, ?, ?, ?, ?, ?, ?)", voos)
    con.execute("CREATE OR REPLACE TABLE refined.aerodromos (codigo_oaci VARCHAR)")
    con.executemany("INSERT INTO refined.aerodromos VALUES (?)", [(a,) for a in aerodromos])


def voo(numero="1000", situacao="REALIZADO", origem="SBGR", partida="2025-01-10 10:00", tipo="N",
        atraso=0, anac="Pontual"):
    return (situacao, "GLO", numero, origem, partida, tipo, atraso, anac)


@pytest.fixture
def con():
    conexao = db.conectar(":memory:")
    yield conexao
    conexao.close()


# --------------------------------------------------------------------------- 01 situação do voo


def test_situacao_voo_valida_passa(con):
    criar_refined(con, [voo("1000"), voo("2000", situacao="CANCELADO", atraso=None, anac=None)])
    assert qualidade.executar_check(con, check("01_situacao_voo")) == (0, [])


def test_situacao_voo_desconhecida_falha(con):
    criar_refined(con, [voo("1000"), voo("2000", situacao="DESVIADO"), voo("3000", situacao=None)])
    violacoes, exemplos = qualidade.executar_check(con, check("01_situacao_voo"))
    assert violacoes == 2
    assert sorted(exemplos, key=str) == [("DESVIADO", 1), (None, 1)]


# --------------------------------------------------------------------------- 02 e 03 unicidade


def test_aerodromo_repetido_falha(con):
    criar_refined(con, [voo()], aerodromos=("SBGR", "SBGR", "SBRJ"))
    assert qualidade.executar_check(con, check("02_aerodromo_unico")) == (1, [("SBGR", 2)])


def test_chave_natural_unica_passa_e_ignora_voos_sem_partida_prevista(con):
    criar_refined(con, [voo("1000"), voo("1000", partida="2025-01-11 10:00"),
                        voo("1000", partida=None), voo("1000", partida=None)])
    assert qualidade.executar_check(con, check("03_chave_natural_unica")) == (0, [])


def test_chave_natural_repetida_falha(con):
    criar_refined(con, [voo("1000"), voo("1000"), voo("2000")])
    violacoes, exemplos = qualidade.executar_check(con, check("03_chave_natural_unica"))
    assert violacoes == 1
    assert exemplos[0][:2] == ("GLO", "1000")
    assert exemplos[0][-1] == 2


# --------------------------------------------------------------------------- 04 origem sem cadastro


@pytest.mark.parametrize(
    ("sem_cadastro", "esperado"),
    [(1, (0, [])), (2, (1, [(2, 100, 2.0, 1.0)]))],
    ids=["1_porcento_passa", "2_porcento_falha"],
)
def test_limite_de_origem_sem_aerodromo(con, sem_cadastro, esperado):
    voos = [voo(str(i), origem="SXXX" if i < sem_cadastro else "SBGR") for i in range(100)]
    # Voos internacionais (tipo I) sem cadastro não entram na conta.
    voos += [voo(f"I{i}", origem="KMIA", tipo="I") for i in range(10)]
    criar_refined(con, voos)
    assert qualidade.executar_check(con, check("04_origem_sem_aerodromo")) == esperado


# --------------------------------------------------------------------------- 05 reconciliação ANAC


def test_reconciliacao_concorda_inclusive_na_fronteira_de_30_min(con):
    criar_refined(con, [
        voo("1000", atraso=-5, anac="Antecipado"), voo("2000", atraso=30, anac="Pontual"),
        voo("3000", atraso=31, anac="Atraso 30-60"), voo("4000", atraso=None, anac=None),
    ])
    assert qualidade.executar_check(con, check("05_reconciliacao_anac")) == (0, [])


def test_reconciliacao_abaixo_do_limite_falha(con):
    criar_refined(con, [
        voo("1000", atraso=10, anac="Pontual"), voo("2000", atraso=10, anac="Atraso 30-60"),
        voo("3000", atraso=90, anac="Pontual"),
    ])
    violacoes, exemplos = qualidade.executar_check(con, check("05_reconciliacao_anac"))
    assert violacoes == 1
    divergencias, comparados, concordancia, limite = exemplos[0]
    assert (divergencias, comparados, round(float(concordancia), 2), float(limite)) == (2, 3, 33.33, 99.9)


# --------------------------------------------------------------------------- execução


def test_executar_roda_todos_os_checks_em_ordem(con):
    criar_refined(con, [voo()])
    resultados = qualidade.executar(con)
    assert list(resultados) == ["01_situacao_voo", "02_aerodromo_unico", "03_chave_natural_unica",
                                "04_origem_sem_aerodromo", "05_reconciliacao_anac"]
    assert all(violacoes == 0 for violacoes, _ in resultados.values())


def test_executar_check_limita_exemplos(con, tmp_path):
    arquivo = tmp_path / "99_tudo.sql"
    arquivo.write_text("SELECT * FROM range(8) -- comentário no fim;\n", encoding="utf-8")
    violacoes, exemplos = qualidade.executar_check(con, arquivo)
    assert (violacoes, len(exemplos)) == (8, 5)


@pytest.mark.parametrize(("situacao", "codigo"), [("REALIZADO", 0), ("DESVIADO", 1)])
def test_main_sai_com_1_se_algum_check_falhar(monkeypatch, situacao, codigo):
    conectar_original = db.conectar

    def conectar():
        conexao = conectar_original(":memory:")
        criar_refined(conexao, [voo(situacao=situacao)])
        return conexao

    monkeypatch.setattr(qualidade.db, "conectar", conectar)
    assert qualidade.main() == codigo
