# Brasileirão Analytics | Dashboard interativo

Dashboard desenvolvido em **Python e Streamlit**, com cinco páginas: **Monitoramento** (página inicial), Classificação, Mandante x Visitante, Evolução por rodada e Forma recente. Os dados analíticos têm origem nas tabelas Gold do BigQuery e são disponibilizados ao aplicativo público por meio de snapshots CSV.

- **Aplicativo público:** https://brasileirao-data-analytics.streamlit.app/
- **Código-fonte:** https://github.com/fermiola/brasileirao-analytics/tree/main/dashboard

## Arquitetura e responsabilidades

O processamento de dados e a execução do dashboard são **independentes**:

```text
PIPELINE DE DADOS (executado separadamente)
Bronze -> Silver -> Gold -> Data Quality
                 |
                 v
      BigQuery: Gold e ds_control
                 |
                 | exportações locais, quando necessário
                 v
DASHBOARD (processo independente)
  exportar_gold.py          -> data/tb_*.csv
  exportar_monitoramento.py -> data/monitoramento.json
                 |
                 v
          Streamlit (app.py)
```

O `orquestrador_dashboard.py` **não executa Bronze, Silver, Gold nem Data Quality**. Ele apenas exporta os metadados de monitoramento do BigQuery e inicia o Streamlit **localmente**. A exportação dos CSVs Gold é um processo separado, executado quando os dados analíticos precisam ser atualizados.

## Estrutura do diretório

```text
dashboard/
├── app.py
├── config.json
├── exportar_gold.py
├── exportar_monitoramento.py
├── orquestrador_dashboard.py
├── requirements.txt
├── data/
│   ├── monitoramento.json
│   ├── tb_classificacao.csv
│   ├── tb_desempenho_clube.csv
│   ├── tb_estatisticas_rodada.csv
│   └── tb_forma_recente.csv
└── README.md
```

Os arquivos em `data/` são snapshots exportados localmente e podem ser publicados no GitHub após revisão.

## Preparação do ambiente local (Windows)

Abra o terminal na pasta `dashboard/`:

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
```

Se já tiver um ambiente virtual configurado e ativado, não é necessário criá-lo novamente. Verifique se `requirements.txt` contém as dependências utilizadas pelo aplicativo e pelo exportador, incluindo `streamlit`, `pandas`, `plotly` e **`google-cloud-bigquery`**. Se esta última estiver ausente, adicione-a ao arquivo e reinstale as dependências.

Para exportar o monitoramento, é necessário ter acesso ao projeto GCP e credenciais locais válidas. Se necessário:

```cmd
gcloud auth application-default login
```

A autenticação de `gcloud` e as credenciais de aplicação (ADC) são mecanismos distintos. Não inclua credenciais no repositório.

## Iniciar o dashboard com o orquestrador

Na pasta `dashboard/`, com o ambiente virtual ativo:

```cmd
python orquestrador_dashboard.py
```

A execução é sequencial:

1. `python exportar_monitoramento.py` — consulta `ds_control.tb_execucoes_pipeline` e `ds_control.tb_data_quality` e gera `data/monitoramento.json`.
2. `python -m streamlit run app.py` — inicia o aplicativo local, normalmente em http://localhost:8501.

**Se a exportação falhar, o orquestrador não inicia o Streamlit.** O comando não atualiza os CSVs Gold, não executa o pipeline de dados e não publica alterações no GitHub.

Para iniciar apenas o aplicativo, sem consultar o BigQuery:

```cmd
python -m streamlit run app.py
```

Nesse caso, a página Monitoramento exibe o último JSON disponível localmente, que pode estar desatualizado.

## Atualizar os snapshots Gold

Após uma execução bem-sucedida do pipeline de dados, quando houver alterações nos dados analíticos:

```cmd
python exportar_gold.py
```

Esse comando exporta as tabelas Gold para os CSVs em `data/`. Ele é **separado** do orquestrador do dashboard. Revise os arquivos antes de publicá-los.

## Página Monitoramento

A página inicial apresenta:

- Status da última execução registrada do pipeline;
- Data e hora da execução no fuso de Brasília;
- Quantidade de verificações de Data Quality aprovadas e reprovadas no último lote identificado;
- Histórico de execuções por etapa e verificações recentes, incluindo violações.

Os dados vêm de `data/monitoramento.json`, exportado das tabelas de controle do BigQuery. **Não é monitoramento em tempo real**: o status corresponde ao último arquivo JSON gerado e publicado. O botão **Atualizar dados** recarrega os arquivos disponíveis, mas não executa o pipeline, não consulta o BigQuery e não atualiza o repositório.

A data de exportação do monitoramento **não é** a data de publicação dos CSVs Gold. Para exibir esta última com precisão, seria necessário registrar metadados próprios da exportação dos CSVs.

## Modos de dados

O `config.json` define o modo de leitura:

- `"data_mode": "csv"`: lê os snapshots em `data/`, sem consultar BigQuery durante a navegação pública.
- `"data_mode": "bigquery"`: consulta as tabelas Gold diretamente, exigindo credenciais e permissões apropriadas.

A variável de ambiente `DATA_MODE` pode sobrescrever o modo configurado. Para a implantação pública, recomenda-se **CSV**, evitando consultas ao BigQuery por visitante. O cache de dados do aplicativo é configurável por `cache_ttl_seconds` (por padrão, 3600 segundos).

## Publicar atualizações no dashboard público

O aplicativo público usa o repositório `fermiola/brasileirao-analytics`, branch `main`, com entrada em `dashboard/app.py`.

1. Execute localmente os exportadores necessários (`exportar_gold.py` para CSVs, `exportar_monitoramento.py` para o JSON).
2. Confira os arquivos gerados e verifique se não contêm dados sensíveis.
3. Atualize no GitHub os arquivos modificados em `dashboard/`, incluindo código, CSVs e `data/monitoramento.json`.
4. Faça commit/push para a branch usada no Streamlit Community Cloud.
5. Aguarde a atualização da implantação e confira https://brasileirao-data-analytics.streamlit.app/.

**Executar `python orquestrador_dashboard.py` não atualiza o endereço público automaticamente.** O Streamlit Community Cloud lê os arquivos versionados no GitHub; não deve executar o exportador de monitoramento na inicialização do aplicativo público.

## Segurança e custos

- Nunca publique `.venv/`, `.env`, chaves JSON de contas de serviço, tokens ou credenciais.
- Os arquivos CSV e JSON enviados ao repositório público ficam acessíveis a terceiros; revise-os antes do commit.
- A navegação pública no modo CSV não consulta BigQuery. **Os exportadores locais consultam BigQuery** e podem gerar custos conforme uso e limites do projeto.
- Evite expor mensagens internas de erro ou informações sensíveis nos snapshots de monitoramento.

## Solução de problemas

**`ModuleNotFoundError: No module named 'google.cloud'`**: confirme que o ambiente virtual correto está ativado e que `google-cloud-bigquery` está instalado nele. Verifique com `python -m pip show google-cloud-bigquery` e corrija o `requirements.txt` para futuras instalações.

**Erro de autenticação no exportador**: configure credenciais ADC com `gcloud auth application-default login` e confira as permissões de leitura das tabelas de controle.

**O dashboard abriu apenas em `localhost:8501`**: isso é esperado. A versão pública é atualizada via commit/push no GitHub e implantação no Streamlit Community Cloud.

**Monitoramento antigo no site público**: confirme que `dashboard/data/monitoramento.json` foi atualizado e enviado ao GitHub. Recarregar a página não cria um novo snapshot.
