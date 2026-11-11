import hashlib
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F,Q,Exists,OuterRef
from django.http import HttpResponseForbidden,JsonResponse
from django.shortcuts import get_object_or_404,redirect,render
from django.utils import timezone
from django.views.decorators.http import require_POST,require_http_methods
from .models import Ticket,OutcomeReview,ImprovementPost,ProblemTheme,FollowUpAlert,FollowUpPolicy,Event
from .access import visible,processable,can_process,role
from .feature_forms import OutcomeForm,PublicationForm,ThemeForm,PolicyForm
from .services import notify,route
from . import ai
from .followups import check_followups
from datetime import timedelta

RESULT_STATUSES=['implemented','closed']

def confirmed(ticket):
    return ticket.status in RESULT_STATUSES and ticket.resolution_revision>0 and ticket.outcome_reviews.filter(revision=ticket.resolution_revision,verdict='helped').exists()

def withdraw_publication(ticket):
    ImprovementPost.objects.filter(ticket=ticket).exclude(status='withdrawn').update(status='withdrawn')

@login_required
@require_POST
def outcome(request,pk):
    ticket=get_object_or_404(visible(request.user),pk=pk)
    if ticket.author_id!=request.user.pk: return HttpResponseForbidden('Результат подтверждает автор обращения.')
    form=OutcomeForm(request.POST)
    if not form.is_valid():
        from .views import render_detail
        return render_detail(request,ticket,outcome_form=form)
    with transaction.atomic():
        ticket=Ticket.objects.select_for_update().get(pk=pk)
        if ticket.status not in RESULT_STATUSES or form.cleaned_data['revision']!=ticket.resolution_revision or ticket.outcome_reviews.filter(revision=ticket.resolution_revision).exists():
            messages.warning(request,'Решение уже оценено или изменилось. Проверьте актуальную версию.')
            return redirect('detail',pk=pk)
        review=OutcomeReview.objects.create(ticket=ticket,author=request.user,**form.cleaned_data)
        if review.verdict=='not_helped':
            ticket.status='work';ticket.closed_at=None;ticket.result_offered_at=None
            ticket.due_at=timezone.now()+timedelta(days=ticket.category.sla_days)
            if not ticket.assignee or not ticket.assignee.is_active: ticket.assignee=route(ticket)
            ticket.save();withdraw_publication(ticket)
        Event.objects.create(ticket=ticket,actor=request.user,text=f'Проверка решения, версия {review.revision}: {review.get_verdict_display()}. '+review.comment)
        notify(ticket,request.user,'Автор проверил результат '+ticket.reference+': '+review.get_verdict_display())
    messages.success(request,'Спасибо! '+('Обращение возвращено в работу.' if review.verdict=='not_helped' else 'Результат подтверждён.'))
    return redirect('detail',pk=pk)

@login_required
@require_http_methods(['GET','POST'])
def publication(request,pk):
    ticket=get_object_or_404(processable(request.user),pk=pk)
    post=ImprovementPost.objects.filter(ticket=ticket).first()
    eligible=confirmed(ticket)
    form=PublicationForm(request.POST if request.method=='POST' else None,instance=post,initial=None if post else {'title':ticket.title,'before':ticket.description[:1500],'after':ticket.resolution[:1500]})
    if request.method=='POST':
        with transaction.atomic():
            ticket=Ticket.objects.select_for_update().get(pk=pk)
            if not can_process(request.user,ticket): return HttpResponseForbidden('Доступ изменился.')
            action=request.POST.get('action')
            if action=='withdraw':
                withdraw_publication(ticket);messages.success(request,'История снята с публикации.');return redirect('publication',pk=pk)
            if not confirmed(ticket):
                messages.error(request,'Публикация доступна после подтверждения актуального решения автором.')
            elif action in ['draft','publish'] and form.is_valid():
                # Serialize concurrent editors on the ticket and use the latest post instance.
                post=ImprovementPost.objects.filter(ticket=ticket).first()
                if post: form.instance.pk=post.pk
                saved=form.save(commit=False);saved.ticket=ticket;saved.source_revision=ticket.resolution_revision;saved.editor=request.user
                saved.status='published' if action=='publish' else 'draft'
                saved.published_at=timezone.now() if action=='publish' else None;saved.save()
                Event.objects.create(ticket=ticket,actor=request.user,text='История улучшения '+('опубликована.' if action=='publish' else 'сохранена как черновик.'))
                messages.success(request,'История '+('опубликована.' if action=='publish' else 'сохранена.'))
                return redirect('publication',pk=pk)
    return render(request,'feedback/publication.html',{'ticket':ticket,'post':post,'eligible':eligible,'form':form})

@login_required
def improvements(request):
    reviews=OutcomeReview.objects.filter(ticket_id=OuterRef('ticket_id'),revision=OuterRef('source_revision'),verdict='helped')
    posts=ImprovementPost.objects.select_related('ticket__department').filter(status='published',source_revision=F('ticket__resolution_revision'),ticket__status__in=RESULT_STATUSES).annotate(verified=Exists(reviews)).filter(verified=True)
    if role(request.user)!='admin':
        dept=getattr(getattr(request.user,'profile',None),'department_id',None)
        posts=posts.filter(Q(audience='company')|Q(ticket__department_id=dept))
    allowed=set(visible(request.user).values_list('pk',flat=True))
    items=[{'post':post,'can_open':post.ticket_id in allowed} for post in posts.order_by('-published_at')]
    return render(request,'feedback/improvements.html',{'items':items})

@login_required
@require_http_methods(['GET','POST'])
def radar(request):
    if role(request.user) not in ['manager','admin']: return HttpResponseForbidden('Радар доступен руководителям.')
    allowed=set(processable(request.user).values_list('pk',flat=True))
    themes=[]
    for theme in ProblemTheme.objects.prefetch_related('tickets__department').order_by('-created_at'):
        ids={ticket.pk for ticket in theme.tickets.all()}
        if ids and ids<=allowed: themes.append(theme)
    if request.method=='POST':
        theme=next((item for item in themes if str(item.pk)==request.POST.get('theme_id')),None)
        if theme is None: return HttpResponseForbidden('Группа недоступна.')
        with transaction.atomic():
            theme=ProblemTheme.objects.select_for_update().get(pk=theme.pk)
            member_ids=set(theme.tickets.values_list('pk',flat=True))
            if not member_ids<=set(processable(request.user).values_list('pk',flat=True)): return HttpResponseForbidden('Доступ изменился.')
            action=request.POST.get('action')
            if action=='dismiss': theme.status='dismissed';theme.confirmed_by=request.user;theme.save();return redirect('radar')
            form=ThemeForm(request.POST,instance=theme,prefix=f'theme-{theme.pk}')
            if action=='confirm' and form.is_valid():
                theme=form.save(commit=False);theme.status='confirmed';theme.confirmed_by=request.user;theme.save()
                messages.success(request,'Повторяющаяся проблема подтверждена. Исходные обращения сохранены отдельно.')
                return redirect('radar')
            messages.error(request,'Проверьте название (до 140 символов) и описание (до 900 символов).')
    for theme in themes: theme.edit_form=ThemeForm(instance=theme,prefix=f'theme-{theme.pk}')
    return render(request,'feedback/radar.html',{'themes':themes,'candidate_count':processable(request.user).exclude(kind='praise').count()})

@login_required
@require_POST
def radar_generate(request):
    if role(request.user) not in ['manager','admin']: return JsonResponse({'error':'Нет доступа.'},status=403)
    tickets=list(processable(request.user).exclude(kind='praise')[:24])
    if len(tickets)<2: return JsonResponse({'error':'Нужно хотя бы два доступных обращения.'},status=400)
    source=[{'id':t.pk,'title':t.title,'description':t.description[:450],'category':t.category.name} for t in tickets]
    try:
        result=ai.generate(request.user,'radar',source,[{'id':t.pk} for t in tickets])
        # Defense in depth even if the provider or validator implementation changes.
        result=ai.validate(result,ai.schema_for('radar',[{'id':t.pk} for t in tickets]))
        used=set();created=0
        for group in result['groups']:
            ids=set(group['ticket_ids'])
            if used&ids or not group['title'] or not group['summary']: raise ai.AIInvalidResponse()
            used|=ids
        with transaction.atomic():
            if not used<=set(processable(request.user).values_list('pk',flat=True)): return JsonResponse({'error':'Доступ к обращениям изменился. Повторите анализ.'},status=409)
            for group in result['groups']:
                ids=sorted(group['ticket_ids'])
                fingerprint=hashlib.sha256(','.join(map(str,ids)).encode()).hexdigest()
                theme,new=ProblemTheme.objects.get_or_create(fingerprint=fingerprint,defaults={'title':group['title'],'summary':group['summary'],'created_by':request.user})
                if new: theme.tickets.set(ids);created+=1
        return JsonResponse({'created':created,'message':f'Новых групп: {created}. Предложения требуют проверки руководителем.'})
    except ai.AIBusy: return JsonResponse({'error':'Ваш предыдущий запрос ещё выполняется.'},status=429)
    except ai.AIUnavailable: return JsonResponse({'error':'ИИ недоступен. Проверьте VPN и Ollama.'},status=503)
    except ai.AIInvalidResponse: return JsonResponse({'error':'Ответ ИИ не прошёл проверку. Ничего не сохранено.'},status=502)

@login_required
@require_http_methods(['GET','POST'])
def followups(request):
    policy,_=FollowUpPolicy.objects.get_or_create(pk=1)
    form=PolicyForm(request.POST if request.method=='POST' and request.POST.get('action')=='policy' else None,instance=policy)
    if request.method=='POST':
        if role(request.user)!='admin': return HttpResponseForbidden('Правила меняет администратор.')
        if request.POST.get('action')=='check':
            result=check_followups();messages.success(request,f"Проверка завершена. Напоминаний: {result['reminded']}, эскалаций: {result['escalated']}.");return redirect('followups')
        if request.POST.get('action')=='policy' and form.is_valid():
            form.save();messages.success(request,'Правила контроля сохранены.');return redirect('followups')
    alerts=FollowUpAlert.objects.filter(ticket__in=visible(request.user),resolved_at__isnull=True).select_related('ticket').order_by('reminded_at')
    return render(request,'feedback/followups.html',{'alerts':alerts,'policy':policy,'policy_form':form})
