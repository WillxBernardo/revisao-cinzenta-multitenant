"""Valida e grava decisões novas da fase 1 da triagem em dados/triagem.csv.

Cada linha do arquivo de decisões tem o formato

    ID|i/e/d|CRITERIO|justificativa

com i = incluir, e = excluir, d = duvida. O critério é obrigatório apenas para
exclusões (EC1-EC5 ou o IC não atendido). A marcação [EC4-tematico] só é aceita
com EC4 (desvio D3e). IDs já triados são recusados: para alterar uma decisão
existente, use scripts/aplicar_correcoes.py.

Se qualquer linha tiver erro, nada é gravado. O triagem.csv é regravado inteiro,
ordenado por id_item, com fim de linha LF.

Uso: python3 scripts/gravar_decisoes.py <raiz do repositório> <decisoes.txt>
"""
import csv
import sys
from collections import Counter
from pathlib import Path

DEC = {"i": "incluir", "e": "excluir", "d": "duvida"}
CRIT = {"IC1", "IC2", "IC3", "IC4", "EC1", "EC2", "EC3", "EC4", "EC5"}
COLUNAS = ["id_item", "url", "titulo", "fonte", "ids_busca", "decisao_f1", "decisao_f2",
           "criterio_exclusao", "justificativa"]


def main(raiz: Path, arq: Path) -> None:
    itens = {l["id_item"]: l for l in csv.DictReader((raiz / "dados/itens.csv").open(encoding="utf-8"))}
    p = raiz / "dados/triagem.csv"
    tri = {l["id_item"]: l for l in csv.DictReader(p.open(encoding="utf-8"))} if p.exists() else {}
    novos, erros = [], []
    for k, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
        if not linha.strip():
            continue
        partes = linha.split("|", 3)
        if len(partes) != 4:
            erros.append(f"linha {k}: formato")
            continue
        i, d, c, j = (x.strip() for x in partes)
        if i not in itens:
            erros.append(f"linha {k}: {i} não existe")
        elif i in tri:
            erros.append(f"linha {k}: {i} já triado")
        elif d not in DEC:
            erros.append(f"linha {k}: decisão {d}")
        elif (d == "e") != bool(c) or (c and c not in CRIT):
            erros.append(f"linha {k}: critério {c!r} com decisão {d}")
        elif not j:
            erros.append(f"linha {k}: sem justificativa")
        elif "[EC4-tematico]" in j and c != "EC4":
            erros.append(f"linha {k}: marcação EC4 sem EC4")
        else:
            it = itens[i]
            novos.append({"id_item": i, "url": it["url_canonica"], "titulo": it["titulo"], "fonte": it["fonte"],
                          "ids_busca": it["ids_busca"], "decisao_f1": DEC[d], "decisao_f2": "",
                          "criterio_exclusao": c, "justificativa": j})
    ids = [n["id_item"] for n in novos]
    if len(set(ids)) != len(ids):
        erros.append("ids repetidos no arquivo")
    if erros:
        sys.exit("NADA GRAVADO:\n" + "\n".join(erros))
    tri.update({n["id_item"]: n for n in novos})
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS, lineterminator="\n")
        w.writeheader()
        w.writerows(tri[i] for i in sorted(tri))
    print(f"gravados {len(novos)}: {dict(Counter(n['decisao_f1'] for n in novos))}; "
          f"triagem.csv agora com {len(tri)} itens de {len(itens)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
