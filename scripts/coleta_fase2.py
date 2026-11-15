"""Coleta o conteúdo completo (corpo + comentários/respostas) dos itens da fase 2.

Elegíveis: itens com decisao_f1 = incluir ou duvida e decisao_f2 ainda vazia
(ou os IDs passados em --ids). Para cada item:

- GitHub issue: REST /issues/{n} e /issues/{n}/comments (todas as páginas);
- GitHub discussion: GraphQL (corpo, comentários e respostas, todas as páginas);
- Stack Overflow / DBA: API 2.3 do Stack Exchange (pergunta, comentários,
  respostas e comentários das respostas; filtro withbody);
- fórum do dbt (Discourse): /t/{id}.json e /t/{id}/posts.json para os demais posts;
- grupo do Debezium (Google Groups): HTML da página do tópico, intervalo de 5 s.

Saídas:
- bruto: dados/brutos/fase2_<AAAAMMDDTHHMMSSZ>/<ID>.json, com as respostas
  completas das APIs (status HTTP incluído, inclusive em erro);
- leitura: <pasta_leitura>/<ID>.txt, texto corrido para a leitura humana. Blocos
  de código com mais de 30 linhas aparecem truncados só neste texto (o bruto fica
  completo).

Espera entre requisições e nova tentativa em 403/429 (CLAUDE.md, regra 9).
Credenciais lidas do .env por comum.ler_env (nunca impressas).

Uso: python scripts/coleta_fase2.py <pasta_leitura> [--ids arquivo_com_ids]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from comum import USER_AGENT, ler_env  # noqa: E402

MAX_LINHAS_CODIGO = 30
Q_DISC = """query($o:String!,$r:String!,$n:Int!,$c:String){repository(owner:$o,name:$r){discussion(number:$n){
title url createdAt author{login} body category{name}
comments(first:50,after:$c){pageInfo{hasNextPage endCursor} nodes{author{login} createdAt body
replies(first:100){nodes{author{login} createdAt body}}}}}}}"""


class Coletor:
    def __init__(self):
        self.token = ler_env("GITHUB_TOKEN")
        self.sekey = ler_env("STACKEXCHANGE_KEY")
        self.s = requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT

    def req(self, metodo, url, espera=1.0, **kw):
        r = None
        for tentativa in range(4):
            time.sleep(espera)
            r = self.s.request(metodo, url, timeout=60, **kw)
            if r.status_code in (403, 429) and tentativa < 3:
                pausa = int(r.headers.get("retry-after", "0") or 0) or 60 * (tentativa + 1)
                print(f"  HTTP {r.status_code} em {url}; pausa de {pausa}s", flush=True)
                time.sleep(pausa)
                continue
            return r
        return r

    def gh_rest(self, caminho):
        h = {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"}
        paginas, url = [], f"https://api.github.com{caminho}"
        while url:
            r = self.req("GET", url, headers=h)
            try:
                corpo = r.json()
            except ValueError:
                corpo = r.text
            paginas.append({"url": url, "status": r.status_code, "json": corpo})
            url = r.links.get("next", {}).get("url") if r.ok else None
        return paginas

    def gh_disc(self, o, rep, n):
        h = {"Authorization": f"Bearer {self.token}"}
        paginas, cursor = [], None
        while True:
            r = self.req("POST", "https://api.github.com/graphql", headers=h,
                         json={"query": Q_DISC, "variables": {"o": o, "r": rep, "n": n, "c": cursor}})
            j = r.json()
            paginas.append({"status": r.status_code, "json": j})
            d = (((j.get("data") or {}).get("repository") or {}).get("discussion") or {})
            pi = (d.get("comments") or {}).get("pageInfo") or {}
            if not pi.get("hasNextPage"):
                return paginas
            cursor = pi["endCursor"]

    def se(self, site, caminho):
        p = {"site": site, "filter": "withbody", "pagesize": 100}
        if self.sekey:
            p["key"] = self.sekey
        r = self.req("GET", f"https://api.stackexchange.com/2.3{caminho}", params=p)
        return {"caminho": caminho, "status": r.status_code, "json": r.json()}


class _Texto(HTMLParser):
    BLOCO = {"p", "div", "br", "li", "pre", "tr", "h1", "h2", "h3", "h4", "blockquote"}

    def __init__(self):
        super().__init__()
        self.partes, self.pular = [], 0

    def handle_starttag(self, t, a):
        if t in ("script", "style"):
            self.pular += 1
        if t in self.BLOCO:
            self.partes.append("\n")

    def handle_endtag(self, t):
        if t in ("script", "style"):
            self.pular -= 1
        if t in self.BLOCO:
            self.partes.append("\n")

    def handle_data(self, d):
        if not self.pular:
            self.partes.append(d)


def texto_html(h):
    p = _Texto()
    p.feed(h or "")
    return re.sub(r"\n\s*\n+", "\n\n", "".join(p.partes)).strip()


def encurtar_codigo(md):
    """Trunca blocos ``` com mais de MAX_LINHAS_CODIGO linhas (só no texto de leitura)."""
    def sub(m):
        linhas = m.group(0).split("\n")
        if len(linhas) <= MAX_LINHAS_CODIGO + 2:
            return m.group(0)
        return "\n".join(linhas[:MAX_LINHAS_CODIGO] + [f"[... {len(linhas) - MAX_LINHAS_CODIGO - 1} linhas de código omitidas na leitura ...]", "```"])
    return re.sub(r"```.*?```", sub, md or "", flags=re.S)


def coletar(c: Coletor, it: dict):
    url, fonte = it["url_canonica"], it["fonte"]
    bruto = {"id_item": it["id_item"], "url": url, "fonte": fonte,
             "coletado_em": datetime.now(timezone.utc).isoformat()}
    linhas = [f"# {it['id_item']} {url}", f"TÍTULO: {it['titulo']}"]
    if fonte == "github":
        m = re.match(r"https://github\.com/([^/]+)/([^/]+)/(issues|discussions)/(\d+)", url)
        if m and m.group(1) != "orgs":
            o, rep, tipo, n = m.groups()
        else:
            m = re.match(r"https://github\.com/orgs/([^/]+)/discussions/(\d+)", url)
            o, rep, tipo, n = m.group(1), ".github", "discussions", m.group(2)
        if tipo == "issues":
            bruto["issue"] = c.gh_rest(f"/repos/{o}/{rep}/issues/{n}")
            bruto["comments"] = c.gh_rest(f"/repos/{o}/{rep}/issues/{n}/comments?per_page=100")
            iss = bruto["issue"][0]["json"] if isinstance(bruto["issue"][0]["json"], dict) else {}
            if bruto["issue"][0]["status"] != 200:
                linhas.append(f"INACESSÍVEL: HTTP {bruto['issue'][0]['status']}")
            linhas += [f"AUTOR: {(iss.get('user') or {}).get('login')} | criado {iss.get('created_at')} | estado {iss.get('state')} | rótulos {[l['name'] for l in iss.get('labels', [])]}",
                       "", encurtar_codigo(iss.get("body"))]
            for pg in bruto["comments"]:
                for cm in (pg["json"] if isinstance(pg["json"], list) else []):
                    linhas += ["", f"--- COMENTÁRIO {cm['user']['login']} ({cm.get('author_association')}) {cm['created_at']}",
                               encurtar_codigo(cm.get("body"))]
        else:
            bruto["discussion"] = c.gh_disc(o, rep, int(n))
            d0 = (((bruto["discussion"][0]["json"].get("data") or {}).get("repository") or {}).get("discussion"))
            if not d0:
                linhas.append(f"INACESSÍVEL: {json.dumps(bruto['discussion'][0]['json'].get('errors'))[:300]}")
            else:
                linhas += [f"AUTOR: {(d0.get('author') or {}).get('login')} | criado {d0['createdAt']} | categoria {d0['category']['name']}",
                           "", encurtar_codigo(d0["body"])]
                for pg in bruto["discussion"]:
                    dd = pg["json"]["data"]["repository"]["discussion"]
                    for cm in dd["comments"]["nodes"]:
                        linhas += ["", f"--- COMENTÁRIO {(cm.get('author') or {}).get('login')} {cm['createdAt']}", encurtar_codigo(cm["body"])]
                        for rp in cm["replies"]["nodes"]:
                            linhas += ["", f"    --- RESPOSTA {(rp.get('author') or {}).get('login')} {rp['createdAt']}", encurtar_codigo(rp["body"])]
    elif fonte in ("stackoverflow", "dba"):
        site = "stackoverflow" if fonte == "stackoverflow" else "dba"
        qid = re.search(r"/questions/(\d+)", url).group(1)
        bruto["question"] = c.se(site, f"/questions/{qid}")
        bruto["question_comments"] = c.se(site, f"/questions/{qid}/comments")
        bruto["answers"] = c.se(site, f"/questions/{qid}/answers")
        itens_q = bruto["question"]["json"].get("items", [])
        if not itens_q:
            linhas.append("INACESSÍVEL: pergunta não retornada pela API")
        else:
            q = itens_q[0]
            linhas += [f"AUTOR: {q['owner'].get('display_name')} | criado {datetime.fromtimestamp(q['creation_date'], timezone.utc).date()} | score {q['score']}",
                       "", texto_html(q["body"])]
        for cm in bruto["question_comments"]["json"].get("items", []):
            linhas += ["", f"--- COMENTÁRIO {cm['owner'].get('display_name')}", texto_html(cm["body"])]
        respostas = bruto["answers"]["json"].get("items", [])
        if respostas:
            bruto["answer_comments"] = c.se(site, f"/answers/{';'.join(str(a['answer_id']) for a in respostas)}/comments")
        for a in respostas:
            linhas += ["", f"--- RESPOSTA {a['owner'].get('display_name')} score {a['score']} aceita {a.get('is_accepted')}", texto_html(a["body"])]
            for cm in (bruto.get("answer_comments") or {}).get("json", {}).get("items", []):
                if cm["post_id"] == a["answer_id"]:
                    linhas += ["", f"    --- COMENTÁRIO {cm['owner'].get('display_name')}", texto_html(cm["body"])]
    elif fonte == "dbt_forum":
        tid = re.search(r"/t/(?:[^/]+/)?(\d+)", url).group(1)
        r = c.req("GET", f"https://discourse.getdbt.com/t/{tid}.json")
        bruto["topico"] = {"status": r.status_code, "json": r.json() if r.ok else r.text}
        posts = []
        if r.ok:
            ps = bruto["topico"]["json"]["post_stream"]
            posts = list(ps["posts"])
            faltam = [i for i in ps["stream"] if i not in {p["id"] for p in posts}]
            bruto["posts_extra"] = []
            for k in range(0, len(faltam), 20):
                r2 = c.req("GET", f"https://discourse.getdbt.com/t/{tid}/posts.json",
                           params=[("post_ids[]", i) for i in faltam[k:k + 20]])
                bruto["posts_extra"].append({"status": r2.status_code, "json": r2.json() if r2.ok else r2.text})
                if r2.ok:
                    posts += r2.json()["post_stream"]["posts"]
        else:
            linhas.append(f"INACESSÍVEL: HTTP {r.status_code}")
        for p in sorted(posts, key=lambda p: p["post_number"]):
            linhas += ["", f"--- POST {p['post_number']} {p['username']} {p['created_at']}", texto_html(p["cooked"])]
    elif fonte == "debezium":
        r = c.req("GET", url, espera=5.0, headers={"Accept-Language": "en-US,en;q=0.9"})
        bruto["topico"] = {"status": r.status_code, "url_final": r.url, "html": r.text}
        linhas += ["", texto_html(r.text)]
    else:
        raise ValueError(f"fonte desconhecida: {fonte}")
    return bruto, "\n".join(linhas)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pasta_leitura", type=Path)
    ap.add_argument("--ids", type=Path, help="arquivo com um id_item por linha (padrão: pendentes da fase 2)")
    a = ap.parse_args()
    itens = {l["id_item"]: l for l in csv.DictReader((RAIZ / "dados/itens.csv").open(encoding="utf-8"))}
    tri = {l["id_item"]: l for l in csv.DictReader((RAIZ / "dados/triagem.csv").open(encoding="utf-8"))}
    if a.ids:
        ids = [l.strip() for l in a.ids.read_text().splitlines() if l.strip()]
    else:
        ids = sorted(i for i, l in tri.items() if l["decisao_f1"] in ("incluir", "duvida") and not l["decisao_f2"])
    carimbo = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dir_bruto = RAIZ / "dados" / "brutos" / f"fase2_{carimbo}"
    dir_bruto.mkdir(parents=True, exist_ok=False)
    a.pasta_leitura.mkdir(parents=True, exist_ok=True)
    c = Coletor()
    print(f"{len(ids)} itens; brutos em {dir_bruto.relative_to(RAIZ)}", flush=True)
    for k, id_ in enumerate(ids, 1):
        try:
            bruto, texto = coletar(c, itens[id_])
        except Exception as e:  # registra e segue
            bruto, texto = {"id_item": id_, "erro": repr(e)}, f"# {id_}\nERRO NA COLETA: {e!r}"
            print(f"  {id_}: erro {e!r}", flush=True)
        (dir_bruto / f"{id_}.json").write_text(json.dumps(bruto, ensure_ascii=False, indent=1), encoding="utf-8")
        (a.pasta_leitura / f"{id_}.txt").write_text(texto, encoding="utf-8")
        if k % 20 == 0 or k == len(ids):
            print(f"  {k}/{len(ids)}", flush=True)


if __name__ == "__main__":
    main()
