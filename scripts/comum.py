"""Código compartilhado pelos scripts de coleta da revisão cinzenta.

Responsabilidades:
- termos de busca da seção 5.1 do protocolo e a composição 9 x 9 da seção 5.2;
- verificações anteriores à coleta (CLAUDE.md, regra 2): a tag `v0-protocolo`
  existe, protocolo.md e scripts/ não têm alterações não commitadas, e os termos
  do código são os da seção 5.1 na versão do protocolo marcada pela tag;
- leitura de credenciais do .env, que tem prioridade sobre o ambiente;
- requisições HTTP com espera e nova tentativa em limite de taxa (regra 9);
- registros das seções 5.5 e 11 do protocolo: uma pasta por execução em
  dados/brutos/, um JSON por busca, uma linha por busca em dados/log_buscas.csv
  e uma linha por execução em dados/execucoes.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import unquote_plus

import requests

RAIZ = Path(__file__).resolve().parent.parent
PROTOCOLO = RAIZ / "protocolo.md"
DIR_DADOS = RAIZ / "dados"
DIR_BRUTOS = DIR_DADOS / "brutos"
LOG_BUSCAS = DIR_DADOS / "log_buscas.csv"
LOG_EXECUCOES = DIR_DADOS / "execucoes.csv"
TAG_PROTOCOLO = "v0-protocolo"

# Protocolo, seção 11.
COLUNAS_LOG = [
    "id_busca", "data_hora", "fonte", "termo_a", "termo_b",
    "string_enviada", "n_resultados", "n_coletados",
]
COLUNAS_EXECUCOES = [
    "id_execucao", "fonte", "inicio", "fim", "status",
    "commit", "buscas_ok", "buscas_erro", "avisos",
]

# Protocolo, seção 5.4: até 100 resultados por busca, os primeiros por relevância.
LIMITE_COLETA = 100

USER_AGENT = "revisao-cinzenta-coleta/1.0 (python-requests)"

# Únicos cabeçalhos de resposta gravados nos brutos; todos os outros são descartados.
CABECALHOS_GRAVADOS = ("date", "content-type")
PREFIXO_CABECALHOS_GRAVADOS = "x-ratelimit-"

# Protocolo, seção 5.1 — Bloco A, na ordem em que aparece no protocolo.
BLOCO_A: list[tuple[str, str]] = [
    ("banco_por_tenant", '"database per tenant"'),
    ("banco_por_tenant", '"database-per-tenant"'),
    ("banco_por_tenant", '"database per customer"'),
    ("esquema_por_tenant", '"schema per tenant"'),
    ("esquema_por_tenant", '"schema-per-tenant"'),
    ("esquema_por_tenant", '"schema per customer"'),
    ("esquema_compartilhado", '"shared schema" tenant'),
    ("esquema_compartilhado", '"tenant_id"'),
    ("esquema_compartilhado", '"pool model" tenant'),
]

# Protocolo, seção 5.1 — Bloco B, comum às três estratégias.
BLOCO_B: list[str] = [
    "ingestion",
    "CDC",
    '"change data capture"',
    "ETL",
    "ELT",
    '"data warehouse"',
    "dbt",
    "pipeline",
    "connector",
]


# --------------------------------------------------------------------------
# Buscas
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Busca:
    codigo: str        # posição no protocolo, ex.: "A4B1" = 4º termo A x 1º termo B
    estrategia: str
    termo_a: str
    termo_b: str

    @property
    def consulta(self) -> str:
        """Composição da seção 5.2: um termo A, espaço, um termo B."""
        return f"{self.termo_a} {self.termo_b}"


def gerar_buscas() -> list[Busca]:
    """As 81 combinações A x B, na ordem do protocolo."""
    return [
        Busca(f"A{i}B{j}", estrategia, termo_a, termo_b)
        for i, (estrategia, termo_a) in enumerate(BLOCO_A, start=1)
        for j, termo_b in enumerate(BLOCO_B, start=1)
    ]


@dataclass
class EstadoBusca:
    """O que uma busca acumula enquanto roda. É gravado no bruto mesmo se a busca falhar."""
    string_enviada: str = ""
    requisicoes: list[dict] = field(default_factory=list)   # cada requisição, com a resposta
    avisos: list[str] = field(default_factory=list)


@dataclass
class ResultadoBusca:
    n_resultados: int | None          # None: a fonte não informa o total
    urls_coletadas: list[str]
    espera_minima: float = 0.0        # ex.: campo "backoff" do Stack Exchange


@dataclass
class Tarefa:
    sufixo_id: str                    # final do id_busca e nome do arquivo bruto
    busca: Busca
    previa: str                       # string mostrada no --dry-run
    executar: Callable[[EstadoBusca], ResultadoBusca]


@dataclass
class Preparacao:
    """Requisição feita uma vez por execução, antes das buscas (ex.: filtro do Stack Exchange)."""
    nome: str                                   # gravada em <pasta da execução>/<nome>.json
    executar: Callable[[EstadoBusca], dict]     # devolve parâmetros acrescentados à execução


# --------------------------------------------------------------------------
# Verificações anteriores à coleta
# --------------------------------------------------------------------------

def termos_da_secao_5_1(texto: str) -> tuple[list[tuple[str, str]], list[str]] | None:
    """Termos dos Blocos A e B na seção 5.1 de um protocolo.md; None se a seção não existir."""
    m = re.search(r"^### 5\.1\b(.*?)^### 5\.2\b", texto, flags=re.S | re.M)
    if not m:
        return None
    secao = m.group(1)

    estrategias = {f"`{e}`" for e, _ in BLOCO_A}
    bloco_a: list[tuple[str, str]] = []
    for linha in secao.splitlines():
        celulas = [c.strip() for c in linha.strip().strip("|").split("|")]
        if len(celulas) == 2 and celulas[0] in estrategias:
            estrategia = celulas[0].strip("`")
            bloco_a += [(estrategia, t) for t in re.findall(r"`([^`]+)`", celulas[1])]

    partes = secao.split("Bloco B", 1)
    bloco_b = re.findall(r"`([^`]+)`", partes[1]) if len(partes) == 2 else []
    return bloco_a, bloco_b


def divergencia_de_termos(texto: str, origem: str) -> str | None:
    """Descreve a divergência entre os termos do código e os do protocolo; None se idênticos."""
    termos = termos_da_secao_5_1(texto)
    if termos is None:
        return f"seção 5.1 não encontrada em {origem}"
    bloco_a, bloco_b = termos
    if bloco_a == BLOCO_A and bloco_b == BLOCO_B:
        return None
    return (
        f"os termos do código divergem da seção 5.1 em {origem}\n"
        f"      Bloco A no protocolo: {bloco_a}\n      Bloco A no código:    {BLOCO_A}\n"
        f"      Bloco B no protocolo: {bloco_b}\n      Bloco B no código:    {BLOCO_B}"
    )


def _git(*args: str) -> subprocess.CompletedProcess:
    # --no-optional-locks: o git não atualiza o índice; a consulta é só leitura.
    return subprocess.run(
        ["git", "--no-optional-locks", *args],
        cwd=RAIZ, capture_output=True, text=True, encoding="utf-8",
    )


def _commit_da_tag() -> str | None:
    r = _git("rev-parse", "--verify", "--quiet", f"refs/tags/{TAG_PROTOCOLO}^{{commit}}")
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return r.stdout.strip()


def _cabecalho_csv(caminho: Path) -> list[str] | None:
    if not caminho.exists() or caminho.stat().st_size == 0:
        return None
    with caminho.open(encoding="utf-8", newline="") as f:
        return next(csv.reader(f), [])


def impedimentos_da_coleta() -> list[str]:
    """Condições que impedem a coleta. Lista vazia: a coleta pode começar."""
    impedimentos = []

    # a) a tag do pré-registro existe
    commit_tag = _commit_da_tag()
    if commit_tag is None:
        impedimentos.append(f"a tag '{TAG_PROTOCOLO}' não existe (CLAUDE.md, regra 2)")

    # b) nada pendente em protocolo.md e scripts/ (inclui arquivos não monitorados)
    r = _git("status", "--porcelain", "--untracked-files=all", "--", "protocolo.md", "scripts")
    if r.returncode != 0:
        impedimentos.append(f"git status falhou: {r.stderr.strip()}")
    elif r.stdout.strip():
        arquivos = "\n".join(f"      {linha}" for linha in r.stdout.rstrip().splitlines())
        impedimentos.append(f"alterações não commitadas em protocolo.md ou scripts/:\n{arquivos}")

    # c) termos do código iguais aos da seção 5.1 no protocolo marcado pela tag
    if commit_tag is not None:
        r = _git("show", f"{TAG_PROTOCOLO}:protocolo.md")
        if r.returncode != 0:
            impedimentos.append(f"protocolo.md não existe no commit da tag '{TAG_PROTOCOLO}'")
        else:
            divergencia = divergencia_de_termos(r.stdout, f"protocolo.md da tag {TAG_PROTOCOLO}")
            if divergencia:
                impedimentos.append(divergencia)

    # Os registros existentes precisam ter o cabeçalho da seção 11.
    for caminho, colunas in ((LOG_BUSCAS, COLUNAS_LOG), (LOG_EXECUCOES, COLUNAS_EXECUCOES)):
        cabecalho = _cabecalho_csv(caminho)
        if cabecalho is not None and cabecalho != colunas:
            impedimentos.append(f"cabeçalho inesperado em {caminho.relative_to(RAIZ)}: {cabecalho}")

    return impedimentos


def verificar_antes_da_coleta(dry_run: bool, impedimentos_da_fonte: list[str]) -> dict:
    """Roda as verificações anteriores à coleta.

    Na coleta, aborta se houver qualquer impedimento e devolve os dados do
    repositório gravados em cada bruto. No --dry-run, só relata o que impediria
    a coleta e confere também os termos contra o protocolo.md da árvore de trabalho.
    """
    impedimentos = impedimentos_da_coleta() + impedimentos_da_fonte

    if dry_run:
        divergencia = divergencia_de_termos(
            PROTOCOLO.read_text(encoding="utf-8"), "protocolo.md da árvore de trabalho")
        print("\nVerificações anteriores à coleta")
        print("  termos do código x seção 5.1 do protocolo.md da árvore de trabalho: "
              + ("idênticos" if divergencia is None else "DIVERGENTES"))
        if divergencia:
            print(f"    {divergencia}")
        if impedimentos:
            print("  a coleta real seria abortada por:")
            for impedimento in impedimentos:
                print(f"  - {impedimento}")
        else:
            print("  nenhum impedimento: a coleta real poderia começar")
        print()
        return {}

    if impedimentos:
        sys.exit("Coleta abortada:\n" + "\n".join(f"  - {i}" for i in impedimentos))

    commit_tag = _commit_da_tag()
    return {
        "commit_head": _git("rev-parse", "HEAD").stdout.strip(),
        "tag_protocolo": TAG_PROTOCOLO,
        "commit_tag": commit_tag,
        # Informativo: o protocolo pode mudar depois da tag, com registro na seção 13.
        "protocolo_alterado_desde_tag":
            _git("diff", "--quiet", commit_tag, "HEAD", "--", "protocolo.md").returncode != 0,
    }


def _valor_no_env(nome: str) -> str | None:
    arquivo = RAIZ / ".env"
    if not arquivo.exists():
        return None
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip().removeprefix("export ").strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        if chave.strip() == nome:
            return valor.strip().strip("'\"") or None
    return None


def ler_env(nome: str) -> str | None:
    """Lê `nome` do .env na raiz; só se estiver ausente lá, da variável de ambiente.

    Imprime de onde o valor foi lido (".env" ou "ambiente"), nunca o valor.
    """
    valor, origem = _valor_no_env(nome), ".env"
    if valor is None:
        valor, origem = os.environ.get(nome) or None, "ambiente"
    if valor is None:
        print(f"{nome}: não encontrado no .env nem no ambiente")
    else:
        print(f"{nome} lido de: {origem}")
    return valor


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

class ErroColeta(Exception):
    pass


def agora_iso() -> str:
    """Data e hora atuais em UTC, ISO 8601 com fuso (ex.: 2026-11-15T14:03:07+00:00)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def nova_sessao(cabecalhos: dict | None = None) -> requests.Session:
    sessao = requests.Session()
    sessao.headers["User-Agent"] = USER_AGENT
    sessao.headers.update(cabecalhos or {})
    return sessao


def url_sem_segredos(texto: str) -> str:
    """Mascara a chave da API do Stack Exchange (key=...) em URLs e mensagens de erro."""
    return re.sub(r"([?&]key=)[^&#\s'\"]+", r"\1***", texto)


def url_legivel(url: str) -> str:
    """URL decodificada e sem segredos, usada como string_enviada no log."""
    return unquote_plus(url_sem_segredos(url))


def url_preparada(metodo: str, url: str, params: dict | None) -> str:
    """URL que o requests monta com os parâmetros, sem enviá-la."""
    return requests.Request(metodo, url, params=params).prepare().url


def cabecalhos_gravados(cabecalhos) -> dict:
    """Só date, content-type e x-ratelimit-*; os demais cabeçalhos são descartados."""
    return {
        k.lower(): v for k, v in cabecalhos.items()
        if k.lower() in CABECALHOS_GRAVADOS or k.lower().startswith(PREFIXO_CABECALHOS_GRAVADOS)
    }


def _espera_limite_padrao(resp: requests.Response, tentativa: int) -> float | None:
    """Tempo de espera para HTTP 403/429 de limite de taxa; None se não for limite."""
    if resp.status_code not in (403, 429):
        return None
    retry_after = resp.headers.get("Retry-After", "")
    if retry_after.isdigit():
        return float(retry_after) + 1
    reset = resp.headers.get("X-RateLimit-Reset", "")
    if resp.headers.get("X-RateLimit-Remaining") == "0" and reset.isdigit():
        return max(float(reset) - time.time(), 0) + 2
    if resp.status_code == 429 or "rate limit" in resp.text.lower():
        return min(60 * 2 ** (tentativa - 1), 900)
    return None  # 403 que não é limite de taxa: erro real, sem nova tentativa


def _registro_requisicao(
    metodo: str,
    url: str,
    corpo_enviado: dict | None,
    tentativas_repetidas: list[dict],
    resp: requests.Response | None,
) -> dict:
    """Requisição e resposta bruta, como são gravadas no arquivo da busca."""
    registro = {
        "metodo": metodo,
        "url": url_sem_segredos(resp.request.url if resp is not None else url),
        "corpo_enviado": corpo_enviado,
        "tentativas_repetidas": tentativas_repetidas,
        "status": None,
        "recebido_em": None,
        "cabecalhos_resposta": {},
        "resposta": None,
    }
    if resp is not None:
        try:
            conteudo = resp.json()
        except ValueError:
            conteudo = resp.text
        registro.update(
            status=resp.status_code,
            recebido_em=agora_iso(),
            cabecalhos_resposta=cabecalhos_gravados(resp.headers),
            resposta=conteudo,
        )
    return registro


def requisitar(
    sessao: requests.Session,
    metodo: str,
    url: str,
    estado: EstadoBusca,
    *,
    params: dict | None = None,
    corpo_json: dict | None = None,
    detectar_limite: Callable[[requests.Response], float | None] | None = None,
    max_tentativas: int = 6,
) -> requests.Response:
    """Faz a requisição e a registra em `estado.requisicoes`, com sucesso ou não.

    Em limite de taxa, erro 5xx ou falha de rede, espera e tenta de novo; cada
    tentativa repetida fica anotada no registro. Se a resposta final não for 2xx,
    ela é registrada (é o bruto do erro) e ErroColeta é levantado.

    `detectar_limite` cobre limites sinalizados de outra forma pela fonte
    (ex.: HTTP 400 com error_id 502 no Stack Exchange; erro RATE_LIMITED no GraphQL).
    """
    url_completa = url_preparada(metodo, url, params)
    if not estado.string_enviada:
        estado.string_enviada = url_legivel(url_completa)

    tentativas: list[dict] = []
    resp = None  # última resposta recebida
    for tentativa in range(1, max_tentativas + 1):
        try:
            resp = sessao.request(metodo, url, params=params, json=corpo_json, timeout=60)
        except (requests.ConnectionError, requests.Timeout) as e:
            espera = min(30 * tentativa, 300)
            motivo = f"falha de rede ({type(e).__name__})"
            tentativas.append({"em": agora_iso(), "falha": url_sem_segredos(str(e)), "espera_s": espera})
        else:
            espera = _espera_limite_padrao(resp, tentativa)
            if espera is None and detectar_limite is not None:
                espera = detectar_limite(resp)
            if espera is None and resp.status_code >= 500:
                espera = min(30 * 2 ** (tentativa - 1), 600)

            if espera is None:
                estado.requisicoes.append(
                    _registro_requisicao(metodo, url_completa, corpo_json, tentativas, resp))
                if not resp.ok:
                    raise ErroColeta(f"HTTP {resp.status_code}: {url_sem_segredos(resp.text[:300])}")
                return resp

            motivo = f"HTTP {resp.status_code} (limite de taxa ou indisponibilidade)"
            tentativas.append({"em": agora_iso(), "status": resp.status_code, "espera_s": round(espera, 1)})

        if tentativa < max_tentativas:
            print(f"    ! {motivo}; tentativa {tentativa}/{max_tentativas}, aguardando {espera:.0f}s")
            time.sleep(espera)

    estado.requisicoes.append(_registro_requisicao(metodo, url_completa, corpo_json, tentativas, resp))
    raise ErroColeta(f"sem sucesso após {max_tentativas} tentativas ({motivo})")


# --------------------------------------------------------------------------
# Execução e registros
# --------------------------------------------------------------------------

def argumentos(descricao: str) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=descricao)
    p.add_argument(
        "--dry-run", action="store_true",
        help="lista as buscas, as strings que seriam enviadas e o resultado das "
             "verificações, sem acessar a rede nem gravar nada",
    )
    return p.parse_args()


def imprimir_plano(fonte: str, tarefas: list[Tarefa]) -> None:
    print(f"[dry-run] {fonte}: {len(tarefas)} buscas (nada será enviado nem gravado)\n")
    for t in tarefas:
        print(f"  {t.sufixo_id:<20} {t.previa}")


def _gravar_json(caminho: Path, conteudo: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_name(caminho.name + ".parcial")
    temporario.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8")
    temporario.replace(caminho)


def _anexar_csv(caminho: Path, colunas: list[str], linhas: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    novo = not caminho.exists() or caminho.stat().st_size == 0
    with caminho.open("a", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=colunas, lineterminator="\n")
        if novo:
            escritor.writeheader()
        escritor.writerows(linhas)


def _uma_linha(texto: str, limite: int = 300) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def executar_coleta(
    fonte: str,
    tarefas: list[Tarefa],
    *,
    intervalo: float,
    parametros: dict,
    repositorio: dict,
    script: str,
    preparacao: Preparacao | None = None,
) -> None:
    """Executa as buscas em sequência e grava brutos, log e registro da execução.

    - Pasta da execução: dados/brutos/<fonte>_<AAAAMMDDTHHMMSSZ>/ (UTC), com um
      <sufixo_id>.json por busca, gravado assim que a busca termina.
    - Uma busca com erro não recuperável grava a resposta de erro como bruto,
      entra no log com n_resultados e n_coletados vazios, e a execução segue.
    - dados/execucoes.csv recebe uma linha ao final, mesmo se a execução for
      interrompida: "completa" (todas as buscas executadas, nenhuma com erro),
      "erro" (todas executadas, ao menos uma com erro) ou "incompleta"
      (interrompida antes do fim, por Ctrl+C ou falha fatal).
    """
    inicio = datetime.now(timezone.utc)
    id_execucao = f"{fonte}_{inicio:%Y%m%dT%H%M%SZ}"
    pasta = DIR_BRUTOS / id_execucao
    if pasta.exists():
        sys.exit(f"{pasta.relative_to(RAIZ)} já existe; nada foi sobrescrito.")
    pasta.mkdir(parents=True)

    comuns = {"id_execucao": id_execucao, "fonte": fonte, "script": script, **repositorio}
    params = {**parametros, "limite_coleta": LIMITE_COLETA, "intervalo_s": intervalo}
    n_ok = n_erro = 0
    avisos_execucao: list[str] = []
    status = "incompleta"

    print(f"Coleta {fonte}: {len(tarefas)} buscas -> {pasta.relative_to(RAIZ)}/")
    try:
        if preparacao is not None:
            estado = EstadoBusca()
            data_hora = agora_iso()
            try:
                params.update(preparacao.executar(estado))
            finally:
                _gravar_json(pasta / f"{preparacao.nome}.json", {
                    **comuns, "data_hora": data_hora,
                    "string_enviada": estado.string_enviada, "requisicoes": estado.requisicoes,
                })

        espera = 0.0
        for k, tarefa in enumerate(tarefas, start=1):
            if k > 1:
                time.sleep(espera)
            b = tarefa.busca
            id_busca = f"{id_execucao}_{tarefa.sufixo_id}"
            estado = EstadoBusca()
            data_hora = agora_iso()
            try:
                r, erro = tarefa.executar(estado), None
            except Exception as e:  # erro não recuperável desta busca: registra e segue
                r, erro = None, f"{type(e).__name__}: {url_sem_segredos(str(e))}"

            n_resultados = None if r is None else r.n_resultados
            n_coletados = None if r is None else len(r.urls_coletadas)
            _gravar_json(pasta / f"{tarefa.sufixo_id}.json", {
                "id_busca": id_busca,
                **comuns,
                "data_hora": data_hora,
                "estrategia": b.estrategia,
                "termo_a": b.termo_a,
                "termo_b": b.termo_b,
                "string_enviada": estado.string_enviada,
                "parametros": params,
                "status": "erro" if erro else "ok",
                "erro": erro,
                "n_resultados": n_resultados,
                "n_coletados": n_coletados,
                "avisos": estado.avisos,
                "urls_coletadas": [] if r is None else r.urls_coletadas,
                "requisicoes": estado.requisicoes,
            })
            _anexar_csv(LOG_BUSCAS, COLUNAS_LOG, [{
                "id_busca": id_busca,
                "data_hora": data_hora,
                "fonte": fonte,
                "termo_a": b.termo_a,
                "termo_b": b.termo_b,
                "string_enviada": estado.string_enviada,
                "n_resultados": "" if n_resultados is None else n_resultados,
                "n_coletados": "" if n_coletados is None else n_coletados,
            }])

            if erro:
                n_erro += 1
                avisos_execucao.append(f"{tarefa.sufixo_id}: erro: {_uma_linha(erro, 200)}")
            else:
                n_ok += 1
            avisos_execucao += [f"{tarefa.sufixo_id}: {_uma_linha(a)}" for a in estado.avisos]

            total = "-" if n_resultados is None else n_resultados
            situacao = f"ERRO {_uma_linha(erro, 120)}" if erro else f"resultados={total:<6} coletados={n_coletados}"
            aviso = f"  ({'; '.join(estado.avisos)})" if estado.avisos else ""
            print(f"  [{k:>3}/{len(tarefas)}] {tarefa.sufixo_id:<18} {situacao}{aviso}")
            espera = max(intervalo, r.espera_minima if r is not None else 0.0)

        status = "completa" if n_erro == 0 else "erro"
    except BaseException as e:  # inclui Ctrl+C: a linha da execução é gravada no finally
        motivo = "Ctrl+C" if isinstance(e, KeyboardInterrupt) else f"{type(e).__name__}: {e}"
        avisos_execucao.append(f"execução interrompida: {_uma_linha(url_sem_segredos(motivo))}")
        raise
    finally:
        _anexar_csv(LOG_EXECUCOES, COLUNAS_EXECUCOES, [{
            "id_execucao": id_execucao,
            "fonte": fonte,
            "inicio": inicio.isoformat(timespec="seconds"),
            "fim": agora_iso(),
            "status": status,
            "commit": repositorio.get("commit_head", ""),
            "buscas_ok": n_ok,
            "buscas_erro": n_erro,
            "avisos": " | ".join(avisos_execucao),
        }])
        print(f"\nExecução {id_execucao}: {status} ({n_ok} buscas ok, {n_erro} com erro). "
              f"Brutos em {pasta.relative_to(RAIZ)}/; registro em {LOG_EXECUCOES.relative_to(RAIZ)}")
