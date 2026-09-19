import os

from app.infosimples import consultar_infosimples, infosimples_disponivel, merge_infosimples

CNJ_TJSP = "1001610-20.2023.8.26.0506"
CNJ_TRT = "0001129-55.2014.5.05.0464"

# Formato real de resposta (verificado ao vivo em 2026-09-19 contra processo
# real do TJSP) — só os campos que usamos, o resto omitido.
RESPOSTA_REAL = {
    "code": 200,
    "data": [
        {
            "processos": [
                {
                    "processo": CNJ_TJSP,
                    "foro": "Foro de Ribeirão Preto",
                    "vara": "3ª Vara Cível",
                    "valor_acao": "R$ 1.719,14",
                    "normalizado_valor_acao": 1719.14,
                    "ultimas_movimentacoes": [],
                    "peticoes_diversas": [
                        {"data": "19/09/2023", "tipo": "Pedido de Penhora de Imóvel"},
                        {"data": "17/07/2026", "tipo": "Manifestação do Perito"},
                    ],
                }
            ]
        }
    ],
}


def test_infosimples_disponivel_depende_do_token(monkeypatch):
    monkeypatch.delenv("INFOSIMPLES_API_TOKEN", raising=False)
    assert infosimples_disponivel() is False
    monkeypatch.setenv("INFOSIMPLES_API_TOKEN", "abc")
    assert infosimples_disponivel() is True


def test_sem_token_nao_chama_rede(monkeypatch):
    monkeypatch.delenv("INFOSIMPLES_API_TOKEN", raising=False)

    def fake_fetch(_url, _params):
        raise AssertionError("não deveria chamar a rede sem token")

    assert consultar_infosimples(CNJ_TJSP, fetch=fake_fetch) == {}


def test_so_atende_tjsp_por_ora(monkeypatch):
    monkeypatch.setenv("INFOSIMPLES_API_TOKEN", "abc")

    def fake_fetch(_url, _params):
        raise AssertionError("TRT não é rota validada — não deveria chamar")

    assert consultar_infosimples(CNJ_TRT, fetch=fake_fetch) == {}


def test_extrai_valor_da_causa_e_peticoes_da_resposta_real(monkeypatch):
    monkeypatch.setenv("INFOSIMPLES_API_TOKEN", "abc")
    out = consultar_infosimples(CNJ_TJSP, fetch=lambda _u, _p: RESPOSTA_REAL)
    assert out["infosimples"] == "ok"
    assert out["infosimples_valor_causa"] == 1719.14
    assert out["infosimples_foro"] == "Foro de Ribeirão Preto"
    assert len(out["infosimples_peticoes_recentes"]) == 2
    assert out["infosimples_consultado_para"] == CNJ_TJSP


def test_resposta_sem_processo_nao_inventa(monkeypatch):
    monkeypatch.setenv("INFOSIMPLES_API_TOKEN", "abc")
    out = consultar_infosimples(CNJ_TJSP, fetch=lambda _u, _p: {"code": 200, "data": []})
    assert out == {"infosimples": "nao_encontrado"}


def test_falha_de_rede_nao_quebra(monkeypatch):
    monkeypatch.setenv("INFOSIMPLES_API_TOKEN", "abc")

    def fake_fetch(_u, _p):
        raise ConnectionError("timeout")

    assert consultar_infosimples(CNJ_TJSP, fetch=fake_fetch) == {"infosimples": "indisponivel"}


def test_merge_infosimples_so_troca_chaves_presentes():
    base = {"score": 50, "infosimples_foro": "Foro antigo"}
    out = merge_infosimples(base, {"infosimples_valor_causa": 1000.0})
    assert out["score"] == 50
    assert out["infosimples_foro"] == "Foro antigo"
    assert out["infosimples_valor_causa"] == 1000.0


if __name__ == "__main__":
    class _Monkeypatch:
        def setenv(self, k, v):
            os.environ[k] = v

        def delenv(self, k, raising=False):
            os.environ.pop(k, None)

    mp = _Monkeypatch()
    test_infosimples_disponivel_depende_do_token(mp)
    test_sem_token_nao_chama_rede(mp)
    test_so_atende_tjsp_por_ora(mp)
    test_extrai_valor_da_causa_e_peticoes_da_resposta_real(mp)
    test_resposta_sem_processo_nao_inventa(mp)
    test_falha_de_rede_nao_quebra(mp)
    test_merge_infosimples_so_troca_chaves_presentes()
    print("ok")
