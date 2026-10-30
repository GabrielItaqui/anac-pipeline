"""Testes da refined: os próprios arquivos sql/refined/*.sql sobre uma raw inventada.

Todos os dados são inventados; o banco é sempre `:memory:`.
"""

from datetime import date, datetime

import duckdb
import pytest

from pipeline import db, transformacao

COLUNAS_VRA = (
    "Sigla ICAO Empresa Aérea", "Empresa Aérea", "Número Voo", "Código DI", "Código Tipo Linha",
    "Modelo Equipamento", "Número de Assentos", "Sigla ICAO Aeroporto Origem",
    "Descrição Aeroporto Origem", "Partida Prevista", "Partida Real",
    "Sigla ICAO Aeroporto Destino", "Descrição Aeroporto Destino", "Chegada Prevista",
    "Chegada Real", "Situação Voo", "Justificativa", "Referência", "Situação Partida",
    "Situação Chegada", "Codeshare", "_arquivo_origem",
)

COLUNAS_AERODROMOS = (
    "Código OACI", "CIAD", "Nome", "Município", "UF", "Município Servido", "UF Servido",
    "LATGEOPOINT", "LONGEOPOINT", "Latitude", "Longitude", "Altitude", "Operação Diurna",
    "Operação Noturna", "Situação", "Validade do Registro", "Portaria de Registro", "Link Portaria",
    "_arquivo_origem",
)


def voo(numero: str, **campos: str | None) -> dict[str, str | None]:
    """Um voo realizado pontual de jan/2025; `campos` sobrescreve colunas pelo nome da raw."""
    base = {
        "Sigla ICAO Empresa Aérea": "GLO", "Empresa Aérea": "GOL", "Número Voo": numero,
        "Código DI": "0", "Código Tipo Linha": "N", "Modelo Equipamento": "B738",
        "Número de Assentos": "186", "Sigla ICAO Aeroporto Origem": "SBGR",
        "Descrição Aeroporto Origem": "GUARULHOS", "Partida Prevista": "10/01/2025 10:00",
        "Partida Real": "10/01/2025 10:00", "Sigla ICAO Aeroporto Destino": "SBRJ",
        "Descrição Aeroporto Destino": "SANTOS DUMONT", "Chegada Prevista": "10/01/2025 11:00",
        "Chegada Real": "10/01/2025 11:00", "Situação Voo": "REALIZADO", "Justificativa": None,
        "Referência": "01/01/2025 00:00:00", "Situação Partida": "Pontual",
        "Situação Chegada": "Pontual", "Codeshare": None, "_arquivo_origem": "VRA_2025_01.csv",
    }
    return base | campos


def _criar_raw(con, tabela, colunas, linhas):
    definicao = ", ".join(f'"{c}" VARCHAR' for c in colunas)
    con.execute(f"CREATE OR REPLACE TABLE {tabela} ({definicao}, _carregado_em TIMESTAMP)")
    marcadores = ", ".join("?" for _ in colunas)
    for linha in linhas:
        con.execute(
            f"INSERT INTO {tabela} VALUES ({marcadores}, TIMESTAMP '2026-10-30 12:00:00')",
            [linha[c] for c in colunas],
        )


AERODROMO = dict(zip(COLUNAS_AERODROMOS, (
    "SBRB", "AC0001", "Plácido de Castro", "RIO BRANCO", "Acre", "Rio Branco", "Acre",
    "-9.8683333", "-67.898056", "09°52'06\"S", "067°53'53\"W", "193,0", "VFR", "VFR",
    "Cadastrado", None, None, None, "AerodromosPublicos.csv",
), strict=True))


@pytest.fixture
def con():
    conexao = db.conectar(":memory:")
    _criar_raw(conexao, "raw.aerodromos", COLUNAS_AERODROMOS, [AERODROMO])
    yield conexao
    conexao.close()


def refinar(con, voos):
    """Carrega `voos` em raw.vra, roda os .sql da refined e devolve {numero_voo: linha}."""
    _criar_raw(con, "raw.vra", COLUNAS_VRA, voos)
    transformacao.executar(con)
    cursor = con.execute("SELECT * FROM refined.voos")
    nomes = [d[0] for d in cursor.description]
    return {linha["numero_voo"]: linha for linha in (dict(zip(nomes, r, strict=True)) for r in cursor.fetchall())}


# --------------------------------------------------------------------------- atraso e pontualidade


def test_atraso_simples(con):
    v = refinar(con, [voo("1000", **{"Partida Real": "10/01/2025 10:07", "Chegada Real": "10/01/2025 11:30"})])
    assert v["1000"]["atraso_partida_min"] == 7
    assert v["1000"]["atraso_chegada_min"] == 30
    assert v["1000"]["pontual_15"] is False


def test_virada_da_meia_noite(con):
    v = refinar(con, [voo("1000", **{
        "Chegada Prevista": "10/01/2025 23:50", "Chegada Real": "11/01/2025 00:10",
    })])
    assert v["1000"]["atraso_chegada_min"] == 20


@pytest.mark.parametrize(
    ("chegada_real", "atraso", "pontual"),
    [("10/01/2025 11:15", 15, True), ("10/01/2025 11:16", 16, False), ("10/01/2025 10:50", -10, True)],
    ids=["15_min_pontual", "16_min_atrasado", "antecipado_pontual"],
)
def test_limite_de_15_minutos(con, chegada_real, atraso, pontual):
    v = refinar(con, [voo("1000", **{"Chegada Real": chegada_real})])
    assert v["1000"]["atraso_chegada_min"] == atraso
    assert v["1000"]["pontual_15"] is pontual


def test_cancelado_e_sem_previsao_ficam_sem_pontualidade(con):
    v = refinar(con, [
        voo("1000", **{"Situação Voo": "CANCELADO", "Partida Real": None, "Chegada Real": None}),
        voo("2000", **{"Partida Prevista": None, "Chegada Prevista": None}),
        voo("3000", **{"Chegada Prevista": None}),
    ])
    assert (v["1000"]["cancelado"], v["1000"]["sem_previsao"], v["1000"]["pontual_15"]) == (True, False, None)
    assert (v["2000"]["cancelado"], v["2000"]["sem_previsao"], v["2000"]["pontual_15"]) == (False, True, None)
    assert (v["3000"]["sem_previsao"], v["3000"]["pontual_15"]) == (True, None)


def test_tipos_dos_horarios_e_hora_da_partida(con):
    v = refinar(con, [voo("1000", **{"Partida Prevista": "10/01/2025 23:55"})])
    assert v["1000"]["partida_prevista"] == datetime(2025, 1, 10, 23, 55)
    assert v["1000"]["hora_partida_prevista"] == 23
    assert v["1000"]["assentos"] == 186


def test_formato_de_data_inesperado_derruba(con):
    with pytest.raises(duckdb.Error, match="Could not parse"):
        refinar(con, [voo("1000", **{"Partida Real": "2025-01-10 10:00"})])


# --------------------------------------------------------------------------- mês e chaves


def test_mes_vem_da_referencia_mesmo_com_voo_no_mes_seguinte(con):
    v = refinar(con, [voo("1000", **{
        "Partida Prevista": "31/01/2025 23:30", "Partida Real": "01/02/2025 00:20",
        "Chegada Prevista": "01/02/2025 01:00", "Chegada Real": "01/02/2025 01:40",
    })])
    assert v["1000"]["referencia"] == date(2025, 1, 1)
    assert v["1000"]["mes_referencia"] == date(2025, 1, 1)


def test_numero_voo_mantem_zero_a_esquerda(con):
    v = refinar(con, [voo("0904")])
    assert list(v) == ["0904"]


def test_duplicata_pela_chave_fica_a_do_arquivo_menor(con):
    refinar(con, [
        voo("1000", **{"_arquivo_origem": "VRA_2025_02.csv", "Modelo Equipamento": "A320"}),
        voo("1000", **{"_arquivo_origem": "VRA_2025_01.csv"}),
    ])
    linhas = con.execute("SELECT _arquivo_origem, modelo_equipamento FROM refined.voos").fetchall()
    assert linhas == [("VRA_2025_01.csv", "B738")]


@pytest.mark.parametrize("inverter", [False, True], ids=["ordem_original", "ordem_invertida"])
def test_duplicata_no_mesmo_arquivo_tem_desempate_deterministico(con, inverter):
    linhas = [
        voo("1000", **{"Partida Real": None, "Chegada Real": None, "Modelo Equipamento": "A320"}),
        voo("1000", **{"Partida Real": "10/01/2025 10:20", "Chegada Real": "10/01/2025 11:20",
                       "Modelo Equipamento": "E195"}),
        voo("1000", **{"Partida Real": "10/01/2025 10:05", "Chegada Real": "10/01/2025 11:05",
                       "Referência": "02/01/2025 00:00:00", "Modelo Equipamento": "A321"}),
        voo("1000", **{"Partida Real": "10/01/2025 10:05", "Chegada Real": "10/01/2025 11:05"}),
    ]
    v = refinar(con, linhas[::-1] if inverter else linhas)
    assert transformacao.contar(con, "refined.voos") == 1
    assert (v["1000"]["modelo_equipamento"], v["1000"]["atraso_partida_min"]) == ("B738", 5)
    assert v["1000"]["referencia"] == date(2025, 1, 1)


def test_voos_sem_partida_prevista_nao_sao_deduplicados(con):
    sem_previsao = {"Partida Prevista": None, "Chegada Prevista": None}
    refinar(con, [
        voo("1000", **sem_previsao, **{"Partida Real": "10/01/2025 08:00"}),
        voo("1000", **sem_previsao, **{"Partida Real": "10/01/2025 18:00"}),
    ])
    assert transformacao.contar(con, "refined.voos") == 2


def test_executar_devolve_contagens_raw_e_refined(con):
    _criar_raw(con, "raw.vra", COLUNAS_VRA, [voo("1000"), voo("1000"), voo("2000")])
    assert transformacao.executar(con) == {"refined.voos": (3, 2), "refined.aerodromos": (1, 1)}


# --------------------------------------------------------------------------- aeródromos


def test_aerodromos_tipados(con):
    refinar(con, [voo("1000")])
    linha = con.execute("SELECT * FROM refined.aerodromos").fetchone()
    assert linha == ("SBRB", "AC0001", "Plácido de Castro", "RIO BRANCO", "Acre", "Cadastrado",
                     -9.8683333, -67.898056, 193.0)
