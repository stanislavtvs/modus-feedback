import uuid
from pathlib import Path
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Q
class Department(models.Model):
    name=models.CharField('Подразделение',max_length=120,unique=True)
    def __str__(self): return self.name
class Profile(models.Model):
    class Role(models.TextChoices):
        EMPLOYEE='employee','Сотрудник'
        MANAGER='manager','Руководитель'
        ADMIN='admin','Администратор'
    user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='profile')
    department=models.ForeignKey(Department,on_delete=models.PROTECT)
    role=models.CharField(max_length=20,choices=Role.choices,default=Role.EMPLOYEE)
    def __str__(self): return str(self.user)
class Category(models.Model):
    name=models.CharField('Категория',max_length=120,unique=True)
    responsible=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,limit_choices_to={'is_active':True})
    sla_days=models.PositiveSmallIntegerField('Срок в календарных днях',default=7)
    def __str__(self): return self.name
class Ticket(models.Model):
    class Kind(models.TextChoices):
        PROBLEM='problem','Проблема'
        IDEA='idea','Предложение'
        PRAISE='praise','Положительный отзыв'
    class Status(models.TextChoices):
        NEW='new','Новое'
        REVIEW='review','На рассмотрении'
        WORK='work','В работе'
        CLARIFY='clarify','Ожидает уточнения'
        IMPLEMENTED='implemented','Реализовано'
        REJECTED='rejected','Отклонено'
        CLOSED='closed','Закрыто'
    class Priority(models.TextChoices):
        LOW='low','Низкий'
        MEDIUM='medium','Средний'
        HIGH='high','Высокий'
    title=models.CharField('Кратко о сути',max_length=180)
    description=models.TextField('Описание')
    suggestion=models.TextField('Предлагаемое решение',blank=True)
    kind=models.CharField('Тип',max_length=20,choices=Kind.choices)
    category=models.ForeignKey(Category,verbose_name='Категория',on_delete=models.PROTECT)
    department=models.ForeignKey(Department,on_delete=models.PROTECT)
    author=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='authored')
    assignee=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name='assigned')
    priority=models.CharField('Приоритет',max_length=10,choices=Priority.choices,default=Priority.MEDIUM)
    status=models.CharField(max_length=20,choices=Status.choices,default=Status.NEW)
    resolution=models.TextField(blank=True)
    due_at=models.DateTimeField()
    created_at=models.DateTimeField(default=timezone.now)
    updated_at=models.DateTimeField(auto_now=True)
    first_response_at=models.DateTimeField(null=True,blank=True)
    closed_at=models.DateTimeField(null=True,blank=True)
    resolution_revision=models.PositiveIntegerField(default=0)
    result_offered_at=models.DateTimeField(null=True,blank=True)
    source_id=models.CharField(max_length=20,blank=True,unique=True,null=True)
    class Meta:
        ordering=['-created_at']
        indexes=[models.Index(fields=['status','due_at']),models.Index(fields=['department','category'])]
    @property
    def reference(self): return f'MT-{self.pk:04d}'
    @property
    def overdue(self): return self.status not in ['implemented','rejected','closed'] and self.due_at<timezone.now()
    def __str__(self): return f'{self.reference} {self.title}'
class Event(models.Model):
    ticket=models.ForeignKey(Ticket,on_delete=models.CASCADE,related_name='events')
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    text=models.TextField()
    created_at=models.DateTimeField(default=timezone.now)
    class Meta: ordering=['created_at','pk']
class Comment(models.Model):
    ticket=models.ForeignKey(Ticket,on_delete=models.CASCADE,related_name='comments')
    author=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    text=models.TextField('Комментарий')
    created_at=models.DateTimeField(default=timezone.now)
def upload_path(instance,name): return f'{uuid.uuid4().hex}{Path(name).suffix.lower()}'
class Attachment(models.Model):
    ticket=models.ForeignKey(Ticket,on_delete=models.CASCADE,related_name='attachments')
    file=models.FileField(upload_to=upload_path)
    name=models.CharField(max_length=255)
class Notification(models.Model):
    recipient=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    ticket=models.ForeignKey(Ticket,on_delete=models.CASCADE)
    text=models.CharField(max_length=255)
    read=models.BooleanField(default=False)
    created_at=models.DateTimeField(default=timezone.now)
    class Meta: ordering=['-created_at']

class AIRequestLock(models.Model):
    """Cross-worker reservation. No prompts or generated text are persisted."""
    user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    token=models.CharField(max_length=36,blank=True)
    reserved_until=models.DateTimeField(null=True,blank=True)

class OutcomeReview(models.Model):
    ticket=models.ForeignKey(Ticket,on_delete=models.CASCADE,related_name='outcome_reviews')
    revision=models.PositiveIntegerField()
    author=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    verdict=models.CharField(max_length=12,choices=[('helped','Помогло'),('not_helped','Проблема осталась')])
    comment=models.TextField(blank=True)
    created_at=models.DateTimeField(default=timezone.now)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['ticket','revision'],name='one_outcome_per_revision')]

class ImprovementPost(models.Model):
    ticket=models.OneToOneField(Ticket,on_delete=models.CASCADE,related_name='publication')
    source_revision=models.PositiveIntegerField()
    title=models.CharField('Заголовок',max_length=180)
    before=models.TextField('Что было')
    after=models.TextField('Что изменилось')
    effect=models.TextField('Подтверждённый эффект')
    audience=models.CharField('Кому показать',max_length=12,choices=[('department','Подразделению'),('company','Всей компании')],default='department')
    status=models.CharField(max_length=12,default='draft',choices=[('draft','Черновик'),('published','Опубликовано'),('withdrawn','Снято с публикации')])
    editor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    published_at=models.DateTimeField(null=True,blank=True)
    updated_at=models.DateTimeField(auto_now=True)

class ProblemTheme(models.Model):
    title=models.CharField(max_length=140)
    summary=models.TextField()
    tickets=models.ManyToManyField(Ticket,related_name='problem_themes')
    fingerprint=models.CharField(max_length=64,unique=True)
    status=models.CharField(max_length=12,default='proposed',choices=[('proposed','Предложено ИИ'),('confirmed','Подтверждено'),('dismissed','Отклонено')])
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='+')
    confirmed_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.PROTECT,related_name='+')
    created_at=models.DateTimeField(default=timezone.now)

class FollowUpPolicy(models.Model):
    enabled=models.BooleanField('Включить автоматические напоминания',default=True)
    first_response_hours=models.PositiveSmallIntegerField('Первый ответ, часов',default=24)
    inactivity_hours=models.PositiveSmallIntegerField('Без обновлений, часов',default=72)
    escalation_hours=models.PositiveSmallIntegerField('Эскалация после напоминания, часов',default=24)

class FollowUpAlert(models.Model):
    ticket=models.ForeignKey(Ticket,on_delete=models.CASCADE,related_name='followup_alerts')
    kind=models.CharField(max_length=20,choices=[('no_response','Нет первого ответа'),('stale','Нет обновлений'),('overdue','Срок истёк')])
    episode=models.CharField(max_length=64)
    reminded_at=models.DateTimeField(default=timezone.now)
    escalated_at=models.DateTimeField(null=True,blank=True)
    resolved_at=models.DateTimeField(null=True,blank=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['ticket'],condition=Q(resolved_at__isnull=True),name='one_active_followup')]

class Initiative(models.Model):
    theme=models.OneToOneField(ProblemTheme,on_delete=models.PROTECT,related_name='initiative')
    goal=models.CharField('Цель изменения',max_length=180)
    owner=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='initiatives')
    plan=models.TextField('Контекст и общий подход',blank=True)
    due_date=models.DateField('Срок общей инициативы')
    status=models.CharField('Состояние',max_length=12,default='planned',choices=[('planned','Запланировано'),('work','В работе'),('done','Завершено')])
    result=models.TextField('Результат и способ проверки',blank=True)
    updated_at=models.DateTimeField(auto_now=True)

class InitiativeEvent(models.Model):
    initiative=models.ForeignKey(Initiative,on_delete=models.CASCADE,related_name='events')
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    text=models.TextField()
    created_at=models.DateTimeField(default=timezone.now)
    class Meta: ordering=['created_at','pk']

class InitiativeStep(models.Model):
    initiative=models.ForeignKey(Initiative,on_delete=models.CASCADE,related_name='steps')
    title=models.CharField('Действие',max_length=180)
    owner=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='initiative_steps')
    due_date=models.DateField('Срок шага')
    done=models.BooleanField('Выполнено',default=False)
    active=models.BooleanField('Включить шаг в план',default=True)
    revision=models.PositiveIntegerField(default=0)
    creation_token=models.UUIDField(default=uuid.uuid4,unique=True,editable=False)
    completed_at=models.DateTimeField(null=True,blank=True)
    completed_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,related_name='+')
    class Meta: ordering=['pk']
    @property
    def overdue(self): return self.active and not self.done and self.due_date<timezone.localdate()
