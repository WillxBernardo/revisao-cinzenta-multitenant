# Protocolo da Revisão de Literatura Cinzenta

**Trabalho:** Impactos das Arquiteturas de Dados para Aplicações SaaS Multi-Tenant Baseadas em Bancos de Dados Relacionais na Engenharia de Dados
**Autor:** William Bernardo da Silva — Universidade de Brasília
**Versão:** 1.0 (pré-registro)
**Data de registro:** data do commit marcado com a tag `v0-protocolo`

Este documento é o pré-registro da revisão. Ele foi fixado **antes** de qualquer busca. Qualquer alteração posterior deve ser registrada na seção 13 (Desvios do protocolo), com data, descrição e justificativa.

---

## 1. Objetivo

Reunir evidências de praticantes sobre os problemas (e eventuais benefícios) que as estratégias de isolamento multi-tenant em bancos relacionais impõem à engenharia de dados, identificando quem os enfrenta e em que etapa do ciclo de vida da engenharia de dados (Reis e Housley) eles ocorrem.

A literatura acadêmica sobre multi-tenancy avalia as estratégias de isolamento sob critérios da aplicação (isolamento, segurança, custo, escalabilidade, customização). As evidências sobre seus efeitos na engenharia de dados estão majoritariamente em fontes produzidas por praticantes, o que justifica uma revisão de literatura cinzenta.

**Diretriz metodológica:** Garousi, V.; Felderer, M.; Mäntylä, M. V. Guidelines for including grey literature and conducting multivocal literature reviews in software engineering. *Information and Software Technology*, 2019.

## 2. Questão da revisão

> **QR:** Que problemas praticantes relatam ao construir pipelines de dados sobre aplicações multi-tenant baseadas em bancos relacionais, e como esses problemas se distribuem entre as estratégias de isolamento e as etapas do ciclo de vida da engenharia de dados?

## 3. Estratégias de isolamento consideradas

| Código | Estratégia | Descrição |
|---|---|---|
| `banco_por_tenant` | Banco de dados por tenant | Cada tenant possui um banco de dados próprio. |
| `esquema_por_tenant` | Esquema por tenant | Tenants compartilham o banco; cada um possui um esquema próprio. |
| `esquema_compartilhado` | Esquema compartilhado | Tenants compartilham banco, esquema e tabelas; o isolamento é feito por coluna identificadora (`tenant_id`). |
| `hibrida` | Híbrida | Combinação explícita de duas ou mais estratégias. |

## 4. Fontes

| Código | Fonte | Acesso |
|---|---|---|
| `github` | Issues e discussions do GitHub (busca global) | API REST (issues) e API GraphQL (discussions) |
| `stackoverflow` | Stack Overflow | API do Stack Exchange (`site=stackoverflow`) |
| `dba` | Database Administrators Stack Exchange | API do Stack Exchange (`site=dba`) |
| `dbt_forum` | Fórum da comunidade dbt (Discourse) | Endpoint público de busca do Discourse |
| `debezium` | Grupo de usuários do Debezium | Busca manual na interface do grupo (alterado pelo desvio D1, seção 13) |

**Justificativa:** as fontes concentram relatos técnicos de praticantes e oferecem mecanismos de busca próprios, o que favorece a reprodutibilidade.

**Fontes desconsideradas:** fóruns generalistas (ex.: Reddit, Hacker News) e mecanismos de busca na web (ex.: Google), por oferecerem menor controle sobre a credibilidade e a reprodutibilidade dos resultados. Canais de chat (ex.: o Zulip do Debezium) também foram desconsiderados, por sua natureza conversacional e fragmentada, que dificulta delimitar relatos e reproduzir as buscas; perguntas sobre Debezium publicadas no Stack Overflow são cobertas pela fonte `stackoverflow`.

**Verificação prévia:** antes da coleta, confirmar se o grupo de usuários do Debezium continua ativo. Caso a comunidade tenha migrado para outro canal, a substituição deve ser registrada como desvio (seção 13).

## 5. Strings de busca

### 5.1 Termos

**Bloco A — estratégia de isolamento**

| Estratégia | Termos |
|---|---|
| `banco_por_tenant` | `"database per tenant"`, `"database-per-tenant"`, `"database per customer"` |
| `esquema_por_tenant` | `"schema per tenant"`, `"schema-per-tenant"`, `"schema per customer"` |
| `esquema_compartilhado` | `"shared schema" tenant`, `"tenant_id"`, `"pool model" tenant` |

**Bloco B — engenharia de dados (comum às três estratégias)**

`ingestion`, `CDC`, `"change data capture"`, `ETL`, `ELT`, `"data warehouse"`, `dbt`, `pipeline`, `connector`

### 5.2 Composição

Cada busca combina **um** termo do Bloco A com **um** termo do Bloco B (9 termos A × 9 termos B = 81 buscas por fonte). O mesmo Bloco B é usado para as três estratégias, garantindo simetria entre elas.

Exemplo: `"schema per tenant" ingestion`

### 5.3 Sintaxe por fonte

| Fonte | Forma da consulta | Filtros |
|---|---|---|
| `github` (issues) | `q=<termo A> <termo B> is:issue` | ordenação por relevância (padrão) |
| `github` (discussions) | `search(query: "<termo A> <termo B>", type: DISCUSSION)` | ordenação por relevância (padrão) |
| `stackoverflow` / `dba` | `/2.3/search/advanced?q=<termo A> <termo B>&site=<site>&sort=relevance&order=desc` | perguntas |
| `dbt_forum` | `/search.json?q=<termo A> <termo B>` | tópicos |
| `debezium` | `<termo A> <termo B>` na caixa de busca do grupo (alterado pelo desvio D1, seção 13) | — |

As strings efetivamente enviadas a cada API são registradas no `dados/log_buscas.csv`.

### 5.4 Critério de parada

Para cada busca, são coletados todos os resultados se houver até 100. Acima disso, são coletados os **100 primeiros por relevância**.

### 5.5 Regras operacionais da coleta

- Cada execução de um script de coleta gera uma pasta própria em `dados/brutos/`, com um arquivo por busca, e uma linha em `dados/execucoes.csv`.
- Para cada fonte, vale a **última execução completa** (todas as buscas sem erro). Execuções incompletas permanecem no repositório, identificadas no `execucoes.csv`, e não entram na triagem.
- Respostas de erro são gravadas como brutos e registradas no log.
- No GitHub, buscas com resultado parcial (`incomplete_results`) são repetidas até três vezes; persistindo, o aviso é registrado.
- A busca de issues do GitHub considera título, corpo e comentários, e sua correspondência de frases entre aspas é menos estrita que a das demais fontes. A busca não foi restringida a título e corpo para não excluir relatos publicados em comentários; o ruído decorrente é tratado na triagem.
- Para discussions do GitHub, o bruto contém os campos solicitados na consulta GraphQL (título, corpo, URL, datas, repositório); o conteúdo completo é lido na fase 2 pela URL.
- No fórum do dbt, `n_resultados` vazio indica que a API não informou o total de tópicos (busca com mais de 100 tópicos ou paginação interrompida); o motivo é registrado nos avisos da busca.
- A busca no grupo do Debezium é manual, registrada em `dados/debezium_manual.csv`, com a página de resultados salva em HTML (alterado pelo desvio D1, seção 13).
- Cada bruto registra o commit do repositório no momento da coleta.

## 6. Critérios de seleção

### 6.1 Inclusão (todos obrigatórios)

| Código | Critério |
|---|---|
| IC1 | Relato de experiência vivenciada (problema, benefício ou ambos), em primeira pessoa ou por mantenedor da ferramenta. |
| IC2 | Aplicação multi-tenant sobre banco de dados relacional. |
| IC3 | Estratégia de isolamento identificável. |
| IC4 | Situação localizada em ao menos uma etapa do ciclo de vida da engenharia de dados. |

### 6.2 Exclusão

| Código | Critério |
|---|---|
| EC1 | Tutorial, guia ou material promocional sem relato de caso. |
| EC2 | Problema restrito à aplicação, sem relação com a engenharia de dados. |
| EC3 | Duplicata (mesmo item encontrado por outra busca ou fonte). |
| EC4 | Idioma diferente de inglês ou português. |
| EC5 | Conteúdo inacessível. |

### 6.3 Processo

1. **Deduplicação:** itens com a mesma URL canônica são unificados antes da triagem. Todas as buscas que encontraram o item são registradas.
2. **Fase 1 (título e trecho):** decisão `incluir`, `excluir` ou `duvida`. Itens em `duvida` seguem para a fase 2.
3. **Fase 2 (leitura completa):** decisão final `incluir` ou `excluir`.
4. Toda exclusão registra o código do critério (EC1–EC5, ou o IC não atendido) e uma justificativa curta.

## 7. Avaliação de credibilidade

Checklist adaptado de Garousi et al. (2019). Cada item recebe `1` (sim) ou `0` (não).

| Código | Critério |
|---|---|
| CR1 | Autoria identificável (perfil, nome ou organização). |
| CR2 | Relato em primeira pessoa ou por mantenedor. |
| CR3 | Detalhes técnicos concretos (versões, números, mensagens de erro, configurações). |
| CR4 | Independência em relação a fornecedores (o autor não vende a solução discutida). |
| CR5 | Presença de contexto ou desfecho (o que foi tentado, o que aconteceu). |

A pontuação (0–5) **não** exclui itens; ela é usada na análise para ponderar o peso das evidências.

## 8. Codebook (extração e codificação)

As categorias iniciais derivam do ciclo de vida da engenharia de dados (Reis e Housley) e das métricas do trabalho. **Categorias novas podem ser criadas quando os dados exigirem**; cada nova categoria é adicionada a este codebook com data e um exemplo, e registrada na seção 13.

### 8.1 `estrategia`
Valores da seção 3.

### 8.2 `etapa` (múltipla)

| Valor | Definição |
|---|---|
| `geracao` | Impacto no sistema de origem (banco da aplicação), ex.: carga da extração sobre o banco. |
| `ingestao` | Captura e movimentação dos dados da origem (conectores, CDC, cargas). |
| `armazenamento` | Organização dos dados no destino (data warehouse, lake). |
| `transformacao` | Modelagem e transformação (ex.: dbt, SQL, união de tenants). |
| `servico` | Consumo dos dados (dashboards, produtos de dados, IA). |

### 8.3 `tipo_problema` (múltipla)

| Valor | Definição |
|---|---|
| `config_manual_novo_tenant` | Cada novo tenant exige configuração manual no pipeline. |
| `multiplicacao_conectores` | Número de conectores, slots de replicação ou jobs cresce com o número de tenants. |
| `multiplicacao_modelos` | Número de modelos de transformação cresce com o número de tenants. |
| `consolidacao_tenants` | Dificuldade em unir dados de vários tenants numa visão única. |
| `desempenho_origem` | A extração degrada o banco de origem. |
| `desempenho_ferramenta` | Ferramentas de dados degradam com o volume de objetos (esquemas, tabelas, catálogo). |
| `evolucao_esquema` | Divergência de estrutura entre tenants (migrações em momentos diferentes, layouts distintos). |
| `governanca_isolamento` | Dificuldade em manter isolamento, rastrear ou excluir dados de um tenant no ambiente analítico. |
| `custo` | Custo financeiro ou operacional explicitamente associado à estratégia. |
| `outro` | Não se encaixa nas categorias acima (descrever em `observacao`). |

### 8.4 `polaridade`

| Valor | Definição |
|---|---|
| `problema` | A estratégia dificultou a engenharia de dados. |
| `beneficio` | A estratégia facilitou a engenharia de dados. |
| `misto` | O relato descreve ambos. |

### 8.5 `metrica_relacionada` (múltipla)

| Valor | Definição |
|---|---|
| `n_conectores` | Número de conectores necessários. |
| `complexidade_pipeline` | Complexidade dos pipelines (DAGs, modelos, macros). |
| `esforco_novo_tenant` | Esforço para incorporar um novo tenant. |
| `nenhuma` | Não se relaciona às métricas do trabalho. |

### 8.6 `motivo_escolha`

`seguranca_isolamento`, `regulatorio`, `desempenho`, `custo`, `customizacao`, `outro`, `nao_informado`

### 8.7 `papel_relator`

`eng_dados`, `eng_analytics`, `dev_aplicacao`, `dba_plataforma`, `mantenedor`, `nao_identificado`

### 8.8 `desfecho`

`resolvido_ferramenta`, `contorno_proprio`, `migracao_arquitetura`, `nao_resolvido`, `nao_informado`

## 9. Validação da codificação

1. Após a codificação completa, uma amostra aleatória de **20%** dos itens incluídos é sorteada com **semente fixa (`42`)**.
2. A amostra é recodificada pelo autor, sem consulta à codificação original.
3. A concordância é calculada por variável (`estrategia`, `etapa`, `tipo_problema`, `polaridade`) com o **kappa de Cohen**.
4. As divergências são discutidas e, se necessário, o codebook é ajustado (registrado na seção 13).

## 10. Arquivamento

Cada item incluído é salvo no Wayback Machine (web.archive.org). A URL original e a URL arquivada são registradas no `dados/extracao.csv`.

## 11. Registros

| Arquivo | Conteúdo |
|---|---|
| `dados/brutos/<fonte>_<AAAAMMDDTHHMMSSZ>/<busca>.json` | Uma pasta por execução (carimbo em UTC) e um arquivo por busca (`issues_A1B1.json` e `discussions_A1B1.json` no GitHub; `A1B1.json` nas demais fontes), com os metadados da busca (`id_busca`, commit, data e hora, parâmetros, avisos) e a resposta completa, inclusive respostas de erro. No Stack Exchange, a pasta também traz `filtro.json`, com a criação do filtro da API. |
| `dados/log_buscas.csv` | `id_busca, data_hora, fonte, termo_a, termo_b, string_enviada, n_resultados, n_coletados` |
| `dados/execucoes.csv` | `id_execucao, fonte, inicio, fim, status, commit, buscas_ok, buscas_erro, avisos`. `status`: `completa` (todas as buscas executadas, nenhuma com erro), `erro` (todas executadas, ao menos uma com erro) ou `incompleta` (execução interrompida antes do fim). |
| `dados/debezium_manual.csv` | Registro das buscas manuais no grupo do Debezium, com o mesmo cabeçalho do `log_buscas.csv`; páginas de resultados salvas em `dados/brutos/debezium_<AAAAMMDD>/` (alterado pelo desvio D1, seção 13). |
| `dados/triagem.csv` | `id_item, url, titulo, fonte, ids_busca, decisao_f1, decisao_f2, criterio_exclusao, justificativa` |
| `dados/extracao.csv` | `id_item, url, url_arquivada, data_relato, data_acesso, fonte, papel_relator, estrategia, etapa, tipo_problema, polaridade, metrica_relacionada, motivo_escolha, desfecho, cr1, cr2, cr3, cr4, cr5, trecho_chave, observacao` |
| `dados/validacao.csv` | Itens da amostra com as duas codificações e o resultado da comparação. |

Um commit é feito ao final de cada fase (coleta, fase 1, fase 2, extração, validação).

## 12. Busca piloto e limitações

**Busca piloto:** antes deste protocolo, uma busca exploratória identificou relatos preliminares. Eles foram usados **exclusivamente** para definir as fontes, as strings e as categorias iniciais do codebook. Os itens da busca piloto **não** são incluídos automaticamente; só entram se forem recuperados pelas buscas deste protocolo.

**Limitações conhecidas:**
- A seleção e a codificação são realizadas por um único pesquisador. Mitigação: codebook explícito, recodificação de amostra e trilha de auditoria pública.
- Relatos de praticantes tendem a super-representar experiências problemáticas. Os resultados indicam a existência e a natureza dos problemas, e não a sua frequência real.
- Os mecanismos de busca das fontes podem mudar, e os itens podem ser editados ou removidos. Mitigação: resultados brutos versionados e itens arquivados.

## 13. Desvios do protocolo

| Data | Seção | Descrição | Justificativa |
|---|---|---|---|
| 2026-11-15 | 4, 5.3, 5.5, 11 | **D1.** A busca no grupo de usuários do Debezium passa de manual para automatizada, por requisições HTTP à página de busca do Google Groups (`/g/debezium/search`), coletando apenas a primeira página de resultados de cada busca (até 30 tópicos), com intervalo de 5 s entre requisições. O HTML bruto de cada busca é gravado em `dados/brutos/debezium_<AAAAMMDDTHHMMSSZ>/`, e o registro segue o mesmo padrão das demais fontes (`log_buscas.csv` e `execucoes.csv`); o `debezium_manual.csv` deixa de ser usado. `n_resultados` fica vazio quando a interface não informa o total, e buscas com indicação de mais resultados recebem aviso. | Reduzir o risco de erro humano em 81 buscas repetitivas e manter o padrão de registro das demais fontes. O `robots.txt` de groups.google.com permite o acesso a `/g/` para agentes genéricos. A paginação depende de JavaScript e de uma rota interna bloqueada pelo `robots.txt`; por isso a coleta se limita à primeira página, critério aplicado igualmente a todas as buscas. |
| 2026-11-15 | 6.3 | **D2.** Esclarecimento operacional da fase 1 da triagem: o "trecho" corresponde aos primeiros 600 caracteres do corpo de cada item, sem HTML, para todas as fontes; itens que geram dúvida quanto a qualquer critério recebem `duvida` e seguem para a fase 2. A deduplicação usa a URL canônica (sem âncoras, parâmetros ou identificadores de mensagem) e considera apenas a última execução completa de cada fonte. | Uniformizar a quantidade de texto avaliada na fase 1, já que as fontes entregam trechos de tamanhos diferentes, e evitar exclusões prematuras. |
| 2026-11-15 | 6.1, 6.2, 7 | **D3.** Esclarecimentos de interpretação definidos após o lote de calibração da fase 1 (100 itens, semente 42): (a) IC1 — especificações, tarefas, ADRs e tickets de planejamento contam como relato apenas quando descrevem uma situação vivenciada que os motiva; textos apenas prospectivos ou comparações hipotéticas não contam; (b) IC2 — o banco relacional exigido é o da aplicação (origem dos dados), um SGBD relacional transacional; o destino analítico pode ser de qualquer tipo; (c) EC2 aplica-se a problemas da aplicação e IC4 a operação e infraestrutura fora das etapas da engenharia de dados; (d) itens aparentemente gerados por agentes de IA não são excluídos por isso, mas recebem marcação na extração e são considerados no critério CR2; (e) exclusões por EC4 registram se o item era tematicamente relevante, para relato da perda. | Uniformizar a aplicação dos critérios diante de ambiguidades observadas na calibração, sem alterar os critérios em si. |
| 2026-11-15 | 6.2, 6.3, 8, 11 | **D4.** Regras definidas ao fim da fase 1 da triagem: (a) ordem de precedência na atribuição do critério de exclusão: EC4 > EC3 > EC1 > IC1 > IC2 > EC2 > IC4, aplicada retroativamente aos lotes iniciais; (b) espelhos de um mesmo item em repositórios distintos são excluídos por EC3; (c) multi-tenancy de ferramentas e plataformas de dados atende IC2 quando o isolamento multi-tenant de uma origem relacional afeta o fluxo de engenharia de dados; não atende quando o tenant apenas organiza usuários ou catálogos da ferramenta; (d) provas de conceito atendem IC1 quando relatam resultados observados; (e) itens em idioma misto são classificados pelo idioma predominante do corpo; (f) a extração inclui as colunas `projeto` (repositório ou comunidade de origem) e `gerado_por_agente` (sim/não/incerto), e a síntese reporta os resultados por item e por projeto. | Uniformizar decisões diante de ambiguidades observadas na fase 1 e permitir controlar a concentração de evidências em um mesmo projeto. |