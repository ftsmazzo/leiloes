# CONTEXTO — venda-epis e Leilões

Este arquivo vale para **qualquer agente, de qualquer modelo**, nos dois produtos:

| Produto | Pasta | GitHub |
|---------|--------|--------|
| Pré-orçamento HDM | `C:\Users\anjo_\OneDrive\Projetos-FabriaIA\venda-epis` | [ftsmazzo/venda-epis](https://github.com/ftsmazzo/venda-epis) |
| Imóveis em leilão | `C:\Users\anjo_\OneDrive\Projetos-FabriaIA\Leilões` | [ftsmazzo/leiloes](https://github.com/ftsmazzo/leiloes) |

Conta GitHub de trabalho: **ftsmazzo**. Não usar `fredmazzo-ia`.

São **dois sistemas**. Mesmo padrão de trabalho. Código e deploy separados.

Leia isto **antes** de implementar.

---

## 1. Como trabalhamos (GitHub)

### Issues

Crie Issues para **todas** as tarefas. Cada Issue leva **um** rótulo:

- `Correção` — bug ou comportamento errado
- `Melhoria` — melhorar o que já existe
- `Nova função` — capacidade nova

Passos **curtos**. Uma Issue = um recorte que cabe num PR. Se a busca “não faz sentido”, isso vira várias Issues (Calil, Vegas, filtro, telas por base) — não um epic único.

### Pull Requests

`main` é a esteira de deploy. Ninguém empurra feature direto nela.

Em **todo** PR:

1. Mencione a Issue (`Closes #N` ou `Relates #N`).
2. Explique o que mudou.
3. Descreva como foi validado (comando, URL, caso de teste).
4. Registre riscos, limitações e próximos passos.

Modelo:

```markdown
## Issue
Closes #N

## O que mudou
- …

## Como foi validado
- …

## Riscos, limitações e próximos passos
- …
```

### Dois produtos

- Trabalho em venda-epis **não** altera Leilões (e o inverso).
- Não misture commit de pedido de leilão com orçamento de EPI.

---

## 2. Motion (UI)

Fonte: [kylezantos/design-motion-principles](https://github.com/kylezantos/design-motion-principles)  
(o URL `kylezantos/design-principles` não existe; use este.)

Estes painéis são **dashboard / ferramenta de trabalho**. Peso:

- Primário: **Emil Kowalski** (restrição, velocidade)
- Secundário: **Jakub Krehel** (polimento)
- Jhey: só empty state pontual — não no fluxo diário

Obrigatório na interface:

- Lazy loading quando a lista/imagem está fora da dobra
- Skeleton no lugar do conteúdo (mesmo tamanho, sem pulsar em loop)
- Entrada/saída suaves em modal, card que aparece/some, troca de tela
- Progresso em botão/ação longa (scrape, buscar, OCR)
- Feedback da ação (sucesso, erro, vazio) — não sumir o clique
- Transição consistente (180–220ms, `transform`/`opacity`, não `width`/`top`)

Proibido (AI-slop):

- `animate-pulse` em badge/CTA
- `hover:scale` em todo card
- stagger em toda lista
- spring com bounce em menu/modal
- fade-in idêntico em cada bloco da página
- animar texto estático e nav no mount
- ignorar `prefers-reduced-motion`

Antes de fechar UI: revisar como designer sênior. Se parecer brusco, travado, genérico ou amador — corrige no mesmo PR.

---

## 3. Esteira de qualidade (antes da `main`)

Nada entra em `main` sem o CI do repositório passar.

**Incluir agora** (faz sentido nestes repos):

| Área | Escolha | Por quê |
|------|---------|---------|
| Testes | unitários (pytest / `python test_*.py`) | já existem casos |
| Lint Python | Ruff, quando a Issue de lint abrir | barato, um só |
| Lint JS/TS | ESLint no Next do Leilões; Biome só se o front crescer | não dois linters |
| E2E | Playwright no fluxo feliz, Issue própria | scrape/e-mail são frágeis |
| Segurança | rate limit + revisão no PR de API pública | `/run-scrape` e pedidos sem auth |
| Arquitetura | API ≠ UI; DRY só depois da 2ª cópia | sem framework novo |

**Não instalar agora** (overengineering / duplicata):

- Sentry **e** Datadog **e** New Relic juntos → Issue: só **Sentry** (depois OpenTelemetry se precisar)
- Stryker, Knip, Endtest, arch-contract, Commitlint — só com Issue e dor real
- Codecov quando houver cobertura estável, não no dia 1

**Jurídico:** termos de uso e privacidade = Issue `Nova função` para o humano/advogado. O agente **não** marca como aprovado.

Arquitetura:

- Evitar overengineering e bottleneck (scrape síncrono no request HTTP é o gargalo atual do Leilões)
- Componentizar o que a tela já repete
- Não reconstruir AdminLTE/Next/caixa de e-mail que já existem
- Backend e frontend separados (Leilões já; venda-epis é FastAPI + `static/` — não fundir os dois produtos)

---

## 4. Recorte de produto

### venda-epis

HDM: e-mail/WhatsApp → conferir texto/foto → buscar ML/Serper → montar orçamento. Sem fechar cego. Sem estoque.

### Leilões

Pedido → conferir filtro → buscar **lotes já persistidos** (Calil, Vegas, demo) → dossiê. Scrape é job, não a busca.

A busca “sem sentido” hoje: filtro frágil + scrapers HTML + lotes que não atualizam. Ordem:

1. Revisar scraper Calil  
2. Revisar scraper Vegas  
3. Upsert de lote no re-scrape  
4. Busca com filtro de verdade + telas por base  
5. Motion no catálogo e no pedido  

Não inventar dezenas de fontes no mesmo PR. Nova fonte: Issue em [ftsmazzo/leiloes#16](https://github.com/ftsmazzo/leiloes/issues/16), classe `BaseScraper` e uma linha em `backend/app/scrapers/registry.py`.

---

## 5. Segurança operacional

- Não commitar `.env`, senha de app, OpenRouter, Gmail
- Não escrever exploit, bypass de login/CAPTCHA, scrape autenticado
- Páginas públicas + httpx/BS4; se o site bloquear, documentar na Issue — não contornar
