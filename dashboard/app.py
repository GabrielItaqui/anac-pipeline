"""Dashboard (opcional): painel Streamlit sobre os marts.

Lê só do schema `marts` e não calcula nada: toda regra de negócio fica nos .sql dos marts.
Aqui só se ordena, renomeia e formata para exibição.

Uso: uv run --group dashboard streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

import duckdb
import streamlit as st

# O `streamlit run` põe só dashboard/ no sys.path; a raiz é necessária para importar o pipeline.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import config  # noqa: E402

URL_REPOSITORIO = "https://github.com/GabrielItaqui/anac-pipeline"

COMANDOS_PIPELINE = """uv sync
uv run python -m pipeline.ingestao
uv run python -m pipeline.transformacao
uv run python -m pipeline.marts"""

# Nomes curtos para exibição; a base traz a razão social (ex.: "TAM LINHAS AÉREAS S.A.").
NOMES_EMPRESAS = {
    "ABJ": "ATA Aerotáxi Abaeté",
    "ACN": "Azul Conecta",
    "AZU": "Azul",
    "GLO": "GOL",
    "PTB": "Passaredo",
    "SID": "Sideral",
    "TAM": "LATAM (TAM)",
}

PERCENTUAL = "%.2f%%"


def ler_mart(nome: str):
    """Lê o mart inteiro, como está: a única forma de ler dados neste app."""
    with duckdb.connect(str(config.CAMINHO_BANCO), read_only=True) as con:
        return con.execute(f"SELECT * FROM marts.{nome}").df()


def inteiro(n) -> str:
    """804857 -> '804.857'."""
    return f"{n:,}".replace(",", ".")


def decimal(x, casas: int = 2) -> str:
    """85.79 -> '85,79'."""
    return f"{x:.{casas}f}".replace(".", ",")


def com_nome_empresa(df):
    """Troca a razão social pelo nome curto, quando houver."""
    return df.assign(empresa=df["empresa_icao"].map(NOMES_EMPRESAS).fillna(df["empresa_nome"]))


st.set_page_config(page_title="Pontualidade aérea 2025", layout="wide")
st.title("Pontualidade da aviação doméstica brasileira em 2025")
st.write(
    "Quais empresas, aeroportos, horários e estados têm os voos mais pontuais "
    "(e os mais cancelados) na aviação doméstica brasileira em 2025?"
)

try:
    kpis = ler_mart("kpis")
    mensal = ler_mart("voos_mensais")
    pontualidade_empresa = ler_mart("pontualidade_por_empresa")
    cancelamento_empresa = ler_mart("cancelamento_por_empresa")
    por_hora = ler_mart("pontualidade_por_hora")
    por_uf = ler_mart("pontualidade_por_uf")
    rotas = ler_mart("rotas_mais_voadas")
    por_aeroporto = ler_mart("atraso_por_aeroporto")
except duckdb.Error as e:
    st.warning("Banco ou marts não encontrados. Rode o pipeline primeiro (veja o README):")
    st.code(COMANDOS_PIPELINE, language="powershell")
    st.caption(f"Detalhe: {e}")
    st.stop()

st.caption("Voos domésticos (tipo N). Pontual = chegada com até 15 min de atraso (OTP15).")

# 1. KPIs
# to_dict mantém o tipo de cada coluna (iloc[0] converteria os inteiros para float).
k = kpis.to_dict("records")[0]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Voos programados", inteiro(k["voos_programados"]), border=True)
c2.metric(
    "Pontualidade",
    f"{decimal(k['pontualidade'])}%",
    help=f"Sobre {inteiro(k['voos_avaliados'])} voos avaliados",
    border=True,
)
c3.metric(
    "Taxa de cancelamento",
    f"{decimal(k['taxa_cancelamento'])}%",
    help=f"{inteiro(k['voos_cancelados'])} voos cancelados",
    border=True,
)
c4.metric(
    "Atraso mediano de chegada",
    f"{decimal(k['atraso_mediano_chegada_min'], 0)} min",
    help="Negativo = chegou antes do previsto",
    border=True,
)
c5, c6, c7, c8 = st.columns(4)
c5.metric("Voos realizados", inteiro(k["voos_realizados"]), border=True)
c6.metric("Realizados sem horário previsto", inteiro(k["voos_sem_previsao"]), border=True)
c7.metric("Empresas", inteiro(k["empresas"]), border=True)
c8.metric("Aeroportos de origem", inteiro(k["aeroportos_origem"]), border=True)

# 2. Por mês
st.header("Por mês")
# Mês como texto "MM/AAAA": ordena certo dentro do ano e não estica o eixo como uma data.
mensal = mensal.assign(Mês=mensal["mes"].dt.strftime("%m/%Y")).rename(
    columns={"pontualidade": "Pontualidade (%)", "taxa_cancelamento": "Cancelamento (%)"}
)
col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Pontualidade")
    st.line_chart(mensal, x="Mês", y="Pontualidade (%)")
with col_b:
    st.subheader("Taxa de cancelamento")
    st.line_chart(mensal, x="Mês", y="Cancelamento (%)", color="#d62728")

# 3. Por empresa (só empresas com pelo menos 1.000 voos no ano, regra do mart)
st.header("Por empresa")
st.caption("Só empresas com pelo menos 1.000 voos no ano.")
col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Pontualidade")
    st.bar_chart(
        com_nome_empresa(pontualidade_empresa).rename(columns={"pontualidade": "Pontualidade (%)"}),
        x="empresa",
        y="Pontualidade (%)",
        x_label="Pontualidade (%)",
        y_label="",
        horizontal=True,
        sort="-Pontualidade (%)",
    )
with col_b:
    st.subheader("Taxa de cancelamento")
    st.bar_chart(
        com_nome_empresa(cancelamento_empresa).rename(columns={"taxa_cancelamento": "Cancelamento (%)"}),
        x="empresa",
        y="Cancelamento (%)",
        x_label="Cancelamento (%)",
        y_label="",
        horizontal=True,
        sort="-Cancelamento (%)",
        color="#d62728",
    )

# 4. Por hora do dia
st.header("Por hora do dia")
st.caption("Hora da partida prevista (horário de Brasília).")
# Hora como texto "00h" a "23h": as barras mostram as 24 horas, na ordem do mart.
st.bar_chart(
    por_hora.assign(Hora=por_hora["hora"].map("{:02d}h".format)).rename(
        columns={"pontualidade": "Pontualidade (%)"}
    ),
    x="Hora",
    y="Pontualidade (%)",
    sort=False,
)

# 5. Tabelas
st.header("Por UF de origem")
st.dataframe(
    por_uf,
    hide_index=True,
    column_config={
        "uf": "UF",
        "voos_programados": st.column_config.NumberColumn("Voos programados", format="localized"),
        "voos_avaliados": st.column_config.NumberColumn("Voos avaliados", format="localized"),
        "pontualidade": st.column_config.NumberColumn("Pontualidade", format=PERCENTUAL),
    },
)

st.header("Rotas mais voadas")
st.dataframe(
    rotas,
    hide_index=True,
    column_config={
        "origem_icao": "Origem",
        "destino_icao": "Destino",
        "voos_realizados": st.column_config.NumberColumn("Voos realizados", format="localized"),
        "voos_avaliados": st.column_config.NumberColumn("Voos avaliados", format="localized"),
        "pontualidade": st.column_config.NumberColumn("Pontualidade", format=PERCENTUAL),
    },
)

st.header("Atraso por aeroporto de origem")
st.caption("Só aeroportos com pelo menos 1.000 voos avaliados no ano.")
st.dataframe(
    por_aeroporto,
    hide_index=True,
    column_config={
        "origem_icao": "Código",
        "aeroporto_nome": "Aeroporto",
        "uf": "UF",
        "voos_avaliados": st.column_config.NumberColumn("Voos avaliados", format="localized"),
        "pontualidade": st.column_config.NumberColumn("Pontualidade", format=PERCENTUAL),
        "atraso_mediano_partida_min": st.column_config.NumberColumn(
            "Atraso mediano de partida (min)", format="%.0f"
        ),
    },
)

st.divider()
st.caption(
    f"Fonte: ANAC – Voo Regular Ativo (VRA) 2025 e lista de aeródromos públicos. "
    f"Código e regras: [{URL_REPOSITORIO}]({URL_REPOSITORIO})"
)
