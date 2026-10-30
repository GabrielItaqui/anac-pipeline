"""Configuração central: URLs das fontes, caminhos locais e parâmetros de rede."""

from pathlib import Path

# Raiz do projeto, independente do diretório de onde o comando é executado.
RAIZ = Path(__file__).resolve().parent.parent

# Fontes
URL_VRA = "https://siros.anac.gov.br/siros/registros/diversos/vra/2025/VRA_2025_{mes:02d}.csv"
MESES = range(1, 13)
URL_AERODROMOS = (
    "https://sistemas.anac.gov.br/dadosabertos/Aerodromos/Aer%C3%B3dromos%20P%C3%BAblicos/"
    "Lista%20de%20aer%C3%B3dromos%20p%C3%BAblicos/AerodromosPublicos.csv"
)

# Caminhos
DIR_DATA = RAIZ / "data"
DIR_RAW_VRA = DIR_DATA / "raw" / "vra"
DIR_RAW_AERODROMOS = DIR_DATA / "raw" / "aerodromos"
CAMINHO_MANIFESTO = DIR_DATA / "manifesto.json"
CAMINHO_BANCO = DIR_DATA / "anac.duckdb"
DIR_SQL = RAIZ / "sql"

# Rede
TIMEOUT_SEGUNDOS = 60
# 3 novas tentativas após a primeira falha, esperando 2 s, 4 s e 8 s antes de cada uma.
TENTATIVAS = 3
BACKOFF_SEGUNDOS = tuple(2 * 2**i for i in range(TENTATIVAS))
USER_AGENT = "anac-pipeline/0.1 (projeto academico; dados abertos ANAC)"
TAMANHO_BLOCO = 1024 * 1024  # 1 MiB por leitura no streaming
