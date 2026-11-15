"""Sobrescreve decisões da fase 1 já gravadas em dados/triagem.csv.

Cada linha do arquivo de correções tem o mesmo formato de scripts/gravar_decisoes.py:

    ID|i/e/d|CRITERIO|justificativa

Diferente de gravar_decisoes.py, aqui o ID precisa já estar triado. Para cada
correção, o script imprime a decisão e o critério anteriores e os novos, para
registro. Se qualquer linha tiver erro, nada é gravado. O triagem.csv é regravado
inteiro, ordenado por id_item, com fim de linha LF.

Uso: python3 scripts/aplicar_correcoes.py <raiz do repositório> <correcoes.txt>
"""
import csv
import sys
from pathlib import Path

DEC = {"i": "incluir", "e": "excluir", "d": "duvida"}
CRIT = {"IC1", "IC2", "IC3", "IC4", "EC1", "EC2", "EC3", "EC4", "EC5"}


def main(raiz: Path, arq: Path) -> None:
    p = raiz / "dados/triagem.csv"
    with p.open(encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        colunas = r.fieldnames
        tri = {l["id_item"]: l for l in r}
    corr, erros = {}, []
    for k, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
        if not linha.strip():
            continue
        partes = linha.split("|", 3)
        if len(partes) != 4:
            erros.append(f"linha {k}: formato")
            continue
        i, d, c, j = (x.strip() for x in partes)
        if i not in tri:
            erros.append(f"linha {k}: {i} não está no triagem.csv")
        elif i in corr:
            erros.append(f"linha {k}: {i} repetido")
        elif d not in DEC:
            erros.append(f"linha {k}: decisão {d}")
        elif (d == "e") != bool(c) or (c and c not in CRIT):
            erros.append(f"linha {k}: critério {c!r} com decisão {d}")
        elif not j:
            erros.append(f"linha {k}: sem justificativa")
        elif "[EC4-tematico]" in j and c != "EC4":
            erros.append(f"linha {k}: marcação EC4 sem EC4")
        else:
            corr[i] = (DEC[d], c, j)
    if erros:
        sys.exit("NADA GRAVADO:\n" + "\n".join(erros))
    for i, (d, c, j) in corr.items():
        l = tri[i]
        print(f"{i}: {l['decisao_f1']}/{l['criterio_exclusao'] or '-'} -> {d}/{c or '-'}")
        l["decisao_f1"], l["criterio_exclusao"], l["justificativa"] = d, c, j
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=colunas, lineterminator="\n")
        w.writeheader()
        w.writerows(tri[i] for i in sorted(tri))
    print(f"corrigidos {len(corr)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
