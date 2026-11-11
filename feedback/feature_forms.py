from django import forms
from django.core.validators import MaxLengthValidator,MinValueValidator,MaxValueValidator
from .models import ImprovementPost, FollowUpPolicy, ProblemTheme

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
