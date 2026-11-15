"""Coleta no Stack Overflow (API do Stack Exchange, site=stackoverflow).

Detalhes da consulta, do filtro e da cota em api_stackexchange.py.

Uso (a partir da raiz do repositório):
  python scripts/coleta_stackoverflow.py --dry-run
  python scripts/coleta_stackoverflow.py
"""

import api_stackexchange

if __name__ == "__main__":
    api_stackexchange.main(
        fonte="stackoverflow",
        site="stackoverflow",
        script="scripts/coleta_stackoverflow.py",
        descricao=__doc__.splitlines()[0],
    )
