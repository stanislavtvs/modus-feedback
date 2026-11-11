import tempfile
from datetime import timedelta
from django.test import TestCase,override_settings,Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from .models import Department,Profile,Category,Ticket,Notification,Attachment
from .access import visible
from .forms import TicketForm
from .services import route
class WorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a=Department.objects.create(name='Закупки');cls.b=Department.objects.create(name='IT')
        def user(name,role,dept):
            u=get_user_model().objects.create_user(username=name,password='demo-test-password-123')
            Profile.objects.create(user=u,department=dept,role=role)
            return u
        cls.employee=user('employee','employee',cls.a);cls.other=user('other','employee',cls.b)
        cls.manager=user('manager','manager',cls.a);cls.admin=user('admin','admin',cls.b)
        cls.category=Category.objects.create(name='Процессы',responsible=cls.manager)
        cls.ticket=Ticket.objects.create(title='Обращение',description='Текст',kind='problem',category=cls.category,department=cls.a,author=cls.employee,assignee=cls.manager,due_at=timezone.now()+timedelta(days=7))
    def test_access_boundaries(self):
        self.client.force_login(self.other)
        for url in [reverse('detail',args=[self.ticket.pk])]: self.assertEqual(self.client.get(url).status_code,404)
        for u in [self.employee,self.manager,self.admin]: self.assertTrue(visible(u).filter(pk=self.ticket.pk).exists())
        self.assertFalse(visible(self.other).exists())
    def test_full_workflow_and_notification(self):
        self.client.force_login(self.employee)
        response=self.client.post(reverse('create'),{'title':'Новая инструкция','description':'Нужна инструкция','kind':'idea','category':self.category.pk,'priority':'medium'})
        self.assertEqual(response.status_code,302)
        ticket=Ticket.objects.latest('pk');self.assertEqual(ticket.assignee,self.manager)
        self.assertTrue(Notification.objects.filter(recipient=self.manager,ticket=ticket).exists())
        self.client.force_login(self.manager)
        fields={'action':'process','status':'clarify','assignee':self.manager.pk,'priority':'high','due_at':timezone.localtime(ticket.due_at).strftime('%Y-%m-%dT%H:%M'),'resolution':'Какой процесс нужно описать?'}
        self.assertEqual(self.client.post(reverse('detail',args=[ticket.pk]),fields).status_code,302)
        ticket.refresh_from_db();self.assertEqual(ticket.status,'clarify');self.assertIsNotNone(ticket.first_response_at)
        self.client.force_login(self.employee)
        self.client.post(reverse('detail',args=[ticket.pk]),{'action':'comment','text':'Обработку заявок'})
        self.client.force_login(self.manager);fields.update(status='implemented',resolution='Инструкция опубликована')
        self.client.post(reverse('detail',args=[ticket.pk]),fields)
        ticket.refresh_from_db();self.assertIsNotNone(ticket.closed_at);self.assertEqual(ticket.status,'implemented');self.assertEqual(ticket.comments.count(),1)
        self.assertEqual(ticket.events.count(),3)
        self.assertNotIn('Срок:', ' '.join(ticket.events.values_list('text',flat=True)))
        self.assertTrue(Notification.objects.filter(recipient=self.employee,ticket=ticket).exists())
    def test_cannot_close_without_reason(self):
        self.client.force_login(self.manager)
        r=self.client.post(reverse('detail',args=[self.ticket.pk]),{'action':'process','status':'rejected','priority':'medium','due_at':'2027-01-01T12:00','resolution':''})
        self.assertEqual(r.status_code,200);self.ticket.refresh_from_db();self.assertEqual(self.ticket.status,'new')
        self.assertContains(r,'Укажите результат рассмотрения')
    def test_employee_cannot_process(self):
        self.client.force_login(self.employee)
        r=self.client.post(reverse('detail',args=[self.ticket.pk]),{'action':'process','status':'closed'})
        self.assertEqual(r.status_code,403)
    def test_routing_fallback(self):
        self.category.responsible=None;self.category.save()
        self.assertEqual(route(self.ticket),self.manager)
        self.manager.is_active=False;self.manager.save()
        self.assertIsNone(route(self.ticket))
    def test_upload_validation_and_private_download(self):
        with tempfile.TemporaryDirectory() as directory,override_settings(MEDIA_ROOT=directory):
            self.client.force_login(self.employee)
            response=self.client.post(reverse('create'),{'title':'Файл','description':'Пример','kind':'problem','category':self.category.pk,'priority':'low','attachment':SimpleUploadedFile('sample.txt','пример'.encode())})
            self.assertEqual(response.status_code,302)
            attachment=Attachment.objects.latest('pk')
            self.assertEqual(self.client.get(reverse('download',args=[attachment.pk])).status_code,200)
            self.client.force_login(self.other);self.assertEqual(self.client.get(reverse('download',args=[attachment.pk])).status_code,404)
            bad=TicketForm(files={'attachment':SimpleUploadedFile('fake.pdf',b'<script>bad</script>')},data={'title':'x','kind':'idea','category':self.category.pk,'description':'x','priority':'low'})
            self.assertFalse(bad.is_valid());self.assertIn('attachment',bad.errors)
    def test_pages_and_filters(self):
        self.client.force_login(self.manager)
        for name in ['dashboard','tickets','create','analytics','notifications']:
            self.assertEqual(self.client.get(reverse(name)).status_code,200,name)
        self.assertEqual(self.client.get(reverse('detail',args=[self.ticket.pk])).status_code,200)
        self.assertContains(self.client.get(reverse('tickets'),{'q':'Обращение'}),'Обращение')
        self.assertNotContains(self.client.get(reverse('tickets'),{'status':'closed'}),'ticket-title')
        self.assertEqual(self.client.get(reverse('tickets'),{'from':'bad'}).status_code,200)
    def test_csrf_and_login_required(self):
        self.assertEqual(self.client.get(reverse('tickets')).status_code,302)
        client=Client(enforce_csrf_checks=True);client.force_login(self.employee)
        self.assertEqual(client.post(reverse('create'),{}).status_code,403)
    def test_notifications_only_owner(self):
        Notification.objects.create(recipient=self.employee,ticket=self.ticket,text='Private')
        self.client.force_login(self.other);self.client.post(reverse('notifications'))
        self.assertFalse(Notification.objects.get().read)
    def test_similarity_does_not_expose_private(self):
        foreign=Ticket.objects.create(title=self.ticket.title,description=self.ticket.description,kind='idea',category=self.category,department=self.b,author=self.other,due_at=timezone.now())
        self.client.force_login(self.employee)
        self.assertNotContains(self.client.get(reverse('detail',args=[self.ticket.pk])),foreign.reference)

    def test_seed_is_idempotent_and_complete(self):
        import os
        from unittest.mock import patch
        from django.core.management import call_command
        with patch.dict(os.environ,{'DEMO_PASSWORD':'temporary-test-password-123'}):
            call_command('seed_demo',verbosity=0)
            call_command('seed_demo',verbosity=0)
        self.assertEqual(Ticket.objects.filter(source_id__isnull=False).count(),20)
        self.assertEqual(Ticket.objects.filter(source_id='A-017').get().status,'rejected')
