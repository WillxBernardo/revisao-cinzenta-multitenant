# scripts/testes/

Testes dos scripts de coleta. Nenhum deles grava em `dados/`: os dois conferem, ao final, que a pasta não mudou.

| Teste | Acessa a rede? | O que verifica |
|---|---|---|
| `teste_offline.py` | Não | Roda os `main()` reais de `coleta_github`, `api_stackexchange` e `coleta_dbt_forum` contra respostas simuladas. Confere: um JSON por busca com metadados e resposta completa; cabeçalhos gravados (só `date`, `content-type`, `x-ratelimit-*`); erro não recuperável (422) gravado como bruto, com a execução seguindo; limites de taxa (429 com `Retry-After`, `RATE_LIMITED` no GraphQL, throttle e `backoff` do Stack Exchange); `incomplete_results` persistente; paginação do dbt; execução interrompida; `log_buscas.csv` e `execucoes.csv`; chave do Stack Exchange mascarada; prioridade do `.env` sobre o ambiente; aborto sem chave ou sem a tag. Grava só num diretório temporário, apagado ao final. |
| `teste_fumaca.py` | Sim (7 requisições) | Valida endpoints, autenticação e os campos que a coleta espera, com consultas neutras, fora do protocolo: `"dead letter queue"` no GitHub (issues e discussions) e no Stack Exchange (stackoverflow e dba), `incremental` no fórum do dbt. Usa `requisitar`, `criar_filtro` e a consulta GraphQL reais. Só imprime um resumo e consome um pouco da cota das APIs. |

## Como rodar

A partir da raiz do repositório, com o `.venv` ativo:

```bash
python -B scripts/testes/teste_offline.py              # temporário no diretório padrão do sistema
python -B scripts/testes/teste_offline.py /outro/dir   # ou em outro diretório
python -B scripts/testes/teste_fumaca.py               # requer GITHUB_TOKEN e STACKEXCHANGE_KEY no .env
```

Os dois terminam com código 0 se tudo passar e 1 se alguma verificação falhar. O `-B` evita criar `__pycache__`.

Nenhum dos testes contém credenciais. O offline usa valores fictícios num `.env` temporário. O de fumaça lê o `.env` real em tempo de execução e só imprime de onde leu cada valor.
