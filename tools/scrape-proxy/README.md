# Scrape proxy (casa)

O EasyPanel (IP de datacenter) leva bloqueio em Calil/Vegas. Este processo roda no **PC** e faz o GET com o IP residencial — mesmo padrão do BeautyOS (Funnel ou WireGuard).

## Subir no Windows

```bat
cd tools\scrape-proxy
set TOKEN=troque-por-um-segredo
node server.mjs
```

Health: `http://127.0.0.1:8788/health`

## Expor para o EasyPanel

**Opção A — Tailscale Funnel** (preferida no BeautyOS):

```bat
tailscale funnel 8788
```

No serviço `backend` do EasyPanel:

```
SCRAPE_PROXY_URL=https://seu-host.tailxxxxx.ts.net
SCRAPE_PROXY_TOKEN=troque-por-um-segredo
```

**Opção B — WireGuard** (`docs` do BeautyOS): proxy escuta em `10.66.66.1:8788`; a VPS chama esse IP pelo túnel.

## Contrato

`POST /fetch` com `Authorization: Bearer <TOKEN>` e body `{"url":"https://www.calilleiloes.com.br/..."}`.

Só aceita hosts Calil e Vegas. Resposta: `{"status":200,"url":"...","text":"<html>..."}`.

## Segurança

- Não use `0.0.0.0/0` no peer da VPS.
- Troque o TOKEN.
- Deixe o PC ligado (ou Startup) enquanto precisar atualizar o catálogo.
