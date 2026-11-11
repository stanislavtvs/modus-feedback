from django import forms
from django.core.validators import MaxLengthValidator,MinValueValidator,MaxValueValidator
from .models import ImprovementPost, FollowUpPolicy, ProblemTheme, Initiative

class OutcomeForm(forms.Form):
    revision=forms.IntegerField(min_value=1,widget=forms.HiddenInput)
    verdict=forms.ChoiceField(choices=[('','Выберите результат'),('helped','Помогло'),('not_helped','Проблема осталась')],label='Результат')
    comment=forms.CharField(label='Что осталось нерешённым или что помогло',max_length=1000,required=False,widget=forms.Textarea(attrs={'rows':3}))
    def clean(self):
        data=super().clean()
        if data.get('verdict')=='not_helped' and not data.get('comment'):
            self.add_error('comment','Опишите, что осталось нерешённым.')
        return data

class PublicationForm(forms.ModelForm):
    class Meta:
        model=ImprovementPost
        fields=['title','before','after','effect','audience']
        widgets={key:forms.Textarea(attrs={'rows':3}) for key in ['before','after','effect']}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for name in ['before','after','effect']:
            self.fields[name].max_length=1500;self.fields[name].validators.append(MaxLengthValidator(1500));self.fields[name].widget.attrs['maxlength']=1500

class ThemeForm(forms.ModelForm):
    class Meta:
        model=ProblemTheme
        fields=['title','summary']
        labels={'title':'Название проблемы','summary':'Общий рабочий процесс'}
        widgets={'summary':forms.Textarea(attrs={'rows':3})}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['summary'].max_length=900
        self.fields['summary'].validators.append(MaxLengthValidator(900))

class PolicyForm(forms.ModelForm):
    class Meta:
        model=FollowUpPolicy
        fields=['enabled','first_response_hours','inactivity_hours','escalation_hours']
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for name in self.fields:
            if name!='enabled':
                self.fields[name].validators.extend([MinValueValidator(1),MaxValueValidator(8760)])
                self.fields[name].widget.attrs.update(min=1,max=8760)

class InitiativeForm(forms.ModelForm):
    class Meta:
        model=Initiative
        fields=['goal','owner','plan','due_date','status','result']
        widgets={'plan':forms.Textarea(attrs={'rows':5}),'result':forms.Textarea(attrs={'rows':3}),'due_date':forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d')}
    def __init__(self,*args,allowed_owners,**kwargs):
        super().__init__(*args,**kwargs)
        from .forms import ResponsibleChoiceField
        self.fields['owner']=ResponsibleChoiceField(label='Ответственный за инициативу',queryset=allowed_owners)
        self.fields['plan'].required=False
        for key in ['plan','result']: self.fields[key].validators.append(MaxLengthValidator(5000));self.fields[key].widget.attrs['maxlength']=5000
    def clean_plan(self): return self.cleaned_data['plan'].replace('\r\n','\n')
    def clean_result(self): return self.cleaned_data['result'].replace('\r\n','\n')
    def clean(self):
        data=super().clean()
        if self.instance.pk:
            if data.get('status')=='done' and self.instance.steps.filter(active=True,done=False).exists(): self.add_error('status','Сначала выполните или уберите из плана незавершённые шаги.')
            if data.get('due_date') and self.instance.steps.filter(active=True,due_date__gt=data['due_date']).exists(): self.add_error('due_date','Есть шаги с более поздним сроком. Сначала измените их сроки.')
        if data.get('status')=='done' and not data.get('result'):
            self.add_error('result','Укажите результат и способ его проверки. Завершение инициативы не подтверждает решения отдельных обращений автоматически.')
        return data

class StepForm(forms.ModelForm):
    import uuid
    revision=forms.IntegerField(min_value=0,widget=forms.HiddenInput,initial=0)
    creation_token=forms.UUIDField(widget=forms.HiddenInput,initial=uuid.uuid4)
    class Meta:
        from .models import InitiativeStep
        model=InitiativeStep
        fields=['title','owner','due_date','active']
        widgets={'due_date':forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d')}
    def __init__(self,*args,allowed_owners,initiative,**kwargs):
        super().__init__(*args,**kwargs)
        from .forms import ResponsibleChoiceField
        self.initiative=initiative
        self.fields['owner']=ResponsibleChoiceField(label='Ответственный за шаг',queryset=allowed_owners)
        self.fields['due_date'].widget.attrs['max']=initiative.due_date.isoformat()
        if self.instance.pk:
            self.fields.pop('creation_token');self.fields['revision'].initial=self.instance.revision
    def clean_due_date(self):
        value=self.cleaned_data['due_date']
        if value>self.initiative.due_date: raise forms.ValidationError('Срок шага не может быть позже срока инициативы.')
        return value

class StepStateForm(forms.Form):
    revision=forms.IntegerField(min_value=0,widget=forms.HiddenInput)
    done=forms.BooleanField(required=False,label='Выполнено')
