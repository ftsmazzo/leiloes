/**
 * Proxy de scrape no PC (IP residencial).
 * EasyPanel chama POST /fetch; a saída para Calil/Vegas sai daqui.
 *
 * Uso local:
 *   set TOKEN=segredo
 *   node server.mjs
 *
 * Funnel (como BeautyOS):
 *   tailscale funnel 8788
 *   No EasyPanel: SCRAPE_PROXY_URL=https://seu-funnel.ts.net
 *                 SCRAPE_PROXY_TOKEN=segredo
 */
import http from "node:http";

const PORT = Number(process.env.PORT || 8788);
const HOST = (process.env.HOST || "127.0.0.1").trim();
const TOKEN = (process.env.TOKEN || process.env.SCRAPE_PROXY_TOKEN || "").trim();

const ALLOWED = new Set([
  "www.calilleiloes.com.br",
  "calilleiloes.com.br",
  "www.vegasleiloes.com.br",
  "vegasleiloes.com.br",
]);

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

function allow(url) {
  try {
    const u = new URL(url);
    if (u.protocol !== "https:" && u.protocol !== "http:") return false;
    return ALLOWED.has(u.hostname.toLowerCase());
  } catch {
    return false;
  }
}

function authOk(req) {
  if (!TOKEN) return false;
  const header = req.headers.authorization || "";
  if (header === `Bearer ${TOKEN}`) return true;
  const q = new URL(req.url || "/", "http://x").searchParams.get("token");
  return q === TOKEN;
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

async function pull(url) {
  const res = await fetch(url, {
    redirect: "follow",
    headers: {
      "User-Agent": UA,
      Accept: "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
      "Accept-Language": "pt-BR,pt;q=0.9",
    },
  });
  const text = await res.text();
  return { status: res.status, url: res.url || url, text };
}

const server = http.createServer(async (req, res) => {
  const path = (req.url || "/").split("?")[0];

  if (req.method === "GET" && (path === "/" || path === "/health")) {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: true, service: "scrape-proxy", hosts: [...ALLOWED] }));
    return;
  }

  if (req.method !== "POST" || path !== "/fetch") {
    res.writeHead(404, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "not_found" }));
    return;
  }

  if (!authOk(req)) {
    res.writeHead(401, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "unauthorized" }));
    return;
  }

  try {
    const raw = await readBody(req);
    const body = raw ? JSON.parse(raw) : {};
    const url = typeof body.url === "string" ? body.url.trim() : "";
    if (!url || !allow(url)) {
      res.writeHead(400, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "url_not_allowed" }));
      return;
    }
    const out = await pull(url);
    res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
    res.end(JSON.stringify(out));
  } catch (err) {
    res.writeHead(502, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "fetch_failed", detail: String(err?.message || err) }));
  }
});

server.listen(PORT, HOST, () => {
  console.log(`scrape-proxy em http://${HOST}:${PORT}/fetch (health /health)`);
  if (!TOKEN) console.warn("AVISO: TOKEN vazio — todas as /fetch serão 401");
});
