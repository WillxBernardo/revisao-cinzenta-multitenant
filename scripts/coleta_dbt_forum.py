"""Coleta no fórum da comunidade dbt (Discourse), endpoint público de busca.

Protocolo, seção 5.3:
  /search.json?q=<termo A> <termo B>   (tópicos)

O Discourse devolve 50 resultados por página e não informa o total. Por isso:
- as páginas são lidas em sequência (page=1, 2, ...) até reunir 100 tópicos
  distintos (seção 5.4) ou acabarem os resultados;
- n_resultados só é preenchido quando os resultados acabaram (o total é então
  conhecido). Se havia mais resultados além dos coletados, n_resultados fica
  vazio no log (seção 5.5); quando a paginação para antes dos 100 tópicos
  (página sem tópicos novos ou limite de páginas), o motivo vai para os avisos.

Brutos: dados/brutos/dbt_forum_<AAAAMMDDTHHMMSSZ>/A1B1.json ... A9B9.json, cada
um com todas as páginas lidas.

Uso (a partir da raiz do repositório):
  python scripts/coleta_dbt_forum.py --dry-run
  python scripts/coleta_dbt_forum.py
"""

from __future__ import annotations

import time

import comum
from comum import (
    LIMITE_COLETA, Busca, EstadoBusca, ResultadoBusca, Tarefa,
    requisitar, url_legivel, url_preparada,
)

FONTE = "dbt_forum"
URL_BASE = "https://discourse.getdbt.com"
URL_BUSCA = f"{URL_BASE}/search.json"

# Os limites padrão do Discourse para buscas anônimas são baixos; 5 s entre
# requisições (inclusive entre páginas da mesma busca) evita HTTP 429.
INTERVALO = 5.0
MAX_PAGINAS = 10  # salvaguarda contra paginação sem fim


def params_busca(busca: Busca, pagina: int) -> dict:
    return {"q": busca.consulta, "page": pagina}


def buscar(sessao, busca: Busca, estado: EstadoBusca) -> ResultadoBusca:
    topicos: dict[int, str] = {}  # id do tópico -> URL, na ordem de relevância
    ha_mais = True  # o Discourse indica se existem resultados além desta página
    pagina = 1

    while ha_mais and len(topicos) < LIMITE_COLETA and pagina <= MAX_PAGINAS:
        if pagina > 1:
            time.sleep(INTERVALO)
        # A string_enviada do log é a da página 1 (definida na primeira requisição).
        resp = requisitar(sessao, "GET", URL_BUSCA, estado, params=params_busca(busca, pagina))
        dados = resp.json()

        slugs = {t["id"]: t.get("slug", "") for t in dados.get("topics", [])}
        novos = 0
        for post in dados.get("posts", []):  # a ordem dos posts é a de relevância
            tid = post.get("topic_id")
            if tid is not None and tid not in topicos:
                slug = slugs.get(tid, "")
                topicos[tid] = f"{URL_BASE}/t/{slug}/{tid}" if slug else f"{URL_BASE}/t/{tid}"
                novos += 1

        grupo = dados.get("grouped_search_result") or {}
        ha_mais = bool(grupo.get("more_full_page_results"))
        pagina += 1
        if ha_mais and novos == 0:
            estado.avisos.append(f"página {pagina - 1} sem tópicos novos; paginação interrompida")
            break

    if ha_mais and pagina > MAX_PAGINAS and len(topicos) < LIMITE_COLETA:
        estado.avisos.append(f"parou em {MAX_PAGINAS} páginas com {len(topicos)} tópicos")

    return ResultadoBusca(
        n_resultados=None if ha_mais else len(topicos),
        urls_coletadas=list(topicos.values())[:LIMITE_COLETA],
    )


def main() -> None:
    args = comum.argumentos(__doc__.splitlines()[0])
    repositorio = comum.verificar_antes_da_coleta(args.dry_run, [])

    sessao = None if args.dry_run else comum.nova_sessao({"Accept": "application/json"})
    buscas = comum.gerar_buscas()
    tarefas = [
        Tarefa(
            sufixo_id=b.codigo,
            busca=b,
            previa=url_legivel(url_preparada("GET", URL_BUSCA, params_busca(b, 1))),
            executar=lambda estado, b=b: buscar(sessao, b, estado),
        )
        for b in buscas
    ]

    if args.dry_run:
        comum.imprimir_plano(FONTE, tarefas)
        return

    comum.executar_coleta(
        FONTE, tarefas,
        intervalo=INTERVALO,
        parametros={"url_busca": URL_BUSCA, "resultados_por_pagina": 50, "max_paginas": MAX_PAGINAS},
        repositorio=repositorio,
        script="scripts/coleta_dbt_forum.py",
    )


if __name__ == "__main__":
    main()
