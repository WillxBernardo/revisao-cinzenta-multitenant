"""Deduplicação dos itens coletados (protocolo, seção 6.3, passo 1; desvio D2).

Considera só a última execução "completa" de cada fonte em dados/execucoes.csv
(seção 5.5). Para cada busca dessa execução, lê os itens de urls_coletadas e tira
título, trecho e data da resposta bruta. Itens com a mesma URL canônica são
unificados, com o registro de todas as buscas que os encontraram.

URL canônica: sem âncora (#...), sem parâmetros (?...), sem /m/<id da mensagem>
no Google Groups e sem barra final; esquema e domínio em minúsculas.

Trecho (D2): os primeiros 600 caracteres do corpo, sem HTML e com espaços
normalizados. O fórum do dbt e o Google Groups não entregam o corpo na busca;
nesses casos, o trecho é o que a busca oferece, e a coluna origem_trecho registra
isso:
  corpo            corpo do item (GitHub issues e discussions, Stack Exchange)
  corpo_vazio      a fonte entregou o corpo vazio
  trecho_da_busca  trecho em torno do termo encontrado (blurb do Discourse;
                   texto da linha de resultado do Google Groups)

data_publicacao (AAAA-MM-DD): criação do item; no Google Groups, a data exibida
na linha de resultado (a interface não informa a criação do tópico na busca).

Saída: dados/itens.csv, ordenado por fonte e depois por url_canonica, com
id_item I0001, I0002, ... nessa ordem. O script só lê dados/brutos/.

Uso (a partir da raiz do repositório):
  python scripts/deduplicar.py
"""

from __future__ import annotations

import csv
import html
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

RAIZ = Path(__file__).resolve().parent.parent
DIR_DADOS = RAIZ / "dados"
LOG_EXECUCOES = DIR_DADOS / "execucoes.csv"
SAIDA = DIR_DADOS / "itens.csv"

TAMANHO_TRECHO = 600
ESTRATEGIAS = ["banco_por_tenant", "esquema_por_tenant", "esquema_compartilhado"]
COLUNAS = [
    "id_item", "url_canonica", "fonte", "tipo", "titulo", "trecho", "data_publicacao",
    "ids_busca", "n_buscas", "estrategias", "origem_trecho",
]


# --------------------------------------------------------------------------
# Texto
# --------------------------------------------------------------------------

def espacos(texto: str) -> str:
    return " ".join(texto.split())


BLOCOS_HTML = {
    "address", "article", "blockquote", "br", "dd", "div", "dl", "dt", "figcaption", "h1", "h2",
    "h3", "h4", "h5", "h6", "hr", "li", "ol", "p", "pre", "section", "table", "td", "th", "tr", "ul",
}


class _Texto(HTMLParser):
    """Texto de um fragmento HTML. Elementos de bloco viram espaço; os inline
    (<b>, <code>, <a>...) não, para não separar palavras; script/style são ignorados."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self._ignorar = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._ignorar += 1
        if tag in BLOCOS_HTML:
            self.partes.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._ignorar:
            self._ignorar -= 1
        if tag in BLOCOS_HTML:
            self.partes.append(" ")

    def handle_data(self, data):
        if not self._ignorar:
            self.partes.append(data)


def texto_de_html(fragmento: str | None) -> str:
    """Para HTML de verdade (Stack Exchange, Discourse, Google Groups)."""
    p = _Texto()
    p.feed(fragmento or "")
    p.close()
    return espacos("".join(p.partes))


# Markdown do GitHub: remove comentários HTML e tags HTML conhecidas, mas preserva
# marcadores como <tenant_id> ou <schema>, que são texto e não HTML.
TAGS_HTML = (
    "a|abbr|b|blockquote|br|code|dd|del|details|div|dl|dt|em|h[1-6]|hr|i|img|input|ins|kbd|li|"
    "ol|p|picture|pre|q|s|samp|source|span|strike|strong|sub|summary|sup|table|tbody|td|tfoot|"
    "th|thead|tr|tt|u|ul|var|video"
)
RE_COMENTARIO = re.compile(r"<!--.*?(?:-->|$)", re.S)
RE_TAG = re.compile(rf"</?(?:{TAGS_HTML})\b[^>]*/?>", re.I)


def texto_de_markdown(corpo: str | None) -> str:
    sem_html = RE_TAG.sub(" ", RE_COMENTARIO.sub(" ", corpo or ""))
    return espacos(html.unescape(sem_html))


def trecho(texto: str) -> str:
    return texto[:TAMANHO_TRECHO]


# --------------------------------------------------------------------------
# URLs e datas
# --------------------------------------------------------------------------

def url_canonica(url: str) -> str:
    p = urlsplit(url.strip())
    caminho = re.sub(r"(/g/[^/]+/c/[^/]+)/m/[^/]+$", r"\1", p.path)
    caminho = caminho.rstrip("/")
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), caminho, "", ""))


def data_iso(valor: str | None) -> str:
    return valor[:10] if valor else ""


def data_unix(valor: int | None) -> str:
    return datetime.fromtimestamp(valor, timezone.utc).strftime("%Y-%m-%d") if valor else ""


def data_groups(texto: str, data_hora_coleta: str) -> str:
    """'1/16/22' -> 2022-01-16; 'Oct 22' -> ano da coleta; '10:15 AM' -> dia da coleta."""
    texto = texto.strip()
    coleta = datetime.fromisoformat(data_hora_coleta)
    for formato in ("%m/%d/%y", "%b %d"):
        try:
            d = datetime.strptime(texto, formato)
        except ValueError:
            continue
        if formato == "%b %d":
            d = d.replace(year=coleta.year)
        return d.strftime("%Y-%m-%d")
    if re.fullmatch(r"\d{1,2}:\d{2}\s?[AP]M", texto):
        return coleta.strftime("%Y-%m-%d")
    return ""


# --------------------------------------------------------------------------
# Itens de cada fonte: {url como coletada: (tipo, titulo, trecho, origem, data)}
# --------------------------------------------------------------------------

def _corpo(texto: str) -> tuple[str, str]:
    return (trecho(texto), "corpo") if texto else ("", "corpo_vazio")


def itens_github_issues(bruto: dict) -> dict:
    resposta = bruto["requisicoes"][-1]["resposta"]  # vale a última (seção 5.5)
    itens = {}
    for it in resposta["items"]:
        t, origem = _corpo(texto_de_markdown(it.get("body")))
        itens[it["html_url"]] = ("issue", espacos(it["title"]), t, origem, data_iso(it.get("created_at")))
    return itens


def itens_github_discussions(bruto: dict) -> dict:
    resposta = bruto["requisicoes"][-1]["resposta"]
    itens = {}
    for n in resposta["data"]["search"]["nodes"]:
        if n:
            t, origem = _corpo(texto_de_markdown(n.get("body")))
            itens[n["url"]] = ("discussion", espacos(n["title"]), t, origem, data_iso(n.get("createdAt")))
    return itens


def itens_stackexchange(bruto: dict) -> dict:
    itens = {}
    for r in bruto["requisicoes"]:
        for it in (r["resposta"] or {}).get("items", []):
            t, origem = _corpo(texto_de_html(it.get("body")))
            itens[it["link"]] = ("pergunta", espacos(html.unescape(it["title"])), t, origem,
                                 data_unix(it.get("creation_date")))
    return itens


def itens_dbt(bruto: dict) -> dict:
    topicos, blurbs = {}, {}
    for r in bruto["requisicoes"]:  # todas as páginas lidas
        for t in r["resposta"].get("topics", []):
            topicos.setdefault(t["id"], t)
        for p in r["resposta"].get("posts", []):  # ordem de relevância: vale o 1º post do tópico
            blurbs.setdefault(p["topic_id"], p.get("blurb") or "")
    itens = {}
    for url in bruto["urls_coletadas"]:
        tid = int(url.rstrip("/").rsplit("/", 1)[1])
        t = topicos[tid]
        itens[url] = ("topico", espacos(html.unescape(t["title"])), trecho(texto_de_html(blurbs.get(tid))),
                      "trecho_da_busca", data_iso(t.get("created_at")))
    return itens


RE_LINHA = re.compile(r'<div\b[^>]*\brole="row"[^>]*>')
RE_ROWID = re.compile(r'\bdata-rowid="([^"]+)"')
RE_TITULO_TRECHO = re.compile(
    r'<a\b[^>]*href="\./g/[^/]+/c/[^"]+"[^>]*>\s*<div\b[^>]*>\s*<span\b[^>]*>(.*?)</span>\s*</div>'
    r'\s*<div\b[^>]*>(.*?)</div>\s*</a>', re.S)
RE_DATA_LINHA = re.compile(r">(\d{1,2}/\d{1,2}/\d{2}|[A-Z][a-z]{2} \d{1,2}|\d{1,2}:\d{2}\s?[AP]M)<")


def itens_groups(bruto: dict) -> dict:
    pagina = bruto["requisicoes"][-1]["resposta"]
    linhas = list(RE_LINHA.finditer(pagina))
    por_id = {}
    for k, m in enumerate(linhas):
        fim = linhas[k + 1].start() if k + 1 < len(linhas) else len(pagina)
        bloco = pagina[m.start():fim]
        tid = RE_ROWID.search(m.group(0)).group(1)
        tt = RE_TITULO_TRECHO.search(bloco)
        d = RE_DATA_LINHA.search(bloco)
        if not tt:
            sys.exit(f"{bruto['id_busca']}: linha {tid} sem título/trecho reconhecível")
        por_id[tid] = ("topico", texto_de_html(tt.group(1)), trecho(texto_de_html(tt.group(2))),
                       "trecho_da_busca", data_groups(d.group(1), bruto["data_hora"]) if d else "")
    # urls_coletadas termina em /c/<id do tópico>
    return {url: por_id[url.rsplit("/", 1)[1]] for url in bruto["urls_coletadas"] if url.rsplit("/", 1)[1] in por_id}


def extrator(fonte: str, arquivo: Path):
    if fonte == "github":
        return itens_github_issues if arquivo.name.startswith("issues_") else itens_github_discussions
    return {
        "stackoverflow": itens_stackexchange, "dba": itens_stackexchange,
        "dbt_forum": itens_dbt, "debezium": itens_groups,
    }[fonte]


# --------------------------------------------------------------------------
# Execução
# --------------------------------------------------------------------------

def ultimas_completas() -> dict[str, str]:
    """fonte -> id_execucao da última execução completa (ordem do execucoes.csv)."""
    escolhidas: dict[str, str] = {}
    with LOG_EXECUCOES.open(encoding="utf-8", newline="") as f:
        for linha in csv.DictReader(f):
            if linha["status"] == "completa":
                escolhidas[linha["fonte"]] = linha["id_execucao"]
    return escolhidas


def main() -> None:
    execucoes = ultimas_completas()
    itens: dict[str, dict] = {}
    divergencias = 0
    print("Execuções consideradas (última completa de cada fonte):")
    for fonte, id_execucao in sorted(execucoes.items()):
        pasta = DIR_DADOS / "brutos" / id_execucao
        arquivos = sorted(p for p in pasta.glob("*.json") if p.name != "filtro.json")
        print(f"  {fonte:<14} {id_execucao}  ({len(arquivos)} buscas)")
        for arquivo in arquivos:
            bruto = json.loads(arquivo.read_text(encoding="utf-8"))
            if bruto["status"] != "ok":
                sys.exit(f"{arquivo}: busca com status {bruto['status']} numa execução completa")
            dados = extrator(fonte, arquivo)(bruto)
            for url in bruto["urls_coletadas"]:
                if url not in dados:
                    sys.exit(f"{arquivo}: {url} está em urls_coletadas, mas não na resposta bruta")
                tipo, titulo, txt, origem, data = dados[url]
                canonica = url_canonica(url)
                item = itens.setdefault(canonica, {
                    "url_canonica": canonica, "fonte": fonte, "tipo": tipo, "titulo": titulo,
                    "trecho": txt, "data_publicacao": data, "origem_trecho": origem,
                    "buscas": set(), "estrategias": set(),
                })
                if (item["titulo"], item["trecho"]) != (titulo, txt):
                    divergencias += 1  # vale a primeira ocorrência
                item["buscas"].add(bruto["id_busca"])
                item["estrategias"].add(bruto["estrategia"])

    ordenados = sorted(itens.values(), key=lambda i: (i["fonte"], i["url_canonica"]))
    with SAIDA.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUNAS, lineterminator="\n")
        escritor.writeheader()
        for n, item in enumerate(ordenados, start=1):
            escritor.writerow({
                "id_item": f"I{n:04d}",
                **{k: item[k] for k in ("url_canonica", "fonte", "tipo", "titulo", "trecho",
                                        "data_publicacao", "origem_trecho")},
                "ids_busca": ";".join(sorted(item["buscas"])),
                "n_buscas": len(item["buscas"]),
                "estrategias": ";".join(e for e in ESTRATEGIAS if e in item["estrategias"]),
            })
    print(f"\n{len(ordenados)} itens únicos -> {SAIDA.relative_to(RAIZ)}")
    if divergencias:
        print(f"aviso: {divergencias} ocorrências com título ou trecho diferente da primeira (vale a primeira)")


if __name__ == "__main__":
    main()
