# revisao-cinzenta-multitenant

Protocolo, dados e scripts da revisão de literatura cinzenta do Trabalho de Conclusão de Curso *Impactos das Arquiteturas de Dados para Aplicações SaaS Multi-Tenant Baseadas em Bancos de Dados Relacionais na Engenharia de Dados*, de William Bernardo da Silva (Universidade de Brasília).

O TCC investiga como cada estratégia de isolamento multi-tenant (banco por tenant, esquema por tenant, esquema compartilhado) afeta a ingestão, a transformação e a modelagem dos dados. Esta revisão reúne relatos de praticantes que mostram que o problema existe e quem o enfrenta. A questão da revisão é:

> **QR:** Que problemas praticantes relatam ao construir pipelines de dados sobre aplicações multi-tenant baseadas em bancos relacionais, e como esses problemas se distribuem entre as estratégias de isolamento e as etapas do ciclo de vida da engenharia de dados?

O método está pré-registrado em [`protocolo.md`](protocolo.md). O protocolo define as fontes, as strings de busca, os critérios de seleção, o checklist de credibilidade, o codebook e a validação. A versão fixada antes de qualquer busca é a da tag [`v0-protocolo`](https://github.com/WillxBernardo/revisao-cinzenta-multitenant/blob/v0-protocolo/protocolo.md). As alterações posteriores estão registradas como desvios na [seção 13 do protocolo](protocolo.md#13-desvios-do-protocolo).

**Fontes:** issues e discussions do GitHub, Stack Overflow, Database Administrators Stack Exchange (DBA), fórum da comunidade dbt e grupo de usuários do Debezium. Cada fonte recebeu as mesmas 81 buscas, formadas por 9 termos de estratégia combinados com 9 termos de engenharia de dados (seção 5 do protocolo).

## Fluxo de seleção

| Etapa | Resultado | Detalhamento |
|---|---|---|
| Buscas | 486 | 81 por fonte. No GitHub, são 81 em issues e 81 em discussions. Todas as execuções terminaram sem erro. |
| Resultados coletados | 3.720 | GitHub 3.678, Stack Overflow 32, DBA 5, Debezium 3, dbt 2. |
| Itens únicos | 2.121 | 1.599 repetições unificadas pela URL canônica. |
| Fase 1 (título e trecho) | 102 seguem | 18 receberam `incluir` e 84 `duvida`. Foram excluídos 2.019 itens: IC1 1.470, IC2 267, EC4 126, EC2 79, EC1 55, IC4 18, EC3 4. |
| Fase 2 (leitura completa) | 17 incluídos | Foram excluídos 85 itens: IC2 32, IC3 28, IC1 19, EC2 3, IC4 2, EC1 1. Cinco dessas exclusões vieram depois da validação: I0729 (D7) e I0926, I1888, I1889, I1893 (D8). |
| Extração e codificação | 17 itens de 12 projetos | 14 itens vêm do GitHub e 3 do Stack Overflow, que conta como um projeto. O projeto com mais itens é `debezium/dbz`, com 4. |

Dos 17 incluídos, 12 já tinham `incluir` na fase 1 e 5 vieram das 84 dúvidas.

Alguns itens excluídos eram tematicamente relevantes. Para relatar essa perda, a justificativa deles traz uma marcação:

| Marcação | Motivo da exclusão | Itens |
|---|---|---|
| `[EC4-tematico]` | Idioma | 9 |
| `[D3b-tematico]` | Multi-tenancy só no lado analítico | 8 |
| `[D7a-tematico]` | Informação necessária só fora do próprio item | 5 |

As fontes dos números são `dados/log_buscas.csv` e `dados/execucoes.csv` (buscas e resultados), `dados/itens.csv` (itens únicos), `dados/triagem.csv` (fases 1 e 2) e `dados/extracao.csv` (incluídos).

## Desvios do protocolo

Todos foram registrados em 2026-11-15. O texto completo, com a justificativa de cada um, está na [seção 13 do protocolo](protocolo.md#13-desvios-do-protocolo).

| Desvio | Seções | Resumo |
|---|---|---|
| D1 | 4, 5.3, 5.5, 11 | A busca no grupo do Debezium deixou de ser manual e passou a ser automatizada, limitada à primeira página de resultados de cada busca. |
| D2 | 6.3 | O trecho da fase 1 são os 600 primeiros caracteres do corpo. A deduplicação usa a URL canônica e a última execução completa de cada fonte. |
| D3 | 6.1, 6.2, 7 | Interpretação de IC1, IC2, EC2 e IC4 após a calibração da fase 1. Itens gerados por IA são marcados, não excluídos. Marcação `[EC4-tematico]`. |
| D4 | 6.2, 6.3, 8, 11 | Ordem de precedência entre critérios de exclusão; espelhos contam como EC3; regras para multi-tenancy de ferramentas de dados, provas de conceito e idioma misto; colunas `projeto` e `gerado_por_agente`. |
| D5 | 6.1, 8.3 | IC3 exige que a estratégia faça parte da situação relatada. Marcação `[D3b-tematico]`. A propagação do `tenant_id` é codificada como `governanca_isolamento`. |
| D6 | 6.3, 9, 10 | Profundidade de leitura dos itens com mais de 15 KB; falha do Wayback Machine nos 3 itens do Stack Overflow; exposição prévia do autor a parte da amostra de validação. |
| D7 | 6.1, 9 | Os critérios são avaliados só no conteúdo do próprio item, o que excluiu o I0729. A concordância ganha uma análise secundária com mapeamento de vocabulário, e a codificação da amostra é consolidada. |
| D8 | 6.1 | A regra D7a foi aplicada aos demais incluídos, com 4 exclusões. Marcação `[D7a-tematico]`. |

## Estrutura do repositório

```
.
├── protocolo.md                 # pré-registro e desvios (seção 13)
├── README.md
├── LICENSE                      # MIT, para os scripts
├── requirements.txt
├── .env                         # credenciais; não versionado
├── scripts/
│   ├── comum.py                 # termos, verificações, credenciais, requisições e registros da coleta
│   ├── coleta_github.py         # coleta: issues (REST) e discussions (GraphQL)
│   ├── coleta_stackoverflow.py  # coleta: Stack Overflow
│   ├── coleta_dba.py            # coleta: DBA Stack Exchange
│   ├── api_stackexchange.py     # código comum às duas anteriores
│   ├── coleta_dbt_forum.py      # coleta: fórum do dbt (Discourse)
│   ├── coleta_debezium.py       # coleta: grupo do Debezium (Google Groups; D1)
│   ├── deduplicar.py            # deduplicação: gera dados/itens.csv
│   ├── sortear_lote.py          # sorteios com semente 42
│   ├── gravar_decisoes.py       # grava decisões novas da fase 1
│   ├── aplicar_correcoes.py     # corrige decisões já gravadas da fase 1
│   ├── coleta_fase2.py          # conteúdo completo dos itens da fase 2
│   ├── arquivar_wayback.py      # arquivamento no Wayback Machine
│   ├── validacao_kappa.py       # concordância e kappa de Cohen
│   └── testes/                  # testes offline e de fumaça
└── dados/
```

### Arquivos em `dados/`

A descrição completa, com as colunas de cada arquivo, está em [`dados/README.md`](dados/README.md).

| Arquivo | Papel |
|---|---|
| `brutos/` | Respostas completas das fontes, sem filtragem. Contém uma pasta por execução de coleta, o conteúdo completo dos itens da fase 2 (`fase2_*`) e o log do arquivamento (`wayback_*`). |
| `log_buscas.csv` | Uma linha por busca: string enviada, total de resultados e itens coletados. |
| `execucoes.csv` | Uma linha por execução de coleta, com status e commit. |
| `debezium_manual.csv` | Registro previsto para a busca manual no Debezium. Deixou de ser usado com o desvio D1 e tem só o cabeçalho. |
| `itens.csv` | Os 2.121 itens únicos, com título, trecho e as buscas que encontraram cada um. |
| `triagem.csv` | Decisões das fases 1 e 2, cada uma com critério e justificativa. |
| `extracao.csv` | Codificação dos 17 incluídos: codebook, credibilidade, trecho-chave e URL arquivada. |
| `validacao_cega.csv` | Recodificação da amostra de validação (5 itens), feita sem consulta à codificação original. |
| `validacao_original.csv` | Codificação original da mesma amostra, antes da consolidação. |
| `validacao.csv` | Comparação item a item, concordância e kappa de Cohen. |

## Como reproduzir

Os comandos abaixo partem da raiz do repositório, com o ambiente virtual ativo, e seguem a ordem das fases.

### 1. Ambiente

É preciso ter Python 3.9 ou mais recente e o `git` no PATH. A revisão rodou com Python 3.12.3.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

As credenciais ficam num `.env` na raiz, que não é versionado:

```
GITHUB_TOKEN=<token do GitHub>
STACKEXCHANGE_KEY=<chave de aplicativo do stackapps.com>
```

- O `GITHUB_TOKEN` é usado na coleta e na fase 2 do GitHub.
- A `STACKEXCHANGE_KEY` é usada no Stack Overflow e no DBA.
- O fórum do dbt, o Google Groups e o Wayback Machine não exigem credenciais.

Os valores do `.env` têm prioridade sobre variáveis de ambiente de mesmo nome. Os scripts informam de onde leram cada valor, sem mostrá-lo.

### 2. Coleta

Cada script de coleta tem o modo `--dry-run`, que lista as buscas e o resultado das verificações sem acessar a rede nem gravar nada:

```bash
python scripts/coleta_github.py --dry-run
python scripts/coleta_stackoverflow.py --dry-run
python scripts/coleta_dba.py --dry-run
python scripts/coleta_dbt_forum.py --dry-run
python scripts/coleta_debezium.py --dry-run
```

Sem `--dry-run`, a coleta só começa se três condições forem atendidas:

1. a tag `v0-protocolo` existe;
2. `protocolo.md` e `scripts/` não têm alterações não commitadas;
3. os termos do código são iguais aos da seção 5.1 do protocolo marcado pela tag.

Cada execução cria `dados/brutos/<fonte>_<AAAAMMDDTHHMMSSZ>/` e acrescenta linhas ao `log_buscas.csv` e ao `execucoes.csv`.

> **Atenção:** uma nova coleta não reproduz a desta revisão. As fontes mudam com o tempo, e a deduplicação passa a usar a execução mais recente de cada fonte, o que gera outro `itens.csv`, com outros identificadores. Para reproduzir a análise com os dados desta revisão, comece pelo passo 3.

### 3. Deduplicação

```bash
python scripts/deduplicar.py
```

O script lê a última execução completa de cada fonte e regrava o `dados/itens.csv`. Com os brutos versionados, o arquivo gerado é idêntico ao do repositório.

### 4. Triagem, fase 1

O lote de calibração tem 100 itens, sorteados com semente 42 (desvio D3):

```bash
python scripts/sortear_lote.py
```

As decisões são julgamentos de leitura. Os scripts apenas validam e gravam essas decisões no `dados/triagem.csv`:

```bash
python scripts/gravar_decisoes.py . decisoes.txt      # decisões novas
python scripts/aplicar_correcoes.py . correcoes.txt   # correção de decisões já gravadas
```

Cada linha do arquivo de entrada tem a forma `ID|i/e/d|CRITERIO|justificativa`, em que `i` = incluir, `e` = excluir e `d` = duvida.

### 5. Triagem, fase 2

O lote de calibração tem 15 itens, sorteados com semente 42 entre os 102 elegíveis, com pelo menos 3 dúvidas de fontes que não o GitHub (desvio D5). O código abaixo devolve os 15 itens de `dados/brutos/fase2_20261115T100112Z/`:

```python
import csv, random
T = list(csv.DictReader(open("dados/triagem.csv", encoding="utf-8")))
eleg = sorted(t["id_item"] for t in T if t["decisao_f1"] in ("incluir", "duvida"))
nao_github = sorted(t["id_item"] for t in T if t["decisao_f1"] == "duvida" and t["fonte"] != "github")
rng = random.Random(42)
a = rng.sample(nao_github, 3)
b = rng.sample([i for i in eleg if i not in a], 12)
print(sorted(a + b))
```

O conteúdo completo (corpo e comentários ou respostas) é obtido com:

```bash
python scripts/coleta_fase2.py <pasta_de_leitura> --ids ids.txt
```

- O arquivo passado em `--ids` traz um `id_item` por linha.
- Sem `--ids`, o script coleta os itens com `decisao_f1` igual a `incluir` ou `duvida` e `decisao_f2` vazia. No `triagem.csv` final, não há nenhum nessa situação.
- As respostas das APIs vão para `dados/brutos/fase2_<AAAAMMDDTHHMMSSZ>/`.
- Na pasta de leitura fica um texto por item, que não é versionado.

As decisões da fase 2 estão no `triagem.csv`: na coluna `decisao_f2` e, na justificativa, depois de `|| F2:`.

### 6. Extração e arquivamento

A codificação segue o codebook (seção 8 do protocolo) e as colunas do desvio D4f, e está gravada no `dados/extracao.csv`. O arquivamento é feito com:

```bash
python scripts/arquivar_wayback.py
```

- O script processa as linhas com `url_arquivada` vazia.
- Usa 20 s de intervalo entre itens e até 3 tentativas por item.
- Grava o log em `dados/brutos/wayback_<AAAAMMDDTHHMMSSZ>.json`.

Hoje só os 3 itens do Stack Overflow estão nessa situação (desvio D6b). Rodar o script de novo tenta outra vez esses itens e altera o `extracao.csv`.

### 7. Validação

A amostra corresponde a 20% dos 22 incluídos da época, arredondado para cima (5 itens), sorteados com semente 42. A extração daquele momento está no commit `db07814`:

```bash
git show db07814:dados/extracao.csv > /tmp/extracao_22.csv
python scripts/sortear_lote.py --entrada /tmp/extracao_22.csv --n 5   # I0452 I0729 I0893 I0894 I2105
```

O cálculo da concordância e do kappa de Cohen é feito com:

```bash
python scripts/validacao_kappa.py
```

O script compara o `validacao_original.csv` com o `validacao_cega.csv` e regrava o `validacao.csv`. Ele produz duas análises:

- **principal:** com os 5 itens e com os 4 itens sem o I0729 (desvios D6c e D7b);
- **secundária:** com os valores fora do codebook mapeados às categorias da seção 8.3 (desvio D7b).

### Testes

A pasta `scripts/testes/` tem um teste offline, que roda as coletas contra respostas simuladas, e um teste de fumaça, que confere os endpoints com consultas neutras. Os detalhes estão em [`scripts/testes/README.md`](scripts/testes/README.md).

## Limitações

- **Validação limitada.** Não houve segundo codificador independente, e a validação recodificou só 5 itens (4 após a D7a). A concordância foi alta em `etapa`, moderada em `estrategia` e baixa em `tipo_problema`: κ = 0,01 na análise principal e 0,65 na secundária (`dados/validacao.csv`).
- **Corpus pequeno e concentrado.** Dos 17 itens, 14 vêm do GitHub e 4 do mesmo projeto (`debezium/dbz`). Por isso, os resultados são reportados por item e por projeto.
- **Cobertura limitada pelas buscas.** Cada busca coleta até 100 resultados, e no Debezium só a primeira página (D1). As fontes também mudam com o tempo: os brutos estão versionados, e 14 itens foram arquivados no Wayback Machine.
- **Viés para problemas.** Todos os 17 incluídos têm polaridade `problema`. Os achados mostram a existência e a natureza dos problemas, não a sua frequência.
- **Perdas temáticas.** O critério de idioma e a regra de avaliar só o conteúdo do próprio item excluíram 22 itens tematicamente relevantes (marcações acima).

## Licença e direitos

Os scripts em `scripts/` são distribuídos sob a licença MIT (ver [`LICENSE`](LICENSE)).

O conteúdo dos relatos coletados pertence aos seus autores e às plataformas de origem, e segue os termos de uso de cada uma (no Stack Exchange, licenças CC BY-SA). Isso inclui as respostas brutas em `dados/brutos/` e os títulos, trechos e citações nos CSVs. O conteúdo está reproduzido aqui apenas como registro da pesquisa.

## Como citar

W. B. da Silva, "revisao-cinzenta-multitenant: protocolo, dados e scripts da revisão de literatura cinzenta," repositório GitHub, 2026. [Online]. Disponível: https://github.com/WillxBernardo/revisao-cinzenta-multitenant
