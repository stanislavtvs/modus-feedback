from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from feedback.models import Ticket,Category,ProblemTheme,Initiative,InitiativeEvent,InitiativeStep,Event,OutcomeReview,ImprovementPost

class Command(BaseCommand):
    help='Дополнить только DEMO_MODE учебным маршрутом; существующие записи не перезаписываются.'
    @transaction.atomic
    def handle(self,*args,**options):
        if not settings.DEMO_MODE: raise CommandError('Разрешено только в отдельной установке DEMO_MODE=1.')
        User=get_user_model()
        try: employee=User.objects.get(username='employee');manager=User.objects.get(username='manager');admin=User.objects.get(username='admin')
        except User.DoesNotExist: raise CommandError('Сначала выполните seed_demo.')
        category,_=Category.objects.get_or_create(name='Демо · передача заявок',defaults={'responsible':manager,'sla_days':7})
        now=timezone.now();items=[]
        for number,title,description in [
            (1,'Демо: заявка возвращается из-за неполных полей','Учебный пример. При передаче заявки приходится отдельно уточнять формат и срок. Нужен понятный шаблон.'),
            (2,'Демо: сложно передать заявку другому отделу','Учебный пример. В заявках нет одинаковых обязательных полей. Требуется памятка по передаче задач.'),
            (3,'Демо: памятка для новых сотрудников','Учебный пример. Предложение дополнить шаблон короткой памяткой с примерами.')]:
            done=number==3
            ticket,added=Ticket.objects.get_or_create(source_id=f'DEMO-{number:02d}',defaults={'title':title,'description':description,'kind':'idea','category':category,'department':employee.profile.department,'author':employee,'assignee':manager,'status':'implemented' if done else 'work','due_at':now+timedelta(days=7),'first_response_at':now,'resolution':'Учебный результат: подготовлена памятка с примерами.' if done else '', 'resolution_revision':1 if done else 0,'result_offered_at':now if done else None,'closed_at':now if done else None})
            if added: Event.objects.create(ticket=ticket,actor=admin,text='Подготовлено командой демо. Все данные и результаты учебные.')
            items.append(ticket)
        theme,added=ProblemTheme.objects.get_or_create(fingerprint='demo-system-problem',defaults={'title':'Демо: единый процесс передачи заявок','summary':'Учебная тема подготовлена сценарием демонстрации вручную; это не результат живой генерации ИИ. Два обращения относятся к единому шаблону и правилам передачи.','status':'confirmed','created_by':admin,'confirmed_by':manager})
        if added:theme.tickets.set(items[:2])
        initiative,added=Initiative.objects.get_or_create(theme=theme,defaults={'goal':'Демо: сделать передачу заявок понятной','owner':manager,'plan':'1. Проверить недостающие поля на учебных примерах.\n2. Согласовать общий шаблон.\n3. Подготовить памятку.\n4. Получить оценку авторов обращений.','due_date':timezone.localdate()+timedelta(days=14),'status':'work'})
        if added:
            InitiativeEvent.objects.create(initiative=initiative,actor=admin,text='Учебная инициатива подготовлена сценарием демо.')
            for line in initiative.plan.splitlines():
                InitiativeStep.objects.create(initiative=initiative,title=line[:180],owner=initiative.owner,due_date=initiative.due_date)
        ticket=items[2]
        # Re-running never confirms a solution edited during a demonstration.
        if ticket.resolution_revision==1 and ticket.status=='implemented' and ticket.resolution=='Учебный результат: подготовлена памятка с примерами.':
            OutcomeReview.objects.get_or_create(ticket=ticket,revision=1,defaults={'author':employee,'verdict':'helped','comment':'Учебное подтверждение для демонстрации витрины.'})
            ImprovementPost.objects.get_or_create(ticket=ticket,defaults={'source_revision':1,'title':'Демо: от предложения к памятке','before':'В учебном сценарии не хватало понятных примеров.','after':'В учебном сценарии подготовлена памятка.','effect':'Синтетический автор подтвердил учебное решение. Реальный эффект в компании не измерялся.','audience':'company','status':'published','editor':manager,'published_at':now})
        self.stdout.write(self.style.SUCCESS('Учебный маршрут готов. Исходные и уже изменённые записи сохранены.'))
