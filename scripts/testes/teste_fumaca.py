#!/usr/bin/env python3
"""Teste de fumaça das APIs com consultas neutras, fora do protocolo. Nada é gravado.

Usa o código real dos scripts (requisitar, criar_filtro, CONSULTA_GRAPHQL e o
analisar do coleta_debezium) para validar endpoints, autenticação e os campos ou
páginas que a coleta espera. 9 requisições, com 2 s de pausa entre elas (5 s entre
as duas do Google Groups). Nunca imprime token, chave ou cabeçalhos de autenticação.
Não grava nada; ao final, confere que dados/ não foi alterado.

Uso (a partir da raiz do repositório; requer GITHUB_TOKEN e STACKEXCHANGE_KEY no .env):
  python -B scripts/testes/teste_fumaca.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]  # scripts/testes/ -> raiz
sys.path.insert(0, str(REPO / "scripts"))

import comum  # noqa: E402
import coleta_github  # noqa: E402
import api_stackexchange  # noqa: E402
import coleta_dbt_forum  # noqa: E402
import coleta_debezium  # noqa: E402
from comum import EstadoBusca, requisitar  # noqa: E402

PAUSA = 2.0
FRASE = "dead letter queue"
RESULTADOS: list[tuple[str, str]] = []


def etapa(nome: str, funcao) -> None:
    print(f"\n== {nome}")
    try:
        funcao()
        RESULTADOS.append((nome, "OK"))
    except Exception as e:  # noqa: BLE001
        print(f"  FALHOU: {type(e).__name__}: {comum.url_sem_segredos(str(e))[:400]}")
        RESULTADOS.append((nome, "FALHOU"))
    time.sleep(PAUSA)


def retrato_dados() -> dict:
    pasta = REPO / "dados"
    return {str(p.relative_to(pasta)): (p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(pasta.rglob("*"))}


DADOS_ANTES = retrato_dados()


def contem_frase(item: dict) -> bool:
    return FRASE in f"{item.get('title') or ''} {item.get('body') or ''}".lower()


token = comum.ler_env("GITHUB_TOKEN")
chave = comum.ler_env("STACKEXCHANGE_KEY")
gh = comum.nova_sessao({
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": coleta_github.VERSAO_API,
})
se = comum.nova_sessao({"Accept": "application/json"})
dbt = comum.nova_sessao({"Accept": "application/json"})
gg = comum.nova_sessao({"Accept": "text/html", "Accept-Language": coleta_debezium.IDIOMA})


def github_rest() -> None:
    totais = {}
    for q in [f'"{FRASE}" is:issue', f"{FRASE} is:issue"]:
        r = requisitar(gh, "GET", coleta_github.URL_REST, EstadoBusca(), params={"q": q, "per_page": 5, "page": 1})
        d = r.json()
        itens = d["items"]
        totais[q] = d["total_count"]
        print(f"  q={q:<30} HTTP {r.status_code}  total_count={d['total_count']:<7} "
              f"incomplete_results={d['incomplete_results']}  itens={len(itens)}  "
              f"com a frase exata no título/corpo: {sum(map(contem_frase, itens))}/{len(itens)}  "
              f"html_url presente: {all('html_url' in i for i in itens)}")
        print(f"    x-ratelimit-resource={r.headers.get('X-RateLimit-Resource')}  "
              f"x-ratelimit-remaining={r.headers.get('X-RateLimit-Remaining')}/{r.headers.get('X-RateLimit-Limit')}")
        time.sleep(PAUSA)
    com, sem = totais.values()
    print(f"  com aspas {com} < sem aspas {sem}: {com < sem}")
    if not com < sem:
        raise AssertionError("as aspas não reduziram o total_count")


def github_graphql() -> None:
    corpo = {"query": coleta_github.CONSULTA_GRAPHQL, "variables": {"consulta": f'"{FRASE}"', "n": 5}}
    r = requisitar(gh, "POST", coleta_github.URL_GRAPHQL, EstadoBusca(),
                   corpo_json=corpo, detectar_limite=coleta_github.limite_graphql)
    d = r.json()
    if d.get("errors"):
        raise AssertionError(f"erros do GraphQL: {d['errors']}")
    s = d["data"]["search"]
    nos = [n for n in s["nodes"] if n]
    print(f"  HTTP {r.status_code}  discussionCount={s['discussionCount']}  nós={len(nos)}  "
          f"com a frase exata: {sum(map(contem_frase, nos))}/{len(nos)}  rateLimit={d['data']['rateLimit']}")
    print(f"  campos do 1º nó: {sorted(nos[0]) if nos else '-'}")


FILTRO: dict[str, str] = {}


def stackexchange_filtro() -> None:
    FILTRO["valor"] = api_stackexchange.criar_filtro(se, chave, EstadoBusca())
    print(f"  filtro criado com {api_stackexchange.PARAMS_FILTRO}: {FILTRO['valor']}")


def stackexchange(site: str):
    def buscar() -> None:
        params = {"q": f'"{FRASE}"', "site": site, "sort": "relevance", "order": "desc",
                  "pagesize": 5, "page": 1, "filter": FILTRO["valor"], "key": chave}
        r = requisitar(se, "GET", api_stackexchange.URL_BUSCA, EstadoBusca(), params=params,
                       detectar_limite=api_stackexchange.limite_stackexchange)
        d = r.json()
        if "error_id" in d:
            raise AssertionError(f"erro da API: {d}")
        itens = d.get("items", [])
        print(f"  site={site:<14} HTTP {r.status_code}  total={d.get('total')}  itens={len(itens)}  "
              f"has_more={d.get('has_more')}  quota_remaining={d.get('quota_remaining')}/{d.get('quota_max')}")
        print(f"    link presente: {all('link' in i for i in itens)}  body presente: {all('body' in i for i in itens)}  "
              f"com a frase exata: {sum(map(contem_frase, itens))}/{len(itens)}")
        if "total" not in d:
            raise AssertionError("o filtro não incluiu .total")
    return buscar


def dbt_forum() -> None:
    r = requisitar(dbt, "GET", coleta_dbt_forum.URL_BUSCA, EstadoBusca(), params={"q": "incremental", "page": 1})
    d = r.json()
    posts, topicos = d.get("posts", []), d.get("topics", [])
    grupo = d.get("grouped_search_result") or {}
    print(f"  HTTP {r.status_code}  URL final: {r.url}  redirecionamentos: {len(r.history)}")
    print(f"  content-type={r.headers.get('Content-Type')}  posts={len(posts)}  topics={len(topicos)}")
    print(f"  chaves no topo: {sorted(d)}")
    esperado = {
        "posts[].topic_id": bool(posts) and all("topic_id" in p for p in posts),
        "topics[].id": bool(topicos) and all("id" in t for t in topicos),
        "topics[].slug": bool(topicos) and all("slug" in t for t in topicos),
        "grouped_search_result.more_full_page_results": "more_full_page_results" in grupo,
    }
    print(f"  campos esperados: {esperado}  (more_full_page_results = {grupo.get('more_full_page_results')})")
    if topicos:
        t = topicos[0]
        print(f"  1º tópico como o script monta: {coleta_dbt_forum.URL_BASE}/t/{t.get('slug')}/{t.get('id')}")
    if not all(esperado.values()):
        raise AssertionError("faltam campos esperados pelo script")


def google_groups() -> None:
    """Página de busca do grupo do Debezium, classificada pelo analisar() real.

    PaginaInvalida (login, bloqueio, access-error, formato mudado) faz a etapa falhar.
    """
    for k, (q, espera_zero) in enumerate([(f'"{FRASE}"', False), ("xqzv lorem kjh", True)]):
        if k:
            time.sleep(coleta_debezium.INTERVALO)
        r = requisitar(gg, "GET", coleta_debezium.URL_BUSCA, EstadoBusca(), params={"q": q},
                       max_tentativas=coleta_debezium.MAX_TENTATIVAS)
        p = coleta_debezium.analisar(r.url, r.text)
        total = "many" if p.total is None else p.total
        print(f"  q={q:<20} HTTP {r.status_code}  redirecionamentos: {len(r.history)}  "
              f"tópicos na página: {len(p.topicos)}  total: {total}")
        if p.topicos:
            print(f"    1º tópico como o script monta: {coleta_debezium.URL_TOPICO}{p.topicos[0]}")
        if espera_zero and (p.topicos or p.total != 0):
            raise AssertionError("a consulta sem sentido deveria ser reconhecida como 0 resultados")


etapa("GitHub REST (issues)", github_rest)
etapa("GitHub GraphQL (discussions)", github_graphql)
etapa("Stack Exchange: criação do filtro", stackexchange_filtro)
etapa("Stack Exchange: stackoverflow", stackexchange("stackoverflow"))
etapa("Stack Exchange: dba", stackexchange("dba"))
etapa("Fórum do dbt (Discourse)", dbt_forum)
etapa("Google Groups (grupo do Debezium)", google_groups)

RESULTADOS.append(("dados/ não foi alterado", "OK" if retrato_dados() == DADOS_ANTES else "FALHOU"))

print("\n== Resumo")
for nome, situacao in RESULTADOS:
    print(f"  {situacao:<7} {nome}")
sys.exit(0 if all(s == "OK" for _, s in RESULTADOS) else 1)
