"""Coleta no GitHub: issues (API REST) e discussions (API GraphQL), busca global.

Protocolo, seção 5.3:
  issues       q=<termo A> <termo B> is:issue              (ordenação padrão: relevância)
  discussions  search(query: "<termo A> <termo B>", type: DISCUSSION)
Seção 5.4: no máximo 100 resultados por busca (per_page/first = 100, uma página).
Seção 5.5: se a busca de issues voltar com incomplete_results=true, ela é repetida
até 3 vezes; vale a última resposta, e todas ficam no bruto. Se persistir, o aviso
vai para o bruto e para dados/execucoes.csv.

São 81 buscas de issues seguidas de 81 de discussions na mesma execução:
dados/brutos/github_<AAAAMMDDTHHMMSSZ>/issues_A1B1.json ... discussions_A9B9.json.
No log, as duas aparecem com fonte "github" e se distinguem pelo id_busca
(..._issues_A1B1 / ..._discussions_A1B1) e pela string_enviada.

Requer GITHUB_TOKEN no .env.

Uso (a partir da raiz do repositório):
  python scripts/coleta_github.py --dry-run
  python scripts/coleta_github.py
"""

from __future__ import annotations

import json
import time

import comum
from comum import (
    LIMITE_COLETA, Busca, ErroColeta, EstadoBusca, ResultadoBusca, Tarefa,
    requisitar, url_legivel, url_preparada,
)

FONTE = "github"
URL_REST = "https://api.github.com/search/issues"
URL_GRAPHQL = "https://api.github.com/graphql"
VERSAO_API = "2022-11-28"

# A busca REST autenticada aceita 30 requisições/min; 3 s mantém folga.
INTERVALO = 3.0

# Protocolo, seção 5.5: novas tentativas quando incomplete_results=true.
NOVAS_TENTATIVAS_INCOMPLETO = 3

CONSULTA_GRAPHQL = """
query($consulta: String!, $n: Int!) {
  rateLimit { cost remaining resetAt }
  search(query: $consulta, type: DISCUSSION, first: $n) {
    discussionCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on Discussion {
        id
        number
        url
        title
        body
        createdAt
        updatedAt
        author { login }
        repository { nameWithOwner }
        category { name }
        isAnswered
        answerChosenAt
        upvoteCount
        comments { totalCount }
      }
    }
  }
}
""".strip()


def params_issues(busca: Busca) -> dict:
    return {"q": f"{busca.consulta} is:issue", "per_page": LIMITE_COLETA, "page": 1}


def string_discussions(busca: Busca) -> str:
    return (f"POST {URL_GRAPHQL} search(query: {json.dumps(busca.consulta)}, "
            f"type: DISCUSSION, first: {LIMITE_COLETA})")


def buscar_issues(sessao, busca: Busca, estado: EstadoBusca) -> ResultadoBusca:
    for tentativa in range(NOVAS_TENTATIVAS_INCOMPLETO + 1):
        if tentativa > 0:
            time.sleep(INTERVALO)
        resp = requisitar(sessao, "GET", URL_REST, estado, params=params_issues(busca))
        dados = resp.json()
        if not dados.get("incomplete_results"):
            break
    else:
        estado.avisos.append(
            f"incomplete_results=true mesmo após {NOVAS_TENTATIVAS_INCOMPLETO} novas tentativas "
            "(a busca do GitHub expirou antes de concluir)")

    return ResultadoBusca(
        n_resultados=dados["total_count"],
        urls_coletadas=[item["html_url"] for item in dados["items"]],
    )


def limite_graphql(resp) -> float | None:
    """O GraphQL sinaliza limite primário com HTTP 200 e erro do tipo RATE_LIMITED."""
    if resp.status_code != 200:
        return None
    try:
        erros = resp.json().get("errors") or []
    except ValueError:
        return None
    if any(e.get("type") == "RATE_LIMITED" for e in erros):
        reset = resp.headers.get("X-RateLimit-Reset", "")
        return max(float(reset) - time.time(), 0) + 2 if reset.isdigit() else 60.0
    return None


def buscar_discussions(sessao, busca: Busca, estado: EstadoBusca) -> ResultadoBusca:
    estado.string_enviada = string_discussions(busca)
    corpo = {"query": CONSULTA_GRAPHQL, "variables": {"consulta": busca.consulta, "n": LIMITE_COLETA}}
    resp = requisitar(sessao, "POST", URL_GRAPHQL, estado,
                      corpo_json=corpo, detectar_limite=limite_graphql)
    dados = resp.json()

    if dados.get("errors"):
        if not (dados.get("data") or {}).get("search"):
            raise ErroColeta(f"GraphQL sem dados: {dados['errors']}")
        estado.avisos.append(f"erros parciais do GraphQL: {dados['errors']}")

    resultado = dados["data"]["search"]
    nos = [n for n in resultado["nodes"] if n]  # nós inacessíveis vêm como null
    return ResultadoBusca(
        n_resultados=resultado["discussionCount"],
        urls_coletadas=[n["url"] for n in nos],
    )


def main() -> None:
    args = comum.argumentos(__doc__.splitlines()[0])
    token = comum.ler_env("GITHUB_TOKEN")
    repositorio = comum.verificar_antes_da_coleta(
        args.dry_run,
        [] if token else ["GITHUB_TOKEN não encontrado no .env nem no ambiente"],
    )

    sessao = None
    if not args.dry_run:
        sessao = comum.nova_sessao({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": VERSAO_API,
        })

    buscas = comum.gerar_buscas()
    tarefas = [
        Tarefa(
            sufixo_id=f"issues_{b.codigo}",
            busca=b,
            previa=url_legivel(url_preparada("GET", URL_REST, params_issues(b))),
            executar=lambda estado, b=b: buscar_issues(sessao, b, estado),
        )
        for b in buscas
    ] + [
        Tarefa(
            sufixo_id=f"discussions_{b.codigo}",
            busca=b,
            previa=string_discussions(b),
            executar=lambda estado, b=b: buscar_discussions(sessao, b, estado),
        )
        for b in buscas
    ]

    if args.dry_run:
        comum.imprimir_plano(FONTE, tarefas)
        return

    comum.executar_coleta(
        FONTE, tarefas,
        intervalo=INTERVALO,
        parametros={
            "url_rest": URL_REST,
            "url_graphql": URL_GRAPHQL,
            "x_github_api_version": VERSAO_API,
            "novas_tentativas_incomplete_results": NOVAS_TENTATIVAS_INCOMPLETO,
            "consulta_graphql": CONSULTA_GRAPHQL,
        },
        repositorio=repositorio,
        script="scripts/coleta_github.py",
    )


if __name__ == "__main__":
    main()
