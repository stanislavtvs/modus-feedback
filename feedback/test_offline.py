from unittest.mock import patch
from django.test import TestCase,override_settings
from django.urls import reverse
from django.utils import timezone
from . import test_development
from .test_helpers import approved_post
from .models import Ticket,ImprovementPost

@override_settings(AI_ENABLED=False)
class OfflineWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls): test_development.DevelopmentTests.setUpTestData.__func__(cls)
    @patch('feedback.ai.build_opener')
    def test_core_workflow_remains_available_without_model(self,network):
        self.client.force_login(self.employee)
        self.assertEqual(approved_post(self.client,reverse('ai_draft'),{'description':'Нужен понятный шаблон передачи заявок'}).status_code,503)
        network.assert_not_called()
        self.client.post(reverse('create'),{'title':'Проверка без ИИ','description':'Нужен шаблон передачи заявок','kind':'idea','category':self.category.pk,'priority':'medium'})
        ticket=Ticket.objects.latest('pk');self.assertEqual(ticket.assignee,self.manager)
        self.client.force_login(self.manager)
        self.client.post(reverse('detail',args=[ticket.pk]),{'action':'process','status':'implemented','assignee':self.manager.pk,'priority':'medium','due_at':timezone.localtime(ticket.due_at).strftime('%Y-%m-%dT%H:%M'),'resolution':'Учебный результат: шаблон подготовлен.'})
        ticket.refresh_from_db();self.assertEqual(ticket.status,'implemented')
        self.client.force_login(self.employee);self.client.post(reverse('outcome',args=[ticket.pk]),{'revision':ticket.resolution_revision,'verdict':'helped','comment':'Учебная проверка без модели'})
        self.client.force_login(self.manager);self.client.post(reverse('publication',args=[ticket.pk]),{'action':'publish','title':'Проверка без ИИ','before':'Не было шаблона','after':'Подготовлен учебный шаблон','effect':'Подтверждено в тестовом сценарии','audience':'department'})
        self.assertEqual(ImprovementPost.objects.get(ticket=ticket).status,'published')
        self.assertContains(self.client.get(reverse('pulse')),'Закупки')
        self.assertContains(self.client.get(reverse('improvements')),'Проверка без ИИ')
        network.assert_not_called()
