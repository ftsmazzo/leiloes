from datetime import datetime, timezone

from app.leitura import resumir_leitura

AGORA = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)


def test_conta_so_avaliacao_da_semana():
    cru = [
        '{"avaliado_em": "2026-11-01T10:00:00Z"}',
        '{"avaliado_em": "2026-11-01T11:00:00Z", "docs_limitados": true}',
        '{"avaliado_em": "2026-10-01T11:00:00Z", "docs_limitados": true}',
        '{"cidade": "Salvador"}',
        "nao-json",
    ]
    out = resumir_leitura(cru, agora=AGORA)
    assert out["com_peca"] == 1
    assert out["sem_peca"] == 1
    assert out["ocr_vazio"] == 0
    assert out["dias"] == 7


def test_ocr_vazio_nao_conta_trecho_curto():
    vazio = '{"avaliado_em": "2026-11-02T08:00:00Z", "docs_limitados": true, "docs": [{"scanned": true, "chars": 0}]}'
    curto = '{"avaliado_em": "2026-11-02T08:00:00Z", "docs_limitados": true, "docs": [{"scanned": true, "chars": 12, "ocr_curto": true}]}'
    sem_texto = '{"avaliado_em": "2026-11-02T08:00:00Z", "docs_limitados": true, "edital_sem_texto": true}'
    out = resumir_leitura([vazio, curto, sem_texto], agora=AGORA)
    assert out["ocr_vazio"] == 2
    assert out["sem_peca"] == 3


if __name__ == "__main__":
    test_conta_so_avaliacao_da_semana()
    test_ocr_vazio_nao_conta_trecho_curto()
    print("ok")
