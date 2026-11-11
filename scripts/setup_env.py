#!/usr/bin/env python3
"""Create local demo configuration using only the Python standard library."""
import argparse
from pathlib import Path
import secrets


def main():
    parser = argparse.ArgumentParser(description='Создать .env со случайными секретами для локального демо.')
    parser.add_argument('--port', type=int, default=8000, help='Локальный порт приложения (по умолчанию 8000).')
    parser.add_argument('--enable-ai', action='store_true', help='Включить Gemma через VPN-сервер из .env.example.')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Укажите порт от 1024 до 65535.')
    root = Path(__file__).resolve().parent.parent
    config = (root / '.env.example').read_text(encoding='utf-8')
    replacements = {
        'SECRET_KEY': secrets.token_urlsafe(48),
        'POSTGRES_PASSWORD': secrets.token_urlsafe(32),
        'DEMO_PASSWORD': secrets.token_urlsafe(18),
        'WEB_PORT': str(args.port),
        'AI_ENABLED': '1' if args.enable_ai else '0',
    }
    lines = []
    for line in config.splitlines():
        key = line.split('=', 1)[0]
        lines.append(f'{key}={replacements[key]}' if key in replacements else line)
    path = root / '.env'
    try:
        with path.open('x', encoding='utf-8') as handle:
            path.chmod(0o600)
            handle.write('\n'.join(lines) + '\n')
    except FileExistsError:
        parser.exit(1, '.env уже существует и не изменён. Отредактируйте его вручную.\n')
    print(f'Создан {path}. Пароль демо-аккаунтов указан в DEMO_PASSWORD.')
    print(f'После запуска: http://localhost:{args.port}')
    print('ИИ включён; нужен доступ к VPN-серверу из Docker.' if args.enable_ai else 'ИИ выключен. Основные сценарии работают без внешних сервисов.')


if __name__ == '__main__':
    main()
