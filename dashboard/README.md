# Brasileirão Analytics | Dashboard interativo

Dashboard Streamlit com quatro páginas: Classificação, Mandante x Visitante, Evolução por rodada e Forma recente. Fonte original: BigQuery Gold.

## Preparar a publicação (no seu Windows)

1. Extraia este ZIP para uma nova pasta. **Não substitua o projeto local que já funciona.**
2. Abra o Google Cloud SDK Shell na pasta extraída, com seu ambiente Python 3.13 ativado.
3. Instale as dependências: `python -m pip install -r requirements.txt`.
4. Autentique localmente: `gcloud auth application-default login` (caso necessário).
5. Exporte as quatro tabelas: `python exportar_gold.py`.
6. Confirme que `data/` contém quatro CSVs, com dados corretos e próprios para divulgação.
7. Teste a aplicação: `python -m streamlit run app.py`.
8. No repositório existente `brasileirao-analytics`, publique a pasta `dashboard/` contendo `app.py`, `config.json`, `requirements.txt`, `README.md`, `.gitignore` e a pasta `data/` com os CSVs. **Não envie `.venv`, tokens ou credenciais.**
9. No Streamlit Community Cloud, edite as configurações do aplicativo existente e altere o caminho do arquivo principal de `app.py` para `dashboard/app.py`. Confirme que a implantação terminou antes de remover os arquivos antigos da raiz.
10. Compartilhe a URL do app no LinkedIn.

## Modos de dados

- `config.json` com `"data_mode": "csv"`: lê `data/tb_*.csv` e não consulta GCP em acessos públicos.
- `"data_mode": "bigquery"`: consulta BigQuery usando credenciais disponíveis no ambiente (adequado para uso local).
- Pode sobrescrever com variável de ambiente `DATA_MODE=bigquery` ou `DATA_MODE=csv`.

## Atualização

Quando atualizar a Gold, execute novamente `python exportar_gold.py` localmente, revise os CSVs e faça commit/push das atualizações para o GitHub. O dashboard público passa a ler o novo snapshot após a atualização/reinicialização do app.

## Segurança e custos

Não inclua chaves de serviço nem tokens no GitHub. O modo CSV não realiza consultas BigQuery no servidor público. A exportação local **realiza consultas BigQuery**, que podem ter cobrança conforme seu plano e limites. Os CSVs serão públicos no repositório: revise antes de publicar. Hospedagem gratuita depende das condições do provedor.

## Organização no repositório

Este diretório deve ficar em `brasileirao-analytics/dashboard/`. Os CSVs ficam em `dashboard/data/`; `app.py` e `exportar_gold.py` usam caminhos relativos e não exigem mudança de código. Execute os comandos a partir da pasta `dashboard/`.
