# Brasileirão Analytics | Plataforma de Dados e Dashboard

[![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![BigQuery](https://img.shields.io/badge/Google_Cloud-BigQuery-4285F4?logo=googlecloud&logoColor=white)](https://cloud.google.com/bigquery)
[![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)

**Projeto de Engenharia de Dados e Analytics aplicado ao Campeonato Brasileiro**, integrando ingestão e tratamento de dados com Python, modelagem analítica no Google BigQuery, verificações de qualidade e visualização interativa no Streamlit.

**[Acessar o dashboard](https://brasileirao-data-analytics.streamlit.app/)** · **[Explorar o repositório](https://github.com/fermiola/brasileirao-analytics)** · **[Documentação técnica da plataforma](data-platform/README.md)**

> O dashboard público utiliza snapshots CSV gerados a partir da camada Gold. Assim, a navegação dos visitantes não exige consultas ao BigQuery.

## Visão geral

A solução separa o processamento dos dados da camada de apresentação. Os frameworks de engenharia de dados ficam em `data-platform/`; o aplicativo Streamlit apresenta os indicadores ao usuário final.

### Arquitetura

```mermaid
flowchart TD
    A[Planilha Excel de partidas] --> B[Python: Framework Bronze]
    B --> C[(BigQuery: ds_bronze)]
    C --> D[Python + SQL: Framework Silver]
    D --> E[(BigQuery: ds_silver)]
    E --> F[Python + SQL: Framework Gold]
    F --> G[(BigQuery: ds_gold)]
    G --> H[Exportação de snapshots CSV]
    H --> I[Dashboard Streamlit]
    J[Orquestrador Geral] -. coordena .-> B
    J -. coordena .-> D
    J -. coordena .-> F
    J -. executa .-> K[Framework Data Quality]
    K -. verifica .-> E
    K -. verifica .-> G
    J -. registra execução .-> L[(BigQuery: ds_control)]
    K -. registra auditoria .-> L
```

### Camadas da plataforma

| Componente | Responsabilidade |
| --- | --- |
| **Bronze** | Ingestão dos dados de origem e controle de reprocessamento de arquivos idênticos |
| **Silver** | Padronização, tipagem e consolidação das partidas, com lógica de `MERGE` |
| **Gold** | Geração das tabelas analíticas utilizadas nos indicadores |
| **Data Quality** | Execução de regras de qualidade e registro dos resultados de auditoria |
| **Orquestrador Geral** | Execução sequencial dos frameworks e registro de status das etapas |
| **Streamlit** | Exploração visual dos dados analíticos |

## Dashboard interativo

O aplicativo disponibiliza quatro visões:

1. **Classificação:** acompanhamento da tabela do campeonato.
2. **Mandante x Visitante:** comparação do desempenho dos clubes em casa e fora.
3. **Evolução por rodada:** análise da trajetória dos indicadores ao longo do campeonato.
4. **Forma recente:** visualização do desempenho nas partidas mais recentes.

**Dashboard:** https://brasileirao-data-analytics.streamlit.app/

## Modelo analítico no BigQuery

A camada Gold disponibiliza quatro tabelas:

| Tabela | Conteúdo |
| --- | --- |
| `ds_gold.tb_classificacao` | Classificação dos clubes |
| `ds_gold.tb_desempenho_clube` | Indicadores por clube e condição de mando |
| `ds_gold.tb_estatisticas_rodada` | Indicadores organizados por rodada |
| `ds_gold.tb_forma_recente` | Forma recente dos clubes |

Os datasets de controle e auditoria ficam em `ds_control`. O processamento é realizado no projeto GCP configurado para a plataforma; para executar em outro ambiente, revise os arquivos de configuração.

## Estrutura do repositório

```text
brasileirao-analytics/
├── dashboard/
│   ├── app.py                   # Aplicação Streamlit
│   ├── config.json              # Configuração de leitura
│   ├── exportar_gold.py         # Exportação local da Gold
│   ├── requirements.txt         # Dependências do dashboard
│   ├── data/                    # Quatro snapshots CSV
│   └── README.md                # Guia do dashboard
├── data-platform/
│   ├── README.md                # Guia técnico da plataforma
│   ├── requirements.txt         # Dependências consolidadas
│   ├── framework_bronze_generico/
│   ├── framework_silver/
│   ├── framework_gold/
│   ├── framework_data_quality/
│   ├── Orquestrador_Geral/
│   └── sql_setup/
├── .gitignore
└── README.md                    # Visão geral do projeto
```

## Como executar o dashboard localmente

Acesse a pasta `dashboard/`, onde estão o `app.py`, as dependências e os CSVs. Para usar o modo CSV, não é necessário autenticar no Google Cloud.

```powershell
cd dashboard
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Se usar Google Cloud SDK Shell ou outro terminal com ambiente virtual já ativado, não precisa criar outro. Em `dashboard/config.json`, `"data_mode": "csv"` utiliza os snapshots locais. Consulte o [guia do dashboard](dashboard/README.md) para exportação e modo BigQuery.

**Aplicativo publicado:** [Brasileirão Data Analytics](https://brasileirao-data-analytics.streamlit.app/) — arquivo principal `dashboard/app.py` na branch `main`.

## Como executar a plataforma de dados

Para reproduzir o pipeline, são necessários um projeto Google Cloud com BigQuery habilitado, permissões apropriadas, autenticação local e configurações ajustadas ao ambiente.

```powershell
cd data-platform
python -m pip install -r requirements.txt
cd Orquestrador_Geral
python orquestrador_pipeline.py --validar
```

O comando `--validar` verifica a configuração local sem executar o pipeline no GCP. Para processamento real, consulte primeiro o [guia técnico da plataforma](data-platform/README.md), incluindo provisionamento dos datasets, autenticação e custos. A execução completa utiliza `--all`.

## Atualização dos dados

O dashboard publicado consome snapshots CSV. Após atualizar a camada Gold:

1. Na pasta `dashboard/`, execute localmente `python exportar_gold.py` com autenticação e permissões BigQuery configuradas.
2. Revise os CSVs gerados em `dashboard/data/` e verifique se podem ser publicados.
3. Atualize os arquivos no GitHub para refletir os novos dados no aplicativo.

**Importante:** o modo CSV evita consultas ao BigQuery durante o acesso público, mas a execução do pipeline e a exportação local podem consumir recursos cobrados do Google Cloud.

## Qualidade, rastreabilidade e boas práticas

- Separação das responsabilidades de ingestão, tratamento, modelagem e apresentação.
- Regras de qualidade para chaves, campos obrigatórios, status, placares e disponibilidade das tabelas Gold.
- Registro de execuções e auditorias no dataset de controle.
- Configurações externalizadas em arquivos JSON.
- Proteção contra reingestão desnecessária de arquivos idênticos na Bronze.
- Execução do pipeline desacoplada do acesso público ao dashboard.

## Segurança e publicação

Não publique `.venv/`, chaves de serviço, tokens, credenciais ou arquivos `.env`. Revise os JSONs antes de enviá-los. Os CSVs da pasta `dashboard/data/` e quaisquer planilhas incluídas no repositório tornam-se acessíveis publicamente. O `.gitignore` não impede o envio manual de arquivos pela interface do GitHub.

## Documentação

O [guia do dashboard](dashboard/README.md) detalha a aplicação Streamlit. A documentação operacional completa — instalação do Google Cloud CLI/SDK Shell, autenticação, configurações, scripts SQL, execução e validações — está em **[data-platform/README.md](data-platform/README.md)**.

---

*Projeto de portfólio para demonstrar práticas de Engenharia de Dados, Analytics e desenvolvimento Python aplicadas a dados de futebol.*
