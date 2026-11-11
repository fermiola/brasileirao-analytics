# Framework Data Quality v1

Regras SQL configuradas em JSON, Python 3.8+, BigQuery US.

## Instalação

Extraia a pasta inteira, incluindo `sql/`, no Windows. Reutiliza `google-cloud-bigquery` já instalado.

## Testes

No terminal, dentro da pasta:

```powershell
py data_quality.py --validar
py data_quality.py --all
py data_quality.py --job silver_chaves_duplicadas
```

`--validar` valida apenas estrutura JSON e presença/forma dos arquivos SQL, **não executa consultas nem garante a correção do SQL no BigQuery**.

A execução real cria `ds_control.tb_data_quality` automaticamente (é necessário permissão para criar tabela no dataset) e registra um evento por regra. `PASS` = 0 violações; `FAIL` = violações > 0; `ERROR` = consulta inválida/erro. Se qualquer regra **crítica** falhar, o processo retorna código 1. Regras não críticas registram falha sem interromper o pipeline. `--fail-fast` interrompe após a primeira falha crítica. Falha ao registrar auditoria também interrompe a execução.

## Consulta de auditoria

```sql
SELECT execution_id, rule_name, status, critical, violations,
       started_at, finished_at, error_message
FROM `brasileirao-data-platform.ds_control.tb_data_quality`
ORDER BY started_at DESC
LIMIT 30;
```

## Adicionar uma regra

Crie `sql/minha_regra.sql` com **uma única consulta SELECT** que retorna **exatamente uma linha e uma coluna INT64 chamada `violations`**, representando o número de problemas. Adicione ao array `rules` do `config.json`:

```json
{"name":"minha_regra","enabled":true,"critical":true,"sql_file":"sql/minha_regra.sql"}
```

Os arquivos SQL são código confiável sob seu controle; não carregue SQL fornecido por usuários externos. Ajuste as regras de status e placares se seu domínio mudar. Verificação de Gold vazia pressupõe que existem partidas finalizadas. Regras Silver são por tabela inteira, sem limitar temporada. Uma alteração no arquivo de origem pode gerar nova carga Bronze por `WRITE_APPEND`, mas a deduplicação deve ocorrer na Silver.

## Integração com Orquestrador Geral

A integração **já está configurada** em `../Orquestrador_Geral/pipeline_config.json`, usando caminhos relativos. **Não substitua** o orquestrador oficial pelo `orquestrador_pipeline.py` presente nesta pasta: esse arquivo foi mantido como legado.

Na raiz do pacote, execute `python Orquestrador_Geral/orquestrador_pipeline.py --validar` e, após provisionamento e autenticação, `python Orquestrador_Geral/orquestrador_pipeline.py --all`. A qualidade é executada **após** a Gold; regras críticas podem interromper a execução.

As regras SQL executam consultas reais e gravam auditoria em `ds_control.tb_data_quality`, com possíveis custos do BigQuery.
