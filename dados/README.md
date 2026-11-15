# dados/

Estes são os arquivos produzidos em cada fase da revisão, na ordem do fluxo. O protocolo está em [`../protocolo.md`](../protocolo.md), e os desvios citados (D1 a D8) estão na seção 13 dele.

Todos os CSVs estão em UTF-8, com fim de linha LF. Quando uma célula tem vários valores, eles são separados por `;`.

## Coleta

| Caminho | Conteúdo |
|---|---|
| `brutos/<fonte>_<AAAAMMDDTHHMMSSZ>/` | Uma pasta por execução de script, com carimbo em UTC, e um JSON por busca com os metadados e a resposta completa, inclusive de erros. No Stack Exchange, a pasta também traz `filtro.json`. |
| `log_buscas.csv` | Uma linha por busca feita pelos scripts (protocolo, seção 11): `id_busca, data_hora, fonte, termo_a, termo_b, string_enviada, n_resultados, n_coletados`. São 486 buscas. |
| `execucoes.csv` | Uma linha por execução de script. O `status` pode ser `completa` (todas as buscas executadas, nenhuma com erro), `erro` (todas executadas, ao menos uma com erro) ou `incompleta` (interrompida antes do fim). Vale a última execução `completa` de cada fonte (protocolo, seção 5.5). As cinco execuções registradas, uma por fonte, estão completas. |
| `debezium_manual.csv` | Deixou de ser usado com o desvio D1, quando a busca no grupo do Debezium passou de manual para automatizada. O arquivo permanece no repositório, só com o cabeçalho, como registro do que o pré-registro previa. |

## Deduplicação: `itens.csv`

O arquivo tem os 2.121 itens únicos, gerados por `scripts/deduplicar.py` a partir dos brutos de coleta (protocolo, seção 6.3; desvio D2). Há uma linha por URL canônica.

| Coluna | Conteúdo |
|---|---|
| `id_item` | `I0001` a `I2121`, em ordem de fonte e URL canônica. É o identificador usado em todos os outros arquivos. |
| `url_canonica` | URL sem âncora, sem parâmetros, sem identificador de mensagem e sem barra final. |
| `fonte` | `github`, `stackoverflow`, `dba`, `dbt_forum` ou `debezium`. |
| `tipo` | `issue` ou `discussion` (GitHub); `pergunta` (Stack Exchange); `topico` (dbt e Debezium). |
| `titulo`, `trecho` | Título e os 600 primeiros caracteres do corpo, sem HTML (D2). |
| `data_publicacao` | Data de criação do item, no formato AAAA-MM-DD. |
| `ids_busca`, `n_buscas` | Buscas que encontraram o item (o `id_busca` do `log_buscas.csv`) e quantas foram. |
| `estrategias` | Estratégias dos termos do bloco A dessas buscas. É uma pista de busca, não a codificação. |
| `origem_trecho` | `corpo`, `corpo_vazio` ou `trecho_da_busca`, este último quando a fonte não entrega o corpo na busca. |

## Triagem: `triagem.csv`

O arquivo tem uma linha por item (2.121), com as colunas `id_item, url, titulo, fonte, ids_busca, decisao_f1, decisao_f2, criterio_exclusao, justificativa`.

| Coluna | Conteúdo |
|---|---|
| `decisao_f1` | Decisão da fase 1, por título e trecho: `incluir` (18), `duvida` (84) ou `excluir` (2.019). |
| `decisao_f2` | Decisão da fase 2, por leitura completa: `incluir` (17) ou `excluir` (85). É preenchida só para os 102 itens com `incluir` ou `duvida` na fase 1. |
| `criterio_exclusao` | Critério da exclusão final: EC1 a EC5, ou o IC não atendido. A atribuição segue a ordem de precedência do desvio D4a. A coluna fica vazia nos incluídos. |
| `justificativa` | Justificativa da fase 1. A da fase 2 vem depois de `\|\| F2:`, e as decisões posteriores à validação vêm depois de `\|\| D7:` e `\|\| D8:`. |

Itens excluídos, mas tematicamente relevantes, trazem uma marcação na justificativa:

| Marcação | Desvio | Motivo | Itens |
|---|---|---|---|
| `[EC4-tematico]` | D3e | Idioma | 9 |
| `[D3b-tematico]` | D5b | Multi-tenancy só no lado analítico | 8 |
| `[D7a-tematico]` | D8 | Exclusão pela regra D7a | 5 |

## Extração: `extracao.csv`

O arquivo tem uma linha por item incluído (17). As colunas são as da seção 11 do protocolo, mais `projeto` e `gerado_por_agente` (desvio D4f).

| Coluna | Conteúdo |
|---|---|
| `url`, `url_arquivada` | URL original e cópia no Wayback Machine. A cópia está vazia nos 3 itens do Stack Overflow, cuja captura falhou: para eles, a cópia de referência é o bruto da API em `brutos/fase2_*` (D6b), e a falha é anotada em `observacao`. |
| `data_relato`, `data_acesso` | Data de publicação do item e data da leitura completa, no formato AAAA-MM-DD. |
| `papel_relator`, `estrategia`, `polaridade`, `motivo_escolha`, `desfecho` | Codebook, seção 8. Cada coluna tem um valor. |
| `etapa`, `tipo_problema`, `metrica_relacionada` | Codebook, seção 8. Cada coluna pode ter vários valores. |
| `cr1` a `cr5` | Checklist de credibilidade (seção 7): `1` = sim, `0` = não. |
| `trecho_chave`, `observacao` | Citação do item que sustenta a codificação e notas do codificador. |
| `projeto` | Repositório (`dono/nome`) ou comunidade de origem. O Stack Overflow conta como uma comunidade. |
| `gerado_por_agente` | `sim`, `não` ou `incerto`, para itens que parecem gerados por agentes de IA (D3d). |

A codificação dos itens da amostra de validação é a consolidada pelo desvio D7c.

## Validação

| Arquivo | Conteúdo |
|---|---|
| `validacao_cega.csv` | Amostra de validação e recodificação de `estrategia`, `etapa`, `tipo_problema` e `polaridade`, feita sem consulta à codificação original (ver D6c sobre a exposição prévia a parte da amostra). A amostra tem 5 itens: I0452, I0729, I0893, I0894 e I2105. Eles foram sorteados com semente 42 entre os 22 incluídos da época (20%, arredondado para cima). Os valores estão como foram escritos, inclusive os que ficam fora do codebook. |
| `validacao_original.csv` | Codificação original dos mesmos 5 itens, copiada do `extracao.csv` no commit `240a301`. É anterior à consolidação (D7c) e à exclusão do I0729 (D7a), que retirou o item do `extracao.csv`. |
| `validacao.csv` | Saída de `scripts/validacao_kappa.py`. A coluna `linha_tipo` separa quatro seções, descritas abaixo. A coluna `consolidada` traz a codificação final (D7c), que é a do `extracao.csv`. |

Seções do `validacao.csv`:

- `item`: comparação item a item;
- `resumo`: concordância e kappa de Cohen, com os 5 itens e com os 4 sem o I0729 (D6c, D7b);
- `item_secundario` e `resumo_secundario`: análise secundária, com os valores fora do codebook mapeados às categorias da seção 8.3 (D7b).

## Fase 2 e arquivamento

| Caminho | Conteúdo |
|---|---|
| `brutos/fase2_20261115T100112Z/` | Conteúdo completo dos 15 itens da calibração da fase 2 (D5). |
| `brutos/fase2_20261115T101207Z/` | Conteúdo completo dos outros 87 itens avaliados na fase 2. |
| `brutos/wayback_20261115T102424Z.json` | Log do arquivamento, com uma entrada por tentativa no Save Page Now: `url`, `tentativa`, `status`, `url_final`, `content_location`, `data`. Cobre os 22 incluídos da época: 19 foram capturados na primeira tentativa, e os 3 do Stack Overflow falharam nas três (HTTP 520). Cinco desses 22 foram excluídos depois (D7, D8). |

Cada `<ID>.json` da fase 2 traz `id_item`, `url`, `fonte` e `coletado_em`, além das respostas completas das APIs, com o status HTTP. O conteúdo varia por fonte:

| Fonte | Conteúdo do bruto |
|---|---|
| Issues do GitHub | `issue` e `comments` |
| Discussions do GitHub | `discussion`, com comentários e respostas |
| Stack Exchange | `question`, `question_comments` e `answers`; no DBA, também `answer_comments` |
| Fórum do dbt | `topico` e `posts_extra` |
| Debezium | `topico`, com o HTML da página |

O texto de leitura gerado pelo `scripts/coleta_fase2.py` não é versionado. Ele é derivado das mesmas respostas.

## Debezium (desvio D1)

O grupo de usuários do Debezium (Google Groups) não tem API. Pelo desvio D1, as 81 buscas são feitas pelo `scripts/coleta_debezium.py` na página de busca do grupo (`https://groups.google.com/g/debezium/search?q=<termo A> <termo B>`), com 5 s entre requisições. Elas seguem o mesmo registro das demais fontes: `brutos/debezium_<AAAAMMDDTHHMMSSZ>/A{i}B{j}.json`, `log_buscas.csv` e `execucoes.csv`.

- Só a primeira página de cada busca é coletada (até 30 tópicos). As páginas seguintes dependem de JavaScript e de uma rota interna bloqueada pelo `robots.txt`.
- O HTML completo da página fica no bruto da busca, em `requisicoes[0].resposta`.
- `urls_coletadas` traz a URL canônica de cada tópico (`https://groups.google.com/g/debezium/c/<id>`).
- `n_resultados` é o total informado pela interface ("1–4 of 4" → 4). Fica vazio quando ela mostra "of many"; nesse caso, a busca recebe o aviso "mais resultados não coletados (limite da 1ª página)".
- Uma busca só tem 0 resultados quando a página mostra "No conversations matched your search". São registrados como erro da busca, e nunca como zero resultados:
  - redirecionamento para login;
  - acesso negado;
  - bloqueio do Google, inclusive CAPTCHA;
  - página fora do formato esperado.
- Após 3 buscas seguidas com erro, a execução é interrompida (`incompleta`).

## Posições dos termos

Os códigos `A{i}B{j}`, usados nos nomes dos brutos e no `id_busca`, indicam as posições dos termos, na ordem da seção 5.1:

- **A:** A1 `"database per tenant"`, A2 `"database-per-tenant"`, A3 `"database per customer"`, A4 `"schema per tenant"`, A5 `"schema-per-tenant"`, A6 `"schema per customer"`, A7 `"shared schema" tenant`, A8 `"tenant_id"`, A9 `"pool model" tenant`
- **B:** B1 `ingestion`, B2 `CDC`, B3 `"change data capture"`, B4 `ETL`, B5 `ELT`, B6 `"data warehouse"`, B7 `dbt`, B8 `pipeline`, B9 `connector`
