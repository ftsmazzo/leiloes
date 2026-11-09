# Deploy no Easy Panel

Tudo roda na implantação: você conecta o repositório, o Easy Panel faz o build e sobe os serviços. Configure só as variáveis de ambiente no painel.

## Serviços

- **Backend:** Dockerfile `Dockerfile.backend`, contexto = raiz do repo, porta 8000.
- **Frontend:** Dockerfile `Dockerfile.frontend`, contexto = raiz do repo, porta 3000.
- **PostgreSQL:** crie um banco no Easy Panel (ou use um externo) e use a URL que o painel fornece.

## Variáveis de ambiente (no painel do Easy Panel)

- **Backend:** `DATABASE_URL` — URL normal do PostgreSQL, por exemplo:  
  `postgresql://usuario:senha@host:5432/nome_do_banco`  
  (a mesma URL que o Easy Panel ou seu provedor de banco mostra.)
- **Frontend:** `NEXT_PUBLIC_API_URL` — URL pública do backend (ex.: `https://leiloes-backend.xxx.easypanel.host`).  
  **Importante:** no Next.js essa variável é usada no **build**. Se o painel tiver "Build args" ou "Variáveis de build", defina `NEXT_PUBLIC_API_URL` também lá com a mesma URL. Depois de alterar, faça **Implantar** de novo no frontend para que o build use a URL correta.

Nada de shell: as variáveis são definidas na interface do Easy Panel em cada serviço.

## Calil e Vegas (proxy na casa)

O IP do Easy Panel costuma ser bloqueado nessas duas fontes. No PC rode `tools/scrape-proxy` (ver README na pasta) e no **backend** defina:

- `SCRAPE_PROXY_URL` — URL do Funnel/túnel (sem `/fetch` no final)
- `SCRAPE_PROXY_TOKEN` — o mesmo `TOKEN` do processo no PC

Zuk, Mega, Lance e TRT5 seguem direto do VPS.
