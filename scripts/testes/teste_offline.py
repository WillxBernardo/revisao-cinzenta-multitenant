#!/usr/bin/env python3
"""Teste offline dos scripts de coleta: respostas simuladas, nenhuma requisição de rede.

Roda os main() reais de coleta_github, api_stackexchange, coleta_dbt_forum e
coleta_debezium com:
- sessão HTTP falsa, que responde conforme um roteiro por busca (inclusive
  redirecionamentos simulados);
- time.sleep substituído (as esperas são só anotadas);
- comum.RAIZ e os caminhos de dados/ apontando para um diretório temporário;
- comum.verificar_antes_da_coleta substituída (o diretório de teste não é git).
O diretório temporário é apagado ao final; o dados/ do repositório não é tocado.

Uso (a partir da raiz do repositório):
  python -B scripts/testes/teste_offline.py [diretório onde criar o temporário]
Sem argumento, o temporário é criado no diretório temporário padrão do sistema.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json as jsonlib
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]  # scripts/testes/ -> raiz
BASE_TMP = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(tempfile.gettempdir())
sys.path.insert(0, str(REPO / "scripts"))

import requests  # noqa: E402
from requests.structures import CaseInsensitiveDict  # noqa: E402

import comum  # noqa: E402
import coleta_github  # noqa: E402
import api_stackexchange  # noqa: E402
import coleta_dbt_forum  # noqa: E402
import coleta_debezium  # noqa: E402

FALHAS: list[str] = []


def checar(condicao, descricao: str) -> None:
    print(("  ok     " if condicao else "  FALHOU ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


# --- esperas: anotadas, não executadas ------------------------------------
ESPERAS: list[float] = []
_sleep_real = time.sleep
time.sleep = lambda s: ESPERAS.append(round(float(s), 1))

BUSCAS = comum.gerar_buscas()
CODIGO = {b.consulta: b.codigo for b in BUSCAS}

CAB_JSON = {"Content-Type": "application/json; charset=utf-8", "Date": "Sun, 15 Nov 2026 12:00:00 GMT"}
CAB_GITHUB = {
    **CAB_JSON,
    "X-RateLimit-Limit": "30",
    "X-RateLimit-Remaining": "29",
    "X-RateLimit-Reset": "1999999999",
    "X-RateLimit-Resource": "search",
    # Estes devem ser descartados:
    "X-OAuth-Scopes": "repo",
    "github-authentication-token-expiration": "2027-01-01 00:00:00 UTC",
    "Set-Cookie": "sessao=x",
    "Server": "github.com",
    "X-GitHub-Request-Id": "ABCD:1234",
}


# --- sessão HTTP falsa ----------------------------------------------------
class SessaoFalsa:
    def __init__(self, roteiro):
        self.roteiro = roteiro
        self.contagem: dict = {}
        self.params_enviados: list[dict] = []

    def request(self, metodo, url, params=None, json=None, timeout=None):
        params = params or {}
        self.params_enviados.append(dict(params))
        consulta = params.get("q") or ((json or {}).get("variables") or {}).get("consulta")
        chave = (url, consulta, params.get("page"))
        n = self.contagem[chave] = self.contagem.get(chave, 0) + 1
        # O roteiro devolve (status, corpo, cabeçalhos) ou, para simular um
        # redirecionamento 302 seguido pelo requests, (status, corpo, cabeçalhos, url_final).
        status, corpo, cabecalhos, *url_final = self.roteiro(metodo, url, params, json, n)
        r = requests.Response()
        r.status_code = status
        r.reason = "simulado"
        r._content = (corpo if isinstance(corpo, str) else jsonlib.dumps(corpo)).encode("utf-8")
        r.encoding = "utf-8"
        r.headers = CaseInsensitiveDict(cabecalhos)
        r.request = requests.Request(metodo, url, params=params or None, json=json).prepare()
        r.url = r.request.url
        if url_final:
            anterior = requests.Response()
            anterior.status_code = 302
            anterior.headers = CaseInsensitiveDict({"Location": url_final[0]})
            anterior.url = r.url
            r.history = [anterior]
            r.request = requests.Request(metodo, url_final[0]).prepare()
            r.url = url_final[0]
        return r


SESSAO: dict = {"atual": None, "cabecalhos": None}


def nova_sessao_falsa(cabecalhos=None):
    SESSAO["cabecalhos"] = dict(cabecalhos or {})
    return SESSAO["atual"]


REPOSITORIO_FALSO = {
    "commit_head": "abc1234", "tag_protocolo": "v0-protocolo",
    "commit_tag": "abc1234", "protocolo_alterado_desde_tag": False,
}
verificar_real = comum.verificar_antes_da_coleta
comum.nova_sessao = nova_sessao_falsa
comum.verificar_antes_da_coleta = lambda dry_run, impedimentos: dict(REPOSITORIO_FALSO)


# --- roteiros ---------------------------------------------------------------
def roteiro_github(metodo, url, params, corpo, n):
    if url == coleta_github.URL_REST:
        codigo = CODIGO[params["q"].removesuffix(" is:issue")]
        if codigo == "A1B2" and n == 1:                       # limite de taxa
            return 429, {"message": "API rate limit exceeded"}, {**CAB_JSON, "Retry-After": "7"}
        if codigo == "A1B4":                                  # erro não recuperável
            return 422, {"message": "Validation Failed", "errors": [{"code": "invalid"}]}, CAB_GITHUB
        itens = {"A1B1": 2, "A1B2": 1, "A1B3": 1}.get(codigo, 0)
        return 200, {
            "total_count": itens + (4 if codigo == "A1B3" else 0),
            "incomplete_results": codigo == "A1B3",           # parcial persistente
            "items": [{"html_url": f"https://github.com/org/repo/issues/{codigo}-{i}"} for i in range(itens)],
        }, CAB_GITHUB
    if url == coleta_github.URL_GRAPHQL:
        codigo = CODIGO[corpo["variables"]["consulta"]]
        if codigo == "A1B2" and n == 1:                       # limite do GraphQL (HTTP 200)
            return 200, {"errors": [{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}]}, \
                {**CAB_GITHUB, "X-RateLimit-Reset": str(int(time.time()) + 30)}
        nos = [{"url": "https://github.com/org/repo/discussions/1", "title": "t"}, None] if codigo == "A1B1" else []
        return 200, {"data": {"rateLimit": {"cost": 1, "remaining": 4999},
                              "search": {"discussionCount": len(nos),
                                         "pageInfo": {"hasNextPage": False, "endCursor": None},
                                         "nodes": nos}}}, CAB_GITHUB
    raise AssertionError(f"URL inesperada: {url}")


CHAVE_FALSA = "CHAVE_FALSA_123"


def roteiro_se(metodo, url, params, corpo, n):
    if url == api_stackexchange.URL_FILTRO:
        return 200, {"items": [{"filter": "!filtroFalso"}], "quota_remaining": 9999}, CAB_JSON
    codigo = CODIGO[params["q"]]
    if codigo == "A1B1" and n == 1:                           # throttle do Stack Exchange
        return 400, {"error_id": 502, "error_name": "throttle_violation",
                     "error_message": "too many requests from this IP, more requests available in 3 seconds"}, CAB_JSON
    resposta = {"items": [], "total": 0, "has_more": False, "quota_max": 10000, "quota_remaining": 9990}
    if codigo == "A1B1":
        resposta.update(items=[{"link": "https://stackoverflow.com/questions/1/x"}], total=1)
    if codigo == "A1B2":
        resposta["backoff"] = 5
    return 200, resposta, CAB_JSON


INTERROMPER = {"ativo": False}


def roteiro_dbt(metodo, url, params, corpo, n):
    codigo = CODIGO[params["q"]]
    pagina = params["page"]
    if INTERROMPER["ativo"] and codigo == "A1B4":
        raise KeyboardInterrupt

    def pagina_com(ids, mais):
        ids = list(ids)
        return 200, {
            "posts": [{"id": 1000 + i, "topic_id": t} for i, t in enumerate(ids)],
            "topics": [{"id": t, "slug": f"topico-{t}"} for t in dict.fromkeys(ids)],
            "grouped_search_result": {"more_full_page_results": mais},
        }, CAB_JSON

    if codigo == "A1B1":                                      # mais de 100 tópicos
        return pagina_com(range(1, 51), True) if pagina == 1 else pagina_com(range(51, 111), True)
    if codigo == "A1B2":                                      # 10 tópicos, total conhecido
        return pagina_com([201, 202, 202, 203, 204, 205, 206, 207, 208, 209, 210], False)
    if codigo == "A1B3":                                      # página 2 sem tópicos novos
        return pagina_com(range(301, 306), True)
    return pagina_com([], None)


CAB_HTML = {"Content-Type": "text/html; charset=utf-8", "Date": "Sun, 15 Nov 2026 12:00:00 GMT",
            "Set-Cookie": "NID=x"}  # Set-Cookie deve ser descartado


def pagina_groups(ids=(), contador=None, sem_resultados=False, titulo=coleta_debezium.TITULO_BUSCA):
    """Página de busca do Google Groups com a estrutura observada no teste de fumaça."""
    partes = [f"<!doctype html><html><head><title>{titulo}</title></head><body>",
              # Presente em toda página real; não pode ser confundido com redirecionamento para login.
              '<a href="https://accounts.google.com/ServiceLogin?continue=x">Sign in</a>']
    if contador:
        partes.append(f'<div class="c"><div class="n">{contador}</div>'
                      '<div role="button" aria-label="Next page"></div></div>')
    for i, t in enumerate(ids):
        # O trecho imita um contador; só o contador antes da lista pode valer.
        partes.append(f'<div class="l" role="row" data-rowid="{t}"><a href="./g/debezium/c/{t}/m/msg{i}">'
                      f'<span>Tópico {t}</span><div>1–2 of 3</div></a></div>')
    if sem_resultados:
        partes.append(f"<div>{coleta_debezium.TEXTO_SEM_RESULTADOS}</div>")
    return "".join(partes) + "</body></html>"


SORRY = "https://www.google.com/sorry/index?continue=https://groups.google.com/g/debezium/search"
PAGINA_BLOQUEIO = ("<html><head><title>https://groups.google.com/</title></head><body>"
                   "<form id='captcha-form'><div class='g-recaptcha'></div></form>"
                   "Our systems have detected unusual traffic from your computer network.</body></html>")
DEBEZIUM = {"modo": "casos"}


def roteiro_debezium(metodo, url, params, corpo, n):
    if url != coleta_debezium.URL_BUSCA:
        raise AssertionError(f"URL inesperada: {url}")
    codigo = CODIGO[params["q"]]
    poucos = pagina_groups(["t1", "t2", "t3", "t4"], "1–4 of 4")
    zero = pagina_groups(sem_resultados=True)
    if DEBEZIUM["modo"] == "completa":
        return 200, (poucos if codigo.startswith("A1") else zero), CAB_HTML
    return {
        "A1B1": (200, pagina_groups([f"id{i:02d}" for i in range(30)], "1–30 of many"), CAB_HTML),
        "A1B2": (200, poucos, CAB_HTML),
        "A1B3": (200, zero, CAB_HTML),
        "A1B4": (200, PAGINA_BLOQUEIO, CAB_HTML),                                # bloqueio com HTTP 200
        "A1B5": (200, pagina_groups(["t1", "t2", "t3"], "1–5 of 5"), CAB_HTML),  # contador incoerente
        "A1B6": (200, poucos, CAB_HTML),
        "A1B7": (200, "<html><head><title>Sign in - Google Accounts</title></head></html>", CAB_HTML,
                 "https://accounts.google.com/v3/signin/identifier?continue=x"),
        "A1B8": (200, "<html><head><title>Google Groups</title></head><body>Content unavailable</body></html>",
                 CAB_HTML, "https://groups.google.com/access-error?continue=x"),
        "A1B9": (429, PAGINA_BLOQUEIO, CAB_HTML, SORRY),                         # 429 persistente
    }.get(codigo, (200, zero, CAB_HTML))


# --- utilitários -------------------------------------------------------------
def rodar(funcao, *args):
    """Roda um main() capturando a saída; devolve (saída, exceção ou None)."""
    sys.argv = ["teste"]
    saida = io.StringIO()
    excecao = None
    with contextlib.redirect_stdout(saida):
        try:
            funcao(*args)
        except BaseException as e:  # noqa: BLE001 — o teste inspeciona a exceção
            excecao = e
    return saida.getvalue(), excecao


def pasta_da_execucao(fonte: str) -> Path:
    padrao = re.compile(rf"{re.escape(fonte)}_\d{{8}}T\d{{6}}Z")
    pastas = sorted(p for p in comum.DIR_BRUTOS.iterdir() if p.is_dir() and padrao.fullmatch(p.name))
    return pastas[-1]


def ler(p: Path) -> dict:
    return jsonlib.loads(p.read_text(encoding="utf-8"))


def ler_csv(p: Path) -> tuple[list[str], list[dict]]:
    with p.open(encoding="utf-8", newline="") as f:
        leitor = csv.DictReader(f)
        return list(leitor.fieldnames or []), list(leitor)


def retrato(pasta: Path) -> dict:
    return {str(p.relative_to(pasta)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(pasta.rglob("*"))}


# --- execução ----------------------------------------------------------------
DADOS_REAIS_ANTES = retrato(REPO / "dados")
TMP = Path(tempfile.mkdtemp(prefix="teste_coleta_", dir=BASE_TMP))
try:
    comum.RAIZ = TMP
    comum.DIR_DADOS = TMP / "dados"
    comum.DIR_BRUTOS = comum.DIR_DADOS / "brutos"
    comum.LOG_BUSCAS = comum.DIR_DADOS / "log_buscas.csv"
    comum.LOG_EXECUCOES = comum.DIR_DADOS / "execucoes.csv"
    comum.DIR_DADOS.mkdir(parents=True)
    # Estado anterior à primeira coleta: execucoes.csv só com cabeçalho; log_buscas.csv ausente.
    comum.LOG_EXECUCOES.write_text(",".join(comum.COLUNAS_EXECUCOES) + "\n", encoding="utf-8")
    (TMP / ".env").write_text(f"GITHUB_TOKEN=token_do_arquivo_env\nSTACKEXCHANGE_KEY={CHAVE_FALSA}\n",
                              encoding="utf-8")
    os.environ["GITHUB_TOKEN"] = "token_do_ambiente"
    os.environ.pop("STACKEXCHANGE_KEY", None)
    print(f"Diretório temporário: {TMP}\n")

    # 1) GitHub ---------------------------------------------------------------
    print("[1] GitHub: busca normal, 429 com Retry-After, incomplete_results persistente, 422, RATE_LIMITED no GraphQL")
    SESSAO["atual"] = SessaoFalsa(roteiro_github)
    ESPERAS.clear()
    saida, exc = rodar(coleta_github.main)
    checar(exc is None, f"execução terminou sem exceção ({exc!r})")
    gh = pasta_da_execucao("github")
    arquivos = sorted(p.name for p in gh.iterdir())
    checar(re.fullmatch(r"github_\d{8}T\d{6}Z", gh.name), f"pasta da execução em UTC: {gh.name}")
    checar(len(arquivos) == 162, f"162 arquivos na pasta (um por busca): {len(arquivos)}")
    checar("issues_A1B1.json" in arquivos and "discussions_A9B9.json" in arquivos, "nomes issues_A1B1.json ... discussions_A9B9.json")
    checar("GITHUB_TOKEN lido de: .env" in saida, "ler_env: imprime 'GITHUB_TOKEN lido de: .env'")
    checar("token_do_arquivo_env" not in saida and "token_do_ambiente" not in saida, "ler_env: valor do token não aparece na saída")
    checar(SESSAO["cabecalhos"]["Authorization"] == "Bearer token_do_arquivo_env", "ler_env: .env tem prioridade sobre o ambiente")

    b = ler(gh / "issues_A1B1.json")
    checar(b["status"] == "ok" and b["n_resultados"] == 2 and b["n_coletados"] == 2, "busca normal: status ok, n_resultados=2, n_coletados=2")
    checar(b["id_busca"] == f"{gh.name}_issues_A1B1", f"id_busca: {b['id_busca']}")
    checar(b["commit_head"] == "abc1234" and b["data_hora"].endswith("+00:00"), "metadados: commit_head e data_hora ISO com fuso")
    checar({"parametros", "avisos", "requisicoes", "string_enviada"} <= set(b), "metadados: parametros, avisos, requisicoes, string_enviada")
    checar(b["requisicoes"][0]["resposta"]["total_count"] == 2, "resposta completa gravada")
    cab = b["requisicoes"][0]["cabecalhos_resposta"]
    checar(set(cab) == {"content-type", "date", "x-ratelimit-limit", "x-ratelimit-remaining",
                        "x-ratelimit-reset", "x-ratelimit-resource"},
           f"cabeçalhos gravados só date, content-type, x-ratelimit-*: {sorted(cab)}")
    texto_gh = "".join(p.read_text(encoding="utf-8") for p in gh.iterdir())
    checar(not any(s in texto_gh.lower() for s in ("x-oauth-scopes", "token-expiration", "set-cookie", "x-github-request-id")),
           "nenhum cabeçalho descartado aparece nos brutos")

    b = ler(gh / "issues_A1B2.json")
    tent = b["requisicoes"][0]["tentativas_repetidas"]
    checar(b["status"] == "ok" and len(b["requisicoes"]) == 1, "429: busca terminou ok após nova tentativa")
    checar(len(tent) == 1 and tent[0]["status"] == 429 and tent[0]["espera_s"] == 8.0,
           f"429: tentativa anotada com espera Retry-After+1 = 8 s: {tent}")
    checar(8.0 in ESPERAS, "429: o script esperou 8 s")

    b = ler(gh / "issues_A1B3.json")
    checar(len(b["requisicoes"]) == 4, f"incomplete_results: 1 + 3 novas tentativas = 4 requisições no bruto: {len(b['requisicoes'])}")
    checar(any("incomplete_results=true" in a for a in b["avisos"]), f"incomplete_results: aviso no bruto: {b['avisos']}")
    checar(b["status"] == "ok", "incomplete_results: a busca não conta como erro")

    b = ler(gh / "issues_A1B4.json")
    checar(b["status"] == "erro" and "HTTP 422" in (b["erro"] or ""), f"422: status erro, mensagem: {(b['erro'] or '')[:60]}")
    checar(b["requisicoes"][0]["status"] == 422 and b["requisicoes"][0]["resposta"]["message"] == "Validation Failed",
           "422: resposta de erro gravada como bruto")
    checar(b["n_resultados"] is None and b["n_coletados"] is None, "422: n_resultados e n_coletados vazios no bruto")
    checar((gh / "issues_A1B5.json").exists(), "422: a execução seguiu para a próxima busca")

    b = ler(gh / "discussions_A1B1.json")
    checar(b["n_coletados"] == 1 and b["string_enviada"].startswith("POST https://api.github.com/graphql"),
           "GraphQL normal: nó nulo descartado de urls_coletadas; string_enviada descritiva")
    b = ler(gh / "discussions_A1B2.json")
    tent = b["requisicoes"][0]["tentativas_repetidas"]
    checar(b["status"] == "ok" and len(tent) == 1 and 25 <= tent[0]["espera_s"] <= 35,
           f"RATE_LIMITED (HTTP 200): nova tentativa após esperar até o reset: {tent}")
    checar(ESPERAS.count(3.0) == 161 + 3, f"intervalo de 3 s entre buscas (161) e entre tentativas do incomplete (3): {ESPERAS.count(3.0)}")

    # 2) Stack Exchange -------------------------------------------------------
    print("\n[2] Stack Exchange: filtro, throttle (400/502), backoff, chave mascarada")
    SESSAO["atual"] = SessaoFalsa(roteiro_se)
    ESPERAS.clear()
    saida, exc = rodar(api_stackexchange.main, "stackoverflow", "stackoverflow", "scripts/coleta_stackoverflow.py", "teste")
    checar(exc is None, f"execução terminou sem exceção ({exc!r})")
    se = pasta_da_execucao("stackoverflow")
    arquivos = sorted(p.name for p in se.iterdir())
    checar(len(arquivos) == 82 and "filtro.json" in arquivos, f"81 buscas + filtro.json: {len(arquivos)}")
    checar("STACKEXCHANGE_KEY lido de: .env" in saida and CHAVE_FALSA not in saida, "ler_env: origem impressa, valor não")
    enviados = [p for p in SESSAO["atual"].params_enviados if "q" in p]
    checar(all(p.get("key") == CHAVE_FALSA and p.get("filter") == "!filtroFalso" for p in enviados),
           "a chave e o filtro criado foram enviados em todas as buscas")
    texto_se = "".join(p.read_text(encoding="utf-8") for p in se.iterdir())
    checar(CHAVE_FALSA not in texto_se and "key=***" in texto_se, "a chave não aparece nos brutos (key=***)")
    b = ler(se / "A1B1.json")
    tent = b["requisicoes"][0]["tentativas_repetidas"]
    checar(b["status"] == "ok" and len(tent) == 1 and tent[0]["espera_s"] == 4.0,
           f"throttle 400/502: nova tentativa após 3+1 s: {tent}")
    checar(6.0 in ESPERAS and ESPERAS.count(2.0) == 79, "backoff de 5 s respeitado (espera de 6 s) e intervalo de 2 s nas demais")

    # 3) dbt ------------------------------------------------------------------
    print("\n[3] dbt: paginação até 100 tópicos, total conhecido, página sem tópicos novos")
    SESSAO["atual"] = SessaoFalsa(roteiro_dbt)
    ESPERAS.clear()
    saida, exc = rodar(coleta_dbt_forum.main)
    checar(exc is None, f"execução terminou sem exceção ({exc!r})")
    dbt = pasta_da_execucao("dbt_forum")
    checar(len(list(dbt.iterdir())) == 81, "81 arquivos na pasta")
    b = ler(dbt / "A1B1.json")
    checar(b["n_coletados"] == 100 and b["n_resultados"] is None and len(b["requisicoes"]) == 2,
           "mais de 100 tópicos: 2 páginas, 100 coletados, n_resultados vazio")
    checar(b["urls_coletadas"][0] == "https://discourse.getdbt.com/t/topico-1/1", "URL do tópico montada com slug")
    b = ler(dbt / "A1B2.json")
    checar(b["n_coletados"] == 10 and b["n_resultados"] == 10, "total conhecido: n_resultados = 10 tópicos distintos")
    b = ler(dbt / "A1B3.json")
    checar(b["n_resultados"] is None and any("sem tópicos novos" in a for a in b["avisos"]),
           f"paginação interrompida: n_resultados vazio e motivo nos avisos: {b['avisos']}")
    checar(ESPERAS.count(5.0) == 80 + 2, "5 s entre buscas (80) e entre páginas (2)")

    # 4) Execução interrompida --------------------------------------------------
    print("\n[4] Execução interrompida (Ctrl+C na 4ª busca)")
    _sleep_real(1.1)  # carimbo de execução diferente do anterior
    INTERROMPER["ativo"] = True
    SESSAO["atual"] = SessaoFalsa(roteiro_dbt)
    saida, exc = rodar(coleta_dbt_forum.main)
    checar(isinstance(exc, KeyboardInterrupt), f"KeyboardInterrupt propagado: {exc!r}")
    dbt2 = pasta_da_execucao("dbt_forum")
    checar(dbt2 != dbt and sorted(p.name for p in dbt2.iterdir()) == ["A1B1.json", "A1B2.json", "A1B3.json"],
           "nova pasta com só as 3 buscas concluídas")
    checar(not list(TMP.rglob("*.parcial")), "nenhum arquivo .parcial sobrou")

    # 5) Debezium -----------------------------------------------------------------
    print("\n[5] Debezium: 'of many', poucos, zero, bloqueio com HTTP 200, formato inesperado, login, "
          "access-error, 429 persistente, interrupção após 3 erros seguidos")
    DEBEZIUM["modo"] = "casos"
    SESSAO["atual"] = SessaoFalsa(roteiro_debezium)
    ESPERAS.clear()
    saida, exc = rodar(coleta_debezium.main)
    checar(isinstance(exc, SystemExit) and "3 buscas seguidas com erro (A1B7, A1B8, A1B9)" in str(exc.code),
           f"3 erros seguidos: execução interrompida antes de A2B1: {exc!r}"[:160])
    dz = pasta_da_execucao("debezium")
    checar(sorted(p.name for p in dz.iterdir()) == [f"A1B{j}.json" for j in range(1, 10)],
           "9 brutos (A1B1 a A1B9), nenhum para A2B1")
    checar(not any(CODIGO.get(p.get("q")) == "A2B1" for p in SESSAO["atual"].params_enviados),
           "nenhuma requisição enviada para A2B1")
    checar("User-Agent" not in SESSAO["cabecalhos"] and SESSAO["cabecalhos"].get("Accept-Language", "").startswith("en-US"),
           "User-Agent padrão do comum.py (não sobrescrito); Accept-Language en-US")
    checar(ESPERAS.count(5.0) == 9, f"intervalo de 5 s antes de cada busca a partir da 2ª (9): {ESPERAS.count(5.0)}")

    b = ler(dz / "A1B1.json")
    checar(b["status"] == "ok" and b["n_coletados"] == 30 and b["n_resultados"] is None
           and b["avisos"] == [coleta_debezium.AVISO_MAIS],
           f"'1–30 of many': 30 coletados, n_resultados vazio, aviso: {b['avisos']}")
    checar(b["urls_coletadas"][0] == "https://groups.google.com/g/debezium/c/id00", "URL canônica do tópico (sem /m/<mensagem>)")
    checar(b["requisicoes"][0]["resposta"] == pagina_groups([f"id{i:02d}" for i in range(30)], "1–30 of many"),
           "HTML completo gravado no bruto (requisicoes[0].resposta)")
    checar(b["string_enviada"] == 'https://groups.google.com/g/debezium/search?q="database per tenant" ingestion',
           "string_enviada legível, igual à do --dry-run")
    checar(set(b["requisicoes"][0]["cabecalhos_resposta"]) == {"content-type", "date"},
           "cabeçalhos gravados só date e content-type (Set-Cookie descartado)")
    b = ler(dz / "A1B2.json")
    checar(b["status"] == "ok" and (b["n_resultados"], b["n_coletados"]) == (4, 4) and b["avisos"] == [],
           "'1–4 of 4': 4/4, sem aviso; o '1–2 of 3' dentro das linhas é ignorado")
    b = ler(dz / "A1B3.json")
    checar(b["status"] == "ok" and (b["n_resultados"], b["n_coletados"]) == (0, 0) and b["urls_coletadas"] == [],
           "zero resultados: n_resultados = n_coletados = 0, status ok")
    b = ler(dz / "A1B4.json")
    checar(b["status"] == "erro" and "bloqueio" in (b["erro"] or "")
           and b["n_resultados"] is None and b["n_coletados"] is None,
           f"bloqueio com HTTP 200: erro com n vazios, nunca 0 resultados: {(b['erro'] or '')[:70]}")
    checar("unusual traffic" in b["requisicoes"][0]["resposta"], "bloqueio: página gravada como bruto")
    b = ler(dz / "A1B5.json")
    checar(b["status"] == "erro" and "fora do formato esperado" in (b["erro"] or ""),
           "contador '1–5 of 5' com 3 linhas: erro")
    checar(ler(dz / "A1B6.json")["status"] == "ok", "2 erros seguidos não interrompem; a busca ok seguinte zera a contagem")
    b = ler(dz / "A1B7.json")
    checar(b["status"] == "erro" and "redirecionamento para login" in (b["erro"] or "")
           and any(a.startswith("redirecionado: HTTP 302") for a in b["avisos"]),
           "login: erro, com a cadeia de redirecionamento nos avisos")
    checar(b["requisicoes"][0]["url"].startswith("https://accounts.google.com/"), "login: URL final gravada no bruto")
    b = ler(dz / "A1B8.json")
    checar(b["status"] == "erro" and "access-error" in (b["erro"] or ""), "access-error: erro")
    b = ler(dz / "A1B9.json")
    tent = b["requisicoes"][0]["tentativas_repetidas"]
    checar(b["status"] == "erro" and "bloqueio do Google" in (b["erro"] or "")
           and len(tent) == 3 and all(t["status"] == 429 for t in tent),
           "429 persistente (/sorry/): 3 tentativas registradas, depois erro de bloqueio")
    checar(ESPERAS.count(60.0) == 1 and ESPERAS.count(120.0) == 1, "429: esperas de 60 s e 120 s entre as tentativas")

    url_busca = coleta_debezium.URL_BUSCA + "?q=x"
    try:
        coleta_debezium.analisar(url_busca, "<html><head><title>Pesquisar conversas</title></head>"
                                            "<body>Nenhuma conversa corresponde à sua pesquisa</body></html>")
        resultado = "aceita"
    except coleta_debezium.PaginaInvalida:
        resultado = "erro"
    checar(resultado == "erro", "página sem resultados em outro idioma: erro, não 0 resultados")
    p = coleta_debezium.analisar(url_busca, pagina_groups([f"id{i}" for i in range(30)], "1–30 of 45"))
    checar(p.total == 45 and len(p.topicos) == 30, "contador numérico maior que a página: n_resultados = 45")

    _sleep_real(1.1)  # carimbo de execução diferente do anterior
    DEBEZIUM["modo"] = "completa"
    SESSAO["atual"] = SessaoFalsa(roteiro_debezium)
    ESPERAS.clear()
    saida, exc = rodar(coleta_debezium.main)
    checar(exc is None, f"execução sem erros terminou sem exceção ({exc!r})")
    dz2 = pasta_da_execucao("debezium")
    checar(dz2 != dz and len(list(dz2.iterdir())) == 81, "execução sem erros: nova pasta com 81 brutos")
    checar(ESPERAS == [5.0] * 80, "5 s entre as 81 buscas (80 esperas)")

    # 6) Registros ----------------------------------------------------------------
    print("\n[6] log_buscas.csv e execucoes.csv")
    cab, linhas = ler_csv(comum.LOG_BUSCAS)
    bruto_log = comum.LOG_BUSCAS.read_text(encoding="utf-8")
    checar(cab == comum.COLUNAS_LOG and bruto_log.count("id_busca,data_hora") == 1, "log_buscas.csv: cabeçalho da seção 11, uma vez")
    checar(len(linhas) == 162 + 81 + 81 + 3 + 9 + 81, f"log_buscas.csv: uma linha por busca executada (417): {len(linhas)}")
    por_id = {l["id_busca"]: l for l in linhas}
    l = por_id[f"{gh.name}_issues_A1B4"]
    checar(l["n_resultados"] == "" and l["n_coletados"] == "", "log: busca com erro tem n_resultados e n_coletados vazios")
    l = por_id[f"{dbt.name}_A1B1"]
    checar(l["n_resultados"] == "" and l["n_coletados"] == "100", "log: dbt com mais de 100 tópicos -> vazio / 100")
    checar(all(CHAVE_FALSA not in l["string_enviada"] for l in linhas), "log: chave do Stack Exchange não aparece")
    checar(por_id[f"{gh.name}_issues_A1B1"]["string_enviada"]
           == 'https://api.github.com/search/issues?q="database per tenant" ingestion is:issue&per_page=100&page=1',
           "log: string_enviada do GitHub igual à do --dry-run")
    log_dz = [(por_id[f"{dz.name}_{c}"]["n_resultados"], por_id[f"{dz.name}_{c}"]["n_coletados"])
              for c in ("A1B1", "A1B2", "A1B3", "A1B4")]
    checar(log_dz == [("", "30"), ("4", "4"), ("0", "0"), ("", "")],
           f"log Debezium: of many -> vazio/30; poucos -> 4/4; zero -> 0/0; bloqueio -> vazio/vazio: {log_dz}")

    cab, execs = ler_csv(comum.LOG_EXECUCOES)
    bruto_exec = comum.LOG_EXECUCOES.read_text(encoding="utf-8")
    checar(cab == comum.COLUNAS_EXECUCOES and bruto_exec.count("id_execucao,fonte") == 1,
           "execucoes.csv: cabeçalho pedido, uma vez (arquivo pré-existente com cabeçalho)")
    checar([e["id_execucao"] for e in execs] == [gh.name, se.name, dbt.name, dbt2.name, dz.name, dz2.name],
           "execucoes.csv: uma linha por execução, na ordem")
    resumo = [(e["status"], e["buscas_ok"], e["buscas_erro"]) for e in execs]
    checar(resumo == [("erro", "161", "1"), ("completa", "81", "0"), ("completa", "81", "0"), ("incompleta", "3", "0"),
                      ("incompleta", "4", "5"), ("completa", "81", "0")],
           f"status e contagens: {resumo}")
    checar(f"A1B1: {coleta_debezium.AVISO_MAIS}" in execs[4]["avisos"]
           and "execução interrompida: SystemExit: 3 buscas seguidas com erro" in execs[4]["avisos"],
           "execucoes.csv: aviso de mais resultados e motivo da interrupção do Debezium")
    checar(all(e["commit"] == "abc1234" and e["inicio"].endswith("+00:00") and e["fim"].endswith("+00:00") for e in execs),
           "commit e horários em UTC com fuso")
    checar("issues_A1B3: incomplete_results=true" in execs[0]["avisos"], "execucoes.csv: aviso de incomplete_results")
    checar("issues_A1B4: erro: ErroColeta: HTTP 422" in execs[0]["avisos"], "execucoes.csv: erro da busca nos avisos")
    checar("A1B3: página 2 sem tópicos novos" in execs[2]["avisos"], "execucoes.csv: aviso de paginação do dbt")
    checar("execução interrompida: Ctrl+C" in execs[3]["avisos"], "execucoes.csv: motivo da interrupção")

    # 7) Verificações e .env ------------------------------------------------------
    print("\n[7] Verificações anteriores à coleta e ler_env")
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            verificar_real(False, [api_stackexchange.SEM_CHAVE])
            mensagem = ""
        except SystemExit as e:
            mensagem = str(e.code)
    checar("Coleta abortada" in mensagem and "STACKEXCHANGE_KEY não encontrada" in mensagem,
           "sem STACKEXCHANGE_KEY a coleta aborta com a explicação da cota")
    checar("a tag 'v0-protocolo' não existe" in mensagem, "sem a tag a coleta aborta")
    (TMP / ".env").write_text("OUTRA=1\n", encoding="utf-8")
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        valor_gh = comum.ler_env("GITHUB_TOKEN")
        valor_se = comum.ler_env("STACKEXCHANGE_KEY")
    checar(valor_gh == "token_do_ambiente" and "GITHUB_TOKEN lido de: ambiente" in saida.getvalue(),
           "ler_env: sem a chave no .env, usa o ambiente e informa 'ambiente'")
    checar(valor_se is None and "STACKEXCHANGE_KEY: não encontrado" in saida.getvalue(), "ler_env: ausente nos dois")

finally:
    shutil.rmtree(TMP, ignore_errors=True)

print()
checar(not TMP.exists(), f"diretório temporário apagado: {TMP}")
checar(retrato(REPO / "dados") == DADOS_REAIS_ANTES, "dados/ do repositório não foi alterado")
print(f"\n{'TODOS OS TESTES PASSARAM' if not FALHAS else f'{len(FALHAS)} FALHA(S)'}")
sys.exit(1 if FALHAS else 0)
