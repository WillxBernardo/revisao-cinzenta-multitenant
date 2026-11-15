# dados/

| Caminho | Conteúdo |
|---|---|
| `brutos/<fonte>_<AAAAMMDDTHHMMSSZ>/` | Uma pasta por execução de script (carimbo em UTC), com um JSON por busca: metadados e resposta completa, inclusive de erros. |
| `log_buscas.csv` | Uma linha por busca feita pelos scripts (protocolo, seção 11). |
| `execucoes.csv` | Uma linha por execução de script. `status`: `completa` (todas as buscas executadas, nenhuma com erro), `erro` (todas executadas, ao menos uma com erro) ou `incompleta` (interrompida antes do fim). Vale a última `completa` de cada fonte (protocolo, seção 5.5). |
| `debezium_manual.csv` | Deixou de ser usado pelo desvio D1 (protocolo, seção 13): a busca no grupo do Debezium passou de manual para automatizada. O arquivo permanece no repositório, só com o cabeçalho. |

## Debezium (desvio D1)

O grupo de usuários do Debezium (Google Groups) não tem API. Pelo desvio D1, as 81 buscas são feitas pelo `scripts/coleta_debezium.py` na página de busca do grupo (`https://groups.google.com/g/debezium/search?q=<termo A> <termo B>`), com 5 s entre requisições, e seguem o mesmo registro das demais fontes: `brutos/debezium_<AAAAMMDDTHHMMSSZ>/A{i}B{j}.json`, `log_buscas.csv` e `execucoes.csv`.

- Só a primeira página de cada busca é coletada (até 30 tópicos). As páginas seguintes dependem de JavaScript e de uma rota interna bloqueada pelo `robots.txt`.
- O HTML completo da página fica no bruto da busca, em `requisicoes[0].resposta`.
- `urls_coletadas` traz a URL canônica de cada tópico (`https://groups.google.com/g/debezium/c/<id>`).
- `n_resultados` é o total informado pela interface ("1–4 of 4" → 4). Fica vazio quando ela mostra "of many"; nesse caso, a busca recebe o aviso "mais resultados não coletados (limite da 1ª página)".
- Uma busca só tem 0 resultados quando a página mostra "No conversations matched your search". Redirecionamento para login, acesso negado, bloqueio do Google (inclusive CAPTCHA) ou página fora do formato esperado são registrados como erro da busca. Após 3 buscas seguidas com erro, a execução é interrompida (`incompleta`).

## Posições dos termos

Os códigos `A{i}B{j}`, usados nos nomes dos brutos e no `id_busca`, indicam as posições dos termos, na ordem da seção 5.1:

- **A:** A1 `"database per tenant"`, A2 `"database-per-tenant"`, A3 `"database per customer"`, A4 `"schema per tenant"`, A5 `"schema-per-tenant"`, A6 `"schema per customer"`, A7 `"shared schema" tenant`, A8 `"tenant_id"`, A9 `"pool model" tenant`
- **B:** B1 `ingestion`, B2 `CDC`, B3 `"change data capture"`, B4 `ETL`, B5 `ELT`, B6 `"data warehouse"`, B7 `dbt`, B8 `pipeline`, B9 `connector`
