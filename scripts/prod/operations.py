#!/usr/bin/env python3
"""Host-side operations. No shell interpolation or application credentials in reports."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl

APP = Path(__file__).resolve().parents[2]
DEFAULTS = {
    'compose_file': 'docker/prod/docker-compose.yml',
    'backup_root': '/opt/vemdedelivery/backups',
    'release_root': '/opt/vemdedelivery/releases',
    'state_dir': '/opt/vemdedelivery/operations',
    'base_url': 'https://vemdedelivery.com.br',
    'remote': '',
    'require_offsite': False,
    'retention_days': 14,
    'max_backup_age_hours': 30,
    'min_free_gb': 2,
    'webhook_url': '',
    'heartbeat_url': '',
}
CFG = dict(DEFAULTS)
CONFIG_PATH = Path(os.environ.get('VDD_OPERATIONS_CONFIG', '/etc/vemdedelivery/operations.json'))
STAMP = re.compile(r'^20\d{6}_\d{6}(?:_[a-f0-9]{8})?$')
FILES = ('database.dump', 'media.tar.gz', 'manifest.json')


def run(args, *, data=None, output=None, quiet=False, timeout=3600):
    return subprocess.run([str(x) for x in args], cwd=APP, input=data,
                          stdout=output if output is not None else subprocess.PIPE,
                          stderr=subprocess.PIPE, check=True, timeout=timeout).stdout


def dc(*args, **kwargs):
    return run(['docker', 'compose', '-f', CFG['compose_file'], *args], **kwargs)


def capture(*args):
    return dc(*args).decode().strip()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        temp.chmod(0o600)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


@contextmanager
def lock():
    state = Path(CFG['state_dir'])
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / 'operations.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Outra operação de backup/restauração/publicação está em execução.')
        yield


def db_identity():
    user = capture('exec', '-T', 'db', 'printenv', 'POSTGRES_USER')
    name = capture('exec', '-T', 'db', 'printenv', 'POSTGRES_DB')
    if not user or not name:
        raise RuntimeError('Identificação do PostgreSQL ausente.')
    return user, name


def validate_backup(path):
    path = Path(path).resolve()
    if not (path / 'COMPLETE').is_file() or (path / 'FAILED').exists():
        raise RuntimeError('Backup incompleto ou marcado como falho.')
    expected = {}
    for line in (path / 'SHA256SUMS').read_text().splitlines():
        checksum, name = line.split(maxsplit=1)
        name = name.lstrip('*')
        if name not in (*FILES, 'manifest.txt') or name in expected:
            raise RuntimeError('Manifesto de checksums inválido.')
        expected[name] = checksum
    if not {'database.dump', 'media.tar.gz'}.issubset(expected):
        raise RuntimeError('Checksums obrigatórios ausentes.')
    for name, checksum in expected.items():
        target = path / name
        if target.is_symlink() or not target.is_file() or digest(target) != checksum:
            raise RuntimeError('Integridade do backup inválida.')
    # Never extract links, devices or paths outside the target directory.
    with tarfile.open(path / 'media.tar.gz', 'r:gz') as archive:
        for member in archive:
            parts = Path(member.name).parts
            if member.name.startswith('/') or '..' in parts or not (member.isfile() or member.isdir()):
                raise RuntimeError('Arquivo de mídia contém caminho/tipo inseguro.')
    return path


def latest_backup():
    root = Path(CFG['backup_root'])
    candidates = [p for p in root.glob('20*') if STAMP.fullmatch(p.name) and p.is_dir()
                  and not p.is_symlink() and (p / 'COMPLETE').is_file() and not (p / 'FAILED').exists()]
    if not candidates:
        raise RuntimeError('Nenhum backup completo encontrado.')
    return max(candidates, key=lambda p: (p / 'COMPLETE').stat().st_mtime)


def remote_target(name):
    remote = CFG['remote']
    if not remote or ':' not in remote or remote.startswith(('/', ':')):
        raise RuntimeError('Configure um destino remoto do rclone.')
    return remote.rstrip('/') + '/' + name


def upload_backup(path):
    target = remote_target(path.name)
    # Only publish COMPLETE remotely after verified contents. No remote deletion.
    run(['rclone', 'copy', path, target, '--exclude', 'COMPLETE', '--exclude', 'REMOTE_VERIFIED.json', '--exclude', 'REMOTE_FAILED'])
    run(['rclone', 'check', path, target, '--download', '--one-way', '--exclude', 'COMPLETE', '--exclude', 'REMOTE_VERIFIED.json', '--exclude', 'REMOTE_FAILED'])
    run(['rclone', 'copyto', path / 'COMPLETE', target + '/COMPLETE'])
    if run(['rclone', 'cat', target + '/COMPLETE']) != (path / 'COMPLETE').read_bytes():
        raise RuntimeError('Marcador remoto não confirmado.')
    atomic_json(path / 'REMOTE_VERIFIED.json', {'verified_at': time.time(), 'remote': target})
    (path / 'REMOTE_FAILED').unlink(missing_ok=True)


def _backup(prune=True):
    root = Path(CFG['backup_root'])
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / (datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8])
    path.mkdir(mode=0o700)
    try:
        user, name = db_identity()
        with (path / 'database.dump').open('wb') as out:
            dc('exec', '-T', 'db', 'pg_dump', '-U', user, '-d', name, '-Fc', output=out)
        with (path / 'database.dump').open('rb') as source:
            subprocess.run(['docker', 'compose', '-f', CFG['compose_file'], 'exec', '-T', 'db', 'pg_restore', '--list'], cwd=APP, stdin=source, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True, timeout=600)
        with (path / 'media.tar.gz').open('wb') as out:
            dc('run', '--rm', '--no-deps', '-T', '--entrypoint', 'tar', 'web', '-C', '/app/media', '-czf', '-', '.', output=out)
        try:
            commit = run(['git', 'rev-parse', 'HEAD']).decode().strip()
        except subprocess.CalledProcessError:
            commit = 'unknown'
        atomic_json(path / 'manifest.json', {'created_at': time.time(), 'git_commit': commit, 'format': 2, 'media_consistency': 'live-copy'})
        (path / 'SHA256SUMS').write_text(''.join(f'{digest(path / name)}  {name}\n' for name in FILES))
        (path / 'COMPLETE').write_text('complete\n')
        validate_backup(path)
    except Exception:
        (path / 'FAILED').touch()
        raise
    if CFG['remote']:
        try:
            upload_backup(path)
        except Exception:
            (path / 'REMOTE_FAILED').touch()
            raise RuntimeError('Backup local concluído, mas cópia externa falhou; retenção não executada.') from None
    elif CFG['require_offsite']:
        raise RuntimeError('Backup local concluído, mas destino externo obrigatório não foi configurado.')
    else:
        print('AVISO: somente cópia local. Configure remote para proteção fora do servidor.')
    # Only prune our own completed sets; never arbitrary directories or failed sets.
    cutoff = time.time() - int(CFG['retention_days']) * 86400
    for old in (root.iterdir() if prune else []):
        if old == path or old.is_symlink() or not STAMP.fullmatch(old.name) or not (old / 'COMPLETE').is_file():
            continue
        if (old / 'FAILED').exists() or (old / 'REMOTE_FAILED').exists():
            continue
        if CFG['remote'] and not (old / 'REMOTE_VERIFIED.json').exists():
            continue
        if (old / 'COMPLETE').stat().st_mtime < cutoff:
            shutil.rmtree(old)
    print(f'Backup concluído: {path}')


def backup(prune=True):
    state = Path(CFG['state_dir']) / 'backup-run.json'
    atomic_json(state, {'status': 'running', 'started_at': time.time()})
    try:
        _backup(prune=prune)
    except Exception:
        atomic_json(state, {'status': 'failed', 'finished_at': time.time()})
        raise
    atomic_json(state, {'status': 'ok', 'finished_at': time.time()})


def restore_test(path):
    path = validate_backup(path or latest_backup())
    user, _ = db_identity()
    database = 'vdd_restore_test_' + uuid.uuid4().hex[:20]
    dc('exec', '-T', 'db', 'createdb', '-U', user, database)
    try:
        with (path / 'database.dump').open('rb') as source:
            subprocess.run(['docker', 'compose', '-f', CFG['compose_file'], 'exec', '-T', 'db', 'pg_restore', '-U', user, '-d', database, '--no-owner', '--no-privileges', '--exit-on-error', '--single-transaction'], cwd=APP, stdin=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=3600)
        count = capture('exec', '-T', 'db', 'psql', '-U', user, '-d', database, '-At', '-v', 'ON_ERROR_STOP=1', '-c', 'SELECT count(*) FROM django_migrations;')
        if int(count) < 1:
            raise RuntimeError('Banco restaurado sem migrações.')
        with tempfile.TemporaryDirectory(prefix='vdd-media-restore-') as temp:
            with tarfile.open(path / 'media.tar.gz', 'r:gz') as archive:
                # All members have already passed the strict allowlist.
                archive.extractall(temp, **({'filter': 'data'} if hasattr(tarfile, 'data_filter') else {}))
            media_count = sum(1 for p in Path(temp).rglob('*') if p.is_file())
        atomic_json(Path(CFG['state_dir']) / 'restore-test.json', {'tested_at': time.time(), 'backup': path.name, 'migrations': int(count), 'media_files': media_count})
        print('Restauração verificada em banco e pasta temporários; produção preservada.')
    finally:
        dc('exec', '-T', 'db', 'dropdb', '-U', user, '--if-exists', database)


def restore_production(path, confirmed):
    path = validate_backup(path or '')
    user, database = db_identity()
    if not confirmed:
        if not sys.stdin.isatty() or input(f'Digite RESTAURAR {database} para substituir banco e mídia: ') != f'RESTAURAR {database}':
            raise RuntimeError('Restauração cancelada.')
    # Keep even an old target set during the pre-restore backup.
    backup(prune=False)
    services = ('web', 'celery', 'celery-beat', 'nginx')
    dc('stop', *services)
    try:
        with (path / 'database.dump').open('rb') as source:
            subprocess.run(['docker', 'compose', '-f', CFG['compose_file'], 'exec', '-T', 'db', 'pg_restore', '-U', user, '-d', database, '--clean', '--if-exists', '--no-owner', '--no-privileges', '--exit-on-error', '--single-transaction'], cwd=APP, stdin=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=3600)
        dc('run', '--rm', '--no-deps', '-T', '--entrypoint', 'find', 'web', '/app/media', '-mindepth', '1', '-delete')
        with (path / 'media.tar.gz').open('rb') as source:
            subprocess.run(['docker', 'compose', '-f', CFG['compose_file'], 'run', '--rm', '--no-deps', '-T', '--entrypoint', 'tar', 'web', '-C', '/app/media', '-xzf', '-'], cwd=APP, stdin=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=3600)
    except Exception:
        raise RuntimeError('Restauração falhou; aplicação mantida parada. Consulte o backup de segurança antes de retomar.') from None
    print('Banco e mídia restaurados. Aplicação permanece parada: selecione o código/imagem compatível antes de iniciar (o entrypoint pode executar migrações).')


def fetch_backup(name):
    if not STAMP.fullmatch(name):
        raise RuntimeError('Identificador de backup inválido.')
    root = Path(CFG['backup_root'])
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = root / name
    if target.exists():
        raise RuntimeError('O destino já existe; não será sobrescrito.')
    with tempfile.TemporaryDirectory(prefix='.download-', dir=root) as temp:
        run(['rclone', 'copy', remote_target(name), temp])
        validate_backup(temp)
        os.rename(temp, target)
    print(f'Backup externo recuperado e validado: {target}')


def healthy_http():
    for suffix in ('/health/live/', '/health/ready/'):
        request = urllib.request.Request(CFG['base_url'].rstrip('/') + suffix)
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 200:
                raise RuntimeError('Health check HTTP falhou.')


def check():
    problems = []
    for service in ('web', 'db', 'redis', 'celery', 'celery-beat', 'nginx'):
        try:
            container = capture('ps', '-q', service)
            if not container:
                raise RuntimeError()
            state = json.loads(run(['docker', 'inspect', '--format', '{{json .State}}', container]))
            if not state.get('Running') or state.get('Health', {}).get('Status', 'healthy') != 'healthy':
                raise RuntimeError()
        except Exception:
            problems.append(f'Container indisponível ou não saudável: {service}')
    try:
        healthy_http()
    except Exception:
        problems.append('HTTPS/readiness não respondeu corretamente.')
    try:
        dc('exec', '-T', 'web', 'python', 'manage.py', 'check_admin_security', timeout=60)
        dc('exec', '-T', 'web', 'python', 'manage.py', 'migrate', '--check', timeout=60)
    except Exception:
        problems.append('Verificação administrativa/cache/proxy ou migrações pendentes; execute check_admin_security e migrate --check.')
    try:
        # No new public health endpoint. Disabled environments return success.
        dc('exec', '-T', 'web', 'python', 'manage.py', 'check_whatsapp_monitor', '--require-fresh', timeout=30)
    except Exception:
        problems.append('Monitor WhatsApp atrasado, desconectado ou mal configurado; consulte o superadmin e check_whatsapp_monitor --require-fresh.')
    try:
        path = latest_backup()
        age = time.time() - (path / 'COMPLETE').stat().st_mtime
        if age > float(CFG['max_backup_age_hours']) * 3600:
            problems.append('Backup local atrasado.')
        marker = path / 'REMOTE_VERIFIED.json'
        if not CFG['remote'] or not marker.exists() or (path / 'REMOTE_FAILED').exists():
            problems.append('Último backup sem cópia externa verificada.')
        elif json.loads(marker.read_text()).get('remote') != remote_target(path.name):
            problems.append('Backup verificado em destino diferente do configurado.')
    except Exception:
        problems.append('Backup ausente ou estado inválido.')
    last_run = Path(CFG['state_dir']) / 'backup-run.json'
    if last_run.exists():
        try:
            result = json.loads(last_run.read_text())
            if result['status'] == 'failed' or (result['status'] == 'running' and time.time() - result['started_at'] > 7200):
                problems.append('Última execução de backup falhou ou está atrasada.')
        except Exception:
            problems.append('Estado da execução do backup inválido.')
    if not CFG['webhook_url'] and not CFG['heartbeat_url']:
        problems.append('Destino de alertas/heartbeat não configurado.')
    state = Path(CFG['state_dir']) / 'restore-test.json'
    try:
        if time.time() - json.loads(state.read_text())['tested_at'] > 31 * 86400:
            problems.append('Teste de restauração tem mais de 31 dias.')
    except Exception:
        problems.append('Teste de restauração ainda não registrado.')
    if shutil.disk_usage(CFG['backup_root'] if Path(CFG['backup_root']).exists() else APP).free < float(CFG['min_free_gb']) * 1024**3:
        problems.append('Pouco espaço em disco para backups.')
    for problem in problems:
        print('PENDENTE: ' + problem)
    if not problems:
        print('Verificações operacionais aprovadas.')
    return problems


def notify(problems):
    state_path = Path(CFG['state_dir']) / 'monitor.json'
    previous = json.loads(state_path.read_text()) if state_path.exists() else {}
    status = 'failure' if problems else 'ok'
    if CFG['webhook_url'] and (previous.get('status') != status or previous.get('problems') != problems):
        body = json.dumps({'text': 'VemDeDelivery: ' + ('; '.join(problems) if problems else 'operação recuperada.'), 'status': status}).encode()
        req = urllib.request.Request(CFG['webhook_url'], data=body, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=15) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError('Falha ao entregar alerta.')
    if not CFG['webhook_url']:
        print('AVISO: webhook não configurado; alertas somente no log.')
    if CFG['heartbeat_url'] and not problems:
        with urllib.request.urlopen(CFG['heartbeat_url'], timeout=15) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError('Falha ao entregar heartbeat.')
    atomic_json(state_path, {'checked_at': time.time(), 'status': status, 'problems': problems})


def migration_snapshot():
    code = 'import json; from django.db.migrations.recorder import MigrationRecorder; print(json.dumps(sorted(list(MigrationRecorder.Migration.objects.values_list("app", "name")))))'
    output = capture('exec', '-T', 'web', 'python', 'manage.py', 'shell', '-c', code)
    return json.loads(output.splitlines()[-1])


def release_snapshot():
    name = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8]
    path = Path(CFG['release_root']) / name
    path.mkdir(parents=True, mode=0o700)
    services = {}
    for service in ('web', 'celery', 'celery-beat'):
        container = capture('ps', '-q', service)
        if not container:
            raise RuntimeError('Serviço ausente para snapshot: ' + service)
        image = run(['docker', 'inspect', '--format', '{{.Image}}', container]).decode().strip()
        tag = f'vemdedelivery-rollback:{name}-{service}'
        run(['docker', 'image', 'tag', image, tag])
        services[service] = {'image': tag, 'pull_policy': 'never', 'environment': {'RUN_MIGRATIONS': 'false'}}
    atomic_json(path / 'compose.json', {'services': services})
    atomic_json(path / 'release.json', {'created_at': time.time(), 'migrations': migration_snapshot(), 'compose_file': CFG['compose_file'], 'config_hash': hashlib.sha256(dc('config', '--format', 'json')).hexdigest()})
    print(f'Snapshot para retorno de versão: {name}')


def rollback(name, confirmed):
    if not STAMP.fullmatch(name) or not confirmed:
        raise RuntimeError('Use rollback ID --confirm somente para um snapshot revisado.')
    path = Path(CFG['release_root']) / name
    release = json.loads((path / 'release.json').read_text())
    if release['compose_file'] != CFG['compose_file'] or release['migrations'] != migration_snapshot():
        raise RuntimeError('Compose ou migrações mudaram. Retorno automático bloqueado; siga o roteiro de restauração.')
    if release.get('config_hash') != hashlib.sha256(dc('config', '--format', 'json')).hexdigest():
        raise RuntimeError('Configuração/variáveis do Compose mudaram. Revise o retorno manualmente.')
    override = json.loads((path / 'compose.json').read_text())
    for service in override['services'].values():
        run(['docker', 'image', 'inspect', service['image']])
    run(['docker', 'compose', '-f', CFG['compose_file'], '-f', path / 'compose.json', 'up', '-d', '--no-build', '--no-deps', '--force-recreate', 'web', 'celery', 'celery-beat'])
    print('Imagens anteriores restauradas. Aguarde os health checks e execute operations.py check.')


def main():
    if CONFIG_PATH.exists():
        CFG.update(json.loads(CONFIG_PATH.read_text()))
    if os.environ.get('BACKUP_ROOT'):
        CFG['backup_root'] = os.environ['BACKUP_ROOT']
    if os.environ.get('COMPOSE_FILE'):
        CFG['compose_file'] = os.environ['COMPOSE_FILE']
    if int(CFG['retention_days']) < 1:
        raise RuntimeError('Retenção deve ser de pelo menos um dia.')
    if not str(CFG['base_url']).startswith('https://'):
        raise RuntimeError('base_url deve usar HTTPS.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup', 'verify', 'restore-test', 'restore', 'fetch', 'check', 'monitor', 'release-snapshot', 'rollback'])
    parser.add_argument('target', nargs='?')
    parser.add_argument('--confirm', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    if args.action in ('check', 'monitor'):
        problems = check()
        if args.action == 'monitor':
            notify(problems)
        return 1 if problems else 0
    with lock():
        if args.action == 'backup': backup()
        elif args.action == 'verify': validate_backup(args.target or latest_backup()); print('Backup íntegro.')
        elif args.action == 'restore-test': restore_test(args.target)
        elif args.action == 'restore': restore_production(args.target, args.confirm)
        elif args.action == 'fetch': fetch_backup(args.target or '')
        elif args.action == 'release-snapshot': release_snapshot()
        elif args.action == 'rollback': rollback(args.target or '', args.confirm)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Exception, KeyboardInterrupt) as exc:
        # Do not print command stderr: provider errors may contain secrets/URLs.
        message = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print('ERRO: ' + message, file=sys.stderr)
        sys.exit(1)
