# dados/

| Caminho | Conteúdo |
|---|---|
| `brutos/<fonte>_<AAAAMMDDTHHMMSSZ>/` | Uma pasta por execução de script (carimbo em UTC), com um JSON por busca: metadados e resposta completa, inclusive de erros. |
| `brutos/debezium_<AAAAMMDD>/` | Páginas de resultados das buscas manuais no grupo do Debezium, em HTML. |
| `log_buscas.csv` | Uma linha por busca feita pelos scripts (protocolo, seção 11). |
| `execucoes.csv` | Uma linha por execução de script. `status`: `completa` (todas as buscas executadas, nenhuma com erro), `erro` (todas executadas, ao menos uma com erro) ou `incompleta` (interrompida antes do fim). Vale a última `completa` de cada fonte (protocolo, seção 5.5). |
| `debezium_manual.csv` | Registro manual das buscas no grupo do Debezium. |

## Registro manual do Debezium

O grupo de usuários do Debezium não tem API. As 81 buscas são feitas na caixa de busca do grupo e registradas à mão em `debezium_manual.csv`, que tem o mesmo cabeçalho do `log_buscas.csv`:

| Coluna | Preenchimento |
|---|---|
| `id_busca` | `debezium_<AAAAMMDD>_A{i}B{j}`, com a data da busca e as posições dos termos (ex.: `debezium_20261120_A4B1`) |
| `data_hora` | Data e hora da busca em ISO 8601 com fuso (ex.: `2026-11-20T14:30:00-03:00`) |
| `fonte` | `debezium` |
| `termo_a`, `termo_b` | Os termos como estão na seção 5.1 do protocolo, com as aspas |
| `string_enviada` | A string exatamente como foi digitada na caixa de busca |
| `n_resultados` | Total de resultados informado pela interface; vazio se ela não informar |
| `n_coletados` | Número de resultados presentes na página salva |

A página de resultados de cada busca é salva em HTML em `brutos/debezium_<AAAAMMDD>/A{i}B{j}.html`.

Em CSV, um campo com aspas é escrito entre aspas e com as aspas internas duplicadas: `"database per tenant"` vira `"""database per tenant"""`. Editores de planilha fazem isso sozinhos.

Posições dos termos, na ordem da seção 5.1:

- **A:** A1 `"database per tenant"`, A2 `"database-per-tenant"`, A3 `"database per customer"`, A4 `"schema per tenant"`, A5 `"schema-per-tenant"`, A6 `"schema per customer"`, A7 `"shared schema" tenant`, A8 `"tenant_id"`, A9 `"pool model" tenant`
- **B:** B1 `ingestion`, B2 `CDC`, B3 `"change data capture"`, B4 `ETL`, B5 `ELT`, B6 `"data warehouse"`, B7 `dbt`, B8 `pipeline`, B9 `connector`
