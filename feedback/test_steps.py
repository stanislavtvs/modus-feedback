import uuid
from django.test import TestCase,Client
from django.urls import reverse
from django.utils import timezone
from . import test_development
from .models import Initiative,InitiativeStep,InitiativeEvent,Ticket

class ChecklistTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        test_development.DevelopmentTests.setUpTestData.__func__(cls)
        cls.initiative=Initiative.objects.create(theme=cls.theme,goal='Проверить процесс',owner=cls.manager,plan='',due_date=timezone.localdate().replace(year=2027),status='work')
        cls.step=InitiativeStep.objects.create(initiative=cls.initiative,title='Согласовать поля',owner=cls.manager,due_date=cls.initiative.due_date)
    def data(self,**changes):
        data={'title':'Подготовить памятку','owner':self.manager.pk,'due_date':self.initiative.due_date.isoformat(),'active':'on','revision':0,'creation_token':str(uuid.uuid4())};data.update(changes);return data
    def test_add_edit_and_idempotent_add(self):
        self.client.force_login(self.manager);data=self.data();url=reverse('step_add',args=[self.theme.pk])
        self.assertEqual(self.client.post(url,data).status_code,302);self.client.post(url,data)
        self.assertEqual(self.initiative.steps.count(),2)
        step=InitiativeStep.objects.latest('pk');data=self.data(title='Памятка с примером',revision=step.revision)
        self.assertEqual(self.client.post(reverse('step_edit',args=[self.theme.pk,step.pk]),data).status_code,302)
        step.refresh_from_db();self.assertEqual(step.title,'Памятка с примером');self.assertEqual(step.revision,1)
    def test_owner_due_and_completed_initiative_validation(self):
        self.client.force_login(self.manager);url=reverse('step_add',args=[self.theme.pk])
        for changes in [{'owner':self.foreign.pk},{'due_date':'2028-01-01'}]:self.assertEqual(self.client.post(url,self.data(**changes)).status_code,200)
        self.assertEqual(self.initiative.steps.count(),1)
        self.initiative.status='done';self.initiative.save();self.client.post(url,self.data());self.assertEqual(self.initiative.steps.count(),1)
    def test_done_reopen_and_no_automatic_ticket_change(self):
        self.client.force_login(self.manager);url=reverse('step_state',args=[self.theme.pk,self.step.pk])
        self.client.post(url,{'revision':0,'done':'on'});self.step.refresh_from_db()
        self.assertTrue(self.step.done);self.assertEqual(self.step.completed_by,self.manager);self.assertIsNotNone(self.step.completed_at)
        self.initiative.refresh_from_db();self.assertEqual(self.initiative.status,'work');self.assertEqual(Ticket.objects.filter(status='new').count(),2)
        self.client.post(url,{'revision':0});self.step.refresh_from_db();self.assertTrue(self.step.done)
        self.client.post(url,{'revision':1});self.step.refresh_from_db();self.assertFalse(self.step.done);self.assertIsNone(self.step.completed_at)
        self.assertEqual(InitiativeEvent.objects.count(),2)
    def test_stale_edit_and_cross_theme_are_denied(self):
        self.client.force_login(self.manager);InitiativeStep.objects.filter(pk=self.step.pk).update(revision=1)
        self.client.post(reverse('step_edit',args=[self.theme.pk,self.step.pk]),self.data(title='Устаревшая правка'))
        self.step.refresh_from_db();self.assertEqual(self.step.title,'Согласовать поля')
        for user in [self.employee,self.foreign]:
            self.client.force_login(user);self.assertEqual(self.client.post(reverse('step_state',args=[self.theme.pk,self.step.pk]),{'revision':1,'done':'on'}).status_code,404)
    def test_archive_restore_and_completion_guard(self):
        self.client.force_login(self.manager);url=reverse('initiative',args=[self.theme.pk])
        data={'goal':self.initiative.goal,'owner':self.manager.pk,'plan':'','due_date':self.initiative.due_date.isoformat(),'status':'done','result':'Проверено'}
        self.assertEqual(self.client.post(url,data).status_code,200);self.initiative.refresh_from_db();self.assertEqual(self.initiative.status,'work')
        edit=reverse('step_edit',args=[self.theme.pk,self.step.pk]);self.client.post(edit,self.data(title=self.step.title,active=''))
        self.step.refresh_from_db();self.assertFalse(self.step.active)
        self.client.post(edit,self.data(title=self.step.title,revision=1));self.step.refresh_from_db();self.assertTrue(self.step.active)
        self.client.post(reverse('step_state',args=[self.theme.pk,self.step.pk]),{'revision':2,'done':'on'})
        self.assertEqual(self.client.post(url,data).status_code,302);self.initiative.refresh_from_db();self.assertEqual(self.initiative.status,'done')
    def test_csrf_and_shortening_initiative_due(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.manager)
        self.assertEqual(client.post(reverse('step_state',args=[self.theme.pk,self.step.pk]),{'revision':0}).status_code,403)
        self.client.force_login(self.manager)
        response=self.client.post(reverse('initiative',args=[self.theme.pk]),{'goal':'Цель','owner':self.manager.pk,'plan':'','due_date':'2026-01-01','status':'work','result':''})
        self.assertEqual(response.status_code,200);self.initiative.refresh_from_db();self.assertNotEqual(str(self.initiative.due_date),'2026-01-01')
