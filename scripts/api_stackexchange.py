"""Coleta na API do Stack Exchange, compartilhada por Stack Overflow e DBA.

Não é executado diretamente: use coleta_stackoverflow.py ou coleta_dba.py.

Protocolo, seção 5.3:
  /2.3/search/advanced?q=<termo A> <termo B>&site=<site>&sort=relevance&order=desc  (perguntas)
Parâmetros acrescentados pela implementação:
  pagesize=100, page=1  -> critério de parada da seção 5.4 (100 primeiros por relevância);
  filter=<filtro>       -> inclui o total de resultados (.total) e o corpo das perguntas;
  key=<chave>           -> STACKEXCHANGE_KEY do .env (obrigatória; mascarada nos registros).
O filtro é criado uma vez por execução em /2.3/filters/create e gravado em
dados/brutos/<fonte>_<AAAAMMDDTHHMMSSZ>/filtro.json.

Cota: sem chave, 300 requisições/dia por IP; com chave de aplicativo
(stackapps.com), 10.000/dia. Cada execução usa 82 requisições (1 filtro + 81
buscas), sem contar novas tentativas.
"""

from __future__ import annotations

import re
import sys

import comum
from comum import (
    LIMITE_COLETA, Busca, ErroColeta, EstadoBusca, Preparacao, ResultadoBusca, Tarefa,
    requisitar, url_legivel, url_preparada,
)

URL_BASE = "https://api.stackexchange.com/2.3"
URL_BUSCA = f"{URL_BASE}/search/advanced"
URL_FILTRO = f"{URL_BASE}/filters/create"

# A API aceita até 30 req/s por IP; 2 s é conservador. O campo "backoff" da
# resposta, quando presente, é respeitado (ResultadoBusca.espera_minima).
INTERVALO = 2.0

PARAMS_FILTRO = {"base": "withbody", "include": ".total", "unsafe": "false"}

SEM_CHAVE = (
    "STACKEXCHANGE_KEY não encontrada no .env. Sem chave, a API do Stack Exchange "
    "permite só 300 requisições por dia por IP; as coletas de stackoverflow e dba usam "
    "164 (2 x 81 buscas + 2 filtros), sem contar novas tentativas, e não sobra cota "
    "para repetir uma execução no mesmo dia. Registre um aplicativo em stackapps.com "
    "(com chave, a cota é de 10.000 requisições por dia) e grave a chave no .env "
    "como STACKEXCHANGE_KEY=<chave>."
)


def limite_stackexchange(resp) -> float | None:
    """Limite de taxa do Stack Exchange: HTTP 400 com error_id 502 (throttle_violation)."""
    if resp.status_code != 400:
        return None
    try:
        dados = resp.json()
    except ValueError:
        return None
    if dados.get("error_id") == 502:
        m = re.search(r"(\d+) seconds", dados.get("error_message", ""))
        return float(m.group(1)) + 1 if m else 60.0
    return None


def params_busca(busca: Busca, site: str, filtro: str, chave: str | None) -> dict:
    params = {
        "q": busca.consulta,
        "site": site,
        "sort": "relevance",
        "order": "desc",
        "pagesize": LIMITE_COLETA,
        "page": 1,
        "filter": filtro,
    }
    if chave:
        params["key"] = chave
    return params


def criar_filtro(sessao, chave: str, estado: EstadoBusca) -> str:
    resp = requisitar(sessao, "GET", URL_FILTRO, estado,
                      params={**PARAMS_FILTRO, "key": chave},
                      detectar_limite=limite_stackexchange)
    dados = resp.json()
    if not dados.get("items"):
        raise ErroColeta(f"falha ao criar o filtro: {dados}")
    return dados["items"][0]["filter"]


def buscar(sessao, busca: Busca, site: str, filtro: str, chave: str,
           estado: EstadoBusca) -> ResultadoBusca:
    resp = requisitar(sessao, "GET", URL_BUSCA, estado,
                      params=params_busca(busca, site, filtro, chave),
                      detectar_limite=limite_stackexchange)
    dados = resp.json()
    if "error_id" in dados:
        raise ErroColeta(f"erro da API: {dados}")

    if dados.get("quota_remaining", 999) < 20:
        estado.avisos.append(f"cota restante {dados['quota_remaining']}")
    backoff = float(dados.get("backoff", 0))
    if backoff:
        estado.avisos.append(f"backoff {backoff:.0f}s")

    return ResultadoBusca(
        n_resultados=dados.get("total"),
        urls_coletadas=[item["link"] for item in dados.get("items", [])],
        espera_minima=backoff + 1 if backoff else 0.0,
    )


def main(fonte: str, site: str, script: str, descricao: str) -> None:
    args = comum.argumentos(descricao)
    chave = comum.ler_env("STACKEXCHANGE_KEY")
    repositorio = comum.verificar_antes_da_coleta(args.dry_run, [] if chave else [SEM_CHAVE])

    sessao = None if args.dry_run else comum.nova_sessao({"Accept": "application/json"})
    filtro: dict[str, str] = {}  # preenchido pela preparação, antes das buscas

    def preparar(estado: EstadoBusca) -> dict:
        filtro["valor"] = criar_filtro(sessao, chave, estado)
        return {"filtro": filtro["valor"], "parametros_filtro": PARAMS_FILTRO}

    buscas = comum.gerar_buscas()
    tarefas = [
        Tarefa(
            sufixo_id=b.codigo,
            busca=b,
            previa=url_legivel(url_preparada(
                "GET", URL_BUSCA, params_busca(b, site, "<criado na execução>", chave))),
            executar=lambda estado, b=b: buscar(sessao, b, site, filtro["valor"], chave, estado),
        )
        for b in buscas
    ]

    if args.dry_run:
        comum.imprimir_plano(fonte, tarefas)
        return

    comum.executar_coleta(
        fonte, tarefas,
        intervalo=INTERVALO,
        parametros={"url_busca": URL_BUSCA, "site": site},
        repositorio=repositorio,
        script=script,
        preparacao=Preparacao(nome="filtro", executar=preparar),
    )


if __name__ == "__main__":
    sys.exit("Use scripts/coleta_stackoverflow.py ou scripts/coleta_dba.py.")
