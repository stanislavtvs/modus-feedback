#!/usr/bin/env python3
"""Separate Compose project and credentials. Never resets an existing database."""
import argparse,os,secrets,subprocess
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description='Изолированное демо с синтетическими данными.')
    parser.add_argument('action',choices=['up','down'])
    parser.add_argument('--enable-ai',action='store_true',help='Включить ИИ при первом создании настроек.')
    parser.add_argument('--port',type=int,default=8031)
    args=parser.parse_args()
    if not 1024<=args.port<=65535: parser.error('Порт должен быть от 1024 до 65535.')
    root=Path(__file__).resolve().parent.parent;config=root/'.env.demo'
    if not config.exists():
        if args.action=='down': parser.exit(1,'Демо ещё не настроено.\n')
        values={'SECRET_KEY':secrets.token_urlsafe(48),'POSTGRES_PASSWORD':secrets.token_urlsafe(32),'DEMO_PASSWORD':secrets.token_urlsafe(18),'WEB_PORT':str(args.port),'AI_ENABLED':'1' if args.enable_ai else '0','POSTGRES_DB':'modus_demo','DEMO_MODE':'1'}
        lines=[]
        for line in (root/'.env.example').read_text().splitlines():
            key=line.split('=',1)[0];lines.append(f'{key}={values[key]}' if key in values else line)
        with config.open('x') as stream:
            config.chmod(0o600);stream.write('\n'.join(lines)+'\nAPP_ENV_FILE=.env.demo\n')
    configured=dict(line.split('=',1) for line in config.read_text().splitlines() if '=' in line and not line.lstrip().startswith('#'))
    if configured.get('DEMO_MODE')!='1' or configured.get('APP_ENV_FILE')!='.env.demo': parser.exit(1,'В .env.demo должны быть DEMO_MODE=1 и APP_ENV_FILE=.env.demo. Настройки не изменены.\n')
    # Do not inherit settings from an unrelated shell or the working installation.
    env=os.environ.copy()
    for key in ['COMPOSE_PROJECT_NAME','APP_ENV_FILE','SECRET_KEY','POSTGRES_PASSWORD','POSTGRES_DB','POSTGRES_USER','WEB_PORT','AI_ENABLED','DEMO_MODE']: env.pop(key,None)
    command=['docker','compose','--env-file',str(config),'-p','modus-demo','-f',str(root/'compose.yaml')]
    def run(*tail): subprocess.run(command+list(tail),cwd=root,env=env,check=True)
    if args.action=='down':run('down');return
    run('up','-d','--build','--wait')
    run('exec','-T','web','python','manage.py','seed_demo')
    run('exec','-T','web','python','manage.py','seed_showcase')
    port=next(line.split('=',1)[1] for line in config.read_text().splitlines() if line.startswith('WEB_PORT='))
    print(f'Готово: http://127.0.0.1:{port}/demo/ . Пароль: DEMO_PASSWORD в .env.demo. Рабочая база не использовалась.')

if __name__=='__main__': main()
