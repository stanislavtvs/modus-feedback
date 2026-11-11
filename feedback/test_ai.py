import json
from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from .test_helpers import approved_post
from .models import Department,Profile,Category,Ticket,AIRequestLock
from .ai import validate,schema_for,AIInvalidResponse,AIUnavailable,generate,AIBusy

class AssistantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department=Department.objects.create(name='Закупки')
        cls.user=get_user_model().objects.create_user('author',password='test-ai-password-123')
        cls.other=get_user_model().objects.create_user('other')
        cls.manager=get_user_model().objects.create_user('manager')
        Profile.objects.create(user=cls.user,department=cls.department)
        Profile.objects.create(user=cls.other,department=cls.department)
        Profile.objects.create(user=cls.manager,department=cls.department,role='manager')
        cls.category=Category.objects.create(name='Процессы')
        cls.ticket=Ticket.objects.create(title='Заявка',description='Нужен единый шаблон для заявок',kind='idea',author=cls.user,department=cls.department,category=cls.category,assignee=cls.manager,due_at=timezone.now()+timedelta(days=7))
    def draft_result(self):
        return {'title':'Единый шаблон заявок','description':'Предлагаю единый шаблон для заявок.', 'category_id':self.category.pk,'kind':'idea','priority':'medium','reason':'Улучшение процесса','questions':[]}
    def analysis(self):
        return {'summary':'Нужен шаблон','plain_language':'Сотрудник предлагает единый бланк.','questions':['Какие поля нужны?'],'next_steps':['Уточнить поля'],'reply_draft':'Спасибо за предложение. Какие поля нужны?'}
    def test_draft_requires_authentication_and_post(self):
        self.assertEqual(self.client.post(reverse('ai_draft')).status_code,302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('ai_draft')).status_code,405)
    @patch('feedback.ai_views.generate')
    def test_draft_input_validation(self,mock):
        self.client.force_login(self.user)
        for body in [{'description':'x'},[],{'description':3},{'description':'x'*8001}]:
            response=self.client.post(reverse('ai_draft'),json.dumps(body),content_type='application/json')
            self.assertEqual(response.status_code,400)
        mock.assert_not_called()
    @patch('feedback.ai_views.generate')
    def test_draft_is_proposal_and_does_not_create_ticket(self,mock):
        mock.return_value=self.draft_result()
        self.client.force_login(self.user)
        before=Ticket.objects.count()
        response=approved_post(self.client,reverse('ai_draft'),{'description':'Нужен единый шаблон для заявок'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['result']['category_name'],'Процессы')
        self.assertEqual(Ticket.objects.count(),before)
    @patch('feedback.ai_views.generate')
    def test_private_ticket_not_sent_to_model(self,mock):
        self.client.force_login(self.other)
        self.assertEqual(approved_post(self.client,reverse('ai_analyze',args=[self.ticket.pk])).status_code,404)
        mock.assert_not_called()
    @patch('feedback.ai_views.generate')
    def test_author_gets_summary_without_manager_draft(self,mock):
        mock.return_value=self.analysis()
        self.client.force_login(self.user)
        response=approved_post(self.client,reverse('ai_analyze',args=[self.ticket.pk]))
        self.assertEqual(response.status_code,200)
        self.assertNotIn('reply_draft',response.json()['result'])
        source=mock.call_args.args[2]
        self.assertNotIn('author',source)
        self.assertNotIn('attachments',source)
    @patch('feedback.ai_views.generate')
    def test_manager_receives_draft_without_mutation(self,mock):
        mock.return_value=self.analysis()
        self.client.force_login(self.manager)
        response=approved_post(self.client,reverse('ai_analyze',args=[self.ticket.pk]))
        self.assertIn('reply_draft',response.json()['result'])
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.resolution,'')
        self.assertEqual(self.ticket.status,'new')
    @patch('feedback.ai_views.generate',side_effect=AIUnavailable)
    def test_unavailable_service_is_explained(self,mock):
        self.client.force_login(self.user)
        self.assertEqual(approved_post(self.client,reverse('ai_analyze',args=[self.ticket.pk])).status_code,503)
    def test_response_schema_validation(self):
        schema=schema_for('draft',[{'id':self.category.pk,'name':'Процессы'}])
        for field,value in [('category_id',9999),('category_id',True),('priority','urgent'),('title','x'*181),('questions','bad')]:
            data=self.draft_result();data[field]=value
            with self.assertRaises(AIInvalidResponse):validate(data,schema)
    @override_settings(AI_ENABLED=True,OLLAMA_TIMEOUT=5)
    @patch('feedback.ai.build_opener')
    def test_ollama_protocol_and_lock_release_on_error(self,mock):
        mock.return_value.open.side_effect=TimeoutError()
        with self.assertRaises(AIUnavailable):generate(self.user,'draft',{'description':'Text'},[])
        self.assertIsNone(AIRequestLock.objects.get(user=self.user).reserved_until)
        request=mock.return_value.open.call_args.args[0]
        body=json.loads(request.data)
        self.assertFalse(body['stream']);self.assertFalse(body['think'])
        self.assertIn('properties',body['format']);self.assertNotIn('tools',body)
    @override_settings(AI_ENABLED=True)
    @patch('feedback.ai.build_opener')
    def test_inflight_request_is_not_duplicated(self,mock):
        AIRequestLock.objects.create(user=self.user,token='active',reserved_until=timezone.now()+timedelta(seconds=30))
        with self.assertRaises(AIBusy):generate(self.user,'draft',{},[])
        mock.assert_not_called()
    @override_settings(AI_ENABLED=True)
    @patch('feedback.ai.build_opener')
    def test_real_client_parses_valid_structured_reply(self,mock):
        outer={'done':True,'message':{'content':json.dumps(self.draft_result())}}
        mock.return_value.open.return_value.__enter__.return_value.read.return_value=json.dumps(outer).encode()
        result=generate(self.user,'draft',{},[{'id':self.category.pk,'name':'Процессы'}])
        self.assertEqual(result['kind'],'idea')
        self.assertIsNone(AIRequestLock.objects.get(user=self.user).reserved_until)
    def test_ai_endpoint_requires_csrf(self):
        from django.test import Client
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse('ai_analyze',args=[self.ticket.pk])).status_code,403)
