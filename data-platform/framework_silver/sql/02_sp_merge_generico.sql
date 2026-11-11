-- Framework Silver: MERGE generico com tipagem, deduplicacao e auditoria.
-- A procedure recebe a configuracao das colunas via JSON do orquestrador Python.
-- A coluna tecnica dt_atualizacao_silver e gerenciada exclusivamente aqui.
CREATE OR REPLACE PROCEDURE `brasileirao-data-platform.ds_control.sp_merge_generico`(
  p_source STRING,
  p_target STRING,
  p_keys ARRAY<STRING>,
  p_columns_json STRING,
  p_order_by STRING
)
BEGIN

/*
Framework Silver: procedure generica de tipagem, validacao, deduplicacao e MERGE.
Compatibilidade: CALL sp_merge_generico(source, target, keys, columns_json, order_by).
Nao executa DELETE e nao altera particionamento/clustering de tabelas existentes.
*/

  DECLARE v_cols ARRAY<STRUCT<name STRING, src STRING, typ STRING, fmt STRING, required BOOL>>;
  DECLARE v_source_cols ARRAY<STRING>;
  DECLARE v_target_cols ARRAY<STRUCT<name STRING, typ STRING>>;
  DECLARE v_create_cols STRING DEFAULT '';
  DECLARE v_select_cols STRING DEFAULT '';
  DECLARE v_invalid_predicate STRING DEFAULT '';
  DECLARE v_key_predicate STRING;
  DECLARE v_update_set STRING DEFAULT '';
  DECLARE v_change_predicate STRING DEFAULT '';
  DECLARE v_insert_cols STRING DEFAULT '';
  DECLARE v_insert_vals STRING DEFAULT '';
  DECLARE v_sql STRING;
  DECLARE v_invalid_count INT64 DEFAULT 0;
  DECLARE v_exists_count INT64 DEFAULT 0;
  DECLARE v_src_project STRING;
  DECLARE v_src_dataset STRING;
  DECLARE v_src_table STRING;
  DECLARE v_tgt_project STRING;
  DECLARE v_tgt_dataset STRING;
  DECLARE v_tgt_table STRING;
  DECLARE v_expr STRING;
  DECLARE v_raw STRING;
  DECLARE v_trimmed STRING;
  DECLARE v_type STRING;
  DECLARE v_fmt STRING;
  DECLARE v_name STRING;
  DECLARE v_src STRING;
  DECLARE v_required BOOL;
  DECLARE v_bad_schema_count INT64 DEFAULT 0;

  -- 1. Validar nomes de objetos e parametros obrigatorios.
  ASSERT REGEXP_CONTAINS(p_source, r'^[A-Za-z0-9_-]+\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$') AS 'Origem invalida';
  ASSERT REGEXP_CONTAINS(p_target, r'^[A-Za-z0-9_-]+\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$') AS 'Destino invalido';
  ASSERT p_source != p_target AS 'Origem e destino nao podem ser iguais';
  ASSERT p_keys IS NOT NULL AND ARRAY_LENGTH(p_keys) > 0 AS 'Chaves obrigatorias';
  ASSERT JSON_TYPE(SAFE.PARSE_JSON(p_columns_json)) = 'array' AS 'columns_json deve ser array JSON';

  SET v_src_project = SPLIT(p_source, '.')[OFFSET(0)];
  SET v_src_dataset = SPLIT(p_source, '.')[OFFSET(1)];
  SET v_src_table = SPLIT(p_source, '.')[OFFSET(2)];
  SET v_tgt_project = SPLIT(p_target, '.')[OFFSET(0)];
  SET v_tgt_dataset = SPLIT(p_target, '.')[OFFSET(1)];
  SET v_tgt_table = SPLIT(p_target, '.')[OFFSET(2)];

  -- 2. Ler mapeamentos e tipos configurados pelo Python.
  SET v_cols = ARRAY(
    SELECT AS STRUCT
      JSON_VALUE(item, '$.name') AS name,
      COALESCE(JSON_VALUE(item, '$.source'), JSON_VALUE(item, '$.name')) AS src,
      UPPER(JSON_VALUE(item, '$.type')) AS typ,
      JSON_VALUE(item, '$.format') AS fmt,
      COALESCE(SAFE_CAST(JSON_VALUE(item, '$.required') AS BOOL), FALSE) AS required
    FROM UNNEST(JSON_QUERY_ARRAY(p_columns_json, '$')) AS item
  );
  ASSERT ARRAY_LENGTH(v_cols) > 0 AS 'Nenhuma coluna configurada';
  ASSERT (SELECT COUNT(*) = COUNT(DISTINCT name) FROM UNNEST(v_cols)) AS 'Colunas duplicadas';
  ASSERT (SELECT LOGICAL_AND(
    name IS NOT NULL AND src IS NOT NULL AND typ IS NOT NULL
    AND REGEXP_CONTAINS(name, r'^[A-Za-z_][A-Za-z0-9_]*$')
    AND REGEXP_CONTAINS(src, r'^[A-Za-z_][A-Za-z0-9_]*$')
    AND typ IN ('STRING','INT64','FLOAT64','NUMERIC','BIGNUMERIC','BOOL','DATE','DATETIME','TIMESTAMP','TIME','BYTES','JSON')
    AND (fmt IS NULL OR (NOT REGEXP_CONTAINS(fmt, r"['\\]") AND typ IN ('DATE','DATETIME','TIMESTAMP','TIME')))
    AND name != 'dt_atualizacao_silver'
  ) FROM UNNEST(v_cols)) AS 'Coluna, tipo ou formato invalido';
  ASSERT (SELECT COUNT(*) = COUNT(DISTINCT k) FROM UNNEST(p_keys) AS k) AS 'Chaves duplicadas';
  ASSERT (SELECT LOGICAL_AND(k IN (SELECT name FROM UNNEST(v_cols))) FROM UNNEST(p_keys) AS k) AS 'Chave ausente nas colunas';
  ASSERT (SELECT LOGICAL_AND(required) FROM UNNEST(v_cols) WHERE name IN UNNEST(p_keys)) AS 'Chaves devem ser required=true';
  ASSERT p_order_by IN (SELECT name FROM UNNEST(v_cols)) AS 'order_by nao encontrado';

  -- 3. Confirmar a existencia das colunas na Bronze.
  EXECUTE IMMEDIATE FORMAT(
    'SELECT ARRAY_AGG(column_name) FROM `%s.%s.INFORMATION_SCHEMA.COLUMNS` WHERE table_name = @t',
    v_src_project, v_src_dataset
  ) INTO v_source_cols USING v_src_table AS t;
  ASSERT v_source_cols IS NOT NULL AS 'Tabela Bronze inexistente';
  ASSERT (SELECT LOGICAL_AND(src IN UNNEST(v_source_cols)) FROM UNNEST(v_cols)) AS 'Colunas ausentes na Bronze';

  -- 4. Montar conversoes, verificacoes de qualidade e campos do MERGE.
  FOR c IN (SELECT * FROM UNNEST(v_cols)) DO
    SET v_name = c.name;
    SET v_src = c.src;
    SET v_type = c.typ;
    SET v_fmt = c.fmt;
    SET v_required = c.required;
    SET v_raw = FORMAT('B.`%s`', v_src);
    SET v_trimmed = FORMAT("NULLIF(TRIM(CAST(%s AS STRING)), '')", v_raw);

    IF v_type = 'STRING' THEN
      SET v_expr = FORMAT('CAST(%s AS STRING)', v_raw);
    ELSEIF v_type = 'DATE' AND v_fmt IS NOT NULL THEN
      -- Ex.: "2026-01-28 00:00:00" vira DATE "2026-01-28".
      IF v_fmt = '%Y-%m-%d' THEN
        SET v_expr = FORMAT("SAFE.PARSE_DATE('%%Y-%%m-%%d', SUBSTR(%s, 1, 10))", v_trimmed);
      ELSE
        SET v_expr = FORMAT("SAFE.PARSE_DATE('%s', %s)", v_fmt, v_trimmed);
      END IF;
    ELSEIF v_type = 'DATETIME' AND v_fmt IS NOT NULL THEN
      SET v_expr = FORMAT("SAFE.PARSE_DATETIME('%s', %s)", v_fmt, v_trimmed);
    ELSEIF v_type = 'TIMESTAMP' AND v_fmt IS NOT NULL THEN
      SET v_expr = FORMAT("SAFE.PARSE_TIMESTAMP('%s', %s)", v_fmt, v_trimmed);
    ELSEIF v_type = 'TIME' AND v_fmt IS NOT NULL THEN
      SET v_expr = FORMAT("SAFE.PARSE_TIME('%s', %s)", v_fmt, v_trimmed);
    ELSE
      SET v_expr = FORMAT('SAFE_CAST(%s AS %s)', v_raw, v_type);
    END IF;

    SET v_create_cols = CONCAT(v_create_cols, IF(v_create_cols = '', '', ', '), FORMAT('`%s` %s', v_name, v_type));
    SET v_select_cols = CONCAT(v_select_cols, IF(v_select_cols = '', '', ', '), FORMAT('%s AS `%s`', v_expr, v_name));

    -- Rejeitar valores nao vazios que falham na conversao.
    -- Campos required tambem nao podem ficar nulos depois da conversao.
    SET v_invalid_predicate = CONCAT(
      v_invalid_predicate, IF(v_invalid_predicate = '', '', ' OR '),
      FORMAT('((%s IS NOT NULL AND %s IS NULL)%s)',
        v_trimmed, v_expr,
        IF(v_required, FORMAT(' OR %s IS NULL', v_expr), '')
      )
    );

    SET v_insert_cols = CONCAT(v_insert_cols, IF(v_insert_cols = '', '', ', '), FORMAT('`%s`', v_name));
    SET v_insert_vals = CONCAT(v_insert_vals, IF(v_insert_vals = '', '', ', '), FORMAT('S.`%s`', v_name));

    -- Comparar valores, inclusive NULL, para nao atualizar linhas inalteradas.
    IF v_name NOT IN UNNEST(p_keys) THEN
      SET v_update_set = CONCAT(v_update_set, IF(v_update_set = '', '', ', '), FORMAT('T.`%s` = S.`%s`', v_name, v_name));
      SET v_change_predicate = CONCAT(v_change_predicate, IF(v_change_predicate = '', '', ' OR '), FORMAT('T.`%s` IS DISTINCT FROM S.`%s`', v_name, v_name));
    END IF;
  END FOR;

  -- 5. Falhar antes do MERGE caso existam dados invalidos.
  SET v_sql = FORMAT('SELECT COUNT(*) FROM `%s` B WHERE %s', p_source, v_invalid_predicate);
  EXECUTE IMMEDIATE v_sql INTO v_invalid_count;
  ASSERT v_invalid_count = 0 AS 'Valores invalidos ou campos obrigatorios nulos na Bronze';

  -- 6. Criar a Silver caso ainda nao exista, com coluna tecnica de atualizacao.
  EXECUTE IMMEDIATE FORMAT(
    'SELECT COUNT(*) FROM `%s.%s.INFORMATION_SCHEMA.TABLES` WHERE table_name = @t',
    v_tgt_project, v_tgt_dataset
  ) INTO v_exists_count USING v_tgt_table AS t;
  IF v_exists_count = 0 THEN
    EXECUTE IMMEDIATE FORMAT(
      'CREATE TABLE `%s` (%s, `dt_atualizacao_silver` TIMESTAMP)',
      p_target, v_create_cols
    );
  END IF;

  -- 7. Validar schema do destino; aceitar aliases INTEGER/INT64 etc.
  EXECUTE IMMEDIATE FORMAT(
    'SELECT ARRAY_AGG(STRUCT(column_name AS name, data_type AS typ)) FROM `%s.%s.INFORMATION_SCHEMA.COLUMNS` WHERE table_name = @t',
    v_tgt_project, v_tgt_dataset
  ) INTO v_target_cols USING v_tgt_table AS t;
  SET v_bad_schema_count = (
    SELECT COUNT(*)
    FROM UNNEST(v_cols) AS c
    LEFT JOIN UNNEST(v_target_cols) AS t ON c.name = t.name
    WHERE t.name IS NULL OR
      (CASE t.typ WHEN 'INTEGER' THEN 'INT64' WHEN 'FLOAT' THEN 'FLOAT64' WHEN 'BOOLEAN' THEN 'BOOL' ELSE t.typ END) != c.typ
  );
  ASSERT v_bad_schema_count = 0 AS 'Schema da Silver incompativel com JSON';
  ASSERT EXISTS (
    SELECT 1 FROM UNNEST(v_target_cols)
    WHERE name = 'dt_atualizacao_silver' AND typ = 'TIMESTAMP'
  ) AS 'Coluna dt_atualizacao_silver TIMESTAMP ausente na Silver';

  -- 8. Executar MERGE deduplicando a origem por chave de negocio.
  -- Metadados de origem sao comparados como outras colunas nao-chave.
  SET v_key_predicate = (
    SELECT STRING_AGG(FORMAT('T.`%s` = S.`%s`', k, k), ' AND ')
    FROM UNNEST(p_keys) AS k
  );
  SET v_sql = FORMAT('''
    MERGE `%s` T
    USING (
      SELECT * EXCEPT(_rn)
      FROM (
        SELECT converted.*,
          ROW_NUMBER() OVER (
            PARTITION BY %s
            ORDER BY `%s` DESC NULLS LAST, TO_JSON_STRING(converted) DESC
          ) AS _rn
        FROM (SELECT %s FROM `%s` B) converted
      )
      WHERE _rn = 1
    ) S
    ON %s
    %s
    WHEN NOT MATCHED THEN
      INSERT (%s, `dt_atualizacao_silver`)
      VALUES (%s, CURRENT_TIMESTAMP())
  ''',
    p_target,
    (SELECT STRING_AGG(FORMAT('`%s`', k), ', ') FROM UNNEST(p_keys) AS k),
    p_order_by,
    v_select_cols,
    p_source,
    v_key_predicate,
    IF(v_update_set = '', '', FORMAT(
      'WHEN MATCHED AND (%s) THEN UPDATE SET %s, T.`dt_atualizacao_silver` = CURRENT_TIMESTAMP()',
      v_change_predicate, v_update_set
    )),
    v_insert_cols,
    v_insert_vals
  );
  EXECUTE IMMEDIATE v_sql;

EXCEPTION WHEN ERROR THEN
  -- Mostrar diagnostico e propagar o erro ao Python.
  SELECT
    'ERRO' AS status,
    @@error.message AS mensagem_erro,
    @@error.statement_text AS comando_sql,
    @@error.formatted_stack_trace AS stack_trace;
  RAISE;
END;
