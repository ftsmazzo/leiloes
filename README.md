# Leilões — catálogo de trabalho

Catálogo que junta lotes já publicados de Calil, Vegas, Zuk, Mega, Grupo Lance e TRT5. A busca é no que está no banco. O scrape é um job. O dossiê aponta se vale aprofundar a leitura. Não dá lance e não é palavra final.

Sem matrícula, laudo ou penhora na página pública, o veredito fica **Sem norte**. Isso vale para o TRT5: o edital unificado público vira um lote por imóvel, e o texto daquele bloco não vira matrícula. O sistema não entra em área logada de leiloeiro.

## Stack

- **Backend**: Python 3.11, FastAPI, PostgreSQL (SQLite no exemplo local), httpx e BeautifulSoup
- **Frontend**: Next.js
- **Deploy**: Docker Compose — local e [Easy Panel](https://easypanel.io)

## Rodar localmente

### Pré-requisitos

- Python 3.11 (a imagem Docker e o CI usam 3.11)
- Node 18+
- Docker e Docker Compose (para rodar tudo junto)

### Opção 1 — Docker (recomendado)

```bash
docker compose up -d
```

- API: http://localhost:8000  
- Dashboard: http://localhost:3000  
- Docs API: http://localhost:8000/docs  

### Opção 2 — Manual

**Backend**

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

**Scraper (agendado ou manual)**

```bash
cd backend
python -m app.scrapers.run_all
```

## Deploy no Easy Panel

Envie o código para o GitHub. No Easy Panel, conecte o repositório ao projeto: o painel faz o build e a implantação automaticamente.

No painel, configure só as variáveis de ambiente de cada serviço:

- **Backend:** `DATABASE_URL` com a URL do PostgreSQL (ex.: `postgresql://usuario:senha@host:5432/banco` — a URL normal que o painel ou o provedor do banco fornece).
- **Frontend:** `NEXT_PUBLIC_API_URL` com a URL pública do backend.

Não é preciso rodar nada em shell; tudo ocorre na implantação.

## Tabelas (PostgreSQL)

O backend cria automaticamente duas tabelas ao subir:

| Tabela    | Descrição |
|-----------|-----------|
| **auctions** | Leilões. `source`: calil, vegas, zuk, mega, lance, trt5. |
| **lots**     | Lotes. Preço e texto ficam em coluna. Score, veredito e peças lidas ficam no JSON `raw_data`. |

A API expõe, entre outras: `GET /api/lots`, `GET /api/lots/{id}`, `GET /api/stats` (inclui a leitura dos últimos 7 dias), `POST /api/run-scrape`, `POST /api/lots/{id}/avaliar`, `GET /docs`. Essas rotas de escrita não têm login.

## Primeiro scrape (validar dados)

No dashboard, use **Atualizar catálogo**. Ele dispara as fontes registradas, grava no banco e atualiza a lista. Não é preciso abrir outra URL nem rodar nada em shell.

## Estrutura

```
Leilões/
├── backend/          # API + scrapers + DB
│   ├── app/
│   │   ├── main.py
│   │   ├── models/
│   │   ├── scrapers/
│   │   └── api/
│   └── requirements.txt
├── frontend/         # Dashboard Next.js
├── docker-compose.yml
└── README.md
```

## Licença

Uso interno / projeto FabriaIA.
