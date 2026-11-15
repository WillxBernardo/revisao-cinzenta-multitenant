"""Coleta no grupo de usuários do Debezium (Google Groups), página de busca.

Protocolo, seção 5.3, com o desvio D1 (seção 13):
  https://groups.google.com/g/debezium/search?q=<termo A> <termo B>

O Google Groups não tem API. A página de busca vem renderizada no servidor com
até 30 tópicos; as páginas seguintes dependem de JavaScript e de uma rota interna
bloqueada pelo robots.txt. Por isso (D1), só a primeira página de cada busca é
coletada. O HTML completo fica no bruto da busca (requisicoes[0].resposta), no
mesmo formato JSON das outras fontes.

Classificação da resposta (só as duas primeiras formas são busca "ok"):
- resultados: contador "1–N of M" ou "1–N of many" antes da lista, e N linhas de
  tópico, cada uma com link para o próprio tópico. n_coletados = N;
  n_resultados = M, ou vazio com "of many", caso em que a busca recebe o aviso
  AVISO_MAIS;
- zero resultados: texto "No conversations matched your search", sem linhas e
  sem contador. n_resultados = n_coletados = 0;
- qualquer outra resposta é erro da busca, nunca "0 resultados": redirecionamento
  para login (accounts.google.com), acesso negado (/access-error), bloqueio do
  Google (/sorry/, HTTP 429 que persiste após as novas tentativas) ou página fora
  do formato esperado (ex.: CAPTCHA ou "unusual traffic" servidos com HTTP 200).
As duas primeiras formas exigem a URL final na página de busca do grupo e o
título "Search Conversations". Os textos são reconhecidos em inglês, por isso o
cabeçalho Accept-Language é fixo.

Após 3 buscas seguidas com erro, a execução é interrompida antes da próxima
requisição (status "incompleta"), para não insistir contra um bloqueio.

Brutos: dados/brutos/debezium_<AAAAMMDDTHHMMSSZ>/A1B1.json ... A9B9.json.

Uso (a partir da raiz do repositório):
  python scripts/coleta_debezium.py --dry-run
  python scripts/coleta_debezium.py
"""

from __future__ import annotations

import html
import re
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit

import comum
from comum import (
    Busca, ErroColeta, EstadoBusca, ResultadoBusca, Tarefa,
    requisitar, url_legivel, url_preparada,
)

FONTE = "debezium"
GRUPO = "debezium"
URL_BASE = "https://groups.google.com"
URL_BUSCA = f"{URL_BASE}/g/{GRUPO}/search"
URL_TOPICO = f"{URL_BASE}/g/{GRUPO}/c/"   # + id do tópico = URL canônica do tópico

INTERVALO = 5.0           # D1; o robots.txt de groups.google.com pede Crawl-delay: 1
MAX_TENTATIVAS = 3        # em HTTP 429: esperas de 60 s e 120 s antes de desistir
MAX_ERROS_SEGUIDOS = 3
IDIOMA = "en-US,en;q=0.9"
RESULTADOS_POR_PAGINA = 30

TITULO_BUSCA = "Search Conversations"
TEXTO_SEM_RESULTADOS = "No conversations matched your search"
AVISO_MAIS = "mais resultados não coletados (limite da 1ª página)"
# Só descrevem o erro; o reconhecimento de uma página válida não depende delas.
MARCAS_BLOQUEIO = ("unusual traffic", "captcha", "/sorry/")

RE_DIV = re.compile(r"<div\b[^>]*>")
RE_ROWID = re.compile(r'\bdata-rowid="([^"]+)"')
RE_TITULO = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
# Contador como texto inteiro de um elemento: ">1–30 of many<", ">1–4 of 4<".
RE_CONTADOR = re.compile(r">\s*(\d[\d,]*)\s*(?:–|&ndash;|&#8211;|-)\s*(\d[\d,]*)\s+of\s+(many|\d[\d,]*)\s*<")


class PaginaInvalida(ErroColeta):
    """A resposta não é uma página de busca reconhecível: erro da busca, nunca 0 resultados."""


@dataclass
class Pagina:
    topicos: list[str]     # ids dos tópicos, na ordem da página
    total: int | None      # M de "1–N of M"; None com "of many"; 0 sem resultados


def _inteiro(texto: str) -> int:
    return int(texto.replace(",", ""))


def _id_da_linha(tag: str) -> str | None:
    m = RE_ROWID.search(tag)
    return m.group(1) if m else None


def analisar(url_final: str, texto: str) -> Pagina:
    """Classifica a resposta da busca; levanta PaginaInvalida se não for resultado nem zero."""
    u = urlsplit(url_final)
    if u.hostname == "accounts.google.com":
        raise PaginaInvalida(f"redirecionamento para login: {url_final}")
    if "/sorry/" in u.path:
        raise PaginaInvalida(f"bloqueio do Google (tráfego incomum ou CAPTCHA): {url_final}")
    if u.path.startswith("/access-error"):
        raise PaginaInvalida(f"acesso negado pelo Google Groups (access-error): {url_final}")
    if u.hostname != "groups.google.com" or u.path != f"/g/{GRUPO}/search":
        raise PaginaInvalida(f"URL final inesperada: {url_final}")

    m = RE_TITULO.search(texto)
    titulo = html.unescape(m.group(1)).strip() if m else None
    linhas = [d for d in RE_DIV.finditer(texto) if 'role="row"' in d.group(0)]
    ids = [_id_da_linha(d.group(0)) for d in linhas]
    # O contador fica antes da lista; procurá-lo só ali evita confundi-lo com o
    # texto de um tópico (ex.: um trecho que diga "1-2 of 3").
    contadores = RE_CONTADOR.findall(texto[: linhas[0].start() if linhas else len(texto)])
    sem_resultados = TEXTO_SEM_RESULTADOS in texto

    def invalida(motivo: str) -> PaginaInvalida:
        marcas = [x for x in MARCAS_BLOQUEIO if x in texto.lower()]
        tipo = f"possível bloqueio do Google (marcas: {', '.join(marcas)})" if marcas else "página fora do formato esperado"
        return PaginaInvalida(f"{tipo}: {motivo}; título={titulo!r}, linhas={len(linhas)}, contador={contadores}")

    if titulo != TITULO_BUSCA:
        raise invalida("título diferente do da página de busca")
    if not linhas and not contadores and sem_resultados:
        return Pagina(topicos=[], total=0)
    if sem_resultados or len(contadores) != 1:
        raise invalida("contador ausente, repetido ou junto do texto de zero resultados")

    inicio, fim, total = contadores[0]
    inicio, fim = _inteiro(inicio), _inteiro(fim)
    total = None if total == "many" else _inteiro(total)
    if inicio != 1 or fim != len(linhas) or (total is not None and total < fim):
        raise invalida("contador incoerente com o número de linhas")
    if None in ids or len(set(ids)) != len(ids):
        raise invalida("linha sem id de tópico ou repetida")
    sem_link = [i for i in ids if f'href="./g/{GRUPO}/c/{i}' not in texto]
    if sem_link:
        raise invalida(f"linhas sem link para o tópico: {sem_link[:3]}")
    return Pagina(topicos=ids, total=total)


def params_busca(busca: Busca) -> dict:
    return {"q": busca.consulta}


def buscar(sessao, busca: Busca, estado: EstadoBusca, erros_seguidos: list[str]) -> ResultadoBusca:
    if len(erros_seguidos) >= MAX_ERROS_SEGUIDOS:
        # SystemExit atravessa o tratamento por busca de comum.executar_coleta, que
        # grava a execução como "incompleta". Nenhuma requisição é feita para esta busca.
        sys.exit(f"{len(erros_seguidos)} buscas seguidas com erro ({', '.join(erros_seguidos)}); "
                 f"coleta interrompida antes de {busca.codigo} para não insistir contra um possível bloqueio")
    try:
        try:
            resp = requisitar(sessao, "GET", URL_BUSCA, estado,
                              params=params_busca(busca), max_tentativas=MAX_TENTATIVAS)
        except ErroColeta as e:
            ultima = estado.requisicoes[-1] if estado.requisicoes else {}
            if ultima.get("status") == 429 or "/sorry/" in (ultima.get("url") or ""):
                raise PaginaInvalida(f"bloqueio do Google ({ultima.get('url')}): {e}") from e
            raise
        if resp.history:
            cadeia = " -> ".join(f"HTTP {h.status_code} {h.headers.get('Location', '')}" for h in resp.history)
            estado.avisos.append(f"redirecionado: {cadeia} -> {resp.url}")
        pagina = analisar(resp.url, resp.text)
    except Exception:
        erros_seguidos.append(busca.codigo)
        raise
    erros_seguidos.clear()

    if pagina.total is None or pagina.total > len(pagina.topicos):
        estado.avisos.append(AVISO_MAIS)
    return ResultadoBusca(
        n_resultados=pagina.total,
        urls_coletadas=[URL_TOPICO + t for t in pagina.topicos],
    )


def main() -> None:
    args = comum.argumentos(__doc__.splitlines()[0])
    repositorio = comum.verificar_antes_da_coleta(args.dry_run, [])

    # Mesmo User-Agent das outras fontes (comum.USER_AGENT).
    sessao = None if args.dry_run else comum.nova_sessao({"Accept": "text/html", "Accept-Language": IDIOMA})
    erros_seguidos: list[str] = []
    tarefas = [
        Tarefa(
            sufixo_id=b.codigo,
            busca=b,
            previa=url_legivel(url_preparada("GET", URL_BUSCA, params_busca(b))),
            executar=lambda estado, b=b: buscar(sessao, b, estado, erros_seguidos),
        )
        for b in comum.gerar_buscas()
    ]

    if args.dry_run:
        comum.imprimir_plano(FONTE, tarefas)
        return

    comum.executar_coleta(
        FONTE, tarefas,
        intervalo=INTERVALO,
        parametros={
            "url_busca": URL_BUSCA,
            "desvio_protocolo": "D1 (seção 13): só a 1ª página de cada busca",
            "paginas_coletadas": 1,
            "resultados_por_pagina": RESULTADOS_POR_PAGINA,
            "accept_language": IDIOMA,
            "max_tentativas": MAX_TENTATIVAS,
            "max_erros_seguidos": MAX_ERROS_SEGUIDOS,
        },
        repositorio=repositorio,
        script="scripts/coleta_debezium.py",
    )


if __name__ == "__main__":
    main()
