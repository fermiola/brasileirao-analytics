# -*- coding: utf-8 -*-
"""Exporta um retrato dos controles do BigQuery para o Streamlit público.

Não inventa estados: colunas não reconhecidas aparecem como 'indisponivel'.
Execute localmente com Application Default Credentials.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import bigquery

BASE = Path(__file__).resolve().parent
CONFIG = json.loads((BASE / 'config.json').read_text(encoding='utf-8'))
PROJECT = CONFIG['project']
LOCATION = CONFIG.get('location', 'US')
CONTROL = CONFIG.get('control_dataset', 'ds_control')
MAX_BYTES = int(CONFIG.get('maximum_bytes_billed', 1000000000))


def pick(fields, *candidates):
    lookup = {name.lower(): name for name in fields}
    return next((lookup[c.lower()] for c in candidates if c.lower() in lookup), None)


def safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def get_records(client, table):
    ref = '{}.{}.{}'.format(PROJECT, CONTROL, table)
    obj = client.get_table(ref)
    columns = [field.name for field in obj.schema]
    time_col = pick(columns, 'data_fim', 'dt_fim', 'fim_execucao', 'data_execucao', 'dt_execucao', 'executado_em', 'timestamp_execucao', 'created_at', 'data_inicio', 'dt_inicio', 'timestamp', 'data_verificacao', 'dt_verificacao', 'started_at', 'finished_at')
    order = ' ORDER BY `{}` DESC'.format(time_col) if time_col else ''
    sql = 'SELECT * FROM `{}`{} LIMIT 100'.format(ref, order)
    cfg = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES, use_query_cache=True)
    rows = client.query(sql, job_config=cfg, location=LOCATION).result()
    return [{key: safe(val) for key, val in dict(row.items()).items()} for row in rows], columns, time_col


def normalize_status(value):
    if value is None:
        return 'indisponivel'
    if isinstance(value, bool):
        return 'sucesso' if value else 'falha'
    v = str(value).strip().lower()
    if v in ('success', 'sucesso', 'sucess', 'ok', 'pass', 'passed', 'aprovado', 'concluido', 'concluído', 'completed', 'true', '1'):
        return 'sucesso'
    if v in ('error', 'erro', 'failed', 'fail', 'falha', 'reprovado', 'false', '0'):
        return 'falha'
    if v in ('running', 'em_execucao', 'em execução', 'in_progress', 'started', 'iniciado', 'pendente'):
        return 'em_execucao'
    return 'indisponivel'


def extract_execution(rows, columns, time_col):
    status_col = pick(columns, 'status', 'status_execucao', 'situacao', 'resultado', 'sucesso')
    stage_col = pick(columns, 'etapa', 'camada', 'pipeline', 'nome_etapa', 'processo', 'framework')
    error_col = pick(columns, 'mensagem_erro', 'erro', 'error_message', 'detalhe_erro')
    records = []
    for row in rows:
        records.append({
            'data_execucao': row.get(time_col) if time_col else None,
            'etapa': row.get(stage_col) if stage_col else None,
            'status': normalize_status(row.get(status_col)) if status_col else 'indisponivel',
            # Não publicar mensagens de exceção/SQL: podem conter informações sensíveis.
            'possui_erro': bool(row.get(error_col)) if error_col else None,
        })
    return {'ultima_execucao': records[0] if records else None,
            'execucoes_recentes': records[:20],
            'colunas_detectadas': {'data': time_col, 'status': status_col, 'etapa': stage_col},
            'ordenacao_confiavel': bool(time_col)}


def extract_quality(rows, columns, time_col):
    status_col = pick(columns, 'status', 'status_check', 'resultado', 'situacao', 'aprovado', 'sucesso')
    name_col = pick(columns, 'rule_name', 'regra', 'nome_regra', 'check_name', 'nome_check', 'validacao', 'teste')
    batch_col = pick(columns, 'execution_id', 'execucao_id', 'id_execucao')
    violations_col = pick(columns, 'violations', 'violacoes')
    checks = [{'data_execucao': row.get(time_col) if time_col else None,
               'regra': row.get(name_col) if name_col else None,
               'status': normalize_status(row.get(status_col)) if status_col else 'indisponivel',
               'execution_id': row.get(batch_col) if batch_col else None,
               'violacoes': row.get(violations_col) if violations_col else None} for row in rows]
    # Ordenar por data (get_records já ordena, mas proteger caso de nulos).
    checks.sort(key=lambda x: str(x['data_execucao'] or ''), reverse=True)
    latest_batch = next((c['execution_id'] for c in checks if c['execution_id'] is not None), None)
    batch = [c for c in checks if c['execution_id'] == latest_batch] if latest_batch is not None else []
    # A consulta tem limite de 100 linhas; não afirmar completude se pode haver truncamento.
    summary = None
    if batch and len(rows) < 100:
        summary = {'execution_id': latest_batch, 'total': len(batch),
                   'aprovadas': sum(c['status'] == 'sucesso' for c in batch),
                   'reprovadas': sum(c['status'] == 'falha' for c in batch),
                   'indisponiveis': sum(c['status'] not in ('sucesso', 'falha') for c in batch)}
    return {'verificacoes_recentes': checks[:30],
            'colunas_detectadas': {'data': time_col, 'status': status_col, 'regra': name_col, 'lote': batch_col},
            'resumo_lote': summary,
            'observacao': 'Resumo do último lote identificado; não representa necessariamente o lote da última execução geral.'}


def main():
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    payload = {'versao': 1, 'gerado_em_utc': datetime.now(timezone.utc).isoformat(),
               'fonte': '{}.{}'.format(PROJECT, CONTROL), 'execucoes': None, 'data_quality': None, 'avisos': []}
    for table, key, extractor in [('tb_execucoes_pipeline', 'execucoes', extract_execution),
                                  ('tb_data_quality', 'data_quality', extract_quality)]:
        try:
            rows, columns, time_col = get_records(client, table)
            payload[key] = extractor(rows, columns, time_col)
            if not time_col:
                payload['avisos'].append('{}: coluna temporal não identificada; ordem dos registros não garantida.'.format(table))
            if not rows:
                payload['avisos'].append('{}: sem registros.'.format(table))
            print('{}: {} registros; colunas: {}'.format(table, len(rows), ', '.join(columns)))
        except Exception as exc:
            payload['avisos'].append('{}: consulta indisponível ({}).'.format(table, type(exc).__name__))
            print('ATENÇÃO: {} não pôde ser consultada: {}'.format(table, exc))
    target = BASE / 'data' / 'monitoramento.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix('.json.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(target)
    print('Monitoramento exportado para {}'.format(target))
    print('Revise o arquivo antes de publicar: as colunas precisam corresponder ao seu esquema real.')


if __name__ == '__main__':
    main()
