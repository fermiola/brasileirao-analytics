# ============================================================
# FRAMEWORK BRONZE | BRASILEIRÃO DATA PLATFORM
# Objetivo: Ingere arquivos locais para tabelas BigQuery por jobs de carga, seguindo regras declaradas em JSON.
# Os comentários documentam o código original; não alteram sua lógica.
# Consulte config.json e README.md para parâmetros e execução.
# ============================================================

"""Framework genérico de ingestão local -> BigQuery, Python >=3.8.
Configuração exclusivamente em JSON. Sem SQL DML; usa BigQuery load jobs.
"""
import argparse
import csv
import hashlib
import json
import logging
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

LOG = logging.getLogger('bronze')
BQ_TYPES = {'STRING','INTEGER','FLOAT','NUMERIC','BOOLEAN','DATE','DATETIME','TIMESTAMP','TIME','JSON','BYTES'}
MODES = {'WRITE_APPEND','WRITE_TRUNCATE','WRITE_EMPTY'}

# Interrompe a execução quando uma pré-condição ou validação obrigatória não é atendida.
def required(condition, message):
    if not condition:
        raise ValueError(message)

# Resolve o caminho da fonte, aceitando caminhos absolutos ou relativos à pasta do projeto.
def path_from(base, value):
    p = Path(value).expanduser()
    return p if p.is_absolute() else base / p

# Abre a origem configurada e disponibiliza seus registros para a etapa de transformação.
def source_rows(source, base):
    path = path_from(base, source['path'])
    required(path.is_file(), 'Arquivo não encontrado: {}'.format(path))
    fmt = source.get('format', path.suffix.lstrip('.')).lower()
    if fmt in ('xlsx', 'xlsm'):
        from openpyxl import load_workbook
        wb = load_workbook(str(path), read_only=True, data_only=True)
        try:
            sheet = source.get('sheet') or wb.sheetnames[0]
            required(sheet in wb.sheetnames, 'Aba não encontrada: {}'.format(sheet))
            it = wb[sheet].iter_rows(values_only=True)
            for item in tabular_rows(it, source):
                yield item
        finally:
            wb.close()
    elif fmt == 'csv':
        with path.open('r', encoding=source.get('encoding','utf-8-sig'), newline='') as f:
            it = csv.reader(f, delimiter=source.get('delimiter', ','), quotechar=source.get('quotechar','"'))
            for item in tabular_rows(it, source):
                yield item
    elif fmt in ('jsonl','ndjson'):
        with path.open('r', encoding=source.get('encoding','utf-8')) as f:
            for i, line in enumerate(f, 1):
                if line.strip():
                    obj = json.loads(line)
                    required(isinstance(obj,dict), 'JSONL linha {} deve ser objeto'.format(i))
                    yield i, obj
    elif fmt == 'json':
        with path.open('r', encoding=source.get('encoding','utf-8')) as f:
            obj = json.load(f)
        for key in source.get('record_path', '').split('.'):
            if key:
                obj = obj[key]
        required(isinstance(obj,list), 'JSON deve conter lista de objetos (ou record_path para lista)')
        for i, row in enumerate(obj,1):
            required(isinstance(row,dict), 'JSON item {} não é objeto'.format(i))
            yield i, row
    else:
        raise ValueError('Formato não suportado: {} (xlsx, xlsm, csv, json, jsonl)'.format(fmt))

# Converte linhas da fonte tabular em registros associados às colunas esperadas.
def tabular_rows(it, source):
    header_row = int(source.get('header_row',1))
    required(header_row >= 1, 'header_row deve ser >= 1')
    header = None
    for i, vals in enumerate(it,1):
        if i < header_row:
            continue
        if i == header_row:
            header = [str(v).strip() if v is not None else '' for v in vals]
            required(len(header)==len(set(header)), 'Cabeçalho possui nomes duplicados')
            continue
        if not any(v is not None and str(v).strip() for v in vals):
            continue
        yield i, {name: vals[j] if j < len(vals) else None for j,name in enumerate(header) if name}

# Converte e valida um valor conforme o tipo e as regras da coluna configurada.
def convert(value, col, line):
    typ = col['type'].upper()
    if value is None or (isinstance(value,str) and (value.strip()=='' or value.strip() in col.get('null_values', []))):
        if col.get('mode','NULLABLE').upper() == 'REQUIRED':
            raise ValueError('Linha {}: {} obrigatório ausente'.format(line,col['name']))
        return None
    try:
        if typ == 'STRING':
            return str(value).strip() if col.get('trim', True) else str(value)
        if typ == 'INTEGER':
            if isinstance(value,bool): raise ValueError('booleano não é inteiro')
            d = Decimal(str(value))
            if d != d.to_integral_value(): raise ValueError('valor fracionário')
            return int(d)
        if typ == 'FLOAT': return float(value)
        if typ == 'NUMERIC': return str(Decimal(str(value)))
        if typ == 'BOOLEAN':
            if isinstance(value,bool): return value
            v = str(value).strip().lower()
            if v in ('true','1','sim','s','yes'): return True
            if v in ('false','0','nao','não','n','no'): return False
            raise ValueError('booleano desconhecido')
        if typ in ('DATE','DATETIME','TIMESTAMP','TIME'):
            if isinstance(value,datetime):
                return value.date().isoformat() if typ=='DATE' else value.isoformat()
            if isinstance(value,date): return value.isoformat()
            if isinstance(value,(int,float)) and col.get('excel_serial',False):
                from openpyxl.utils.datetime import from_excel
                value = from_excel(value)
                return value.date().isoformat() if typ=='DATE' else value.isoformat()
            s = str(value).strip()
            for fmt in col.get('input_formats', []):
                try:
                    dt = datetime.strptime(s,fmt)
                    return dt.date().isoformat() if typ=='DATE' else dt.isoformat()
                except ValueError: pass
            if typ=='DATE': return date.fromisoformat(s).isoformat()
            if typ in ('DATETIME','TIMESTAMP'): return datetime.fromisoformat(s.replace('Z','+00:00')).isoformat()
            return s
        if typ == 'JSON': return json.dumps(value,ensure_ascii=False) if not isinstance(value,str) else value
        if typ == 'BYTES': return str(value)
        raise ValueError('tipo não suportado')
    except (ValueError, TypeError, InvalidOperation, OverflowError) as e:
        raise ValueError('Linha {}: coluna {} ({}) valor {!r}: {}'.format(line,col['name'],typ,value,e))

# Confere a estrutura e os parâmetros do job antes de processar dados.
def validate_job(job):
    for k in ('source','destination','columns'):
        required(k in job,'Configuração ausente: {}'.format(k))
    dest=job['destination']
    for k in ('project','dataset','table','location'):
        required(dest.get(k), 'Destino sem {}'.format(k))
    for k in ('project','dataset','table'):
        required(bool(re.fullmatch(r'[A-Za-z0-9_-]+',dest[k])), 'Identificador inválido: {}'.format(k))
    names=[]
    for col in job['columns']:
        required(col.get('name') and col.get('source'), 'Coluna precisa de name e source')
        required(col['type'].upper() in BQ_TYPES,'Tipo inválido: {}'.format(col['type']))
        required(col.get('mode','NULLABLE').upper() in ('NULLABLE','REQUIRED'),'Modo de coluna inválido')
        names.append(col['name'])
    required(len(names)==len(set(names)),'Colunas destino duplicadas')
    audit=job.get('audit',{})
    if audit.get('enabled',True):
        required(not set(names).intersection({'id_execucao','arquivo_origem','hash_arquivo','dt_ingestao'}),'Colunas reservadas de auditoria')
    required(dest.get('write_disposition','WRITE_APPEND') in MODES,'Modo de carga inválido')
    part = dest.get('partitioning', {})
    required(isinstance(part, dict), 'partitioning deve ser objeto JSON')
    if part.get('enabled', False):
        required(part.get('type', 'DAY').upper() == 'DAY',
                 'Particionamento por coluna suporta somente DAY')
        field = part.get('field')
        schema_types = {c['name']: c['type'].upper() for c in job['columns']}
        if audit.get('enabled', True):
            schema_types['dt_ingestao'] = 'TIMESTAMP'
        required(field in schema_types, 'Coluna de partição ausente no schema: {}'.format(field))
        required(schema_types[field] in ('TIMESTAMP', 'DATE', 'DATETIME'),
                 'Coluna de partição deve ser TIMESTAMP, DATE ou DATETIME')
        required(isinstance(part.get('require_partition_filter', False), bool),
                 'require_partition_filter deve ser booleano')

# Calcula uma impressão digital do arquivo para rastreabilidade da ingestão.
def file_hash(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

# Executa uma ingestão configurada, com opção de apenas validar sem carregar.
def run_job(job,base,validate_only):
    validate_job(job)
    src=job['source']; dest=job['destination']
    path=path_from(base,src['path'])
    digest=file_hash(path)
    run_id=str(uuid.uuid4()); now=datetime.now(timezone.utc).isoformat()
    rows=[]; cols=job['columns']; audit=job.get('audit',{}).get('enabled',True)
    for line,raw in source_rows(src,base):
        row={}
        for col in cols:
            if col['source'] not in raw:
                raise ValueError('Linha {}: coluna origem ausente: {}'.format(line,col['source']))
            row[col['name']]=convert(raw[col['source']],col,line)
        if audit:
            row.update(id_execucao=run_id,arquivo_origem=path.name,hash_arquivo=digest,dt_ingestao=now)
        rows.append(row)
    required(rows,'Arquivo não possui registros para carregar')
    table='{}.{}.{}'.format(dest['project'],dest['dataset'],dest['table'])
    LOG.info('%s | %s registros | SHA256 %s | execução %s',table,len(rows),digest,run_id)
    if validate_only:
        LOG.info('Validação local concluída; nenhum acesso ao GCP')
        return
    from google.cloud import bigquery
    client=bigquery.Client(project=dest['project'],location=dest['location'])
    # Valida particionamento antes da carga: load jobs não convertem
    # automaticamente uma tabela já existente em particionada.
    part = dest.get('partitioning', {})
    partition_enabled = part.get('enabled', False)
    existing_table = None
    try:
        existing_table = client.get_table(table)
    except Exception as e:
        from google.api_core.exceptions import NotFound
        if not isinstance(e, NotFound):
            raise
    if existing_table is not None:
        current = existing_table.time_partitioning
        if partition_enabled:
            required(current is not None,
                     'Tabela existente sem particionamento: {}. Migre ou recrie a tabela.'.format(table))
            required(current.field == part['field'] and current.type_ == 'DAY',
                     'Particionamento da tabela diferente do configurado no JSON')
        else:
            required(current is None,
                     'Tabela existente é particionada; configure destination.partitioning no JSON')

    if job.get('skip_if_same_file',False):
        required(audit,'skip_if_same_file exige audit.enabled=true')
        # Consulta somente leitura; falha explicitamente se tabela não existir.
        if existing_table is not None:
            required(any(f.name == 'hash_arquivo' for f in existing_table.schema),
                     'skip_if_same_file exige coluna hash_arquivo na tabela existente')
            sql='SELECT 1 FROM `{}` WHERE hash_arquivo=@hash LIMIT 1'.format(table)
            params=[bigquery.ScalarQueryParameter('hash','STRING',digest)]
            qcfg=bigquery.QueryJobConfig(query_parameters=params)
            if next(iter(client.query(sql,job_config=qcfg,location=dest['location']).result()),None) is not None:
                LOG.info('Arquivo já ingerido (hash idêntico); carga ignorada')
                return
    schema=[bigquery.SchemaField(c['name'],c['type'].upper(),mode=c.get('mode','NULLABLE').upper()) for c in cols]
    if audit:
        schema += [bigquery.SchemaField('id_execucao','STRING'),bigquery.SchemaField('arquivo_origem','STRING'),bigquery.SchemaField('hash_arquivo','STRING'),bigquery.SchemaField('dt_ingestao','TIMESTAMP')]
    time_partitioning = None
    if partition_enabled:
        time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field=part['field']
        )
    config=bigquery.LoadJobConfig(
        schema=schema,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=dest.get('write_disposition','WRITE_APPEND'),
        create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
        time_partitioning=time_partitioning
    )
    job_result=client.load_table_from_json(rows,table,job_config=config,location=dest['location'])
    job_result.result()
    LOG.info('Carga concluída | job_id=%s | enviados=%d',job_result.job_id,len(rows))

# Lê argumentos e configuração, prepara o logging e coordena os jobs Bronze.
def main():
    parser=argparse.ArgumentParser(description='Framework Bronze parametrizado por JSON')
    parser.add_argument('--config',default='config.json')
    parser.add_argument('--validar',action='store_true')
    parser.add_argument('--job',help='Executa apenas job com este nome')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(levelname)s | %(message)s')
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path(__file__).resolve().parent / config_path
    config_path = config_path.resolve()
    cfg=json.loads(config_path.read_text(encoding='utf-8'))
    jobs=cfg.get('jobs',[])
    required(isinstance(jobs,list) and jobs,'JSON deve conter jobs não vazio')
    selected=[j for j in jobs if args.job is None or j.get('name')==args.job]
    required(selected,'Job não encontrado: {}'.format(args.job))
    for job in selected:
        LOG.info('Job: %s',job.get('name','sem_nome'))
        run_job(job,config_path.parent,args.validar)

if __name__=='__main__':
    main()
