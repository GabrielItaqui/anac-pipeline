"""Etapa de ingestão: download idempotente dos arquivos-fonte da ANAC com manifesto,
seguido da carga da camada raw no DuckDB.

Uso: uv run python -m pipeline.ingestao
"""

import hashlib
import http.client
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from pipeline import config, db

log = logging.getLogger(__name__)

# Assinatura de urllib.request.urlopen(request, timeout=...). Substituível nos testes.
Abrir = Callable[..., Any]

# Erros transitórios: vale a pena tentar de novo.
ERROS_DE_REDE = (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException)


class ErroPermanente(Exception):
    """Falha que não se resolve tentando de novo (ex.: HTTP 4xx, URL errada)."""


@dataclass(frozen=True)
class Fonte:
    """Um arquivo a baixar: URL de origem e caminho local de destino."""

    url: str
    caminho: Path

    @property
    def nome(self) -> str:
        return self.caminho.name


# --------------------------------------------------------------------------- lógica pura


def fontes() -> list[Fonte]:
    """Lista os 13 arquivos-fonte (12 meses do VRA + aeródromos) a partir do config."""
    lista = [
        Fonte(config.URL_VRA.format(mes=mes), config.DIR_RAW_VRA / f"VRA_2025_{mes:02d}.csv")
        for mes in config.MESES
    ]
    lista.append(Fonte(config.URL_AERODROMOS, config.DIR_RAW_AERODROMOS / "AerodromosPublicos.csv"))
    return lista


def sha256_arquivo(caminho: Path) -> str:
    """Calcula o SHA-256 de um arquivo local, lendo em blocos."""
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        while bloco := f.read(config.TAMANHO_BLOCO):
            h.update(bloco)
    return h.hexdigest()


def ler_manifesto(caminho: Path) -> dict[str, dict[str, Any]]:
    """Lê o manifesto e devolve as entradas indexadas por nome. Ausente = vazio."""
    if not caminho.exists():
        return {}
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return {e["nome"]: e for e in dados["arquivos"]}


def gravar_manifesto(caminho: Path, entradas: dict[str, dict[str, Any]]) -> None:
    """Grava o manifesto de forma atômica (arquivo temporário + rename)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_name(caminho.name + ".tmp")
    conteudo = {"arquivos": [entradas[nome] for nome in sorted(entradas)]}
    tmp.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, caminho)


def precisa_baixar(
    entrada: dict[str, Any] | None,
    caminho: Path,
    cabecalhos_remotos: dict[str, str] | None,
) -> bool:
    """Decide se o arquivo precisa ser baixado.

    Pula só se: existe no disco, o SHA-256 bate com o manifesto e o Last-Modified
    remoto é o registrado. `cabecalhos_remotos=None` significa que o HEAD falhou:
    nesse caso confia no hash local e pula com aviso.
    """
    if entrada is None:
        log.info("%s: sem entrada no manifesto", caminho.name)
        return True
    if not caminho.exists():
        log.info("%s: arquivo ausente no disco", caminho.name)
        return True
    if sha256_arquivo(caminho) != entrada["sha256"]:
        log.warning("%s: SHA-256 local difere do manifesto (arquivo alterado)", caminho.name)
        return True
    if cabecalhos_remotos is None:
        log.warning("%s: HEAD falhou; usando a cópia local (hash confere)", caminho.name)
        return False
    remoto = cabecalhos_remotos.get("Last-Modified")
    if remoto != entrada.get("last_modified"):
        log.warning(
            "%s: a ANAC republicou o arquivo (Last-Modified %s -> %s)",
            caminho.name,
            entrada.get("last_modified"),
            remoto,
        )
        return True
    return False


def agora_utc() -> str:
    """Instante atual em ISO 8601 UTC, sem frações de segundo."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------- rede


def _requisicao(url: str, metodo: str = "GET") -> urllib.request.Request:
    return urllib.request.Request(url, method=metodo, headers={"User-Agent": config.USER_AGENT})


def com_retry[T](acao: Callable[[], T], descricao: str, esperar: Callable[[float], None] = time.sleep) -> T:
    """Executa `acao` com backoff exponencial em erro de rede ou HTTP 5xx; 4xx falha na hora."""
    esperas = config.BACKOFF_SEGUNDOS
    for tentativa in range(len(esperas) + 1):
        try:
            return acao()
        except urllib.error.HTTPError as e:
            if e.code < 500:
                raise ErroPermanente(f"{descricao}: HTTP {e.code} {e.reason} (URL errada?)") from e
            erro: Exception = e
        except ERROS_DE_REDE as e:
            erro = e
        if tentativa == len(esperas):
            raise erro
        log.warning(
            "%s: %s; nova tentativa em %s s (%d/%d)",
            descricao, erro, esperas[tentativa], tentativa + 1, len(esperas),
        )
        esperar(esperas[tentativa])
    raise AssertionError("inalcançável")


def head(url: str, abrir: Abrir = urllib.request.urlopen) -> dict[str, str]:
    """Faz HEAD na URL e devolve os cabeçalhos da resposta."""
    with abrir(_requisicao(url, "HEAD"), timeout=config.TIMEOUT_SEGUNDOS) as resp:
        return dict(resp.headers.items())


def baixar(fonte: Fonte, abrir: Abrir = urllib.request.urlopen) -> dict[str, Any]:
    """Baixa em streaming para `.part`, calcula o SHA-256 e só então renomeia.

    Devolve a entrada do manifesto para o arquivo baixado.
    """
    fonte.caminho.parent.mkdir(parents=True, exist_ok=True)
    parcial = fonte.caminho.with_name(fonte.caminho.name + ".part")
    h = hashlib.sha256()
    tamanho = 0
    try:
        with abrir(_requisicao(fonte.url), timeout=config.TIMEOUT_SEGUNDOS) as resp, parcial.open("wb") as f:
            last_modified = resp.headers.get("Last-Modified")
            esperado = resp.headers.get("Content-Length")
            while bloco := resp.read(config.TAMANHO_BLOCO):
                f.write(bloco)
                h.update(bloco)
                tamanho += len(bloco)
        if esperado is not None and int(esperado) != tamanho:
            raise http.client.IncompleteRead(b"", int(esperado) - tamanho)
        os.replace(parcial, fonte.caminho)
    finally:
        parcial.unlink(missing_ok=True)
    return {
        "nome": fonte.nome,
        "url": fonte.url,
        "caminho": fonte.caminho.relative_to(config.RAIZ).as_posix(),
        "baixado_em": agora_utc(),
        "tamanho_bytes": tamanho,
        "sha256": h.hexdigest(),
        "last_modified": last_modified,
    }


# --------------------------------------------------------------------------- carga da raw

PRIMEIRA_COLUNA_VRA = "Sigla ICAO Empresa Aérea"
PRIMEIRA_COLUNA_AERODROMOS = "Código OACI"

# Opções fixas, sem depender do sniffer. quote='' porque nenhum arquivo usa aspas como
# delimitador de campo: as que aparecem são literais (`"DIAGORAS"` no nome de aeroporto,
# segundos em `09°52'06"S`). Sem ignore_errors; e como o DuckDB tolera um `;` sobrando no
# fim da linha, o número de separadores é conferido em Python antes (conferir_arquivo).
ENCODING_VRA = "utf-8-sig"  # BOM, se aparecer, é descartado
ENCODING_AERODROMOS = "latin-1"
OPCOES_VRA = "delim=';', header=true, all_varchar=true, quote='', escape='', encoding='utf-8'"
OPCOES_AERODROMOS = (
    "delim=';', header=true, skip=1, all_varchar=true, quote='', escape='', encoding='latin-1'"
)


class ErroCarga(Exception):
    """Arquivo fora do formato esperado: a carga para em vez de se adaptar."""


def instante_carga() -> datetime:
    """Instante da carga em UTC, sem fuso (coluna TIMESTAMP), sem frações de segundo."""
    return datetime.now(UTC).replace(microsecond=0, tzinfo=None)


def conferir_arquivo(caminho: Path, encoding: str, pular: int = 0) -> list[str]:
    """Lê o CSV uma vez: devolve o cabeçalho e exige que toda linha de dados tenha o mesmo
    número de `;` que ele. Com quote='', todo `;` é separador, então a contagem é exata.

    `pular` = linhas antes do cabeçalho. Os números de linha no erro são os do arquivo.
    """
    with caminho.open(encoding=encoding, newline="\n") as f:
        for _ in range(pular):
            f.readline()
        cabecalho = f.readline().rstrip("\r\n")
        esperado = cabecalho.count(";")
        for numero, linha in enumerate(f, start=pular + 2):
            encontrado = linha.count(";")
            if encontrado != esperado:
                raise ErroCarga(
                    f"{caminho.name}: linha {numero} tem {encontrado} separadores ';', esperado {esperado}"
                )
    return cabecalho.split(";")


def conferir_cabecalhos(arquivos: list[Path]) -> list[str]:
    """Confere cada arquivo do VRA e exige o cabeçalho do primeiro em todos; devolve esse cabeçalho."""
    referencia = conferir_arquivo(arquivos[0], ENCODING_VRA)
    for arquivo in arquivos[1:]:
        cabecalho = conferir_arquivo(arquivo, ENCODING_VRA)
        if cabecalho == referencia:
            continue
        ausentes = [c for c in referencia if c not in cabecalho]
        novas = [c for c in cabecalho if c not in referencia]
        detalhe = f"ausentes: {ausentes}; novas: {novas}" if ausentes or novas else "mesmas colunas em outra ordem"
        raise ErroCarga(f"{arquivo.name}: cabeçalho difere de {arquivos[0].name} ({detalhe})")
    return referencia


def _criar_tabela(
    con: duckdb.DuckDBPyConnection,
    tabela: str,
    arquivos: list[Path],
    opcoes: str,
    primeira_coluna: str,
    carregado_em: datetime,
) -> dict[str, int]:
    """Recria `tabela` com exatamente `arquivos` + linhagem; devolve linhas por arquivo."""
    leitura = f"read_csv($arquivos, {opcoes}, filename=true)"
    parametros = {"arquivos": [a.as_posix() for a in arquivos]}

    colunas = [d[0] for d in con.execute(f"SELECT * FROM {leitura} LIMIT 0", parametros).description]
    if colunas[0] != primeira_coluna:
        raise ErroCarga(f"{tabela}: primeira coluna é {colunas[0]!r}, esperado {primeira_coluna!r}")

    con.execute(
        f"""
        CREATE OR REPLACE TABLE {tabela} AS
        SELECT * EXCLUDE (filename),
               parse_filename(filename) AS _arquivo_origem,
               $carregado_em::TIMESTAMP AS _carregado_em
        FROM {leitura}
        """,
        parametros | {"carregado_em": carregado_em},
    )
    contagens = dict(con.execute(f"SELECT _arquivo_origem, count(*) FROM {tabela} GROUP BY ALL").fetchall())
    return {a.name: contagens.get(a.name, 0) for a in arquivos}


def carregar_vra(
    con: duckdb.DuckDBPyConnection, arquivos: list[Path], carregado_em: datetime | None = None
) -> dict[str, int]:
    """Recria `raw.vra` com os CSVs mensais do VRA, depois de conferir os cabeçalhos."""
    if not arquivos:
        raise ErroCarga("raw.vra: nenhum arquivo para carregar")
    conferir_cabecalhos(arquivos)
    return _criar_tabela(
        con, "raw.vra", arquivos, OPCOES_VRA, PRIMEIRA_COLUNA_VRA, carregado_em or instante_carga()
    )


def carregar_aerodromos(
    con: duckdb.DuckDBPyConnection, arquivo: Path, carregado_em: datetime | None = None
) -> dict[str, int]:
    """Recria `raw.aerodromos` (Latin-1, cabeçalho na linha 2)."""
    conferir_arquivo(arquivo, ENCODING_AERODROMOS, pular=1)
    return _criar_tabela(
        con,
        "raw.aerodromos",
        [arquivo],
        OPCOES_AERODROMOS,
        PRIMEIRA_COLUNA_AERODROMOS,
        carregado_em or instante_carga(),
    )


# --------------------------------------------------------------------------- orquestração


@dataclass
class Resumo:
    """Contagem do resultado de uma execução."""

    baixados: int = 0
    pulados: int = 0
    falhas: int = 0


def executar(
    lista: list[Fonte] | None = None,
    caminho_manifesto: Path = config.CAMINHO_MANIFESTO,
    abrir: Abrir = urllib.request.urlopen,
) -> Resumo:
    """Baixa sequencialmente o que for preciso e atualiza o manifesto a cada arquivo."""
    lista = fontes() if lista is None else lista
    manifesto = ler_manifesto(caminho_manifesto)
    resumo = Resumo()

    for i, fonte in enumerate(lista, start=1):
        prefixo = f"[{i}/{len(lista)}] {fonte.nome}"
        entrada = manifesto.get(fonte.nome)
        try:
            cabecalhos: dict[str, str] | None = None
            if entrada is not None and fonte.caminho.exists():
                try:
                    cabecalhos = com_retry(lambda: head(fonte.url, abrir), f"HEAD {fonte.nome}")
                except (ErroPermanente, *ERROS_DE_REDE) as e:
                    log.warning("%s: HEAD falhou (%s)", prefixo, e)

            if not precisa_baixar(entrada, fonte.caminho, cabecalhos):
                log.info("%s: pulado (já atualizado)", prefixo)
                resumo.pulados += 1
                continue

            log.info("%s: baixando %s", prefixo, fonte.url)
            inicio = time.monotonic()
            nova = com_retry(lambda: baixar(fonte, abrir), f"GET {fonte.nome}")
            manifesto[fonte.nome] = nova
            gravar_manifesto(caminho_manifesto, manifesto)
            log.info(
                "%s: baixado (%.1f MB em %.1f s)",
                prefixo, nova["tamanho_bytes"] / 1e6, time.monotonic() - inicio,
            )
            resumo.baixados += 1
        except (ErroPermanente, *ERROS_DE_REDE) as e:
            log.error("%s: FALHA: %s", prefixo, e)
            resumo.falhas += 1

    return resumo


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    resumo = executar()
    print(f"Resumo: {resumo.baixados} baixados, {resumo.pulados} pulados, {resumo.falhas} falhas")
    if resumo.falhas:
        log.error("download com falhas: carga da raw não executada")
        return 1

    # Exatamente a lista de fontes(), nunca um glob da pasta.
    lista = fontes()
    vra = [f.caminho for f in lista if f.caminho.parent == config.DIR_RAW_VRA]
    (aerodromos,) = [f.caminho for f in lista if f.caminho.parent == config.DIR_RAW_AERODROMOS]
    carregado_em = instante_carga()  # um instante para a carga inteira
    try:
        with db.conectar() as con:
            contagens = carregar_vra(con, vra, carregado_em)
            contagens |= carregar_aerodromos(con, aerodromos, carregado_em)
    except (ErroCarga, duckdb.Error) as e:
        log.error("carga da raw: FALHA: %s", e)
        return 1

    for nome, linhas in contagens.items():
        log.info("%s: %d linhas carregadas", nome, linhas)
    log.info("raw.vra: %d linhas; raw.aerodromos: %d linhas", sum(contagens[a.name] for a in vra),
             contagens[aerodromos.name])
    return 0


if __name__ == "__main__":
    sys.exit(main())
