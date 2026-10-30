"""Testes da ingestão: lógica pura, rede com `abrir` falso e carga da raw.

Todos os dados são inventados; o banco é sempre `:memory:`.
"""

import io
import urllib.error
from datetime import datetime

import duckdb
import pytest

from pipeline import config, db, ingestao
from pipeline.ingestao import ErroCarga, ErroPermanente, Fonte

SHA256_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

CABECALHO_VRA = (
    "Sigla ICAO Empresa Aérea;Número Voo;Código Tipo Linha;"
    "Sigla ICAO Aeroporto Origem;Partida Prevista;Situação Voo;Referência;Codeshare"
)


def _linha_vra(voo: str, origem: str = "SBGR") -> str:
    # O `;` final é o Codeshare vazio, como nos arquivos reais.
    return f"GLO;{voo};N;{origem};01/01/2025 10:00;REALIZADO;01/01/2025 00:00:00;"


def _gravar_vra(caminho, linhas, cabecalho=CABECALHO_VRA, bom=False):
    texto = "\n".join([cabecalho, *linhas]) + "\n"
    caminho.write_bytes((b"\xef\xbb\xbf" if bom else b"") + texto.encode("utf-8"))
    return caminho


@pytest.fixture
def con():
    conexao = db.conectar(":memory:")
    yield conexao
    conexao.close()


# --------------------------------------------------------------------------- lógica pura


def test_sha256_arquivo_valor_conhecido(tmp_path):
    arquivo = tmp_path / "abc.txt"
    arquivo.write_bytes(b"abc")
    assert ingestao.sha256_arquivo(arquivo) == SHA256_ABC


def test_manifesto_ida_e_volta(tmp_path):
    caminho = tmp_path / "sub" / "manifesto.json"
    entradas = {
        "VRA_2025_02.csv": {"nome": "VRA_2025_02.csv", "sha256": "bb", "last_modified": None},
        "VRA_2025_01.csv": {"nome": "VRA_2025_01.csv", "sha256": "aa", "last_modified": "x"},
    }
    ingestao.gravar_manifesto(caminho, entradas)
    assert ingestao.ler_manifesto(caminho) == entradas
    assert not (tmp_path / "sub" / "manifesto.json.tmp").exists()


def test_manifesto_ausente_devolve_vazio(tmp_path):
    assert ingestao.ler_manifesto(tmp_path / "nao_existe.json") == {}


@pytest.fixture
def arquivo_local(tmp_path):
    arquivo = tmp_path / "VRA_2025_01.csv"
    arquivo.write_bytes(b"abc")
    return arquivo


ENTRADA_OK = {"sha256": SHA256_ABC, "last_modified": "Wed, 01 Jan 2025 00:00:00 GMT"}
CABECALHOS_OK = {"Last-Modified": "Wed, 01 Jan 2025 00:00:00 GMT"}


def test_precisa_baixar_sem_entrada(arquivo_local):
    assert ingestao.precisa_baixar(None, arquivo_local, CABECALHOS_OK) is True


def test_precisa_baixar_arquivo_ausente(tmp_path):
    assert ingestao.precisa_baixar(ENTRADA_OK, tmp_path / "sumiu.csv", CABECALHOS_OK) is True


def test_precisa_baixar_hash_diferente(arquivo_local):
    entrada = ENTRADA_OK | {"sha256": "0" * 64}
    assert ingestao.precisa_baixar(entrada, arquivo_local, CABECALHOS_OK) is True


def test_precisa_baixar_head_falhou_com_hash_ok(arquivo_local):
    assert ingestao.precisa_baixar(ENTRADA_OK, arquivo_local, None) is False


def test_precisa_baixar_last_modified_diferente(arquivo_local):
    republicado = {"Last-Modified": "Mon, 01 Sep 2025 00:00:00 GMT"}
    assert ingestao.precisa_baixar(ENTRADA_OK, arquivo_local, republicado) is True


def test_precisa_baixar_tudo_igual_nao_baixa(arquivo_local):
    assert ingestao.precisa_baixar(ENTRADA_OK, arquivo_local, CABECALHOS_OK) is False


def test_fontes_lista_os_13_arquivos():
    nomes = [f.nome for f in ingestao.fontes()]
    assert nomes == [f"VRA_2025_{m:02d}.csv" for m in range(1, 13)] + ["AerodromosPublicos.csv"]


# --------------------------------------------------------------------------- rede


def _http_error(codigo: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://exemplo.invalid", codigo, "erro", {}, None)


def test_com_retry_4xx_falha_sem_nova_tentativa():
    chamadas, esperas = [], []

    def acao():
        chamadas.append(1)
        raise _http_error(404)

    with pytest.raises(ErroPermanente, match="HTTP 404"):
        ingestao.com_retry(acao, "GET x", esperar=esperas.append)
    assert len(chamadas) == 1
    assert esperas == []


def test_com_retry_5xx_tenta_de_novo_e_funciona():
    esperas = []
    respostas = iter([_http_error(503), "ok"])

    def acao():
        r = next(respostas)
        if isinstance(r, Exception):
            raise r
        return r

    assert ingestao.com_retry(acao, "GET x", esperar=esperas.append) == "ok"
    assert esperas == [2]


class RespostaFalsa(io.BytesIO):
    """Imita a resposta do urlopen: corpo legível em blocos + `headers`."""

    def __init__(self, corpo: bytes, headers: dict[str, str]):
        super().__init__(corpo)
        self.headers = headers


def _abrir_falso(corpo: bytes, headers: dict[str, str]):
    def abrir(requisicao, timeout):
        return RespostaFalsa(corpo, headers)

    return abrir


def test_baixar_grava_arquivo_com_sha256_correto(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAIZ", tmp_path)
    monkeypatch.setattr(config, "TAMANHO_BLOCO", 2)  # força vários blocos no streaming
    destino = tmp_path / "data" / "raw" / "vra" / "VRA_2025_01.csv"
    fonte = Fonte("http://exemplo.invalid/VRA_2025_01.csv", destino)
    headers = {"Content-Length": "3", "Last-Modified": "Wed, 01 Jan 2025 00:00:00 GMT"}

    entrada = ingestao.baixar(fonte, _abrir_falso(b"abc", headers))

    assert destino.read_bytes() == b"abc"
    assert not destino.with_name("VRA_2025_01.csv.part").exists()
    assert entrada["sha256"] == SHA256_ABC
    assert entrada["tamanho_bytes"] == 3
    assert entrada["caminho"] == "data/raw/vra/VRA_2025_01.csv"
    assert entrada["last_modified"] == "Wed, 01 Jan 2025 00:00:00 GMT"


def test_baixar_content_length_divergente_nao_deixa_arquivo(tmp_path):
    destino = tmp_path / "VRA_2025_01.csv"
    fonte = Fonte("http://exemplo.invalid/VRA_2025_01.csv", destino)

    with pytest.raises(ingestao.http.client.IncompleteRead):
        ingestao.baixar(fonte, _abrir_falso(b"abc", {"Content-Length": "10"}))

    assert list(tmp_path.iterdir()) == []


# --------------------------------------------------------------------------- carga


def test_carregar_vra_preserva_zero_a_esquerda_e_vazio_vira_null(tmp_path, con):
    arquivo = _gravar_vra(tmp_path / "VRA_2025_01.csv", [_linha_vra("0904")])
    ingestao.carregar_vra(con, [arquivo])
    assert con.execute('SELECT "Número Voo", Codeshare FROM raw.vra').fetchall() == [("0904", None)]


def test_carregar_vra_linhagem_e_contagem_por_arquivo(tmp_path, con):
    jan = _gravar_vra(tmp_path / "VRA_2025_01.csv", [_linha_vra("0001"), _linha_vra("0002")])
    fev = _gravar_vra(tmp_path / "VRA_2025_02.csv", [_linha_vra(f"000{i}") for i in range(3)])
    instante = datetime(2025, 3, 1, 12, 0, 0)

    contagens = ingestao.carregar_vra(con, [jan, fev], instante)

    assert contagens == {"VRA_2025_01.csv": 2, "VRA_2025_02.csv": 3}
    linhagem = con.execute(
        "SELECT DISTINCT _arquivo_origem, _carregado_em FROM raw.vra ORDER BY 1"
    ).fetchall()
    assert linhagem == [("VRA_2025_01.csv", instante), ("VRA_2025_02.csv", instante)]


def test_carregar_vra_cabecalhos_diferentes_falha(tmp_path, con):
    jan = _gravar_vra(tmp_path / "VRA_2025_01.csv", [_linha_vra("0001")])
    outro = CABECALHO_VRA.replace("Codeshare", "Codeshare Novo")
    fev = _gravar_vra(tmp_path / "VRA_2025_02.csv", [_linha_vra("0002")], cabecalho=outro)

    with pytest.raises(ErroCarga, match="VRA_2025_02.csv: cabeçalho difere"):
        ingestao.carregar_vra(con, [jan, fev])


def test_carregar_vra_linha_com_campos_a_mais_falha(tmp_path, con):
    linhas = [_linha_vra("0001"), _linha_vra("0002;X;Y"), _linha_vra("0003")]
    arquivo = _gravar_vra(tmp_path / "VRA_2025_01.csv", linhas)
    with pytest.raises(ErroCarga, match="VRA_2025_01.csv: linha 3 tem 9 separadores ';', esperado 7"):
        ingestao.carregar_vra(con, [arquivo])


def test_carregar_vra_linha_com_campo_a_menos_falha(tmp_path, con):
    # Sem o `;` final do Codeshare, a última linha tem um campo a menos.
    linhas = [_linha_vra("0001"), _linha_vra("0002")[:-1]]
    arquivo = _gravar_vra(tmp_path / "VRA_2025_01.csv", linhas)
    with pytest.raises(ErroCarga, match="VRA_2025_01.csv: linha 3 tem 6 separadores ';', esperado 7"):
        ingestao.carregar_vra(con, [arquivo])


def test_carregar_vra_um_campo_a_mais_com_codeshare_vazio_falha(tmp_path, con):
    # BUG em aberto: o DuckDB aceita um `;` final sobrando, então uma linha com
    # exatamente um campo a mais (e Codeshare vazio) entra com as colunas deslocadas.
    linhas = [_linha_vra("0001"), _linha_vra("0002;X"), _linha_vra("0003")]
    arquivo = _gravar_vra(tmp_path / "VRA_2025_01.csv", linhas)
    with pytest.raises((duckdb.Error, ErroCarga)):
        ingestao.carregar_vra(con, [arquivo])


def test_carregar_vra_bom_nao_altera_primeira_coluna(tmp_path, con):
    arquivo = _gravar_vra(tmp_path / "VRA_2025_01.csv", [_linha_vra("0904")], bom=True)
    ingestao.carregar_vra(con, [arquivo])
    primeira = con.execute("SELECT * FROM raw.vra LIMIT 0").description[0][0]
    assert primeira == "Sigla ICAO Empresa Aérea"


def test_carregar_aerodromos_latin1_com_linha_de_atualizacao(tmp_path, con):
    texto = (
        "Atualizado em: 2025-06-01\n"
        "Código OACI;CIAD;Nome;Município;UF;LATGEOPOINT;Latitude;Altitude\n"
        "SWPC;AC0001;Aeródromo Teste;Plácido de Castro;Acre;-10.3;10°18'06\"S;198,5\n"
        "SBRB;AC0002;Rio Branco;Rio Branco;Acre;-9.8;09°52'06\"S;192,0\n"
    )
    arquivo = tmp_path / "AerodromosPublicos.csv"
    arquivo.write_bytes(texto.encode("latin-1"))

    contagens = ingestao.carregar_aerodromos(con, arquivo)

    assert contagens == {"AerodromosPublicos.csv": 2}
    linhas = con.execute(
        'SELECT "Código OACI", "Município", Latitude, Altitude FROM raw.aerodromos ORDER BY 1'
    ).fetchall()
    assert linhas == [
        ("SBRB", "Rio Branco", "09°52'06\"S", "192,0"),
        ("SWPC", "Plácido de Castro", "10°18'06\"S", "198,5"),
    ]


def test_carregar_aerodromos_linha_com_campo_a_mais_falha(tmp_path, con):
    # O número da linha conta a linha `Atualizado em:`: cabeçalho = 2, dados a partir de 3.
    texto = (
        "Atualizado em: 2025-06-01\n"
        "Código OACI;Município;UF\n"
        "SBRB;Rio Branco;Acre\n"
        "SWPC;Plácido;de Castro;Acre\n"
    )
    arquivo = tmp_path / "AerodromosPublicos.csv"
    arquivo.write_bytes(texto.encode("latin-1"))
    with pytest.raises(ErroCarga, match="AerodromosPublicos.csv: linha 4 tem 3 separadores ';', esperado 2"):
        ingestao.carregar_aerodromos(con, arquivo)
