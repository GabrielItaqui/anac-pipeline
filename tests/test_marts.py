"""Testes dos marts: os próprios arquivos sql/marts/*.sql sobre uma refined inventada.

Todos os dados são inventados e os valores esperados foram calculados à mão; o banco é sempre `:memory:`.
"""

import duckdb
import pytest

from pipeline import db, marts

COLUNAS_VOOS = {
    "empresa_icao": "VARCHAR", "empresa_nome": "VARCHAR", "numero_voo": "VARCHAR", "tipo_linha": "VARCHAR",
    "origem_icao": "VARCHAR", "destino_icao": "VARCHAR", "partida_prevista": "TIMESTAMP",
    "mes_referencia": "DATE", "hora_partida_prevista": "INTEGER", "atraso_partida_min": "INTEGER",
    "atraso_chegada_min": "INTEGER", "situacao_voo": "VARCHAR", "situacao_chegada_anac": "VARCHAR",
    "cancelado": "BOOLEAN", "sem_previsao": "BOOLEAN", "pontual_15": "BOOLEAN",
}


def voo(numero: str, **campos):
    """Um voo N realizado e pontual GLO SBGR→SBRJ de jan/2025, às 10h; `campos` sobrescreve colunas."""
    base = {
        "empresa_icao": "GLO", "empresa_nome": "GOL", "numero_voo": numero, "tipo_linha": "N",
        "origem_icao": "SBGR", "destino_icao": "SBRJ", "partida_prevista": "2025-01-10 10:00",
        "mes_referencia": "2025-01-01", "hora_partida_prevista": 10, "atraso_partida_min": 0,
        "atraso_chegada_min": 0, "situacao_voo": "REALIZADO", "situacao_chegada_anac": "Pontual",
        "cancelado": False, "sem_previsao": False, "pontual_15": True,
    }
    return base | campos


def cancelado(numero: str, **campos):
    return voo(numero, situacao_voo="CANCELADO", cancelado=True, pontual_15=None, atraso_partida_min=None,
               atraso_chegada_min=None, situacao_chegada_anac=None, **campos)


def sem_previsao(numero: str, **campos):
    return voo(numero, partida_prevista=None, hora_partida_prevista=None, sem_previsao=True, pontual_15=None,
               atraso_partida_min=None, atraso_chegada_min=None, situacao_chegada_anac=None, **campos)


def atrasado(numero: str, minutos: int, **campos):
    return voo(numero, atraso_partida_min=minutos, atraso_chegada_min=minutos, pontual_15=minutos <= 15,
               situacao_chegada_anac="Pontual" if minutos <= 30 else "Atraso 30-60", **campos)


# 3 avaliados (2 pontuais), 1 cancelado, 1 realizado sem previsão, e 1 voo I que não pode aparecer em nada.
BASE = [
    voo("1000"),
    atrasado("1001", 10),
    atrasado("1002", 30),
    cancelado("1003"),
    sem_previsao("1004"),
    atrasado("9000", 120, tipo_linha="I", empresa_icao="TAP", origem_icao="LPPT", destino_icao="SBGR"),
]


@pytest.fixture
def con():
    conexao = db.conectar(":memory:")
    definicao = ", ".join(f"{c} {t}" for c, t in COLUNAS_VOOS.items())
    conexao.execute(f"CREATE TABLE refined.voos ({definicao})")
    conexao.execute("CREATE TABLE refined.aerodromos (codigo_oaci VARCHAR, nome VARCHAR, uf VARCHAR)")
    conexao.execute("INSERT INTO refined.aerodromos VALUES "
                    "('SBGR', 'Guarulhos', 'São Paulo'), ('SBRJ', 'Santos Dumont', 'Rio de Janeiro')")
    yield conexao
    conexao.close()


def inserir(con, voos):
    marcadores = ", ".join("?" for _ in COLUNAS_VOOS)
    con.executemany(f"INSERT INTO refined.voos VALUES ({marcadores})", [list(v.values()) for v in voos])


def inserir_em_massa(con, empresa: str, origem: str, quantidade: int, cancelados: int = 0):
    """`quantidade` voos N pontuais da empresa gerados com range(); os `cancelados` primeiros são cancelados."""
    con.execute("""
        INSERT INTO refined.voos
        SELECT $empresa, $empresa, $empresa || i, 'N', $origem, 'SBRJ', TIMESTAMP '2025-01-10 10:00',
               DATE '2025-01-01', 10, c, c, CASE WHEN i < $cancelados THEN 'CANCELADO' ELSE 'REALIZADO' END,
               CASE WHEN i < $cancelados THEN NULL ELSE 'Pontual' END, i < $cancelados, false,
               CASE WHEN i < $cancelados THEN NULL ELSE true END
        FROM (SELECT i, CASE WHEN i < $cancelados THEN NULL ELSE 0 END AS c FROM range($quantidade) t(i))
    """, {"empresa": empresa, "origem": origem, "quantidade": quantidade, "cancelados": cancelados})


def mart(con, nome: str) -> list[tuple]:
    """Cria o mart a partir do próprio arquivo sql/marts/<nome>.sql e devolve as linhas."""
    tabela = marts.criar_mart(con, marts.DIR_SQL_MARTS / f"{nome}.sql")
    return con.execute(f"SELECT * FROM {tabela}").fetchall()


def tabelas_em_marts(con) -> list[str]:
    return [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'marts' ORDER BY 1").fetchall()]


# --------------------------------------------------------------------------- denominadores e tipo I


def test_voos_mensais_pontualidade_e_denominadores(con):
    inserir(con, BASE)
    mes, programados, realizados, cancelados_, sem_prev, taxa, avaliados, pontualidade = mart(con, "01_voos_mensais")[0]
    # Programados = 5 voos N (o I fica de fora); realizados = 3 avaliados + 1 sem previsão.
    assert (programados, realizados, cancelados_, sem_prev) == (5, 4, 1, 1)
    # Cancelamento sobre os programados: 1 / 5.
    assert round(taxa, 2) == 20.0
    # Cancelado e sem previsão fora do denominador: 2 pontuais de 3 avaliados.
    assert (avaliados, round(pontualidade, 2)) == (3, 66.67)
    assert str(mes) == "2025-01-01"


def test_kpis_uma_linha_com_os_totais(con):
    inserir(con, BASE)
    linhas = mart(con, "08_kpis")
    # Atraso mediano de (0, 10, 30) = 10; uma empresa e um aeroporto de origem (o voo I da TAP/LPPT não conta).
    assert linhas == [(5, 4, 1, 20.0, 1, 3, 66.67, 10.0, 1, 1)]


def test_rotas_e_hora_ignoram_voo_tipo_i_e_sem_previsao(con):
    inserir(con, BASE)
    # Rota: 4 realizados (inclui o sem previsão), mas só 3 avaliados.
    assert mart(con, "05_rotas_mais_voadas") == [("SBGR", "SBRJ", 4, 3, 66.67)]
    # Hora: o sem previsão não tem hora; o voo I das 10h não entra.
    assert mart(con, "06_pontualidade_por_hora") == [(10, 3, 66.67, 10.0)]


def test_uf_sem_cadastro_vira_nao_cadastrado(con):
    inserir(con, BASE + [voo("1005", origem_icao="SWXX")])
    assert mart(con, "07_pontualidade_por_uf") == [
        ("Não cadastrado", 1, 1, 100.0),
        ("São Paulo", 5, 3, 66.67),
    ]


def test_mediana_nao_e_afetada_por_atraso_extremo(con):
    inserir(con, [voo("1000"), atrasado("1001", 5), atrasado("1002", 10), atrasado("1003", 9999)])
    # Mediana de (0, 5, 10, 9999) = (5 + 10) / 2 = 7.5; a média seria 2503.5.
    assert mart(con, "08_kpis")[0][7] == 7.5
    assert mart(con, "06_pontualidade_por_hora") == [(10, 4, 75.0, 7.5)]


# --------------------------------------------------------------------------- mínimo de 1.000 voos


def test_minimo_de_1000_voos_avaliados_por_empresa_e_aeroporto(con):
    inserir_em_massa(con, "AZU", "SBGR", 1000)
    inserir_em_massa(con, "ABJ", "SBRJ", 999)
    assert mart(con, "02_pontualidade_por_empresa") == [("AZU", "AZU", 1000, 1000, 100.0, 0.0)]
    assert mart(con, "04_atraso_por_aeroporto") == [("SBGR", "Guarulhos", "São Paulo", 1000, 100.0, 0.0)]


def test_cancelamento_por_empresa_sobre_programados_com_minimo_de_1000(con):
    # AZU: 1.000 programados, 100 cancelados -> 10%. ABJ: 999 programados, fica de fora.
    inserir_em_massa(con, "AZU", "SBGR", 1000, cancelados=100)
    inserir_em_massa(con, "ABJ", "SBGR", 999, cancelados=999)
    assert mart(con, "03_cancelamento_por_empresa") == [("AZU", "AZU", 1000, 100, 10.0)]


# --------------------------------------------------------------------------- execução


def test_executar_cria_os_8_marts_quando_a_qualidade_passa(con):
    inserir(con, BASE)
    contagens = marts.executar(con)
    assert contagens == {
        "marts.voos_mensais": 1, "marts.pontualidade_por_empresa": 0, "marts.cancelamento_por_empresa": 0,
        "marts.atraso_por_aeroporto": 0, "marts.rotas_mais_voadas": 1, "marts.pontualidade_por_hora": 1,
        "marts.pontualidade_por_uf": 1, "marts.kpis": 1,
    }


def test_qualidade_falhando_nao_cria_nenhum_mart(con):
    inserir(con, BASE + [voo("1005", situacao_voo="DESVIADO")])
    with pytest.raises(marts.QualidadeFalhou, match="01_situacao_voo"):
        marts.executar(con)
    assert tabelas_em_marts(con) == []


def test_mart_quebrado_desfaz_todos_os_marts(con, tmp_path):
    inserir(con, BASE)
    (tmp_path / "01_ok.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    (tmp_path / "02_quebrado.sql").write_text("SELECT * FROM refined.nao_existe", encoding="utf-8")
    with pytest.raises(duckdb.CatalogException):
        marts.executar(con, dir_sql=tmp_path)
    assert tabelas_em_marts(con) == []


@pytest.mark.parametrize(("situacao", "codigo"), [("REALIZADO", 0), ("DESVIADO", 1)])
def test_main_sai_com_1_se_a_qualidade_falhar(monkeypatch, con, situacao, codigo):
    inserir(con, BASE + [voo("1005", situacao_voo=situacao)])
    # main() fecha a conexão ao sair; o fixture fecha de novo, o que o DuckDB aceita.
    monkeypatch.setattr(marts.db, "conectar", lambda: con)
    assert marts.main() == codigo
