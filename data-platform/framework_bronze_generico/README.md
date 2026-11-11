# Framework Bronze genérico — BigQuery Sandbox

O script `ingestao_bronze.py` **não contém nomes de tabelas, datasets, arquivos, abas ou colunas fixos**. Cada job é definido em `config.json`.

## Formatos

`xlsx`, `xlsm`, `csv`, `json` (lista de objetos) e `jsonl`/`ndjson`.

Para CSV, configurar `delimiter` e `encoding`; para JSON aninhado, `record_path`; para Excel, `sheet` e `header_row`.

## Execução (Google Cloud SDK Shell, Windows)

```cmd
py -m pip install -r requirements.txt
python ingestao_bronze.py --validar
python ingestao_bronze.py --job partidas
python ingestao_bronze.py --config outro_config.json --validar
```

A opção `--validar` não acessa o GCP. Para carregar, omita `--validar`. `--job` seleciona um job; sem ela, executa todos os jobs configurados.

## Configuração de cada job

- `name`: identificador do job.
- `source`: `path`, `format`, `sheet`/`header_row` (Excel), `delimiter`/`encoding` (CSV), `record_path` (JSON).
- `destination`: `project`, `dataset`, `table`, `location`, `write_disposition` (`WRITE_APPEND`, `WRITE_TRUNCATE`, `WRITE_EMPTY`). Dataset precisa existir previamente.
- `columns`: lista com `source`, `name`, `type`, `mode` (`NULLABLE` ou `REQUIRED`), `trim`, `null_values`, `input_formats` (datas), `excel_serial` (datas numéricas).
- `audit.enabled`: acrescenta `id_execucao`, `arquivo_origem`, `hash_arquivo` e `dt_ingestao`.
- `skip_if_same_file`: consulta a tabela destino e pula arquivo cujo SHA256 já foi ingerido. Para uma tabela preexistente sem `hash_arquivo`, mantenha `false` ou migre a tabela antes.

## Limites e comportamento

- `skip_if_same_file` detecta arquivos *idênticos* por SHA256; arquivos diferentes com registros iguais ainda podem duplicar dados, como é esperado na Bronze histórica.
- As linhas são mantidas em memória: para arquivos muito grandes, implementar carga em lotes/arquivo temporário.
- Não há inferência automática de schema: cada mapeamento é explícito no JSON para previsibilidade.
- A compatibilidade com Python 3.8 é provisória; dependências novas podem deixar de suportá-lo.
- Não usa DML; usa load jobs do BigQuery. Sandbox continua sujeito às suas cotas e restrições.

## Provisionamento

Antes da primeira carga, execute `../sql_setup/01_criar_datasets.sql` no BigQuery Studio e a procedure indicada no README geral. O arquivo `Brasileirao_Dados.xlsx` está presente nesta versão, sujeito à revisão de direitos para publicação.
