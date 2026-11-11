from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import Department,Profile,Category,Ticket
from .services import route

class RoutingSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department=Department.objects.create(name='Закупки')
        def user(name,role):
            user=get_user_model().objects.create_user(name,password='settings-test-123')
            Profile.objects.create(user=user,department=cls.department,role=role)
            return user
        cls.admin=user('admin','admin')
        cls.manager=user('manager','manager')
        cls.employee=user('employee','employee')
        cls.category=Category.objects.create(name='Документы',responsible=cls.manager,sla_days=7)
        cls.ticket=Ticket.objects.create(title='Документы',description='Текст',kind='problem',category=cls.category,department=cls.department,author=cls.employee,assignee=cls.manager,due_at=timezone.now()+timedelta(days=7))
    def test_settings_require_admin(self):
        self.assertEqual(self.client.get(reverse('settings')).status_code,302)
        for user in [self.employee,self.manager]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('settings')).status_code,403)
            self.assertEqual(self.client.post(reverse('category_edit',args=[self.category.pk]),{'name':'Changed','sla_days':1}).status_code,403)
        self.category.refresh_from_db();self.assertEqual(self.category.name,'Документы')
    def test_admin_has_native_page_and_navigation(self):
        self.client.force_login(self.admin)
        response=self.client.get(reverse('settings'))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Категории и правила')
        self.assertContains(response,'href="/settings/"')
        self.assertNotContains(response,'href="/admin/"')
    def test_create_rule_and_route_new_ticket(self):
        self.client.force_login(self.admin)
        response=self.client.post(reverse('settings'),{'name':'Обучение','responsible':self.admin.pk,'sla_days':5})
        self.assertRedirects(response,reverse('settings'))
        category=Category.objects.get(name='Обучение')
        self.assertEqual(category.sla_days,5)
        self.ticket.category=category
        self.assertEqual(route(self.ticket),self.admin)
    def test_edit_rule_does_not_reassign_or_change_existing_due_date(self):
        self.client.force_login(self.admin)
        due=self.ticket.due_at
        response=self.client.post(reverse('category_edit',args=[self.category.pk]),{'name':'Документооборот','responsible':self.admin.pk,'sla_days':3})
        self.assertRedirects(response,reverse('settings'))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.assignee,self.manager)
        self.assertEqual(self.ticket.due_at,due)
        self.category.refresh_from_db();self.assertEqual(self.category.responsible,self.admin)
    def test_empty_responsible_uses_fallback(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('category_edit',args=[self.category.pk]),{'name':'Документы','responsible':'','sla_days':10})
        self.category.refresh_from_db();self.assertIsNone(self.category.responsible)
        self.ticket.category=self.category
        self.assertEqual(route(self.ticket),self.manager)
    def test_invalid_rule_not_saved(self):
        self.client.force_login(self.admin)
        for days in [0,366]:
            response=self.client.post(reverse('settings'),{'name':'Ошибочная','responsible':self.manager.pk,'sla_days':days})
            self.assertEqual(response.status_code,200)
        response=self.client.post(reverse('settings'),{'name':'Ошибочная','responsible':self.employee.pk,'sla_days':3})
        self.assertEqual(response.status_code,200)
        self.assertFalse(Category.objects.filter(name='Ошибочная').exists())
    def test_duplicate_name_is_explained(self):
        self.client.force_login(self.admin)
        response=self.client.post(reverse('settings'),{'name':'  документы  ','sla_days':7})
        self.assertContains(response,'Категория с таким названием уже существует.')
        self.assertEqual(Category.objects.count(),1)
    def test_csrf_protects_settings(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.admin)
        self.assertEqual(client.post(reverse('settings'),{'name':'X','sla_days':7}).status_code,403)
