from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction,connection
from django.db.models import Count,Q
from django.http import FileResponse,JsonResponse,HttpResponseForbidden
from django.shortcuts import render,redirect,get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from .models import Ticket,Category,Department,Event,Comment,Attachment,Notification
from .forms import TicketForm,ProcessForm,CommentForm
from .access import visible,can_process,role
from .services import route,notify,similar
CLOSED=['implemented','rejected','closed']
def summary(qs):
    total=qs.count()
    closed=qs.filter(status__in=CLOSED).count()
    return {'total':total,'active':total-closed,'closed':closed,'overdue':qs.exclude(status__in=CLOSED).filter(due_at__lt=timezone.now()).count(),'closed_percent':round(closed*100/total) if total else 0,'implemented':qs.filter(status='implemented').count()}
@login_required
def dashboard(request):
    qs=visible(request.user)
    return render(request,'feedback/dashboard.html',{'stats':summary(qs),'recent':qs[:6],'urgent':qs.exclude(status__in=CLOSED).filter(due_at__lt=timezone.now())[:5]})
@login_required
def ticket_list(request):
    qs=visible(request.user)
    for key,field in [('status','status'),('category','category_id'),('department','department_id'),('kind','kind'),('priority','priority')]:
        value=request.GET.get(key,'')
        if value and (not field.endswith('_id') or value.isdigit()): qs=qs.filter(**{field:value})
    term=request.GET.get('q','').strip()[:200]
    if term: qs=qs.filter(Q(title__icontains=term)|Q(description__icontains=term)|Q(resolution__icontains=term))
    if request.GET.get('overdue'): qs=qs.exclude(status__in=CLOSED).filter(due_at__lt=timezone.now())
    if request.GET.get('mine'): qs=qs.filter(author=request.user)
    if request.GET.get('assigned'): qs=qs.filter(assignee=request.user)
    for key,lookup in [('from','created_at__date__gte'),('to','created_at__date__lte')]:
        value=request.GET.get(key)
        if value:
            from django.forms import DateField,ValidationError
            try: qs=qs.filter(**{lookup:DateField().clean(value)})
            except ValidationError: messages.warning(request,'Дата фильтра не распознана.')
    from django.core.paginator import Paginator
    page=Paginator(qs,20).get_page(request.GET.get('page'))
    params=request.GET.copy();params.pop('page',None)
    return render(request,'feedback/list.html',{'page':page,'querystring':params.urlencode(),'categories':Category.objects.all(),'departments':Department.objects.all(),'statuses':Ticket.Status.choices,'kinds':Ticket.Kind.choices,'priorities':Ticket.Priority.choices})
@login_required
@require_http_methods(['GET','POST'])
def create(request):
    if not hasattr(request.user,'profile'): return HttpResponseForbidden('Администратор должен назначить вам подразделение.')
    form=TicketForm(request.POST or None,request.FILES or None)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            ticket=form.save(commit=False)
            ticket.author=request.user;ticket.department=request.user.profile.department
            ticket.due_at=timezone.now()+timedelta(days=ticket.category.sla_days)
            ticket.assignee=route(ticket);ticket.save()
            Event.objects.create(ticket=ticket,actor=request.user,text='Обращение зарегистрировано. '+('Назначен ответственный: '+(ticket.assignee.get_full_name() or ticket.assignee.username) if ticket.assignee else 'Передано в очередь администраторов: требуется назначение.'))
            f=form.cleaned_data.get('attachment')
            if f: Attachment.objects.create(ticket=ticket,file=f,name=f.name)
            notify(ticket,request.user,'Новое обращение '+ticket.reference)
        messages.success(request,'Обращение зарегистрировано.')
        return redirect('detail',pk=ticket.pk)
    return render(request,'feedback/create.html',{'form':form})
@login_required
@require_http_methods(['GET','POST'])
def detail(request,pk):
    ticket=get_object_or_404(visible(request.user),pk=pk)
    process=can_process(request.user,ticket)
    form=ProcessForm(initial={'status':ticket.status,'assignee':ticket.assignee,'priority':ticket.priority,'due_at':timezone.localtime(ticket.due_at),'resolution':ticket.resolution}) if process else None
    comment_form=CommentForm()
    if request.method=='POST':
        action=request.POST.get('action')
        if action=='process':
            if not process: return HttpResponseForbidden('Нет прав на обработку обращения.')
            form=ProcessForm(request.POST)
            if form.is_valid():
                with transaction.atomic():
                    locked=Ticket.objects.select_for_update().get(pk=pk)
                    changes=[]
                    for field in ['status','assignee','priority','due_at','resolution']:
                        old=getattr(locked,field);new=form.cleaned_data[field]
                        if field=='due_at' and old.replace(second=0,microsecond=0)==new: continue
                        if old!=new:
                            label={'status':'Статус','assignee':'Ответственный','priority':'Приоритет','due_at':'Срок','resolution':'Решение'}[field]
                            if field=='status': old=dict(Ticket.Status.choices)[old]; shown=dict(Ticket.Status.choices)[new]
                            elif field=='priority': old=dict(Ticket.Priority.choices)[old]; shown=dict(Ticket.Priority.choices)[new]
                            elif field=='due_at': old=timezone.localtime(old).strftime('%d.%m.%Y %H:%M');shown=timezone.localtime(new).strftime('%d.%m.%Y %H:%M')
                            elif field=='assignee': old=(old.get_full_name() or old.username) if old else None;shown=(new.get_full_name() or new.username) if new else None
                            else: shown=new
                            changes.append(f'{label}: {old or "—"} → {shown or "—"}')
                            setattr(locked,field,new)
                    if changes:
                        if locked.author_id!=request.user.pk and not locked.first_response_at: locked.first_response_at=timezone.now()
                        locked.closed_at=(locked.closed_at or timezone.now()) if locked.status in CLOSED else None
                        locked.save()
                        Event.objects.create(ticket=locked,actor=request.user,text='; '.join(changes))
                        notify(locked,request.user,'Обновлено обращение '+locked.reference)
                messages.success(request,'Изменения сохранены.')
                return redirect('detail',pk=pk)
        elif action=='comment':
            comment_form=CommentForm(request.POST)
            if comment_form.is_valid():
                with transaction.atomic():
                    locked=Ticket.objects.select_for_update().get(pk=pk)
                    Comment.objects.create(ticket=locked,author=request.user,text=comment_form.cleaned_data['text'])
                    if process and locked.author_id!=request.user.pk and not locked.first_response_at:
                        locked.first_response_at=timezone.now();locked.save(update_fields=['first_response_at'])
                    notify(locked,request.user,'Новый комментарий к '+locked.reference)
                messages.success(request,'Комментарий добавлен.')
                return redirect('detail',pk=pk)
    return render(request,'feedback/detail.html',{'ticket':ticket,'process_form':form,'comment_form':comment_form,'similar':similar(ticket,visible(request.user))})
@login_required
def download(request,pk):
    attachment=get_object_or_404(Attachment,pk=pk,ticket__in=visible(request.user))
    response=FileResponse(attachment.file.open('rb'),as_attachment=True,filename=attachment.name,content_type='application/octet-stream')
    response['X-Content-Type-Options']='nosniff'
    return response
@login_required
@require_http_methods(['GET','POST'])
def notifications(request):
    qs=Notification.objects.filter(recipient=request.user)
    if request.method=='POST':
        qs.update(read=True);return redirect('notifications')
    return render(request,'feedback/notifications.html',{'notifications':qs[:100]})
@login_required
def analytics(request):
    qs=visible(request.user)
    times=[(t.first_response_at-t.created_at).total_seconds()/3600 for t in qs.filter(first_response_at__isnull=False)]
    categories=list(qs.values('category__name').annotate(count=Count('id')).order_by('-count'))
    for row in categories: row['percent']=round(row['count']*100/max(qs.count(),1))
    types=[{'label':label,'count':qs.filter(kind=key).count()} for key,label in Ticket.Kind.choices]
    statuses=[{'label':label,'count':qs.filter(status=key).count()} for key,label in Ticket.Status.choices]
    pairs=[];seen=set()
    for ticket in qs[:100]:
        for other,score in similar(ticket,qs):
            key=tuple(sorted([ticket.pk,other.pk]))
            if key not in seen: pairs.append((ticket,other,score));seen.add(key)
    return render(request,'feedback/analytics.html',{'stats':summary(qs),'response_hours':round(sum(times)/len(times),1) if times else None,'response_count':len(times),'categories':categories,'types':types,'statuses':statuses,'pairs':sorted(pairs,key=lambda x:x[2],reverse=True)[:10],'resolved':qs.exclude(resolution='').count()})
def health(request):
    try:
        with connection.cursor() as cursor: cursor.execute('SELECT 1')
        return JsonResponse({'status':'ok'})
    except Exception: return JsonResponse({'status':'unavailable'},status=503)
