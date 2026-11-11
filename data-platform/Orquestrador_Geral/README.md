# Orquestrador Geral — Bronze → Silver → Gold → Data Quality

Este é o **ponto de entrada oficial** do pacote. O arquivo `pipeline_config.json` referencia os quatro frameworks por caminhos relativos.

## Uso (na raiz do pacote)

```cmd
python Orquestrador_Geral/orquestrador_pipeline.py --help
python Orquestrador_Geral/orquestrador_pipeline.py --validar
python Orquestrador_Geral/orquestrador_pipeline.py --all
python Orquestrador_Geral/orquestrador_pipeline.py --silver-gold
```

- `--validar`: verifica configurações locais, sem consultas ao GCP.
- `--all`: executa Bronze, Silver, Gold e Data Quality.
- `--silver-gold`: executa Silver, Gold e Data Quality, sem nova ingestão Bronze.
- `--permitir-reingestao`: remove a proteção de hash para Bronze `WRITE_APPEND`; **não use sem revisar risco de duplicação**.

## Auditoria

Com `observability.enabled=true`, grava em `brasileirao-data-platform.ds_control.tb_execucoes_pipeline`. O dataset `ds_control` precisa existir; a tabela é criada pelo orquestrador quando necessário. Uma falha de auditoria interrompe a execução.

```sql
SELECT execucao_id, etapa, status, dt_inicio, dt_fim, duracao_segundos, codigo_retorno, erro
FROM `brasileirao-data-platform.ds_control.tb_execucoes_pipeline`
ORDER BY dt_inicio DESC LIMIT 30;
```

A auditoria registra status, tempos e códigos de retorno; não mede automaticamente custos reais ou bytes faturados. Uma falha posterior não desfaz operações já concluídas. Consulte o README geral para provisionamento, credenciais e custos.
