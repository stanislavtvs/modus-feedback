import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from feedback.followups import check_followups

class Command(BaseCommand):
    help='Проверка забытых обращений и внутрисистемные уведомления.'
    def add_arguments(self,parser):
        parser.add_argument('--once',action='store_true')
        parser.add_argument('--interval',type=int,default=60)
    def handle(self,*args,**options):
        while True:
            close_old_connections()
            result=check_followups()
            if options['once'] or any(result.values()): self.stdout.write(str(result))
            if options['once']: return
            time.sleep(max(10,options['interval']))
