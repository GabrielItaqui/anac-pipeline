"""Testes do dashboard: a regra "lê só dos marts" checada no código-fonte.

Não importa o app (nem o Streamlit): a CI não instala o grupo `dashboard`.
"""

import re

from pipeline import config

FONTE = (config.RAIZ / "dashboard" / "app.py").read_text(encoding="utf-8")


def test_toda_consulta_le_do_schema_marts():
    tabelas = re.findall(r"\b(?:FROM|JOIN)\s+([\w.{}]+)", FONTE)
    assert tabelas == ["marts.{nome}"]


def test_nao_cita_refined_nem_raw():
    assert re.findall(r"\b(?:refined|raw)\.", FONTE) == []


def test_so_um_select_no_app():
    # A leitura passa toda por ler_mart: um único SELECT no arquivo.
    assert len(re.findall(r"\bSELECT\b", FONTE)) == 1


def test_nao_agrega_em_python():
    # Sem soma, média, mediana ou agrupamento na tela: o cálculo fica nos marts.
    assert re.findall(r"\.(?:sum|mean|median|groupby|agg|count|pivot_table)\(", FONTE) == []
