"""
Extrai cidade, tipo e endereço do texto do lote.
Regex primeiro. GLiNER e Mistral (OpenRouter) só no que faltar.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

import httpx
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

TIPO_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("veiculo", re.compile(r"\bve[ií]culo|\bmoto(?:cicleta)?\b|\bcarro\b|\bhonda\b|\bfiat\b|\bford\b|\brenault\b|\bvolkswagen\b", re.I)),
    ("apartamento", re.compile(r"\bapartament|\bapto\b", re.I)),
    ("casa", re.compile(r"\bcasa\b|\bsobrado\b|\bed[ií]cula\b", re.I)),
    ("terreno", re.compile(r"\bterreno\b|\b[aá]rea de terras\b|\bfazenda\b", re.I)),
    ("galpao", re.compile(r"\bgalp[aã]o\b", re.I)),
    ("chacara", re.compile(r"\bch[aá]cara\b", re.I)),
    ("sala", re.compile(r"\bsala comercial\b|\bsal[aã]o comercial\b", re.I)),
    ("imovel", re.compile(r"\bim[oó]ve", re.I)),
]

IMOVEIS = {"apartamento", "casa", "terreno", "galpao", "chacara", "imovel"}

TIPO_LABELS = {
    "apartamento": "Apartamento",
    "casa": "Casa",
    "terreno": "Terreno",
    "galpao": "Galpão",
    "chacara": "Chácara",
    "sala": "Sala comercial",
    "imovel": "Imóvel",
    "veiculo": "Veículo",
}

GLINER_LABELS = {
    "cidade": "cidade do imovel no Brasil",
    "endereco": "logradouro, numero e complemento",
    "tipo": "casa, apartamento, terreno, galpao, chacara ou sala comercial",
    "bairro": "bairro se citado",
    "matricula": "numero da matricula do imovel",
    "area": "area em metros quadrados se citada",
}

RE_MATRICULA = re.compile(
    r"matr[ií]cula(?:\s+n[ºo°.]?)?\s*[:.]?\s*([\d.]+(?:\s+do\s+CRI[^\n,]{0,40})?)",
    re.I,
)
RE_BAIRRO = re.compile(
    r"(?:bairro|no parque|no jardim|condom[ií]nio(?: residencial)?)\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ' ]{2,40})",
    re.I,
)
RE_AREA = re.compile(
    r"(\d{1,3}(?:\.\d{3})+|\d+)(?:[.,]\d{1,2})?\s*(?:m[²2]|m\s*²|metros quadrados)",
    re.I,
)
RE_FIELD_CUT = re.compile(
    r"\s+(?:matricula|cidade|processo|descricao|lance(?:\s+inicial)?|tipo do bem|detalhes|exequente|executado)\s*:|\s+lance\s+inicial\b",
    re.I,
)

_ACCENT = str.maketrans(
    "áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ",
    "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC",
)


def _fold(text: str) -> str:
    return text.translate(_ACCENT)


def parse_br_currency(s: str) -> Optional[float]:
    if not s:
        return None
    s = re.sub(r"[^\d,.-]", "", str(s))
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("name", "title", "description", "city"):
            inner = value.get(key)
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
    return ""


def cidade_from_text(*parts: Any, allow_bare: bool = False) -> str | None:
    """Cidade/UF no título; nome nu só com allow_bare (city/cityName)."""
    for part in parts:
        text = _as_text(part)
        if not text:
            continue
        labeled = re.search(r"Cidade:\s*([^\n<]+)", text, re.I)
        if labeled:
            name = re.sub(r"\s+", " ", labeled.group(1)).split("/")[0].strip(" -,")
            if 2 < len(name) <= 40:
                return name
        cidade_de = re.search(
            r"(?:na cidade de|cidade de|em)\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ' -]{2,40}?)\s*/\s*(?:SP|RJ|MG|PR|SC|RS|BA|GO|DF|ES|PE|CE|PA|AM|MT|MS)\b",
            text,
            re.I,
        )
        if cidade_de:
            return re.sub(r"\s+", " ", cidade_de.group(1)).strip(" -,")
        idx = re.search(r"/\s*(?:SP|RJ|MG|PR|SC|RS|BA|GO|DF|ES|PE|CE|PA|AM|MT|MS)\b", text, re.I)
        if idx:
            head = text[: idx.start()].strip()
            chunk = re.split(r"\s+[—–]\s+", head)[-1].strip()
            chunk = re.sub(r"^(?:.*\s)?(?:em|no|na|de)\s+", "", chunk, flags=re.I)
            chunk = re.sub(r"\s+", " ", chunk).strip(" -,")
            if re.search(r"vara|jucesp|leil[aã]o|comarca", chunk, re.I):
                continue
            if 2 < len(chunk) <= 40:
                return chunk
            continue
        if allow_bare and "/" not in text and 2 < len(text) <= 40:
            return text
    return None


def tipo_from_text(*parts: Any) -> str | None:
    blob = " ".join(_as_text(p) for p in parts if p)
    if not blob:
        return None
    for name, pattern in TIPO_PATTERNS:
        if pattern.search(blob):
            return name
    return None


def _clip_field(value: Any, max_len: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = re.sub(r"\s+", " ", value).strip(" -,")
    if not text:
        return None
    nxt = RE_FIELD_CUT.search(_fold(text))
    if nxt:
        text = text[: nxt.start()].strip(" -,")
    if len(text) > max_len:
        text = text[:max_len].rstrip(" -,.")
    return text or None


def matricula_from_text(*parts: Any) -> str | None:
    blob = " ".join(_as_text(p) for p in parts if p)
    found = RE_MATRICULA.search(blob)
    if not found:
        return None
    return re.sub(r"\s+", " ", found.group(1)).strip(" -,")[:80]


def bairro_from_text(*parts: Any) -> str | None:
    blob = " ".join(_as_text(p) for p in parts if p)
    found = RE_BAIRRO.search(blob)
    if not found:
        return None
    name = re.sub(r"\s+", " ", found.group(1)).split("/")[0].strip(" -,")
    name = re.split(r"\s+(?:na cidade|\bem\b|execut)", name, maxsplit=1, flags=re.I)[0].strip(" -,")
    if re.search(r"vara|jucesp|leil|comarca|execut", name, re.I):
        return None
    if 2 < len(name) <= 40:
        return name
    return None


def area_from_text(*parts: Any) -> str | None:
    blob = " ".join(_as_text(p) for p in parts if p)
    found = RE_AREA.search(blob)
    if not found:
        return None
    return f"{found.group(1)} m²"


def format_card(
    title: str,
    description: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Monta o card do lote: tipo, cidade, endereço — sem o texto jurídico cru."""
    out = dict(extra or {})
    tipo = tipo_from_text(title) or out.get("tipo") or tipo_from_text(title, description, out.get("endereco"))
    cidade = out.get("cidade") or cidade_from_text(title, description)
    endereco = _clip_field(out.get("endereco"), 120)
    if isinstance(endereco, str) and re.match(r"matr", _fold(endereco).lstrip(), re.I):
        endereco = None
    if not endereco:
        labeled = re.search(r"Endere[cç]o:\s*([^\n<]+)", f"{title} {description or ''}", re.I)
        if labeled:
            endereco = _clip_field(labeled.group(1), 120)
        if isinstance(endereco, str) and re.match(r"matr", _fold(endereco).lstrip(), re.I):
            endereco = None
    bairro_raw = out.get("bairro") or bairro_from_text(title, description)
    bairro = _clip_field(bairro_raw, 40)
    if bairro and re.search(r"execut|exequente|processo|vara", bairro, re.I):
        bairro = bairro_from_text(title, description)
        bairro = _clip_field(bairro, 40)
        if bairro and re.search(r"execut|exequente|processo|vara", bairro, re.I):
            bairro = None
    matricula = out.get("matricula")
    if (
        not isinstance(matricula, str)
        or len(matricula) > 40
        or re.search(r"Lance|Descri|Processo|R\$|Endere", matricula, re.I)
    ):
        matricula = matricula_from_text(title, description, matricula if isinstance(matricula, str) else "")
    matricula = _clip_field(matricula, 40)
    area = out.get("area")
    if not isinstance(area, str) or re.match(r"0+\s*m", area):
        area = area_from_text(title, description)
    label = TIPO_LABELS.get(str(tipo), "Lote") if tipo else "Lote"
    where = " · ".join(p for p in (bairro, cidade) if isinstance(p, str) and p.strip())
    headline = f"{label} · {where}" if where else label
    if tipo:
        out["tipo"] = tipo
    if cidade:
        out["cidade"] = cidade
    if endereco:
        out["endereco"] = endereco
    else:
        out.pop("endereco", None)
    if bairro:
        out["bairro"] = bairro
    else:
        out.pop("bairro", None)
    if matricula:
        out["matricula"] = matricula
    else:
        out.pop("matricula", None)
    if area:
        out["area"] = area
    out["headline"] = headline
    foto = out.get("foto")
    if not isinstance(foto, str) or not foto.startswith("http") or "facebook.com/tr" in foto:
        out.pop("foto", None)
    return {k: v for k, v in out.items() if v}


def extra_json(extra: dict[str, Any]) -> str | None:
    clean = {k: v for k, v in extra.items() if v not in (None, "", [], {})}
    if not clean:
        return None
    return json.dumps(clean, ensure_ascii=False)


def gliner_configured() -> bool:
    return bool(os.getenv("GLINER_URL", "").strip() and os.getenv("GLINER_API_TOKEN", "").strip())


def openrouter_configured() -> bool:
    return bool(os.getenv("OPENROUTER_API_KEY", "").strip())


def extract_status() -> dict[str, Any]:
    return {
        "gliner": gliner_configured(),
        "openrouter": openrouter_configured(),
        "extract_model": (os.getenv("OPENROUTER_EXTRACT_MODEL") or "mistralai/ministral-8b-2512").strip(),
    }


def enrich_extra(
    title: str,
    description: str | None,
    extra: dict[str, Any] | None = None,
    *,
    use_ai: bool = True,
) -> dict[str, Any]:
    """Card do lote: regex, GLiNER, Mistral. Não inventa campo."""
    out = dict(extra or {})
    blob = " ".join(p for p in (title, description or "") if p)
    out = format_card(title, description, out)
    missing = [k for k in ("cidade", "tipo", "endereco", "bairro", "matricula") if not out.get(k)]
    if use_ai and missing and gliner_configured() and blob.strip():
        ents = _gliner_entities(blob[:4000])
        if not out.get("cidade") and ents.get("cidade"):
            out["cidade"] = cidade_from_text(ents["cidade"][0], allow_bare=True) or ents["cidade"][0]
        if not out.get("tipo") and ents.get("tipo"):
            out["tipo"] = tipo_from_text(ents["tipo"][0], title)
        if not out.get("endereco") and ents.get("endereco"):
            out["endereco"] = ents["endereco"][0]
        if not out.get("bairro") and ents.get("bairro"):
            out["bairro"] = ents["bairro"][0]
        if not out.get("matricula") and ents.get("matricula"):
            out["matricula"] = ents["matricula"][0]
        if not out.get("area") and ents.get("area"):
            out["area"] = ents["area"][0]
        if ents:
            out["extract"] = "gliner"
            out = format_card(title, description, out)

    still = [k for k in ("cidade", "tipo", "endereco") if not out.get(k)]
    if use_ai and still and openrouter_configured() and blob.strip():
        mistral = _mistral_fields(blob[:4000])
        for key in ("cidade", "tipo", "endereco", "bairro", "matricula"):
            if not out.get(key) and mistral.get(key):
                out[key] = mistral[key]
        if mistral:
            out["extract"] = "mistral"
            out = format_card(title, description, out)
    elif not out.get("extract"):
        out["extract"] = "regex"
    return {k: v for k, v in out.items() if v}


def _gliner_entities(text: str) -> dict[str, list[str]]:
    url = os.getenv("GLINER_URL", "").rstrip("/")
    token = os.getenv("GLINER_API_TOKEN", "").strip()
    if not url or not token or not text.strip():
        return {}
    try:
        r = httpx.post(
            f"{url}/v1/extract/entities",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"text": text, "labels": GLINER_LABELS, "include_spans": False},
            timeout=20.0,
        )
        r.raise_for_status()
        payload = r.json()
        result = payload.get("result") or {}
        entities = result.get("entities") if isinstance(result, dict) else result
        out: dict[str, list[str]] = {}
        if isinstance(entities, dict):
            for key, values in entities.items():
                texts: list[str] = []
                if isinstance(values, list):
                    for item in values:
                        if isinstance(item, str):
                            texts.append(item)
                        elif isinstance(item, dict):
                            span = item.get("text") or item.get("span") or item.get("value")
                            if span:
                                texts.append(str(span))
                if texts:
                    out[str(key)] = texts
        return out
    except Exception:
        return {}


def _mistral_fields(blob: str) -> dict[str, str]:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        return {}
    model = (os.getenv("OPENROUTER_EXTRACT_MODEL") or "mistralai/ministral-8b-2512").strip()
    try:
        r = httpx.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL") or "http://127.0.0.1:8050",
                "X-Title": os.getenv("OPENROUTER_APP_NAME") or "leiloes",
            },
            json={
                "model": model,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Extraia a ficha do lote. Não invente. null se não estiver no texto. JSON: "
                            '{"tipo":"casa|apartamento|terreno|galpao|chacara|sala|imovel|veiculo"|null,'
                            '"cidade":string|null,"bairro":string|null,"endereco":string|null,'
                            '"matricula":string|null}'
                        ),
                    },
                    {"role": "user", "content": blob},
                ],
            },
            timeout=35.0,
        )
        if r.status_code >= 400:
            return {}
        content = (((r.json().get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
        parsed = _parse_json(str(content))
        if not isinstance(parsed, dict):
            return {}
        out: dict[str, str] = {}
        for key in ("cidade", "tipo", "endereco", "bairro", "matricula"):
            val = parsed.get(key)
            if isinstance(val, str) and val.strip() and val.strip().lower() != "null":
                out[key] = val.strip()
        if out.get("tipo"):
            mapped = tipo_from_text(out["tipo"])
            if mapped:
                out["tipo"] = mapped
        return out
    except Exception:
        return {}


def _parse_json(content: str) -> dict[str, Any] | None:
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
