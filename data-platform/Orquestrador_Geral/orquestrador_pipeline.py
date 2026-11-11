"""Pipeline Bronze -> Silver -> Gold -> Data Quality, com auditoria BigQuery.
Compatível com Python 3.8. Mantém os parâmetros da versão anterior.
"""
import argparse
import json
import logging
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

LOG = logging.getLogger('pipeline')
ORDER = ('bronze', 'silver', 'gold')
OPTIONAL = ('data_quality',)


# Retorna o instante atual em UTC para os registros de auditoria.
def utc_now():
    return datetime.now(timezone.utc)


# Resolve caminhos relativos ao arquivo de configuração ou caminhos absolutos.
def resolve_path(base, value):
    p = Path(value).expanduser()
    return p.resolve() if p.is_absolute() else (base / p).resolve()


# Lê o JSON e valida a existência dos scripts e configurações das etapas.
def load_config(path):
    cfg = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(cfg.get('stages'), dict):
        raise ValueError('Configuração exige objeto stages')
    for name in ORDER:
        if name not in cfg['stages']:
            raise ValueError('Etapa ausente: ' + name)
    for name in ORDER + OPTIONAL:
        if name not in cfg['stages']:
            continue
        stage = cfg['stages'][name]
        if not isinstance(stage, dict):
            raise ValueError('Etapa inválida: ' + name)
        for key in ('script', 'config'):
            if not isinstance(stage.get(key), str) or not stage[key].strip():
                raise ValueError('{}.{} ausente'.format(name, key))
            p = resolve_path(path.parent, stage[key])
            if not p.is_file():
                raise ValueError('Arquivo não encontrado ({}.{}): {}'.format(name, key, p))
    obs = cfg.get('observability', {})
    if not isinstance(obs, dict):
        raise ValueError('observability deve ser objeto')
    if obs.get('enabled', True):
        import re
        table = obs.get('table', 'brasileirao-data-platform.ds_control.tb_execucoes_pipeline')
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*', table):
            raise ValueError('observability.table inválida')
        if not obs.get('location', 'US'):
            raise ValueError('observability.location inválida')
    return cfg


# Protege a ingestão contra reprocessamento acidental com WRITE_APPEND.
def bronze_append_guard(config_file, permit):
    if permit:
        return
    cfg = json.loads(config_file.read_text(encoding='utf-8-sig'))
    risky = []
    for job in cfg.get('jobs', []):
        if job.get('enabled', True) is False:
            continue
        dest = job.get('destination', {})
        if dest.get('write_disposition', 'WRITE_APPEND') == 'WRITE_APPEND' and not job.get('skip_if_same_file', False):
            risky.append(job.get('name', '<sem nome>'))
    if risky:
        raise ValueError('Bronze WRITE_APPEND sem skip_if_same_file=true: {}. '
                         'Use --permitir-reingestao apenas se aceitar esse risco.'.format(', '.join(risky)))


# Prepara a tabela de observabilidade de execuções no BigQuery.
def make_audit(cfg):
    obs = cfg.get('observability', {})
    if obs.get('enabled', True) is False:
        return None
    from google.cloud import bigquery
    table = obs.get('table', 'brasileirao-data-platform.ds_control.tb_execucoes_pipeline')
    project = table.split('.')[0]
    location = obs.get('location', 'US')
    client = bigquery.Client(project=project, location=location)
    ddl = '''CREATE TABLE IF NOT EXISTS `{}` (
      execucao_id STRING, etapa STRING, status STRING,
      dt_inicio TIMESTAMP, dt_fim TIMESTAMP, duracao_segundos FLOAT64,
      codigo_retorno INT64, erro STRING, modo STRING,
      dt_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
    )'''.format(table)
    client.query(ddl, location=location).result()
    return client, table, location


# Persiste o evento de execução na tabela de auditoria.
def audit_record(audit, row):
    if audit is None:
        return
    from google.cloud import bigquery
    client, table, location = audit
    sql = '''INSERT INTO `{}`
    (execucao_id, etapa, status, dt_inicio, dt_fim, duracao_segundos,
     codigo_retorno, erro, modo)
    VALUES (@id, @etapa, @status, @inicio, @fim, @duracao, @codigo, @erro, @modo)'''.format(table)
    types = [('id', 'STRING', row['execucao_id']),
             ('etapa', 'STRING', row['etapa']), ('status', 'STRING', row['status']),
             ('inicio', 'TIMESTAMP', row['dt_inicio']), ('fim', 'TIMESTAMP', row['dt_fim']),
             ('duracao', 'FLOAT64', row['duracao_segundos']),
             ('codigo', 'INT64', row['codigo_retorno']),
             ('erro', 'STRING', row['erro']), ('modo', 'STRING', row['modo'])]
    params = [bigquery.ScalarQueryParameter(n, t, v) for n, t, v in types]
    client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params), location=location).result()


# Executa a etapa em subprocesso e verifica seu código de retorno.
def run_stage(name, stage, base, validate):
    script = resolve_path(base, stage['script'])
    config = resolve_path(base, stage['config'])
    cmd = [sys.executable, str(script), '--config', str(config)]
    if validate:
        cmd.append('--validar')
    elif name in ('gold', 'data_quality'):
        cmd.append('--all')
    job = stage.get('job')
    if job and (validate or name not in ('gold', 'data_quality')):
        cmd.extend(['--job', job])
    LOG.info('Iniciando %s | script=%s', name.upper(), script.name)
    result = subprocess.run(cmd, cwd=str(script.parent), check=False)
    return result.returncode


# Interpreta argumentos de linha de comando e inicia a execução.
def main():
    parser = argparse.ArgumentParser(description='Orquestrador com observabilidade v1')
    parser.add_argument('--config', default='pipeline_config.json')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--all', action='store_true')
    group.add_argument('--silver-gold', action='store_true')
    group.add_argument('--validar', action='store_true')
    parser.add_argument('--permitir-reingestao', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    path = Path(args.config)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    path = path.resolve()
    cfg = load_config(path)
    stages = ORDER if args.all or args.validar else ('silver', 'gold')
    if 'data_quality' in cfg['stages']:
        stages += ('data_quality',)
    if 'bronze' in stages and not args.validar:
        bronze_append_guard(resolve_path(path.parent, cfg['stages']['bronze']['config']),
                            args.permitir_reingestao)
    run_id = str(uuid.uuid4())
    mode = 'VALIDAR' if args.validar else ('ALL' if args.all else 'SILVER_GOLD')
    # --validar não cria tabela nem consulta GCP.
    audit = None if args.validar else make_audit(cfg)
    pipeline_start = utc_now()
    pipeline_clock = time.monotonic()
    LOG.info('Pipeline | execução=%s | modo=%s', run_id, mode)
    try:
        for name in stages:
            started = utc_now()
            clock = time.monotonic()
            code = None
            error = None
            try:
                code = run_stage(name, cfg['stages'][name], path.parent, args.validar)
                if code != 0:
                    raise RuntimeError('{} falhou com código {}'.format(name.upper(), code))
                status = 'SUCESSO'
            except Exception as exc:
                status = 'FALHA'
                error = '{}: {}'.format(type(exc).__name__, exc)
            ended = utc_now()
            elapsed = round(time.monotonic() - clock, 3)
            record = dict(execucao_id=run_id, etapa=name, status=status,
                          dt_inicio=started, dt_fim=ended, duracao_segundos=elapsed,
                          codigo_retorno=code, erro=error, modo=mode)
            if audit:
                try:
                    audit_record(audit, record)
                except Exception as exc:
                    # Auditoria é obrigatória quando habilitada: falha não pode ser silenciosa.
                    raise RuntimeError('Falha ao registrar auditoria de {}: {}'.format(name, exc))
            LOG.info('%s | %s | %.1f s', name.upper(), status, elapsed)
            if status == 'FALHA':
                raise RuntimeError(error)
        pipeline_status = 'SUCESSO'
        pipeline_error = None
    except Exception as exc:
        pipeline_status = 'FALHA'
        pipeline_error = '{}: {}'.format(type(exc).__name__, exc)
    pipeline_end = utc_now()
    if audit:
        audit_record(audit, dict(execucao_id=run_id, etapa='pipeline', status=pipeline_status,
                                 dt_inicio=pipeline_start, dt_fim=pipeline_end,
                                 duracao_segundos=round(time.monotonic()-pipeline_clock, 3),
                                 codigo_retorno=0 if pipeline_status == 'SUCESSO' else 1,
                                 erro=pipeline_error, modo=mode))
    if pipeline_status != 'SUCESSO':
        raise RuntimeError(pipeline_error)
    LOG.info('Pipeline concluído com sucesso | execução=%s', run_id)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        LOG.error('%s: %s', type(exc).__name__, exc)
        sys.exit(1)
