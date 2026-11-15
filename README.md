# revisao-cinzenta-multitenant

Revisão de literatura cinzenta do TCC *Impactos das Arquiteturas de Dados para Aplicações SaaS Multi-Tenant Baseadas em Bancos de Dados Relacionais na Engenharia de Dados* (Universidade de Brasília). O pré-registro da revisão está em [`protocolo.md`](protocolo.md).

## Ambiente

Use um ambiente virtual próprio deste repositório, em `.venv` (já ignorado pelo git). É preciso ter Python 3.9 ou mais recente e o `git` no PATH.

```bash
deactivate 2>/dev/null          # se houver outro venv ativo no terminal
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

As credenciais ficam no `.env`, na raiz, que não é versionado:

```
GITHUB_TOKEN=<token do GitHub>
STACKEXCHANGE_KEY=<chave de aplicativo do stackapps.com>
```

Os valores do `.env` têm prioridade sobre variáveis de ambiente de mesmo nome. Os scripts informam de onde leram cada valor, sem mostrá-lo.

## Coleta

Cada script tem um modo `--dry-run`, que lista as buscas e o resultado das verificações sem acessar a rede nem gravar nada:

```bash
python scripts/coleta_github.py --dry-run
python scripts/coleta_stackoverflow.py --dry-run
python scripts/coleta_dba.py --dry-run
python scripts/coleta_dbt_forum.py --dry-run
```

Sem `--dry-run`, a coleta só começa se:

- a tag `v0-protocolo` existir;
- `protocolo.md` e `scripts/` não tiverem alterações não commitadas;
- os termos do código forem iguais aos da seção 5.1 do `protocolo.md` marcado pela tag.

A estrutura de `dados/` e o registro manual do Debezium estão descritos em [`dados/README.md`](dados/README.md).
