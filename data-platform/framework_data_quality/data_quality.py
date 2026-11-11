"""Framework Data Quality v1, BigQuery, Python 3.8+.
Cada SQL deve retornar exatamente uma linha/coluna: violations (INT64 >= 0).
"""
import argparse
import json
import logging
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

LOG = logging.getLogger('data_quality')
IDENT = re.compile(r'^[A-Za-z0-9_-]+\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$')
RULE = re.compile(r'^[A-Za-z_][A-Za-z0-9_-]*$')


# Garante que um requisito de configuração esteja preenchido.
def require(value, message):
    if not value:
        raise ValueError(message)


# Lê e valida regras JSON e consultas SQL antes da execução.
def prepare(config_path):
    cfg = json.loads(config_path.read_text(encoding='utf-8-sig'))
    gcp = cfg.get('gcp', {})
    require(isinstance(gcp.get('project'), str) and gcp['project'], 'gcp.project ausente')
    require(isinstance(gcp.get('location'), str) and gcp['location'], 'gcp.location ausente')
    audit_table = cfg.get('audit_table')
    require(isinstance(audit_table, str) and IDENT.fullmatch(audit_table), 'audit_table invalida')
    rules = cfg.get('rules')
    require(isinstance(rules, list) and rules, 'rules deve ser lista nao vazia')
    names = set()
    prepared = []
    for rule in rules:
        name = rule.get('name')
        require(isinstance(name, str) and RULE.fullmatch(name), 'Nome de regra invalido')
        require(name not in names, 'Regra duplicada: ' + name)
        names.add(name)
        require(isinstance(rule.get('enabled', True), bool), 'enabled deve ser booleano')
        require(isinstance(rule.get('critical', True), bool), 'critical deve ser booleano')
        sql_file = rule.get('sql_file')
        require(isinstance(sql_file, str) and sql_file, 'sql_file ausente: ' + name)
        sql_path = (config_path.parent / sql_file).resolve()
        require(sql_path == config_path.parent or config_path.parent in sql_path.parents,
                'SQL fora da pasta do framework: ' + name)
        require(sql_path.is_file(), 'SQL nao encontrado: ' + str(sql_path))
        sql = sql_path.read_text(encoding='utf-8-sig').strip().rstrip(';').strip()
        require(sql.upper().startswith(('SELECT ', 'WITH ', '--')), 'SQL deve ser SELECT: ' + name)
        require(';' not in sql, 'SQL deve conter uma unica consulta: ' + name)
        prepared.append((rule, sql))
    return cfg, prepared


# Confere se a tabela de auditoria existe e a cria se necessário.
def ensure_audit(client, table, location):
    from google.api_core.exceptions import NotFound
    from google.cloud import bigquery
    try:
        client.get_table(table)
    except NotFound:
        schema = [bigquery.SchemaField(n, t) for n, t in [
            ('execution_id', 'STRING'), ('rule_name', 'STRING'),
            ('status', 'STRING'), ('critical', 'BOOLEAN'),
            ('violations', 'INT64'), ('started_at', 'TIMESTAMP'),
            ('finished_at', 'TIMESTAMP'), ('error_message', 'STRING')]]
        client.create_table(bigquery.Table(table, schema=schema), exists_ok=True)


# Registra o resultado de cada regra na tabela de auditoria BigQuery.
def audit(client, table, location, entry):
    from google.cloud import bigquery
    sql = ('INSERT INTO `{}` (execution_id, rule_name, status, critical, violations, '
           'started_at, finished_at, error_message) '
           'VALUES (@id, @name, @status, @critical, @violations, @started, @finished, @error)').format(table)
    params = [
        bigquery.ScalarQueryParameter('id', 'STRING', entry['execution_id']),
        bigquery.ScalarQueryParameter('name', 'STRING', entry['rule_name']),
        bigquery.ScalarQueryParameter('status', 'STRING', entry['status']),
        bigquery.ScalarQueryParameter('critical', 'BOOL', entry['critical']),
        bigquery.ScalarQueryParameter('violations', 'INT64', entry['violations']),
        bigquery.ScalarQueryParameter('started', 'TIMESTAMP', entry['started_at']),
        bigquery.ScalarQueryParameter('finished', 'TIMESTAMP', entry['finished_at']),
        bigquery.ScalarQueryParameter('error', 'STRING', entry['error_message'])]
    client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params), location=location).result()


# Executa regras habilitadas, calcula violações e controla falhas críticas.
def execute(client, cfg, prepared, selected, fail_fast):
    execution_id = str(uuid.uuid4())
    location = cfg['gcp']['location']
    table = cfg['audit_table']
    ensure_audit(client, table, location)
    critical_failed = False
    for rule, sql in prepared:
        if not rule.get('enabled', True) or (selected and rule['name'] != selected):
            continue
        started = datetime.now(timezone.utc)
        violations = None
        error = None
        status = 'ERROR'
        try:
            result = list(client.query(sql, location=location).result())
            require(len(result) == 1 and len(result[0]) == 1,
                    'SQL deve retornar uma linha e uma coluna (violations)')
            value = result[0][0]
            require(type(value) is int and value >= 0, 'violations deve ser INT64 >= 0')
            violations = value
            status = 'PASS' if value == 0 else 'FAIL'
        except Exception as exc:
            error = '{}: {}'.format(type(exc).__name__, exc)[:2000]
        entry = dict(execution_id=execution_id, rule_name=rule['name'],
                     status=status, critical=rule.get('critical', True),
                     violations=violations, started_at=started,
                     finished_at=datetime.now(timezone.utc), error_message=error)
        audit(client, table, location, entry)
        LOG.info('%s | %s | violacoes=%s%s', rule['name'], status, violations,
                 (' | ' + error) if error else '')
        if status != 'PASS' and rule.get('critical', True):
            critical_failed = True
            if fail_fast:
                break
    if critical_failed:
        raise RuntimeError('Uma ou mais regras criticas falharam; consulte a auditoria')
    LOG.info('Data Quality concluido | execucao=%s', execution_id)


# Interpreta argumentos de linha de comando e inicia a execução.
def main():
    parser = argparse.ArgumentParser(description='Framework Data Quality v1')
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--validar', action='store_true', help='Validacao local sem GCP')
    parser.add_argument('--job', help='Executa somente uma regra')
    parser.add_argument('--all', action='store_true', help='Executa todas as regras habilitadas')
    parser.add_argument('--fail-fast', action='store_true', help='Interrompe na primeira falha critica')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    path = Path(args.config)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    path = path.resolve()
    cfg, prepared = prepare(path)
    if args.job:
        require(any(r['name'] == args.job and r.get('enabled', True) for r, _ in prepared),
                'Regra nao encontrada ou desabilitada: ' + args.job)
    if args.validar:
        for rule, _ in prepared:
            LOG.info('Configuracao valida: %s', rule['name'])
        LOG.info('Validacao local concluida; nenhum acesso ao GCP')
        return
    from google.cloud import bigquery
    client = bigquery.Client(project=cfg['gcp']['project'])
    execute(client, cfg, prepared, args.job, args.fail_fast)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        LOG.error('%s: %s', type(exc).__name__, exc)
        sys.exit(1)
