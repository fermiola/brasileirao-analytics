# ============================================================
# FRAMEWORK GOLD | BRASILEIRÃO DATA PLATFORM
# Objetivo: Cria tabelas analíticas a partir de consultas SQL, respeitando dependências e auditoria.
# Os comentários documentam o código original; não alteram sua lógica.
# Consulte config.json e README.md para parâmetros e execução.
# ============================================================

"""Framework Gold v2 - Python 3.8+, BigQuery, dependencias e auditoria."""
import argparse
import json
import logging
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import bigquery

LOG = logging.getLogger('gold')
TABLE_RE = re.compile(r'^[A-Za-z0-9_-]+\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$')
JOB_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_-]*$')
AUDIT_TABLE = 'ds_control.tb_execucoes_gold'


# Valida uma condição e interrompe com mensagem quando não atendida.
def check(condition, message):
    if not condition:
        raise ValueError(message)


# Valida metadados do job e lê o SQL associado, preparando a estratégia de publicação.
def sql_for_job(job, base):
    for field in ('name', 'source', 'target', 'sql_file', 'strategy'):
        check(isinstance(job.get(field), str) and bool(job[field]), 'Campo obrigatorio invalido: ' + field)
    check(JOB_RE.fullmatch(job['name']) is not None, 'Nome de job invalido')
    for field in ('source', 'target'):
        check(TABLE_RE.fullmatch(job[field]) is not None, 'Tabela invalida: ' + field)
    check(job['source'] != job['target'], 'Origem e destino iguais')
    check(job['strategy'] == 'REPLACE_ATOMIC', 'Estrategia nao suportada')
    path = (base / job['sql_file']).resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError:
        raise ValueError('sql_file deve estar dentro da pasta do framework')
    check(path.is_file(), 'Arquivo SQL nao encontrado: ' + str(path))
    sql = path.read_text(encoding='utf-8-sig').strip().rstrip(';')
    check('{source}' in sql, 'SQL deve conter {source}')
    check('{target}' not in sql, 'Use apenas {source} no SELECT')
    # Remover comentarios iniciais para evitar aceitar DDL precedido por comentario.
    statement = re.sub(r'\A(?:\s|--[^\n]*(?:\n|$)|/\*[\s\S]*?\*/)*', '', sql).upper()
    check(statement.startswith(('WITH ', 'SELECT ', 'WITH\n', 'SELECT\n')), 'Arquivo deve conter apenas SELECT/WITH, sem CREATE')
    return sql.replace('{source}', job['source'])


# Ordena os jobs de acordo com dependências e seleção solicitada.
def resolve_order(jobs, requested, include_dependencies):
    by_name = {}
    for job in jobs:
        name = job.get('name')
        check(isinstance(name, str) and JOB_RE.fullmatch(name) is not None, 'Nome de job invalido')
        check(name not in by_name, 'Job duplicado: ' + name)
        by_name[name] = job
    for job in jobs:
        deps = job.get('depends_on', [])
        check(isinstance(deps, list) and all(isinstance(d, str) for d in deps), 'depends_on invalido: ' + job['name'])
        for dep in deps:
            check(dep in by_name, 'Dependencia inexistente: ' + dep)
            check(by_name[dep].get('enabled', True), 'Dependencia desabilitada: ' + dep)
    check(all(name in by_name for name in requested), 'Job solicitado nao encontrado')
    visited, visiting, ordered = set(), set(), []

    # Percorre dependências do job durante a ordenação topológica.
    def visit(name):
        if name in visited:
            return
        check(name not in visiting, 'Ciclo de dependencias envolvendo: ' + name)
        visiting.add(name)
        if include_dependencies:
            for dep in by_name[name].get('depends_on', []):
                visit(dep)
        visiting.remove(name)
        visited.add(name)
        ordered.append(by_name[name])

    for name in requested:
        visit(name)
    return ordered


# Constrói o identificador completo da tabela de auditoria no projeto.
def audit_table_name(project):
    return '{}.{}'.format(project, AUDIT_TABLE)


# Garante que a tabela de auditoria esteja disponível antes da execução.
def ensure_audit_table(client, project, location):
    # Dataset ds_control ja existe no projeto. CREATE IF NOT EXISTS nao apaga historico.
    sql = '''CREATE TABLE IF NOT EXISTS `{}` (
      execution_id STRING, job_name STRING, source_table STRING, target_table STRING,
      status STRING, started_at TIMESTAMP, finished_at TIMESTAMP,
      bq_job_id STRING, rows_written INT64, error_message STRING
    )'''.format(audit_table_name(project))
    client.query(sql, location=location).result()


# Registra informações de execução na tabela de auditoria.
def write_audit(client, project, location, record):
    sql = '''INSERT INTO `{}`
    (execution_id, job_name, source_table, target_table, status, started_at,
     finished_at, bq_job_id, rows_written, error_message)
    VALUES (@execution_id, @job_name, @source_table, @target_table, @status,
            @started_at, @finished_at, @bq_job_id, @rows_written, @error_message)'''.format(audit_table_name(project))
    params = []
    types = {'execution_id': 'STRING', 'job_name': 'STRING', 'source_table': 'STRING',
             'target_table': 'STRING', 'status': 'STRING', 'started_at': 'TIMESTAMP',
             'finished_at': 'TIMESTAMP', 'bq_job_id': 'STRING',
             'rows_written': 'INT64', 'error_message': 'STRING'}
    for name, typ in types.items():
        params.append(bigquery.ScalarQueryParameter(name, typ, record.get(name)))
    cfg = bigquery.QueryJobConfig(query_parameters=params)
    client.query(sql, job_config=cfg, location=location).result()


# Verifica condições esperadas para a tabela de saída do job.
def validate_output(client, job, location):
    """Checagens leves de resultado; queries executadas apos a substituicao."""
    target = job['target']
    query = 'SELECT COUNT(*) AS n FROM `{}`'.format(target)
    rows = list(client.query(query, location=location).result())
    count = rows[0].n
    if job.get('require_nonempty', True):
        check(count > 0, 'Tabela vazia: ' + target)
    keys = job.get('unique_keys', [])
    if keys:
        check(isinstance(keys, list) and all(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', k) for k in keys),
              'unique_keys invalido: ' + job['name'])
        cols = ', '.join('`{}`'.format(k) for k in keys)
        check_sql = 'SELECT COUNT(*) AS n FROM (SELECT {}, COUNT(*) AS c FROM `{}` GROUP BY {} HAVING c > 1)'.format(cols, target, cols)
        duplicate_groups = list(client.query(check_sql, location=location).result())[0].n
        check(duplicate_groups == 0, 'Chaves duplicadas em {}: {}'.format(target, duplicate_groups))
    return count


# Executa o SQL no BigQuery e registra o resultado do processamento.
def run_job(client, project, location, job, sql):
    started = datetime.now(timezone.utc)
    execution_id = str(uuid.uuid4())
    bq_job_id = None
    rows = None
    status = 'SUCCESS'
    error = None
    LOG.info('Iniciando %s | execucao=%s', job['name'], execution_id)
    try:
        ddl = 'CREATE OR REPLACE TABLE `{}` AS {}'.format(job['target'], sql)
        query_job = client.query(ddl, location=location)
        bq_job_id = query_job.job_id
        query_job.result()
        rows = validate_output(client, job, location)
        LOG.info('Concluido | job=%s | linhas=%s | bq_job_id=%s', job['name'], rows, bq_job_id)
    except Exception as exc:
        status = 'FAILED'
        error = '{}: {}'.format(type(exc).__name__, exc)[:8000]
        LOG.error('Falha no job %s: %s', job['name'], error)
    record = dict(execution_id=execution_id, job_name=job['name'],
                  source_table=job['source'], target_table=job['target'],
                  status=status, started_at=started,
                  finished_at=datetime.now(timezone.utc), bq_job_id=bq_job_id,
                  rows_written=rows, error_message=error)
    try:
        write_audit(client, project, location, record)
    except Exception as audit_exc:
        LOG.error('Falha ao registrar auditoria de %s: %s', job['name'], audit_exc)
        raise RuntimeError('Auditoria nao registrada; verificar job e tabela de destino') from audit_exc
    if status != 'SUCCESS':
        raise RuntimeError(error)


# Interpreta argumentos, carrega configurações e orquestra os jobs Gold.
def main():
    parser = argparse.ArgumentParser(description='Orquestrador Gold v2')
    parser.add_argument('--config', default='config.json')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--job', help='Executa somente este job (sem dependencias)')
    group.add_argument('--all', action='store_true', help='Executa todos os jobs habilitados com dependencias')
    parser.add_argument('--validar', action='store_true', help='Valida configuracoes sem acessar GCP')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path(__file__).resolve().parent / config_path
    config_path = config_path.resolve()
    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
    gcp = config['gcp']
    check(bool(gcp.get('project')) and bool(gcp.get('location')), 'gcp incompleto')
    jobs = config['jobs']
    check(isinstance(jobs, list) and jobs, 'Lista de jobs vazia')
    if args.job:
        requested = [args.job]
    else:
        requested = [j['name'] for j in jobs if j.get('enabled', True)]
    check(bool(requested), 'Nenhum job selecionado')
    ordered = resolve_order(jobs, requested, include_dependencies=(not bool(args.job)))
    for job in ordered:
        check(job.get('enabled', True), 'Job desabilitado: ' + job['name'])
    prepared = [(j, sql_for_job(j, config_path.parent)) for j in ordered]
    for job, _ in prepared:
        LOG.info('Configuracao valida: %s', job['name'])
    if args.validar:
        return
    client = bigquery.Client(project=gcp['project'])
    ensure_audit_table(client, gcp['project'], gcp['location'])
    for job, sql in prepared:
        run_job(client, gcp['project'], gcp['location'], job, sql)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        LOG.error('%s: %s', type(exc).__name__, exc)
        sys.exit(1)
