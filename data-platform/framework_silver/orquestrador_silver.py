# ============================================================
# FRAMEWORK SILVER | BRASILEIRÃO DATA PLATFORM
# Objetivo: Executa transformação e MERGE no BigQuery com schema e mapeamento declarados em JSON.
# Os comentários documentam o código original; não alteram sua lógica.
# Consulte config.json e README.md para parâmetros e execução.
# ============================================================

"""Framework Silver v2: schema tipado por JSON e MERGE executado no BigQuery."""
import argparse
import json
import logging
import re
import sys
from pathlib import Path

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

LOG = logging.getLogger('silver')
TABLE = re.compile(r'^[A-Za-z0-9_-]+\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$')
COL = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
TYPES = {'STRING', 'INT64', 'FLOAT64', 'NUMERIC', 'BIGNUMERIC', 'BOOL', 'DATE', 'DATETIME', 'TIMESTAMP', 'TIME', 'BYTES', 'JSON'}


# Padroniza aliases de tipos SQL para os nomes aceitos pelo BigQuery.
def normalizar_tipo(tipo):
    aliases = {
        'INTEGER': 'INT64', 'INT': 'INT64', 'SMALLINT': 'INT64',
        'BIGINT': 'INT64', 'FLOAT': 'FLOAT64', 'BOOLEAN': 'BOOL',
        'DECIMAL': 'NUMERIC', 'BIGDECIMAL': 'BIGNUMERIC'
    }
    tipo = str(tipo).strip().upper()
    return aliases.get(tipo, tipo)


# Garante uma condição de validação, lançando erro descritivo quando falhar.
def require(ok, msg):
    if not ok:
        raise ValueError(msg)


# Verifica se o job Silver possui configuração válida antes de executá-lo.
def validate(job):
    for key in ('name', 'source', 'target', 'strategy', 'keys', 'order_by', 'columns'):
        require(key in job, 'Campo obrigatório ausente: ' + key)
    require(job['strategy'] == 'MERGE', 'Apenas MERGE é suportado')
    require(all(isinstance(job[x], str) and TABLE.fullmatch(job[x]) for x in ('source', 'target')), 'Tabela inválida')
    require(job['source'] != job['target'], 'Origem e destino devem ser diferentes')
    columns = job['columns']
    require(isinstance(columns, list) and bool(columns), 'columns deve ser lista não vazia')
    for c in columns:
        require(isinstance(c, dict) and isinstance(c.get('name'), str) and COL.fullmatch(c['name']), 'Nome de coluna inválido')
        require(normalizar_tipo(c.get('type')) in TYPES, 'Tipo inválido em ' + c['name'])
        require(isinstance(c.get('required', False), bool), 'required deve ser booleano em ' + c['name'])
        if 'format' in c:
            require(normalizar_tipo(c['type']) in ('DATE', 'DATETIME', 'TIMESTAMP', 'TIME'), 'format apenas para datas/horas')
            require(isinstance(c['format'], str) and c['format'] and "'" not in c['format'] and '\\' not in c['format'], 'format inválido')
        if 'source' in c:
            require(isinstance(c['source'], str) and COL.fullmatch(c['source']), 'source de coluna inválido')
    names = [c['name'] for c in columns]
    require(len(names) == len(set(names)), 'Colunas duplicadas')
    keys = job['keys']
    require(isinstance(keys, list) and bool(keys) and all(isinstance(k, str) and k in names for k in keys), 'Chaves inválidas')
    require(len(keys) == len(set(keys)), 'Chaves duplicadas')
    require(job['order_by'] in names, 'order_by deve ser coluna de destino')
    require(all(next(c for c in columns if c['name'] == k).get('required', False) for k in keys), 'Marque as chaves com required=true')


# Prepara e executa o processamento Silver no BigQuery, respeitando dry-run.
def run_job(client, gcp, job, dry_run):
    validate(job)
    LOG.info('%s | %s -> %s', job['name'], job['source'], job['target'])
    if dry_run:
        LOG.info('Configuração válida; nenhuma operação no GCP')
        return
    source = client.get_table(job['source'])
    src = {f.name: f for f in source.schema}
    missing = [c.get('source', c['name']) for c in job['columns'] if c.get('source', c['name']) not in src]
    require(not missing, 'Colunas ausentes na Bronze: ' + ', '.join(missing))
    try:
        target = client.get_table(job['target'])
    except NotFound:
        LOG.info('Tabela Silver não existe; procedure criará com os tipos do JSON')
    else:
        actual = {f.name.lower(): normalizar_tipo(f.field_type) for f in target.schema}
        expected = {c['name']: normalizar_tipo(c['type']) for c in job['columns']}
        mismatch = ['{}: atual={}, esperado={}'.format(n, actual.get(n.lower(), 'AUSENTE'), t)
                    for n, t in expected.items() if actual.get(n.lower()) != t]
        require(not mismatch, 'Schema Silver incompatível: ' + '; '.join(mismatch))
    sql = 'CALL `{}`(@source, @target, @keys, @columns_json, @order_by)'.format(gcp['procedure'])
    params = [
        bigquery.ScalarQueryParameter('source', 'STRING', job['source']),
        bigquery.ScalarQueryParameter('target', 'STRING', job['target']),
        bigquery.ArrayQueryParameter('keys', 'STRING', job['keys']),
        bigquery.ScalarQueryParameter('columns_json', 'STRING', json.dumps([dict(c, type=normalizar_tipo(c['type'])) for c in job['columns']], ensure_ascii=False)),
        bigquery.ScalarQueryParameter('order_by', 'STRING', job['order_by'])
    ]
    query = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params), location=gcp['location'])
    query.result()
    LOG.info('Silver concluída | job_id=%s', query.job_id)


# Carrega a configuração e aciona os jobs Silver solicitados.
def main():
    parser = argparse.ArgumentParser(description='Framework Silver v2')
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--job')
    parser.add_argument('--validar', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    path = Path(args.config)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    cfg = json.loads(path.read_text(encoding='utf-8'))
    gcp = cfg['gcp']
    require(TABLE.fullmatch(gcp['procedure']) is not None, 'Procedure inválida')
    jobs = [j for j in cfg['jobs'] if j.get('enabled', True) and (args.job is None or j.get('name') == args.job)]
    require(jobs, 'Nenhum job selecionado')
    client = None if args.validar else bigquery.Client(project=gcp['project'])
    for job in jobs:
        run_job(client, gcp, job, args.validar)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        LOG.error('%s: %s', type(exc).__name__, exc)
        sys.exit(1)
