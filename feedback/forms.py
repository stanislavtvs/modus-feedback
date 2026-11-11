from pathlib import Path
from django import forms
from django.contrib.auth import get_user_model
from .models import Ticket,Profile,Category
class TicketForm(forms.ModelForm):
    attachment=forms.FileField(label='Материал к обращению',required=False,help_text='PDF, PNG, JPG или TXT, до 10 МБ. Не добавляйте закрытые данные.')
    class Meta:
        model=Ticket
        fields=['title','kind','category','priority','description','suggestion']
        widgets={'description':forms.Textarea(attrs={'rows':6}),'suggestion':forms.Textarea(attrs={'rows':3})}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].empty_label = 'Выберите категорию'
        self.fields['kind'].choices = [('', 'Выберите тип')] + list(Ticket.Kind.choices)

    def clean_attachment(self):
        f=self.cleaned_data.get('attachment')
        if f:
            if f.size>10*1024*1024: raise forms.ValidationError('Размер файла превышает 10 МБ.')
            suffix=Path(f.name).suffix.lower()
            signatures={'.pdf':b'%PDF-', '.png':b'\x89PNG\r\n\x1a\n','.jpg':b'\xff\xd8\xff','.jpeg':b'\xff\xd8\xff'}
            if suffix not in [*signatures,'.txt']: raise forms.ValidationError('Выберите PDF, PNG, JPG или TXT.')
            head=f.read(4096);f.seek(0)
            if suffix in signatures and not head.startswith(signatures[suffix]): raise forms.ValidationError('Содержимое не соответствует формату файла.')
            if suffix=='.txt':
                try: head.decode('utf-8')
                except UnicodeDecodeError: raise forms.ValidationError('Текстовый файл должен иметь кодировку UTF-8.')
        return f
class ResponsibleChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        name = user.get_full_name() or user.username
        return f'{name} · {user.profile.department}'

class ProcessForm(forms.Form):
    status=forms.ChoiceField(label='Статус',choices=Ticket.Status.choices)
    assignee=ResponsibleChoiceField(label='Ответственный',queryset=get_user_model().objects.none(),required=False,empty_label='Очередь администраторов')
    priority=forms.ChoiceField(label='Приоритет',choices=Ticket.Priority.choices)
    due_at=forms.DateTimeField(label='Срок рассмотрения',widget=forms.DateTimeInput(attrs={'type':'datetime-local'},format='%Y-%m-%dT%H:%M'),input_formats=['%Y-%m-%dT%H:%M'])
    resolution=forms.CharField(label='Решение или вопрос для уточнения',required=False,widget=forms.Textarea(attrs={'rows':3}))
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['assignee'].queryset=get_user_model().objects.select_related('profile__department').filter(is_active=True,profile__role__in=[Profile.Role.MANAGER,Profile.Role.ADMIN])
    def clean(self):
        data=super().clean()
        if data.get('status') in ['implemented','rejected','closed','clarify'] and not data.get('resolution','').strip(): self.add_error('resolution','Укажите результат рассмотрения или вопрос для уточнения.')
        return data
class CommentForm(forms.Form):
    text=forms.CharField(label='Комментарий',max_length=5000,widget=forms.Textarea(attrs={'rows':3}))


class CategoryForm(forms.ModelForm):
    responsible = ResponsibleChoiceField(
        label='Ответственный по категории',
        queryset=get_user_model().objects.none(), required=False,
        empty_label='Автоматически: руководитель подразделения',
        help_text='Если ответственный не задан или неактивен, обращение направляется руководителю подразделения автора, затем в очередь администраторов.',
    )
    sla_days = forms.IntegerField(
        label='Срок рассмотрения в календарных днях', min_value=1, max_value=365,
        help_text='Применяется к новым обращениям. Сроки уже созданных обращений не меняются.',
    )
    class Meta:
        model = Category
        fields = ['name', 'responsible', 'sla_days']
        labels = {'name': 'Название категории'}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['responsible'].queryset = get_user_model().objects.select_related('profile__department').filter(
            is_active=True, profile__role__in=[Profile.Role.MANAGER, Profile.Role.ADMIN],
        ).order_by('first_name', 'username')
    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if Category.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Категория с таким названием уже существует.')
        return name
