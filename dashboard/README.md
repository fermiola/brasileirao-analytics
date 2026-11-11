# Brasileirão Analytics | Dashboard interativo

Dashboard Streamlit com quatro páginas: Classificação, Mandante x Visitante, Evolução por rodada e Forma recente. Fonte original: BigQuery Gold.

**Aplicativo público:** https://brasileirao-data-analytics.streamlit.app/  
**Código-fonte:** https://github.com/fermiola/brasileirao-analytics/tree/main/dashboard

## Estrutura do dashboard

```text
dashboard/
├── app.py
├── config.json
├── exportar_gold.py
├── requirements.txt
├── data/
│   ├── tb_classificacao.csv
│   ├── tb_desempenho_clube.csv
│   ├── tb_estatisticas_rodada.csv
│   └── tb_forma_recente.csv
└── README.md
```

## Executar localmente (Windows)

Abra um terminal na pasta `dashboard/` e execute:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Se já tiver um ambiente virtual ativado, use-o em vez de criar outro. No modo CSV, não é necessária autenticação no Google Cloud.

## Implantação no Streamlit Community Cloud

O aplicativo definitivo utiliza o repositório `fermiola/brasileirao-analytics`, branch `main` e arquivo principal `dashboard/app.py`. O endereço público é https://brasileirao-data-analytics.streamlit.app/.

A aplicação lê os snapshots de `dashboard/data/`. Não é necessário executar `exportar_gold.py` no Streamlit Cloud. Não publique credenciais ou arquivos `.env`.

## Modos de dados

- `config.json` com `"data_mode": "csv"`: lê `data/tb_*.csv` e não consulta GCP em acessos públicos.
- `"data_mode": "bigquery"`: consulta BigQuery usando credenciais disponíveis no ambiente (adequado para uso local).
- Pode sobrescrever com variável de ambiente `DATA_MODE=bigquery` ou `DATA_MODE=csv`.

## Atualização

Quando atualizar a Gold, entre na pasta `dashboard/`, autentique-se localmente no GCP se necessário (`gcloud auth application-default login`) e execute `python exportar_gold.py`, revise os CSVs e faça commit/push das atualizações para o GitHub. O dashboard público passa a ler o novo snapshot após o próximo carregamento dos dados ou a expiração do cache (configurado em 3600 segundos).

## Segurança e custos

Não inclua chaves de serviço nem tokens no GitHub. O modo CSV não realiza consultas BigQuery no servidor público. A exportação local **realiza consultas BigQuery**, que podem ter cobrança conforme seu plano e limites. Os CSVs serão públicos no repositório: revise antes de publicar. Hospedagem gratuita depende das condições do provedor.

## Organização no repositório

Este diretório fica em `brasileirao-analytics/dashboard/`. Os CSVs ficam em `dashboard/data/`; `app.py` e `exportar_gold.py` usam caminhos relativos e não exigem mudança de código. Execute os comandos a partir da pasta `dashboard/`.
