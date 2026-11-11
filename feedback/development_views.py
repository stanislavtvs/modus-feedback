from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Exists,OuterRef,Q
from django.http import Http404,HttpResponseForbidden
from django.shortcuts import get_object_or_404,redirect,render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from .models import Ticket,OutcomeReview,FollowUpAlert,ProblemTheme,Initiative,InitiativeEvent
from .access import role,visible,processable
from .feature_forms import InitiativeForm


def accessible_theme(user,pk):
    if role(user) not in ['manager','admin']: raise Http404()
    theme=get_object_or_404(ProblemTheme.objects.prefetch_related('tickets__department'),pk=pk,status='confirmed')
    ids={item.pk for item in theme.tickets.all()}
    if not ids or not ids<=set(processable(user).values_list('pk',flat=True)): raise Http404()
    return theme


def owners_for(user,theme):
    users=get_user_model().objects.filter(is_active=True).filter(Q(is_superuser=True)|Q(profile__role__in=['admin','manager'])).distinct()
    # A new initiative must not grant its owner access to unrelated tickets.
    candidates=[]
    for candidate in users:
        if all(processable(candidate).filter(pk=t.pk).exists() for t in theme.tickets.all()): candidates.append(candidate.pk)
    return users.filter(pk__in=candidates)


@login_required
@require_http_methods(['GET','POST'])
def initiative(request,pk):
    theme=accessible_theme(request.user,pk)
    item=Initiative.objects.filter(theme=theme).first()
    form=InitiativeForm(request.POST if request.method=='POST' else None,instance=item,allowed_owners=owners_for(request.user,theme),initial=None if item else {'goal':theme.title,'due_date':timezone.localdate()+timedelta(days=14),'owner':request.user.pk})
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            ProblemTheme.objects.select_for_update().get(pk=pk)
            theme=accessible_theme(request.user,pk)
            if form.cleaned_data['owner'].pk not in owners_for(request.user,theme).values_list('pk',flat=True): return HttpResponseForbidden('Доступ ответственного изменился.')
            current=Initiative.objects.filter(theme=theme).first()
            before={field:str(getattr(current,field)) for field in form.Meta.fields} if current else {}
            saved=form.save(commit=False)
            if current: saved.pk=current.pk
            saved.theme=theme
            changed=[field for field in form.Meta.fields if before.get(field)!=str(getattr(saved,field))]
            saved.save()
            if changed:
                labels=[str(form.fields[field].label) for field in changed]
                InitiativeEvent.objects.create(initiative=saved,actor=request.user,text=('Создан паспорт инициативы.' if not current else 'Изменено: '+', '.join(labels)+'.')+' Цель: '+saved.goal+'. Ответственный: '+(saved.owner.get_full_name() or saved.owner.username)+'. Срок: '+str(saved.due_date)+'. Состояние: '+saved.get_status_display()+'. План: '+saved.plan+' Результат: '+saved.result)
            messages.success(request,'Паспорт системной проблемы сохранён. Статусы связанных обращений не изменены.')
            return redirect('initiative',pk=pk)
    if request.method=='POST' and item: item.refresh_from_db()
    return render(request,'feedback/initiative.html',{'theme':theme,'initiative':item,'form':form})


@login_required
def pulse(request):
    qs=visible(request.user)
    helped=OutcomeReview.objects.filter(ticket_id=OuterRef('pk'),revision=OuterRef('resolution_revision'),verdict='helped')
    qs=qs.annotate(author_confirmed=Exists(helped))
    rows=[]
    departments=qs.values('department_id','department__name').order_by('department__name').distinct()
    for dept in departments:
        tickets=qs.filter(department_id=dept['department_id'])
        total=tickets.count();active=tickets.exclude(status__in=['implemented','rejected','closed']).count()
        verified=tickets.filter(status__in=['implemented','closed'],author_confirmed=True).count()
        offered=tickets.filter(status__in=['implemented','closed'],resolution_revision__gt=0).count()
        rows.append({'name':dept['department__name'],'total':total,'active':active,
                     'attention':FollowUpAlert.objects.filter(ticket__in=tickets.exclude(status__in=['implemented','rejected','closed']),resolved_at__isnull=True).count(),
                     'confirmed':verified,'offered':offered,'confirmation_percent':round(100*verified/offered) if offered else None,
                     'returned':tickets.filter(outcome_reviews__verdict='not_helped').distinct().count()})
    allowed=set(processable(request.user).values_list('pk',flat=True))
    themes=[]
    for theme in ProblemTheme.objects.filter(status='confirmed').prefetch_related('tickets').select_related('initiative'):
        ids={t.pk for t in theme.tickets.all()}
        if ids and ids<=allowed: themes.append(theme)
    return render(request,'feedback/pulse.html',{'rows':rows,'themes':themes,'personal_scope':role(request.user)=='employee'})


@login_required
def demo(request):
    if not settings.DEMO_MODE: raise Http404()
    return render(request,'feedback/demo.html',{'demo_ticket':visible(request.user).filter(source_id='DEMO-01').first(),'demo_result':visible(request.user).filter(source_id='DEMO-03').first(),'demo_theme':ProblemTheme.objects.filter(fingerprint='demo-system-problem').first() if role(request.user)!='employee' else None})
