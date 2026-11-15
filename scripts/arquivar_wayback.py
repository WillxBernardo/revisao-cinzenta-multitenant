"""Arquiva no Wayback Machine os itens incluídos (protocolo, seção 10).

Para cada linha de dados/extracao.csv com url_arquivada vazia, pede uma captura
ao Save Page Now (GET https://web.archive.org/save/<url>) e registra a URL
arquivada (cabeçalho Content-Location ou URL final do redirecionamento).
Se a captura falhar, a URL arquivada fica vazia e a falha é anotada em
observacao ("Wayback: falha em <data> (<motivo>)"); o script segue para o
próximo item.

Limites (CLAUDE.md, regra 9): intervalo de 20 s entre itens e nova tentativa,
após pausa crescente, em HTTP 429/5xx (até 3 tentativas por item).
Cada tentativa (status, cabeçalhos relevantes, URL final) é gravada em
dados/brutos/wayback_<AAAAMMDDTHHMMSSZ>.json.

Uso: python scripts/arquivar_wayback.py
"""
from __future__ import annotations

import csv
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
EXTRACAO = RAIZ / "dados" / "extracao.csv"
INTERVALO = 20.0
TENTATIVAS = 3
UA = "revisao-cinzenta-arquivamento/1.0 (python-requests)"


def arquivar(sessao: requests.Session, url: str, log: list) -> tuple[str, str]:
    """Devolve (url_arquivada, motivo_da_falha)."""
    motivo = ""
    for k in range(TENTATIVAS):
        try:
            r = sessao.get(f"https://web.archive.org/save/{url}", timeout=180, allow_redirects=True)
        except requests.RequestException as e:
            motivo = type(e).__name__
            log.append({"url": url, "tentativa": k + 1, "erro": repr(e)})
            time.sleep(60 * (k + 1))
            continue
        loc = r.headers.get("content-location", "")
        log.append({"url": url, "tentativa": k + 1, "status": r.status_code, "url_final": r.url,
                    "content_location": loc, "data": datetime.now(timezone.utc).isoformat()})
        arquivada = ""
        if loc.startswith("/web/"):
            arquivada = "https://web.archive.org" + loc
        elif re.match(r"https?://web\.archive\.org/web/\d+", r.url):
            arquivada = r.url
        if r.ok and arquivada:
            return arquivada, ""
        motivo = f"HTTP {r.status_code}"
        if r.status_code in (429, 500, 502, 503, 504, 520, 523):
            time.sleep(60 * (k + 1))
            continue
        break
    return "", motivo or "sem URL de captura"


def main():
    with EXTRACAO.open(encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        colunas, linhas = r.fieldnames, list(r)
    s = requests.Session()
    s.headers["User-Agent"] = UA
    log: list = []
    carimbo = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pendentes = [l for l in linhas if not l["url_arquivada"]]
    print(f"{len(pendentes)} itens a arquivar", flush=True)
    for k, l in enumerate(pendentes, 1):
        arquivada, motivo = arquivar(s, l["url"], log)
        if arquivada:
            l["url_arquivada"] = arquivada
        else:
            nota = f"Wayback: falha em {datetime.now(timezone.utc).date()} ({motivo})."
            l["observacao"] = f"{l['observacao']} {nota}".strip()
        print(f"  {k}/{len(pendentes)} {l['id_item']}: {'ok' if arquivada else 'falha ' + motivo}", flush=True)
        with EXTRACAO.open("w", encoding="utf-8", newline="") as f:  # grava a cada item (retomável)
            w = csv.DictWriter(f, fieldnames=colunas, lineterminator="\n")
            w.writeheader()
            w.writerows(linhas)
        (RAIZ / "dados" / "brutos" / f"wayback_{carimbo}.json").write_text(
            json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
        if k < len(pendentes):
            time.sleep(INTERVALO)


if __name__ == "__main__":
    main()
