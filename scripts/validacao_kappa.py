"""Compara a recodificação cega (dados/validacao_cega.csv) com a codificação original
e grava dados/validacao.csv (protocolo, seção 9; desvios D6c e D7).

Codificação original: dados/validacao_original.csv, instantâneo das linhas da amostra
em dados/extracao.csv no commit 240a301 (antes da consolidação e da exclusão do I0729
pela D7a, que retiraram o I0729 do extracao.csv).

Variáveis: estrategia, etapa, tipo_problema, polaridade.

- Variáveis de valor único (estrategia, polaridade): concordância observada e kappa
  de Cohen nominal sobre os itens.
- Variáveis múltiplas (etapa, tipo_problema; valores separados por ";"):
  (1) concordância exata por item (conjuntos idênticos);
  (2) concordância por categoria (presente/ausente): cada par item x categoria é uma
      unidade binária, e o kappa de Cohen é calculado sobre todas as unidades. O
      universo de categorias é o conjunto de valores usados por pelo menos um dos
      codificadores nos itens da análise de referência (5 itens na análise principal;
      os 4 itens sem o I0729 na secundária).

Seções do arquivo de saída (coluna linha_tipo):
- item / resumo: análise principal (D7b), valores comparados como escritos, com os
  5 itens e sem o I0729 (D6c);
- item_secundario / resumo_secundario: análise secundária (D7b), com os valores da
  recodificação fora do codebook mapeados às categorias da seção 8.3 (MAPEAMENTO,
  definido pelo autor após conhecer a codificação original), só com os 4 itens sem o
  I0729 (excluído pela D7a);
- coluna consolidada: codificação final decidida pelo autor (D7c), que é a gravada em
  dados/extracao.csv.

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
# D7b: mapeamento definido pelo autor (só tipo_problema).
MAPEAMENTO = {
    "tipo_problema": {
        "compatibilidade_esquema": "evolucao_esquema",
        "desempenho_banco": "desempenho_origem",
        "isolamento_recursos": "desempenho_origem",
        "consumo_memoria": "desempenho_ferramenta",
        "multiplicacao_metadados": "desempenho_ferramenta",
        "complexidade_configuracao": "config_manual_novo_tenant",
    }
}
EXCLUIDO_D7A = "I0729"
COLUNAS = ["linha_tipo", "amostra", "id_item", "variavel", "metodo", "original", "validacao", "consolidada",
           "concordancia_exata", "so_original", "so_validacao", "fora_do_codebook",
           "n_unidades", "concordancia", "kappa"]


def conjunto(v: str) -> set[str]:
    return {x.strip() for x in v.split(";") if x.strip()}


def mapear(var: str, valores: set[str]) -> set[str]:
    m = MAPEAMENTO.get(var, {})
    return {m.get(x, x) for x in valores}


def kappa(pares):
    n = len(pares)
    po = sum(a == b for a, b in pares) / n
    ca, cb = Counter(a for a, _ in pares), Counter(b for _, b in pares)
    pe = sum(ca[k] / n * cb[k] / n for k in set(ca) | set(cb))
    return po, (None if pe == 1 else (po - pe) / (1 - pe))


def fmt(x):
    return "indefinido" if x is None else f"{x:.3f}"


def analisar(ori, val, ids, ids_universo, rotulo_item, rotulo_resumo, analises, consolidada):
    linhas = []
    for i in ids:
        for var in VARS_UNICAS + VARS_MULTIPLAS:
            a, b = ori[i][var], val[i][var]
            fora = sorted(x for x in b if x not in CODEBOOK[var])
            linhas.append({"linha_tipo": rotulo_item, "id_item": i, "variavel": var,
                           "original": ";".join(sorted(a)), "validacao": ";".join(sorted(b)),
                           "consolidada": consolidada.get(i, {}).get(var, ""),
                           "concordancia_exata": "sim" if a == b else "não",
                           "so_original": ";".join(sorted(a - b)), "so_validacao": ";".join(sorted(b - a)),
                           "fora_do_codebook": ";".join(fora)})
    universo = {var: sorted(set().union(*(ori[i][var] | val[i][var] for i in ids_universo))) for var in VARS_MULTIPLAS}
    for nome, sub in analises:
        for var in VARS_UNICAS:
            po, k = kappa([(next(iter(ori[i][var]), ""), next(iter(val[i][var]), "")) for i in sub])
            linhas.append({"linha_tipo": rotulo_resumo, "amostra": nome, "variavel": var, "metodo": "kappa_nominal_por_item",
                           "n_unidades": len(sub), "concordancia": f"{po:.3f}", "kappa": fmt(k)})
        for var in VARS_MULTIPLAS:
            ex = sum(ori[i][var] == val[i][var] for i in sub) / len(sub)
            linhas.append({"linha_tipo": rotulo_resumo, "amostra": nome, "variavel": var,
                           "metodo": "concordancia_exata_por_item", "n_unidades": len(sub),
                           "concordancia": f"{ex:.3f}", "kappa": ""})
            pares = [(str(int(c in ori[i][var])), str(int(c in val[i][var]))) for i in sub for c in universo[var]]
            po, k = kappa(pares)
            linhas.append({"linha_tipo": rotulo_resumo, "amostra": nome, "variavel": var,
                           "metodo": f"categoria_presente_ausente ({len(universo[var])} categorias)",
                           "n_unidades": len(pares), "concordancia": f"{po:.3f}", "kappa": fmt(k)})
    return linhas


def main():
    ler = lambda p: {l["id_item"]: l for l in csv.DictReader((RAIZ / p).open(encoding="utf-8"))}
    o_raw, v_raw, ext = ler("dados/validacao_original.csv"), ler("dados/validacao_cega.csv"), ler("dados/extracao.csv")
    todas = VARS_UNICAS + VARS_MULTIPLAS
    ids = sorted(v_raw)
    ori = {i: {var: conjunto(o_raw[i][var]) for var in todas} for i in ids}
    val = {i: {var: conjunto(v_raw[i][var]) for var in todas} for i in ids}
    consolidada = {i: ({var: ext[i][var] for var in todas} if i in ext else
                       {var: "excluído (D7a)" for var in todas}) for i in ids}
    sem = [i for i in ids if i != EXCLUIDO_D7A]
    linhas = analisar(ori, val, ids, ids, "item", "resumo",
                      [("5_itens", ids), ("4_itens_sem_I0729", sem)], consolidada)
    val_map = {i: {var: mapear(var, val[i][var]) for var in todas} for i in sem}
    linhas += analisar({i: ori[i] for i in sem}, val_map, sem, sem, "item_secundario", "resumo_secundario",
                       [("4_itens_sem_I0729_mapeado", sem)], consolidada)
    with (RAIZ / "dados/validacao.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS, lineterminator="\n")
        w.writeheader()
        w.writerows(linhas)
    for l in linhas:
        if l["linha_tipo"].startswith("resumo"):
            print(l["linha_tipo"], l["amostra"], l["variavel"], l["metodo"], l["n_unidades"], l["concordancia"], l["kappa"])


if __name__ == "__main__":
    main()
