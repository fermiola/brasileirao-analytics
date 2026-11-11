# -*- coding: utf-8 -*-
"""Execute LOCALMENTE com ADC GCP; exporta snapshots da Gold para publicar."""
import json
from pathlib import Path
import pandas as pd
from google.cloud import bigquery

BASE = Path(__file__).resolve().parent
CONFIG = json.loads((BASE / 'config.json').read_text(encoding='utf-8'))
PROJECT = CONFIG['project']
DATASET = CONFIG['dataset']
LOCATION = CONFIG.get('location', 'US')
MAX_BYTES = int(CONFIG.get('maximum_bytes_billed', 1000000000))
TABLES = ('tb_classificacao', 'tb_desempenho_clube', 'tb_estatisticas_rodada', 'tb_forma_recente')

def main():
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    folder = BASE / 'data'
    folder.mkdir(parents=True, exist_ok=True)
    for table in TABLES:
        sql = 'SELECT * FROM `{}.{}.{}`'.format(PROJECT, DATASET, table)
        job_config = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES, use_query_cache=True)
        rows = client.query(sql, job_config=job_config, location=LOCATION).result()
        frame = pd.DataFrame([dict(row.items()) for row in rows])
        if frame.empty:
            raise RuntimeError('Tabela vazia: {}. Exportação interrompida.'.format(table))
        path = folder / (table + '.csv')
        frame.to_csv(path, index=False, encoding='utf-8')
        print('{}: {} registros -> {}'.format(table, len(frame), path))
    print('Exportação concluída. Revise os CSVs antes de publicar.')

if __name__ == '__main__':
    main()
