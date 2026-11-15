"""Compara a recodificação cega (dados/validacao_cega.csv) com a codificação original
(dados/extracao.csv) e grava dados/validacao.csv (protocolo, seção 9; desvio D6c).

Variáveis: estrategia, etapa, tipo_problema, polaridade.

- Variáveis de valor único (estrategia, polaridade): concordância observada e kappa
  de Cohen nominal sobre os itens.
- Variáveis múltiplas (etapa, tipo_problema; valores separados por ";"):
  (1) concordância exata por item (conjuntos idênticos);
  (2) concordância por categoria (presente/ausente): cada par item x categoria é uma
      unidade binária, e o kappa de Cohen é calculado sobre todas as unidades. O
      universo de categorias é o conjunto de valores usados por pelo menos um dos
      codificadores na amostra completa (5 itens), mantido igual na análise sem o
      I0729, para que as duas análises sejam comparáveis.
- Os valores são comparados como escritos; nada é mapeado para o codebook
  (CLAUDE.md, regra 8). Valores fora do codebook são apenas sinalizados.
- Análises: com os 5 itens e sem o I0729 (desvio D6c).

Uso: python scripts/validacao_kappa.py
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
VARS_UNICAS = ["estrategia", "polaridade"]
VARS_MULTIPLAS = ["etapa", "tipo_problema"]
CODEBOOK = {
    "estrategia": {"banco_por_tenant", "esquema_por_tenant", "esquema_compartilhado", "hibrida"},
    "etapa": {"geracao", "ingestao", "armazenamento", "transformacao", "servico"},
    "tipo_problema": {"config_manual_novo_tenant", "multiplicacao_conectores", "multiplicacao_modelos",
                      "consolidacao_tenants", "desempenho_origem", "desempenho_ferramenta",
                      "evolucao_esquema", "governanca_isolamento", "custo", "outro"},
    "polaridade": {"problema", "beneficio", "misto"},
}
COLUNAS = ["linha_tipo", "amostra", "id_item", "variavel", "metodo", "original", "validacao",
           "concordancia_exata", "so_original", "so_validacao", "fora_do_codebook",
           "n_unidades", "concordancia", "kappa"]


def conjunto(v: str) -> set[str]:
    return {x.strip() for x in v.split(";") if x.strip()}


def kappa(pares: list[tuple[str, str]]) -> tuple[float, float | None]:
    n = len(pares)
    po = sum(a == b for a, b in pares) / n
    ca, cb = Counter(a for a, _ in pares), Counter(b for _, b in pares)
    pe = sum(ca[k] / n * cb[k] / n for k in set(ca) | set(cb))
    return po, (None if pe == 1 else (po - pe) / (1 - pe))


def fmt(x: float | None) -> str:
    return "indefinido" if x is None else f"{x:.3f}"


def main():
    ori = {e["id_item"]: e for e in csv.DictReader((RAIZ / "dados/extracao.csv").open(encoding="utf-8"))}
    val = {v["id_item"]: v for v in csv.DictReader((RAIZ / "dados/validacao_cega.csv").open(encoding="utf-8"))}
    ids = sorted(val)
    linhas = []
    for i in ids:
        for var in VARS_UNICAS + VARS_MULTIPLAS:
            a, b = conjunto(ori[i][var]), conjunto(val[i][var])
            fora = sorted(x for x in b if x not in CODEBOOK[var])
            linhas.append({"linha_tipo": "item", "id_item": i, "variavel": var,
                           "original": ";".join(sorted(a)), "validacao": ";".join(sorted(b)),
                           "concordancia_exata": "sim" if a == b else "não",
                           "so_original": ";".join(sorted(a - b)), "so_validacao": ";".join(sorted(b - a)),
                           "fora_do_codebook": ";".join(fora)})
    universo = {var: sorted(set().union(*(conjunto(ori[i][var]) | conjunto(val[i][var]) for i in ids)))
                for var in VARS_MULTIPLAS}
    for nome, sub in (("5_itens", ids), ("4_itens_sem_I0729", [i for i in ids if i != "I0729"])):
        for var in VARS_UNICAS:
            po, k = kappa([(ori[i][var].strip(), val[i][var].strip()) for i in sub])
            linhas.append({"linha_tipo": "resumo", "amostra": nome, "variavel": var, "metodo": "kappa_nominal_por_item",
                           "n_unidades": len(sub), "concordancia": f"{po:.3f}", "kappa": fmt(k)})
        for var in VARS_MULTIPLAS:
            ex = sum(conjunto(ori[i][var]) == conjunto(val[i][var]) for i in sub) / len(sub)
            linhas.append({"linha_tipo": "resumo", "amostra": nome, "variavel": var, "metodo": "concordancia_exata_por_item",
                           "n_unidades": len(sub), "concordancia": f"{ex:.3f}", "kappa": ""})
            pares = [(str(int(c in conjunto(ori[i][var]))), str(int(c in conjunto(val[i][var]))))
                     for i in sub for c in universo[var]]
            po, k = kappa(pares)
            linhas.append({"linha_tipo": "resumo", "amostra": nome, "variavel": var,
                           "metodo": f"categoria_presente_ausente ({len(universo[var])} categorias)",
                           "n_unidades": len(pares), "concordancia": f"{po:.3f}", "kappa": fmt(k)})
    with (RAIZ / "dados/validacao.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS, lineterminator="\n")
        w.writeheader()
        w.writerows(linhas)
    for l in linhas:
        if l["linha_tipo"] == "resumo":
            print(l["amostra"], l["variavel"], l["metodo"], l["n_unidades"], l["concordancia"], l["kappa"])


if __name__ == "__main__":
    main()
