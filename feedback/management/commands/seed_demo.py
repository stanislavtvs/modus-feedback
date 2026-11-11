import json,os
from datetime import timedelta
from pathlib import Path
from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from django.conf import settings
from django.utils import timezone
from feedback.models import Department,Profile,Category,Ticket,Event
class Command(BaseCommand):
    help='Load synthetic hackathon data; existing records are preserved.'
    @transaction.atomic
    def handle(self,*args,**options):
        password=os.getenv('DEMO_PASSWORD')
        if not password or len(password)<12: raise CommandError('Set DEMO_PASSWORD to at least 12 characters')
        User=get_user_model()
        departments={name:Department.objects.get_or_create(name=name)[0] for name in ['Закупки','Бухгалтерия','Продажи','Проектирование','Офис']}
        def user(login,name,department,role):
            obj,created=User.objects.get_or_create(username=login,defaults={'first_name':name,'is_staff':role=='admin','is_superuser':role=='admin'})
            if created: obj.set_password(password);obj.save()
            Profile.objects.get_or_create(user=obj,defaults={'department':department,'role':role})
            return obj
        employee=user('employee','Анна',departments['Закупки'],'employee')
        manager=user('manager','Михаил',departments['Закупки'],'manager')
        admin=user('admin','Администратор',departments['Офис'],'admin')
        rows=json.loads((settings.BASE_DIR/'data/demo.json').read_text())
        for i,row in enumerate(rows):
            dept=departments['Закупки'] if 'закупок' in row['author'] else departments['Бухгалтерия'] if 'бухгалтерии' in row['author'] else departments['Продажи'] if 'продажам' in row['author'] else departments['Офис'] if 'офиса' in row['author'] else departments['Проектирование']
            author=employee if dept==departments['Закупки'] else user('demo_author_'+str(dept.pk),'Сотрудник '+dept.name,dept,'employee')
            owner=manager if dept==departments['Закупки'] else user('demo_manager_'+str(dept.pk),'Руководитель '+dept.name,dept,'manager')
            cat,_=Category.objects.get_or_create(name=row['category'],defaults={'responsible':owner,'sla_days':7})
            status={v:k for k,v in Ticket.Status.choices}[row['status']]
            created=timezone.now()-timedelta(days=20-i)
            terminal=status in ['implemented','rejected','closed']
            text=row['description']
            ticket,added=Ticket.objects.get_or_create(source_id=row['id'],defaults={'title':row.get('title',text.split('.')[0][:175]),'description':text,'kind':{v:k for k,v in Ticket.Kind.choices}[row['kind']],'category':cat,'department':dept,'author':author,'assignee':owner,'priority':{v:k for k,v in Ticket.Priority.choices}[row['priority']],'status':status,'created_at':created,'due_at':created+timedelta(days=7),'resolution':row['action'] if terminal or status=='clarify' else '', 'closed_at':created+timedelta(days=3) if terminal else None,'first_response_at':created+timedelta(hours=8) if status!='new' else None})
            if added:
                Event.objects.create(ticket=ticket,actor=author,text='Импортировано синтетическое обращение '+row['id']+'. Условный ответственный из датасета: '+row['owner'],created_at=created)
                if status!='new': Event.objects.create(ticket=ticket,actor=owner,text='Демонстрационный статус: '+row['status']+'. '+row['action'],created_at=created+timedelta(hours=8))
        self.stdout.write(self.style.SUCCESS('Loaded 20 synthetic requests. Accounts: employee, manager, admin. Password: DEMO_PASSWORD.'))
