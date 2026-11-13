# -*- coding: utf-8 -*-
"""Brasileirao Analytics AI - interface Streamlit local (Python 3.8)."""
import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from google.cloud import bigquery

BASE = Path(__file__).resolve().parent
CONFIG = json.loads((BASE / 'config.json').read_text(encoding='utf-8'))
MODE = os.environ.get('DATA_MODE', CONFIG.get('data_mode', 'csv')).strip().lower()
PROJECT = CONFIG['project']
DATASET = CONFIG['dataset']
LOCATION = CONFIG.get('location', 'US')
TTL = int(CONFIG.get('cache_ttl_seconds', 3600))
MAX_BYTES = int(CONFIG.get('maximum_bytes_billed', 1000000000))

st.set_page_config(page_title='Brasileirão Analytics | 2026', page_icon='⚽', layout='wide')
st.markdown('''<style>
.stApp {background-color:#101827;color:#f8fafc;}
h1,h2,h3 {color:#f8fafc;}
[data-testid="stMetric"] {background:#1e293b;padding:14px;border-radius:10px;}
</style>''', unsafe_allow_html=True)

@st.cache_resource
def get_client():
    return bigquery.Client(project=PROJECT, location=LOCATION)

ALLOWED_TABLES = {'tb_classificacao', 'tb_desempenho_clube', 'tb_estatisticas_rodada', 'tb_forma_recente'}

@st.cache_data(ttl=TTL, show_spinner='Carregando dados analíticos...')
def load_table(table):
    if table not in ALLOWED_TABLES:
        raise ValueError('Tabela não permitida: ' + table)
    if MODE == 'csv':
        path = BASE / 'data' / (table + '.csv')
        if not path.is_file():
            raise FileNotFoundError('Arquivo ausente: {}. Execute exportar_gold.py no seu computador.'.format(path))
        return pd.read_csv(path, encoding='utf-8')
    if MODE != 'bigquery':
        raise ValueError('data_mode deve ser csv ou bigquery')
    sql = 'SELECT * FROM `{}.{}.{}`'.format(PROJECT, DATASET, table)
    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES, use_query_cache=True)
    rows = get_client().query(sql, job_config=job_config, location=LOCATION).result()
    return pd.DataFrame([dict(row.items()) for row in rows])

def filter_season(frame, season):
    return frame[frame['temporada'].astype(str) == str(season)].copy()

def show_table(frame, columns, names=None):
    available = [c for c in columns if c in frame.columns]
    result = frame[available].copy()
    if names:
        result = result.rename(columns=names)
    st.dataframe(result, use_container_width=True, hide_index=True)

st.title('⚽ BRASILEIRÃO ANALYTICS')
st.caption('Plataforma de dados • BigQuery Gold • Streamlit')
if MODE == 'csv':
    st.caption('Dados publicados em snapshot • filtros e gráficos interativos')

try:
    classificacao = load_table('tb_classificacao')
except Exception as exc:
    st.error('Não foi possível carregar os dados: {}'.format(exc))
    st.info('Modo público: execute exportar_gold.py localmente e inclua os arquivos CSV em data/. Modo BigQuery: confira as credenciais.')
    st.stop()

if classificacao.empty:
    st.warning('A tabela Gold de classificação está vazia.')
    st.stop()

seasons = sorted(classificacao['temporada'].dropna().unique().tolist(), reverse=True)
with st.sidebar:
    st.header('Filtros')
    season = st.selectbox('Temporada', seasons)
    if st.button('Atualizar dados'):
        load_table.clear()
        load_monitoramento.clear()
        st.rerun()
    st.caption('Dados em cache por {} minutos. Fonte: {}.'.format(TTL // 60, 'snapshot CSV' if MODE == 'csv' else 'BigQuery'))

page = st.sidebar.radio('Página', ['Monitoramento', 'Classificação', 'Mandante x Visitante', 'Evolução por rodada', 'Forma recente'], index=0)

@st.cache_data(ttl=TTL)
def load_monitoramento():
    path = BASE / 'data' / 'monitoramento.json'
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def status_label(value):
    return {'sucesso': 'Sucesso', 'falha': 'Falha', 'em_execucao': 'Em execução',
            'indisponivel': 'Indisponível'}.get(value, 'Indisponível')


def format_brasilia(value):
    if not value:
        return 'Indisponível'
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if dt.tzinfo is None:
            return 'Indisponível'
        return dt.astimezone(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M:%S')
    except (ValueError, TypeError, KeyError):
        return 'Indisponível'

def show_monitoramento():
    st.subheader('MONITORAMENTO • PIPELINE E QUALIDADE')
    st.caption('Retrato exportado do BigQuery. Não é monitoramento em tempo real.')
    metadata = load_monitoramento()
    if metadata is None:
        st.info('Execute localmente: python exportar_monitoramento.py')
        return
    st.caption('Metadados exportados em: {} (Brasília)'.format(format_brasilia(metadata.get('gerado_em_utc'))))
    execution = metadata.get('execucoes') or {}
    recent = execution.get('ultima_execucao') or {}
    quality = metadata.get('data_quality') or {}
    summary = quality.get('resumo_lote')
    a, b, c = st.columns(3)
    a.metric('Status do pipeline', status_label(recent.get('status')))
    b.metric('DQ aprovadas', summary.get('aprovadas', 0) if summary else '—')
    c.metric('DQ reprovadas', summary.get('reprovadas', 0) if summary else '—')
    st.caption('Última execução registrada: {} (Brasília)'.format(format_brasilia(recent.get('data_execucao'))))
    if summary is None:
        st.info('Não foi possível identificar o último lote de Data Quality.')
    if recent.get('status') == 'falha':
        st.error('A última execução registrada indica falha.')
    elif recent.get('status') != 'sucesso':
        st.warning('Não foi possível confirmar sucesso da última execução.')
    if summary and summary['reprovadas']:
        st.error('Existem verificações reprovadas no último lote de Data Quality identificado.')
    if not execution.get('ordenacao_confiavel', False):
        st.warning('A ordem das execuções não está validada.')
    st.markdown('#### Execuções recentes')
    executions = execution.get('execucoes_recentes') or []
    if executions:
        df = pd.DataFrame(executions)
        df['data_execucao'] = df['data_execucao'].map(format_brasilia)
        df['status'] = df['status'].map(status_label)
        df['possui_erro'] = df['possui_erro'].map({True: 'Sim', False: 'Não'}).fillna('Indisponível')
        st.dataframe(df.rename(columns={'data_execucao': 'Data/hora (Brasília)', 'etapa': 'Etapa', 'status': 'Status', 'possui_erro': 'Possui erro'}), use_container_width=True, hide_index=True)
    else:
        st.info('Nenhuma execução disponível.')
    st.markdown('#### Data Quality • verificações recentes')
    checks = quality.get('verificacoes_recentes') or []
    if checks:
        df = pd.DataFrame(checks)
        df['data_execucao'] = df['data_execucao'].map(format_brasilia)
        df['status'] = df['status'].map(status_label)
        cols = [c for c in ['data_execucao', 'regra', 'status', 'violacoes'] if c in df.columns]
        st.dataframe(df[cols].rename(columns={'data_execucao': 'Data/hora (Brasília)', 'regra': 'Regra', 'status': 'Status', 'violacoes': 'Violações'}), use_container_width=True, hide_index=True)
        st.caption('Registros recentes podem pertencer a diferentes execuções.')
    else:
        st.info('Nenhuma verificação disponível.')
    for warning in metadata.get('avisos') or []:
        st.warning(warning)
    st.caption('Atualizar dados recarrega snapshots publicados; não executa o pipeline nem consulta o BigQuery.')

if page == 'Classificação':
    st.subheader('CLASSIFICAÇÃO GERAL')
    data = filter_season(classificacao, season).sort_values('posicao')
    a, b, c = st.columns(3)
    a.metric('Clubes', len(data))
    b.metric('Jogos disputados', int(data['jogos'].sum() // 2))
    c.metric('Líder', str(data.iloc[0]['clube']) if len(data) else '-')
    cols = ['posicao','clube','pontos','jogos','vitorias','empates','derrotas','saldo_gols','aproveitamento']
    labels = {'posicao':'Pos.','clube':'Clube','pontos':'Pts','jogos':'J','vitorias':'V','empates':'E','derrotas':'D','saldo_gols':'SG','aproveitamento':'Apr. %'}
    def color_row(row):
        p = int(row['Pos.'])
        color = '#60a5fa' if p <= 4 else ('#f87171' if p >= 17 else '#f8fafc')
        return ['color: {}; background-color: #1e293b'.format(color)] * len(row)
    result = data[cols].rename(columns=labels)
    st.dataframe(result.style.apply(color_row, axis=1).format({'Apr. %':'{:.2f}'}), use_container_width=True, hide_index=True)
    st.caption('Posições calculadas pela regra estatística da tabela Gold; critérios oficiais de desempate podem diferir.')

elif page == 'Mandante x Visitante':
    st.subheader('DESEMPENHO • MANDANTE X VISITANTE')
    data = filter_season(load_table('tb_desempenho_clube'), season)
    if data.empty:
        st.warning('Sem dados para esta temporada.')
    else:
        clubs = sorted(data['clube'].dropna().unique().tolist())
        selected = st.multiselect('Clubes', clubs, default=clubs[:5])
        view = data[data['clube'].isin(selected)] if selected else data
        fig = px.bar(view, x='aproveitamento', y='clube', color='mando', barmode='group', orientation='h',
                     color_discrete_sequence=['#22c55e','#60a5fa'], labels={'clube':'Clube','aproveitamento':'Aproveitamento (%)','mando':'Mando'})
        fig.update_layout(paper_bgcolor='#101827', plot_bgcolor='#101827', font_color='#f8fafc', height=max(420, len(view['clube'].unique()) * 42))
        st.plotly_chart(fig, use_container_width=True)
        show_table(view.sort_values(['clube','mando']), ['clube','mando','jogos','vitorias','empates','derrotas','pontos','aproveitamento'])

elif page == 'Evolução por rodada':
    st.subheader('EVOLUÇÃO DA CLASSIFICAÇÃO')
    data = filter_season(load_table('tb_estatisticas_rodada'), season)
    if data.empty:
        st.warning('Sem dados para esta temporada.')
    else:
        clubs = sorted(data['clube'].dropna().unique().tolist())
        selected = st.multiselect('Clubes', clubs, default=clubs[:4])
        view = data[data['clube'].isin(selected)] if selected else data
        fig = px.line(view.sort_values('rodada'), x='rodada', y='posicao_apos_rodada', color='clube', markers=True,
                      labels={'rodada':'Rodada','posicao_apos_rodada':'Posição','clube':'Clube'})
        fig.update_yaxes(autorange='reversed', dtick=1)
        fig.update_layout(paper_bgcolor='#101827', plot_bgcolor='#101827', font_color='#f8fafc', height=520)
        st.plotly_chart(fig, use_container_width=True)
        st.caption('Evolução registrada nas rodadas com partidas finalizadas.')

elif page == 'Monitoramento':
    show_monitoramento()

elif page == 'Forma recente':
    st.subheader('FORMA RECENTE • ÚLTIMOS CINCO JOGOS')
    data = filter_season(load_table('tb_forma_recente'), season)
    if data.empty:
        st.warning('Sem dados para esta temporada.')
    else:
        cols = ['clube','sequencia_resultados','jogos','vitorias','empates','derrotas','pontos','aproveitamento']
        show_table(data.sort_values('pontos', ascending=False), cols,
                   {'clube':'Clube','sequencia_resultados':'Sequência','jogos':'J','vitorias':'V','empates':'E','derrotas':'D','pontos':'Pts','aproveitamento':'Apr. %'})

st.divider()
st.caption('Brasileirão Data Platform | Python • GCP • BigQuery • Streamlit')
