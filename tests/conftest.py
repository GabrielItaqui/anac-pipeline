"""Fixtures compartilhadas pelos testes."""

import urllib.request

import pytest


class AcessoARede(Exception):
    """Um teste tentou acessar a internet."""


def _proibido(*args, **kwargs):
    raise AcessoARede("teste tentou acessar a rede")


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch):
    """Faz qualquer acesso via urllib falhar: nenhum teste baixa nada.

    Também bloqueia `OpenerDirector.open`, que o urlopen original usa por dentro: os
    parâmetros `abrir=urllib.request.urlopen` do pipeline guardam a função original
    no momento da definição e escapariam de um patch só em `urlopen`.
    """
    monkeypatch.setattr(urllib.request, "urlopen", _proibido)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", _proibido)
