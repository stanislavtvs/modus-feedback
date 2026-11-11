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
