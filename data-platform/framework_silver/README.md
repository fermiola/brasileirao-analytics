# Framework Silver v2 — Bronze STRING -> Silver tipada

## Implantação
1. Execute `sql/01_create_control_dataset.sql` no BigQuery Studio.
2. Execute `sql/02_sp_merge_generico.sql` para substituir a procedure da v1. **Assinatura alterada:** `p_colunas_json` substitui `p_colunas`.
3. Revise `config.json`, especialmente o formato da coluna `data` na Bronze e o schema existente da Silver.
4. No diretório do projeto: `py orquestrador_silver.py --validar`.
5. Execute `py orquestrador_silver.py --job partidas_silver`.

## Regras
- Bronze: colunas de negócio STRING, `dt_ingestao` TIMESTAMP.
- Silver: tipos definidos em `columns` no JSON, com `source` opcional para renomear colunas.
- `required: true` exige valor não nulo; todas as chaves precisam ser obrigatórias.
- Conversões não vazias inválidas abortam a execução **antes** da criação/alteração da Silver.
- `format` opcional para DATE, DATETIME, TIMESTAMP, TIME. Sem `format`, utiliza SAFE_CAST.
- Tabela Silver inexistente é criada com os tipos configurados.
- Tabela Silver já existente com tipos diferentes é rejeitada pelo Python; **não é recriada nem alterada**.
- A procedure usa MERGE com a última `order_by` por chave. Empates de ordenação ainda exigem uma coluna adicional única para resultado determinístico.
- `EXCEPTION WHEN ERROR THEN ... RAISE` propaga falhas ao Python.
- Não há ainda log persistente em ds_control nem política de quarentena; falhas interrompem o job.

## Observação de compatibilidade
O código usa apenas sintaxe Python 3.8+, mas as dependências instaladas devem ser compatíveis com seu interpretador.
