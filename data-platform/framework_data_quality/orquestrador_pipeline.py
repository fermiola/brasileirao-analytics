"""Orquestrador local Bronze -> Silver -> Gold. Compatível com Python 3.8."""
import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

LOG = logging.getLogger('pipeline')
ORDER = ('bronze', 'silver', 'gold')
OPTIONAL = ('data_quality',)


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
        stage = cfg['stages'].get(name)
        if not isinstance(stage, dict):
            raise ValueError('Etapa ausente: ' + name)
        for key in ('script', 'config'):
            if not isinstance(stage.get(key), str) or not stage[key].strip():
                raise ValueError('{}.{} ausente'.format(name, key))
            p = resolve_path(path.parent, stage[key])
            if not p.is_file():
                raise ValueError('Arquivo não encontrado ({}.{}): {}'.format(name, key, p))
    for name in OPTIONAL:
        if name in cfg['stages']:
            stage = cfg['stages'][name]
            if not isinstance(stage, dict):
                raise ValueError('Etapa invalida: ' + name)
            for key in ('script', 'config'):
                if not isinstance(stage.get(key), str) or not stage[key].strip():
                    raise ValueError('{}.{} ausente'.format(name, key))
                p = resolve_path(path.parent, stage[key])
                if not p.is_file():
                    raise ValueError('Arquivo nao encontrado ({}.{}): {}'.format(name, key, p))
    return cfg


# Protege a ingestão contra reprocessamento acidental com WRITE_APPEND.
def bronze_append_guard(config_file, permit):
    """Evita reingestão acidental de arquivos em WRITE_APPEND sem deduplicação."""
    if permit:
        return
    cfg = json.loads(config_file.read_text(encoding='utf-8-sig'))
    risky = []
    for j in cfg.get('jobs', []):
        if j.get('enabled', True) is False:
            continue
        dest = j.get('destination', {})
        if dest.get('write_disposition', 'WRITE_APPEND') == 'WRITE_APPEND' and not j.get('skip_if_same_file', False):
            risky.append(j.get('name', '<sem nome>'))
    if risky:
        raise ValueError('Bronze WRITE_APPEND sem skip_if_same_file=true nos jobs: {}. '
                         'Habilite skip_if_same_file no JSON Bronze ou execute com '
                         '--permitir-reingestao para autorizar explicitamente uma nova carga.'.format(', '.join(risky)))


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
    if job and not (name == 'gold' and not validate):
        cmd.extend(['--job', job])
    LOG.info('Iniciando %s | script=%s', name.upper(), script.name)
    start = time.monotonic()
    result = subprocess.run(cmd, cwd=str(script.parent), check=False)
    if result.returncode:
        raise RuntimeError('{} falhou com código {} (pipeline interrompido)'.format(name.upper(), result.returncode))
    LOG.info('%s concluída em %.1f s', name.upper(), time.monotonic() - start)


# Interpreta argumentos de linha de comando e inicia a execução.
def main():
    parser = argparse.ArgumentParser(description='Orquestrador Bronze -> Silver -> Gold')
    parser.add_argument('--config', default='pipeline_config.json')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--all', action='store_true', help='Executar Bronze, Silver e Gold')
    group.add_argument('--silver-gold', action='store_true', help='Executar sem nova ingestão Bronze')
    group.add_argument('--validar', action='store_true', help='Validar as configurações localmente')
    parser.add_argument('--permitir-reingestao', action='store_true', help='Autoriza Bronze WRITE_APPEND sem proteção por hash')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
    path = Path(args.config).resolve()
    cfg = load_config(path)
    stages = ORDER if args.all or args.validar else ('silver', 'gold')
    if 'data_quality' in cfg['stages']:
        stages = stages + ('data_quality',)
    if 'bronze' in stages and not args.validar:
        bronze_append_guard(resolve_path(path.parent, cfg['stages']['bronze']['config']), args.permitir_reingestao)
    for name in stages:
        run_stage(name, cfg['stages'][name], path.parent, args.validar)
    LOG.info('Pipeline %s concluído com sucesso', 'VALIDAÇÃO' if args.validar else 'EXECUÇÃO')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        LOG.error('%s: %s', type(exc).__name__, exc)
        sys.exit(1)
