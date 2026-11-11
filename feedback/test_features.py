from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase,Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Department,Profile,Category,Ticket,OutcomeReview,ImprovementPost,ProblemTheme,FollowUpPolicy,FollowUpAlert,Notification,Comment
from .followups import check_followups
from . import ai

class FeatureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a=Department.objects.create(name='Закупки');cls.b=Department.objects.create(name='Продажи')
        def user(name,role,dept):
            u=get_user_model().objects.create_user(username=name,password='test-password-long')
            Profile.objects.create(user=u,role=role,department=dept);return u
        cls.employee=user('employee','employee',cls.a);cls.manager=user('manager','manager',cls.a)
        cls.other=user('other','employee',cls.b);cls.foreign_manager=user('foreign_manager','manager',cls.b)
        cls.admin=user('admin','admin',cls.b)
        cls.category=Category.objects.create(name='Процессы',responsible=cls.manager)
        cls.ticket=Ticket.objects.create(title='Рабочая проблема',description='Секретные подробности автора',kind='problem',category=cls.category,department=cls.a,author=cls.employee,assignee=cls.manager,due_at=timezone.now()+timedelta(days=7))
    def result(self):
        self.ticket.status='implemented';self.ticket.resolution='Инструкция обновлена';self.ticket.resolution_revision=1;self.ticket.result_offered_at=timezone.now();self.ticket.closed_at=timezone.now();self.ticket.save()
    def review(self,verdict='helped',revision=1,comment='Проверено'):
        return self.client.post(reverse('outcome',args=[self.ticket.pk]),{'revision':revision,'verdict':verdict,'comment':comment})
    def fields(self,status='implemented',resolution='Новое решение'):
        return {'action':'process','status':status,'resolution':resolution,'priority':'medium','assignee':self.manager.pk,'due_at':timezone.localtime(self.ticket.due_at).strftime('%Y-%m-%dT%H:%M')}
    def postdata(self,action='publish',audience='department'):
        return {'title':'Понятная инструкция','before':'Не хватало инструкции','after':'Инструкция доступна','effect':'Автор проверил процесс','audience':audience,'action':action}
    def publish(self,audience='department'):
        self.result();OutcomeReview.objects.create(ticket=self.ticket,revision=1,author=self.employee,verdict='helped')
        self.client.force_login(self.manager)
        return self.client.post(reverse('publication',args=[self.ticket.pk]),self.postdata(audience=audience))
    def test_review_author_only_and_csrf(self):
        self.result();self.client.force_login(self.manager);self.assertEqual(self.review().status_code,403)
        c=Client(enforce_csrf_checks=True);c.force_login(self.employee)
        self.assertEqual(c.post(reverse('outcome',args=[self.ticket.pk]),{}).status_code,403)
        self.assertFalse(OutcomeReview.objects.exists())
    def test_helped_once_and_stale_revision(self):
        self.result();self.client.force_login(self.employee)
        self.review(revision=2);self.assertFalse(OutcomeReview.objects.exists())
        self.review();self.review();self.assertEqual(OutcomeReview.objects.count(),1)
        self.ticket.refresh_from_db();self.assertEqual(self.ticket.status,'implemented')
    def test_not_helped_requires_reason_and_reopens(self):
        self.result();self.client.force_login(self.employee)
        self.review('not_helped',comment='');self.assertFalse(OutcomeReview.objects.exists())
        self.review('not_helped',comment='Шаг согласования остался непонятным')
        self.ticket.refresh_from_db();self.assertEqual(self.ticket.status,'work');self.assertIsNone(self.ticket.closed_at)
        self.assertGreater(self.ticket.due_at,timezone.now()+timedelta(days=6))
        self.assertTrue(self.ticket.events.filter(text__contains='Проблема осталась').exists())
        self.assertTrue(Notification.objects.filter(recipient=self.manager).exists())
    def test_next_solution_revision_and_minor_edit(self):
        self.result();self.client.force_login(self.employee);self.review('not_helped')
        self.client.force_login(self.manager);self.client.post(reverse('detail',args=[self.ticket.pk]),self.fields())
        self.ticket.refresh_from_db();self.assertEqual(self.ticket.resolution_revision,2)
        self.client.post(reverse('detail',args=[self.ticket.pk]),self.fields())
        self.ticket.refresh_from_db();self.assertEqual(self.ticket.resolution_revision,2)
        self.client.force_login(self.employee);self.assertContains(self.client.get(reverse('detail',args=[self.ticket.pk])),'Решение помогло?')
        self.review(revision=1);self.assertEqual(OutcomeReview.objects.count(),1)
        self.review(revision=2);self.assertEqual(OutcomeReview.objects.count(),2)
    def test_publication_requires_author_confirmation_and_manager(self):
        self.result();self.client.force_login(self.manager)
        self.client.post(reverse('publication',args=[self.ticket.pk]),self.postdata())
        self.assertFalse(ImprovementPost.objects.exists())
        self.client.force_login(self.employee)
        self.assertEqual(self.client.post(reverse('publication',args=[self.ticket.pk]),self.postdata()).status_code,404)
    def test_draft_moderation_scope_and_no_source_leak(self):
        self.publish();post=ImprovementPost.objects.get();self.assertEqual(post.status,'published')
        self.client.force_login(self.employee);page=self.client.get(reverse('improvements'))
        self.assertContains(page,'Понятная инструкция');self.assertNotContains(page,'Секретные подробности автора')
        self.client.force_login(self.other);self.assertNotContains(self.client.get(reverse('improvements')),'Понятная инструкция')
        self.client.force_login(self.manager);self.client.post(reverse('publication',args=[self.ticket.pk]),self.postdata(audience='company'))
        self.client.force_login(self.other);page=self.client.get(reverse('improvements'))
        self.assertContains(page,'Понятная инструкция');self.assertNotContains(page,reverse('detail',args=[self.ticket.pk]))
        self.client.force_login(self.manager);self.client.post(reverse('publication',args=[self.ticket.pk]),self.postdata(action='draft'))
        self.assertNotContains(self.client.get(reverse('improvements')),'Понятная инструкция')
    def test_solution_change_withdraws_showcase_and_confirmation(self):
        self.publish();self.client.post(reverse('detail',args=[self.ticket.pk]),self.fields(resolution='Исправленная инструкция'))
        self.ticket.refresh_from_db();self.assertEqual(self.ticket.resolution_revision,2)
        self.assertEqual(ImprovementPost.objects.get().status,'withdrawn')
        self.assertNotContains(self.client.get(reverse('improvements')),'Понятная инструкция')
    def test_reopening_removes_showcase_and_stale_records_hidden(self):
        self.publish();self.client.post(reverse('detail',args=[self.ticket.pk]),self.fields(status='work'))
        self.assertEqual(ImprovementPost.objects.get().status,'withdrawn')
        ImprovementPost.objects.update(status='published')
        self.assertNotContains(self.client.get(reverse('improvements')),'Понятная инструкция')
    def test_publication_withdraw_and_escaping(self):
        self.publish();self.client.post(reverse('publication',args=[self.ticket.pk]),dict(self.postdata(),effect='<script>alert(1)</script>'))
        page=self.client.get(reverse('improvements'));self.assertContains(page,'&lt;script&gt;');self.assertNotContains(page,'<script>alert(1)</script>')
        self.client.post(reverse('publication',args=[self.ticket.pk]),{'action':'withdraw'})
        self.assertEqual(ImprovementPost.objects.get().status,'withdrawn')
    def second(self,foreign=False):
        return Ticket.objects.create(title='Ещё проблема',description='Сбой согласования',kind='problem',category=self.category,department=self.b if foreign else self.a,author=self.other if foreign else self.employee,assignee=self.foreign_manager if foreign else self.manager,due_at=timezone.now()+timedelta(days=7))
    def test_radar_scopes_input_and_requires_confirmation(self):
        second=self.second();foreign=self.second(True)
        result={'groups':[{'title':'Согласование','summary':'Один процесс','ticket_ids':[self.ticket.pk,second.pk]}]}
        self.client.force_login(self.manager)
        with patch('feedback.feature_views.ai.generate',return_value=result) as generate:
            response=self.client.post(reverse('radar_generate'));self.assertEqual(response.status_code,200)
            source=generate.call_args.args[2];self.assertNotIn(foreign.pk,[item['id'] for item in source])
            self.assertNotIn('author',source[0]);self.assertNotIn('comments',source[0])
            self.client.post(reverse('radar_generate'))
        self.assertEqual(ProblemTheme.objects.count(),1);theme=ProblemTheme.objects.get();self.assertEqual(theme.status,'proposed')
        response=self.client.post(reverse('radar'),{'theme_id':theme.pk,'action':'confirm',f'theme-{theme.pk}-title':'Проверенная тема',f'theme-{theme.pk}-summary':'Связь проверена'})
        self.assertEqual(response.status_code,302);theme.refresh_from_db();self.assertEqual(theme.status,'confirmed')
    def test_radar_invalid_foreign_and_overlap_are_atomic(self):
        second=self.second();foreign=self.second(True);self.client.force_login(self.manager)
        cases=[{'groups':[{'title':'Недоступно','summary':'x','ticket_ids':[self.ticket.pk,foreign.pk]}]},
               {'groups':[{'title':'a','summary':'x','ticket_ids':[self.ticket.pk,second.pk]},{'title':'b','summary':'x','ticket_ids':[self.ticket.pk,second.pk]}]}]
        for result in cases:
            with patch('feedback.feature_views.ai.generate',return_value=result): self.assertEqual(self.client.post(reverse('radar_generate')).status_code,502)
            self.assertFalse(ProblemTheme.objects.exists())
    def test_radar_group_hidden_after_permission_change(self):
        second=self.second();theme=ProblemTheme.objects.create(title='Скрытая тема',summary='Чужие данные',fingerprint='x',created_by=self.manager);theme.tickets.set([self.ticket,second])
        second.department=self.b;second.assignee=self.foreign_manager;second.save()
        self.client.force_login(self.manager);self.assertNotContains(self.client.get(reverse('radar')),'Скрытая тема')
        self.assertEqual(self.client.post(reverse('radar'),{'theme_id':theme.pk,'action':'dismiss'}).status_code,403)
        self.client.force_login(self.employee);self.assertEqual(self.client.post(reverse('radar_generate')).status_code,403)
    def test_radar_validator_rejects_boolean_and_duplicate_ids(self):
        schema=ai.schema_for('radar',[{'id':self.ticket.pk},{'id':999}])
        for ids in [[True,999],[self.ticket.pk,self.ticket.pk]]:
            with self.assertRaises(ai.AIInvalidResponse): ai.validate({'groups':[{'title':'t','summary':'s','ticket_ids':ids}]},schema)
    def age(self,first_response=False,status='new',hours=100):
        now=timezone.now();past=now-timedelta(hours=hours)
        Ticket.objects.filter(pk=self.ticket.pk).update(created_at=past,updated_at=past,first_response_at=past if first_response else None,status=status,due_at=now+timedelta(days=2))
        return now
    def test_followup_once_then_escalation_admin_only(self):
        now=self.age();self.assertEqual(check_followups(now)['reminded'],1)
        self.assertEqual(check_followups(now+timedelta(minutes=5))['reminded'],0)
        self.assertEqual(Notification.objects.count(),1);self.assertEqual(Notification.objects.get().recipient,self.manager)
        self.assertEqual(check_followups(now+timedelta(hours=24))['escalated'],1)
        self.assertEqual(check_followups(now+timedelta(hours=25))['escalated'],0)
        self.assertEqual(Notification.objects.count(),2);self.assertTrue(Notification.objects.filter(recipient=self.admin).exists())
        self.assertFalse(Notification.objects.filter(recipient=self.foreign_manager).exists())
    def test_followup_stale_clarification_author_and_progress(self):
        now=self.age(True,'clarify');check_followups(now)
        self.assertEqual(FollowUpAlert.objects.get().kind,'stale');self.assertEqual(Notification.objects.get().recipient,self.employee)
        Comment.objects.create(ticket=self.ticket,author=self.employee,text='Уточнение',created_at=now+timedelta(seconds=1))
        result=check_followups(now+timedelta(minutes=1));self.assertEqual(result['resolved'],1)
        self.assertFalse(FollowUpAlert.objects.filter(resolved_at__isnull=True).exists())
    def test_followup_terminal_disabled_and_fallback(self):
        now=self.age();self.manager.is_active=False;self.manager.save()
        check_followups(now);self.assertEqual(Notification.objects.get().recipient,self.admin)
        Ticket.objects.filter(pk=self.ticket.pk).update(status='closed')
        self.assertEqual(check_followups(now+timedelta(minutes=1))['resolved'],1)
        FollowUpPolicy.objects.filter(pk=1).update(enabled=False)
        Ticket.objects.filter(pk=self.ticket.pk).update(status='new')
        self.assertEqual(check_followups(now+timedelta(hours=50))['reminded'],0)
    def test_overdue_waits_for_quiet_hour(self):
        now=timezone.now();Ticket.objects.filter(pk=self.ticket.pk).update(due_at=now-timedelta(hours=2),first_response_at=now)
        self.assertEqual(check_followups(now)['reminded'],0)
        self.assertEqual(check_followups(now+timedelta(hours=2))['reminded'],1)
        self.assertEqual(FollowUpAlert.objects.get().kind,'overdue')
    def test_policy_permissions_validation_and_pages(self):
        self.client.force_login(self.employee)
        self.assertEqual(self.client.post(reverse('followups'),{'action':'check'}).status_code,403)
        self.client.force_login(self.admin)
        response=self.client.post(reverse('followups'),{'action':'policy','enabled':'on','first_response_hours':0,'inactivity_hours':72,'escalation_hours':24})
        self.assertEqual(response.status_code,200);self.assertEqual(FollowUpPolicy.objects.get(pk=1).first_response_hours,24)
        self.client.post(reverse('followups'),{'action':'policy','enabled':'on','first_response_hours':12,'inactivity_hours':48,'escalation_hours':12})
        self.assertEqual(FollowUpPolicy.objects.get(pk=1).first_response_hours,12)
        for name in ['radar','followups','improvements']:
            self.assertEqual(self.client.get(reverse(name)).status_code,200)
    def test_alerts_scoped_and_csrf(self):
        check_followups(self.age())
        self.client.force_login(self.other);self.assertNotContains(self.client.get(reverse('followups')),self.ticket.title)
        c=Client(enforce_csrf_checks=True);c.force_login(self.manager)
        self.assertEqual(c.post(reverse('radar_generate')).status_code,403)
