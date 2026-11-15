"""Sorteio reprodutível de itens (lote de calibração da fase 1; amostra da validação).

Método: random.Random(semente).sample(linhas, n), com as linhas na ordem do
arquivo de entrada (dados/itens.csv está em ordem de id_item). O resultado é
impresso em ordem de id_item, um por linha.

O lote de calibração da fase 1 (desvio D3) é o padrão:
  python scripts/sortear_lote.py                          # 100 itens de dados/itens.csv, semente 42
Outros usos:
  python scripts/sortear_lote.py --n 30 --entrada outro.csv --saida amostra.csv
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def sortear(linhas: list[dict], n: int, semente: int) -> list[dict]:
    return sorted(random.Random(semente).sample(linhas, n), key=lambda l: l["id_item"])


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--entrada", type=Path, default=RAIZ / "dados" / "itens.csv")
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--semente", type=int, default=42)
    p.add_argument("--saida", type=Path, help="grava as linhas sorteadas em CSV (opcional)")
    args = p.parse_args()

    with args.entrada.open(encoding="utf-8", newline="") as f:
        leitor = csv.DictReader(f)
        colunas, linhas = leitor.fieldnames, list(leitor)
    lote = sortear(linhas, args.n, args.semente)

    if args.saida:
        with args.saida.open("w", encoding="utf-8", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=colunas, lineterminator="\n")
            escritor.writeheader()
            escritor.writerows(lote)
    for l in lote:
        print(l["id_item"])


if __name__ == "__main__":
    main()
