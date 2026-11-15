"""Coleta no Database Administrators Stack Exchange (API do Stack Exchange, site=dba).

Detalhes da consulta, do filtro e da cota em api_stackexchange.py.

Uso (a partir da raiz do repositório):
  python scripts/coleta_dba.py --dry-run
  python scripts/coleta_dba.py
"""

import api_stackexchange

if __name__ == "__main__":
    api_stackexchange.main(
        fonte="dba",
        site="dba",
        script="scripts/coleta_dba.py",
        descricao=__doc__.splitlines()[0],
    )
