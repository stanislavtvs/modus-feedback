from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404,redirect,render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods,require_POST
from .models import ProblemTheme,Initiative,InitiativeStep,InitiativeEvent
from .development_views import accessible_theme,owners_for
from .feature_forms import StepForm,StepStateForm


def back(pk,step=None):
    url=reverse('initiative',args=[pk])
    return redirect(url+(f'#step-{step.pk}' if step else '#checklist'))

@login_required
@require_http_methods(['GET','POST'])
def edit_step(request,pk,step_pk=None):
    theme=accessible_theme(request.user,pk)
    initiative=get_object_or_404(Initiative,theme=theme)
    step=get_object_or_404(InitiativeStep,pk=step_pk,initiative=initiative) if step_pk else None
    form=StepForm(request.POST if request.method=='POST' else None,instance=step,allowed_owners=owners_for(request.user,theme),initiative=initiative,initial=None if step else {'owner':initiative.owner_id,'due_date':initiative.due_date,'active':True})
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            ProblemTheme.objects.select_for_update().get(pk=pk)
            theme=accessible_theme(request.user,pk)
            initiative.refresh_from_db()
            if initiative.status=='done':form.add_error(None,'Сначала верните инициативу в работу. План завершённой инициативы менять нельзя.')
            elif form.cleaned_data['due_date']>initiative.due_date:form.add_error('due_date','Срок инициативы изменился. Проверьте срок шага.')
            elif not owners_for(request.user,theme).filter(pk=form.cleaned_data['owner'].pk).exists():return HttpResponseForbidden('Доступ ответственного изменился.')
            else:
                current=get_object_or_404(InitiativeStep,pk=step_pk,initiative=initiative) if step_pk else None
                if current and current.revision!=form.cleaned_data['revision']:
                    form.add_error(None,'Шаг уже изменён. Обновите страницу перед сохранением.')
                else:
                    before={field:getattr(current,field) for field in form.Meta.fields} if current else {}
                    saved=form.save(commit=False);saved.initiative=initiative
                    if not current:
                        token=form.cleaned_data['creation_token']
                        existing=InitiativeStep.objects.filter(creation_token=token).first()
                        if existing:
                            if existing.initiative_id!=initiative.pk:return HttpResponseForbidden('Некорректный идентификатор шага.')
                            messages.info(request,'Этот шаг уже добавлен.');return back(pk,existing)
                        saved.creation_token=token
                    changed=not current or any(before[field]!=getattr(saved,field) for field in form.Meta.fields)
                    if changed:
                        saved.revision=(current.revision+1) if current else 0;saved.save()
                        InitiativeEvent.objects.create(initiative=initiative,actor=request.user,text=('Изменён шаг: ' if current else 'Добавлен шаг: ')+saved.title+'. Ответственный: '+(saved.owner.get_full_name() or saved.owner.username)+'. Срок: '+str(saved.due_date)+'. '+('Включён в план.' if saved.active else 'Убран из плана, запись сохранена.'))
                    messages.success(request,'Шаг сохранён.');return back(pk,saved)
    return render(request,'feedback/step_edit.html',{'theme':theme,'initiative':initiative,'step':step,'form':form})

@login_required
@require_POST
def step_state(request,pk,step_pk):
    theme=accessible_theme(request.user,pk)
    form=StepStateForm(request.POST)
    if not form.is_valid():messages.error(request,'Некорректная отметка шага.');return back(pk)
    with transaction.atomic():
        ProblemTheme.objects.select_for_update().get(pk=pk)
        theme=accessible_theme(request.user,pk)
        initiative=get_object_or_404(Initiative,theme=theme)
        step=get_object_or_404(InitiativeStep,pk=step_pk,initiative=initiative,active=True)
        if initiative.status=='done':messages.error(request,'Сначала верните инициативу в работу.');return back(pk,step)
        if step.revision!=form.cleaned_data['revision']:messages.warning(request,'Шаг уже изменён. Проверьте актуальную отметку.');return back(pk,step)
        desired=form.cleaned_data['done']
        if step.done!=desired:
            step.done=desired;step.completed_at=timezone.now() if desired else None;step.completed_by=request.user if desired else None;step.revision+=1;step.save()
            InitiativeEvent.objects.create(initiative=initiative,actor=request.user,text=('Выполнен шаг: ' if desired else 'Шаг возвращён в работу: ')+step.title)
        messages.success(request,'Отметка сохранена. Инициатива и обращения не закрывались автоматически.')
    return back(pk,step)
