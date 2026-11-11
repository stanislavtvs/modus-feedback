import json,os
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase,override_settings
from django.core import signing
from django.core.management import call_command,CommandError
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import Department,Profile,Category,Ticket,OutcomeReview,ProblemTheme,Initiative,InitiativeEvent,ImprovementPost
from .test_helpers import approved_post
from .privacy import inspect

class DevelopmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a=Department.objects.create(name='Закупки');cls.b=Department.objects.create(name='Продажи')
        def user(name,role,dept):
            u=get_user_model().objects.create_user(username=name,password='test-password-long');Profile.objects.create(user=u,role=role,department=dept);return u
        cls.employee=user('employee','employee',cls.a);cls.manager=user('manager','manager',cls.a);cls.other=user('other','employee',cls.b);cls.foreign=user('foreign','manager',cls.b);cls.admin=user('admin','admin',cls.b)
        cls.category=Category.objects.create(name='Процесс',responsible=cls.manager)
        cls.tickets=[]
        for n in range(2):cls.tickets.append(Ticket.objects.create(title=f'Проблема {n}',description='Связь: anna@example.com, +7 (777) 123-45-67; ИИН 123456789012.',kind='problem',category=cls.category,department=cls.a,author=cls.employee,assignee=cls.manager,due_at=timezone.now()+timedelta(days=7)))
        cls.theme=ProblemTheme.objects.create(title='Общий процесс',summary='Нужен шаблон',status='confirmed',created_by=cls.manager,confirmed_by=cls.manager,fingerprint='system');cls.theme.tickets.set(cls.tickets)
    def fields(self,**changes):
        data={'goal':'Упростить передачу','owner':self.manager.pk,'plan':'Проверить поля. Подготовить шаблон. Получить оценку авторов.','due_date':'2026-12-15','status':'work','result':''};data.update(changes);return data
    def test_initiative_confirmed_group_only_and_access(self):
        url=reverse('initiative',args=[self.theme.pk])
        for user in [self.employee,self.other,self.foreign]:
            self.client.force_login(user);self.assertEqual(self.client.get(url).status_code,404)
        self.client.force_login(self.manager);self.assertEqual(self.client.get(url).status_code,200)
        self.theme.status='proposed';self.theme.save();self.assertEqual(self.client.get(url).status_code,404)
    def test_initiative_owner_cannot_gain_access_and_fields_validated(self):
        self.client.force_login(self.admin);url=reverse('initiative',args=[self.theme.pk])
        response=self.client.post(url,self.fields(owner=self.foreign.pk));self.assertEqual(response.status_code,200);self.assertFalse(Initiative.objects.exists())
        response=self.client.post(url,self.fields(status='done',result=''));self.assertEqual(response.status_code,200);self.assertFalse(Initiative.objects.exists())
        self.client.post(url,self.fields(plan='x'*5001));self.assertFalse(Initiative.objects.exists())
    def test_initiative_workflow_does_not_close_tickets_and_history(self):
        self.client.force_login(self.manager);url=reverse('initiative',args=[self.theme.pk])
        self.assertEqual(self.client.post(url,self.fields()).status_code,302)
        self.client.post(url,self.fields(status='done',result='Проверили шаблон. Авторы отдельно проверят результат.'))
        item=Initiative.objects.get();self.assertEqual(item.status,'done');self.assertEqual(InitiativeEvent.objects.count(),2)
        self.assertEqual(Ticket.objects.filter(status='new').count(),2);self.assertFalse(OutcomeReview.objects.exists())
        self.client.post(url,self.fields(status='done',result=item.result));self.assertEqual(Initiative.objects.count(),1);self.assertEqual(InitiativeEvent.objects.count(),2)
    def test_initiative_hidden_if_any_member_becomes_foreign(self):
        self.client.force_login(self.manager);self.client.post(reverse('initiative',args=[self.theme.pk]),self.fields())
        ticket=self.tickets[1];ticket.department=self.b;ticket.assignee=self.foreign;ticket.save()
        self.assertEqual(self.client.get(reverse('initiative',args=[self.theme.pk])).status_code,404)
        self.assertNotContains(self.client.get(reverse('pulse')),'Упростить передачу')
    def test_pulse_scoped_current_revision_confirmations_and_returns(self):
        first,second=self.tickets
        Ticket.objects.filter(pk=first.pk).update(status='implemented',resolution_revision=2)
        OutcomeReview.objects.create(ticket=first,revision=1,author=self.employee,verdict='not_helped')
        OutcomeReview.objects.create(ticket=first,revision=2,author=self.employee,verdict='helped')
        Ticket.objects.filter(pk=second.pk).update(status='implemented',resolution_revision=2)
        OutcomeReview.objects.create(ticket=second,revision=1,author=self.employee,verdict='helped')
        self.client.force_login(self.manager);response=self.client.get(reverse('pulse'));row=response.context['rows'][0]
        self.assertEqual((row['confirmed'],row['offered'],row['returned'],row['confirmation_percent']),(1,2,1,50))
        self.client.force_login(self.other);self.assertEqual(self.client.get(reverse('pulse')).context['rows'],[])
        self.client.force_login(self.employee);self.assertContains(self.client.get(reverse('pulse')),'не полная статистика подразделений')
    @patch('feedback.ai_views.generate')
    def test_preview_does_not_call_model_and_masks_only_outgoing_copy(self,model):
        self.client.force_login(self.employee);url=reverse('ai_analyze',args=[self.tickets[0].pk])
        preview=self.client.post(url).json();model.assert_not_called()
        self.assertIn('anna@example.com',json.dumps(preview['preview']['original']))
        self.assertNotIn('anna@example.com',json.dumps(preview['preview']['masked']))
        self.assertEqual(len(preview['preview']['findings']),3)
        model.return_value={'summary':'s','plain_language':'p','questions':[],'next_steps':[],'reply_draft':'r'}
        response=self.client.post(url,json.dumps({'privacy_token':preview['privacy_token'],'hide_sensitive':True}),content_type='application/json');self.assertEqual(response.status_code,200)
        sent=model.call_args.args[2];self.assertNotIn('anna@example.com',sent['description']);self.assertNotIn('123456789012',sent['description'])
        self.tickets[0].refresh_from_db();self.assertIn('anna@example.com',self.tickets[0].description)
    @patch('feedback.ai_views.generate')
    def test_explicit_unmasked_choice_and_invalid_tokens(self,model):
        model.return_value={'summary':'s','plain_language':'p','questions':[],'next_steps':[],'reply_draft':'r'}
        self.client.force_login(self.employee);url=reverse('ai_analyze',args=[self.tickets[0].pk]);approved_post(self.client,url,hide=False)
        self.assertIn('anna@example.com',model.call_args.args[2]['description']);model.reset_mock()
        token=self.client.post(url).json()['privacy_token']
        for body in [{'privacy_token':token+'x','hide_sensitive':True},{'privacy_token':token,'hide_sensitive':'true'}]:
            self.assertEqual(self.client.post(url,json.dumps(body),content_type='application/json').status_code,409)
        model.assert_not_called()
    @patch('feedback.ai_views.generate')
    def test_preview_invalidated_by_changed_text_user_and_expiry(self,model):
        self.client.force_login(self.employee);url=reverse('ai_analyze',args=[self.tickets[0].pk]);token=self.client.post(url).json()['privacy_token']
        def send():return self.client.post(url,json.dumps({'privacy_token':token,'hide_sensitive':True}),content_type='application/json')
        self.client.force_login(self.manager);self.assertEqual(send().status_code,409)
        self.client.force_login(self.employee)
        with patch('django.core.signing.time.time',return_value=timezone.now().timestamp()+400):self.assertEqual(send().status_code,409)
        Ticket.objects.filter(pk=self.tickets[0].pk).update(description='Текст изменился');self.assertEqual(send().status_code,409);model.assert_not_called()
    @patch('feedback.ai_views.generate')
    def test_form_confirmation_requires_explicit_mask_choice(self,model):
        self.client.force_login(self.employee)
        url=reverse('ai_analyze',args=[self.tickets[0].pk]);token=self.client.post(url).json()['privacy_token']
        for data in [{'privacy_token':token},{'privacy_token':token,'hide_sensitive':'invalid'}]:
            self.assertEqual(self.client.post(url,data).status_code,409)
        model.assert_not_called()

    def test_mask_preserves_ids_and_handles_passport(self):
        packet,findings=inspect({'id':123456789012,'text':'Паспорт 12 34 567890. test@site.ru; 8 999 123 45 67.'})
        self.assertEqual(packet['id'],123456789012);self.assertNotIn('567890',packet['text']);self.assertEqual(sum(item['count'] for item in findings),3)
    @override_settings(DEMO_MODE=False)
    def test_demo_route_and_seed_denied_on_working_installation(self):
        self.client.force_login(self.admin);self.assertEqual(self.client.get(reverse('demo')).status_code,404)
        with self.assertRaises(CommandError):call_command('seed_showcase',verbosity=0)
        self.assertFalse(Ticket.objects.filter(source_id__startswith='DEMO-').exists())
    @override_settings(DEMO_MODE=True)
    def test_demo_seed_idempotent_and_preserves_demo_changes(self):
        with patch.dict(os.environ,{'DEMO_PASSWORD':'temporary-test-password-123'}):call_command('seed_demo',verbosity=0)
        call_command('seed_showcase',verbosity=0);call_command('seed_showcase',verbosity=0)
        self.assertEqual(Ticket.objects.filter(source_id__startswith='DEMO-').count(),3)
        result=Ticket.objects.get(source_id='DEMO-03');self.assertEqual(ImprovementPost.objects.get(ticket=result).status,'published')
        result.title='Отредактировано на показе';result.status='work';result.resolution_revision=2;result.save()
        call_command('seed_showcase',verbosity=0);result.refresh_from_db();self.assertEqual(result.title,'Отредактировано на показе');self.assertEqual(result.status,'work')
        self.assertFalse(OutcomeReview.objects.filter(ticket=result,revision=2).exists())
        self.client.force_login(self.employee);self.assertContains(self.client.get(reverse('demo')),'Все данные и результаты учебные')
