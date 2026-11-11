# Framework Gold v2 — indicadores analíticos

Transforma a tabela tipada `ds_silver.tb_partidas` em quatro tabelas analíticas do BigQuery, com execução de SQL versionado e estratégia `REPLACE_ATOMIC` (`CREATE OR REPLACE TABLE`).

| Job | SQL | Destino |
|---|---|---|
| `classificacao` | `sql/classificacao.sql` | `ds_gold.tb_classificacao` |
| `desempenho_clube` | `sql/desempenho_clube.sql` | `ds_gold.tb_desempenho_clube` |
| `estatisticas_rodada` | `sql/estatisticas_rodada.sql` | `ds_gold.tb_estatisticas_rodada` |
| `forma_recente` | `sql/forma_recente.sql` | `ds_gold.tb_forma_recente` |

`forma_recente` depende de `estatisticas_rodada`, conforme `config.json`.

## Execução

```cmd
python orquestrador_gold.py --validar
python orquestrador_gold.py --all
python orquestrador_gold.py --job classificacao
```

Antes da execução real, crie `ds_gold` com `../sql_setup/01_criar_datasets.sql` e tenha a Silver populada. O modo `--validar` não acessa o GCP. `--all` consulta e grava no BigQuery e pode gerar custos.

## Observações

- Apenas partidas finalizadas e com placares válidos entram nos cálculos relevantes.
- Critérios de desempate da classificação são estatísticos e podem não reproduzir todos os critérios oficiais.
- `CREATE OR REPLACE TABLE` substitui o destino; não preserva propriedades customizadas preexistentes.
- SQLs devem ser revisados e versionados como código confiável.
- Auditoria persistente do pipeline é feita pelo Orquestrador Geral; Data Quality valida os resultados após a Gold.
