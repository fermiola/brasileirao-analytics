# -*- coding: utf-8 -*-
"""Atualiza o snapshot de monitoramento e inicia o dashboard Streamlit.

Uso: python orquestrador_dashboard.py
Execute a partir de qualquer diretorio; os scripts sao localizados ao lado deste arquivo.
"""
import subprocess
import sys
from pathlib import Path


def main():
    pasta = Path(__file__).resolve().parent
    exportador = pasta / 'exportar_monitoramento.py'
    aplicativo = pasta / 'app.py'

    for arquivo in (exportador, aplicativo):
        if not arquivo.is_file():
            print('ERRO: arquivo nao encontrado: {}'.format(arquivo), file=sys.stderr)
            return 1

    print('1/2 - Atualizando monitoramento...', flush=True)
    resultado = subprocess.run([sys.executable, str(exportador)], cwd=str(pasta), check=False)
    if resultado.returncode != 0:
        print('ERRO: exportacao falhou (codigo {}). Dashboard nao iniciado.'.format(resultado.returncode), file=sys.stderr)
        return resultado.returncode

    print('2/2 - Iniciando Streamlit...', flush=True)
    try:
        return subprocess.run(
            [sys.executable, '-m', 'streamlit', 'run', str(aplicativo)],
            cwd=str(pasta), check=False
        ).returncode
    except KeyboardInterrupt:
        print('\nDashboard encerrado.')
        return 0


if __name__ == '__main__':
    sys.exit(main())
