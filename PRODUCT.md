# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Investidor/arrematante que analisa sozinho, e corretor que tria oportunidades para cliente. Ambos precisam decidir se vale aprofundar a leitura do edital antes de gastar tempo (ou dinheiro) no site do leiloeiro.

## Product Purpose

Catálogo de imóveis em leilão já publicados (Calil, Vegas, Zuk, Mega, Grupo Lance, TRT5). A pessoa filtra o que está no banco, abre o dossiê, pede avaliação sob demanda e sai com indício organizado — inclusive relatório imprimível. O scrape é job; a busca é no persistido. Não dá lance e não substitui edital nem orientação jurídica.

Sucesso: a pessoa deixa de ficar no escuro — sabe o que o documento público sustenta, o que falta e se vale aprofundar — em minutos, não em horas de PDF solto.

## Positioning

Indício analítico com peças públicas e veredito explícito (“Sem norte” / aprofundar / não aprofundar), não marketplace de lances nem agregador genérico de anúncios. A diferença é o dossiê: ledger, trechos citáveis, números (lance / avaliação / ref. mercado) e relatório apresentável.

## Operating Context

Uso no desktop (e mobile leve): filtro → lista → dossiê → avaliar → imprimir/PDF. Fontes Soleon e similares; documentos só do que está na página pública. Avaliação sob demanda baixa PDFs públicos; login do leiloeiro está fora de escopo.

## Capabilities and Constraints

- Fontes atuais: Calil, Vegas, Zuk, Mega, Grupo Lance, TRT5
- Ref. mercado: FipeZap (cidades cobertas) × área; Apify quando configurado
- Sem bypass de CAPTCHA / área logada
- Copy de produto não deve expor jargão de bastidor (tokens, OCR vazio, status de proxy, mensagens de fallback para desenvolvedor)
- Nome de marca ainda em adoção (ver Brand Commitments); rotas e repositório podem continuar `leiloes` tecnicamente

## Brand Commitments

- **Nome proposto: Farol** — curto; remete a “não ficar no escuro” em leilão judicial/extrajudicial, sem soar tribunal burocrático
- **Linha de apoio:** “Indício antes do lance.”
- Tom: marca/consultoria — claro, confiante, sóbrio; profissional e premium, sem gíria de dashboard técnico
- Aviso jurídico permanece, em forma curta e humana (não some; não grita)

## Evidence on Hand

- Produto em produção (EasyPanel): catálogo, dossiê, avaliação, relatório print
- README e CONTEXTO.md descrevem o fluxo e as fontes
- Não fabricar depoimentos, rankings ou volume de arremates

## Product Principles

1. Clareza antes de volume — o que falta importa tanto quanto o que existe.
2. Indício, não sentença — o veredito orienta aprofundar; o lance fica no leiloeiro.
3. Apresentável para o cliente — o corretor pode mostrar o dossiê/relatório sem texto de bastidor.
4. Uma fonte de verdade por vez — scrape controlado; busca no que já está no banco.
5. Respeito ao público e ao jurídico — sem inventar peça; disclaimer curto e visível.

## Accessibility & Inclusion

Interface web em português do Brasil; contraste e hierarquia legíveis em ferramenta de trabalho (WCAG 2.2 AA como meta de polish, não ainda auditada neste registro).
