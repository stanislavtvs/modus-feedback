import re,math
from collections import Counter
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Notification,Event,Ticket

def notify(ticket,actor,text):
    ids={ticket.author_id,ticket.assignee_id}-{None,actor.pk}
    # An unassigned request enters the administrators' queue.
    if not ticket.assignee_id: ids.update(get_user_model().objects.filter(is_active=True,profile__role='admin').values_list('id',flat=True))
    Notification.objects.bulk_create([Notification(recipient_id=pk,ticket=ticket,text=text) for pk in ids if pk!=actor.pk])
def route(ticket):
    candidate=ticket.category.responsible
    if candidate and candidate.is_active and (candidate.is_superuser or hasattr(candidate,'profile') and candidate.profile.role in ['manager','admin']): return candidate
    return get_user_model().objects.filter(is_active=True,profile__role='manager',profile__department=ticket.department).order_by('pk').first()
def tokens(text):
    stop={'котор','предла','можно','нужно','чтобы','сотруд','работ','полез','иногда','было','этого','этой','будет'}
    return Counter(w[:6] for w in re.findall(r'[а-яёa-z]{4,}',text.lower()) if w[:5] not in stop)
def similar(ticket,queryset):
    a=tokens(ticket.description+' '+ticket.title)
    results=[]
    for other in queryset.exclude(pk=ticket.pk)[:500]:
        b=tokens(other.description+' '+other.title)
        norm=math.sqrt(sum(x*x for x in a.values())*sum(x*x for x in b.values()))
        score=sum(v*b[k] for k,v in a.items())/norm if norm else 0
        if score>=.23: results.append((other,round(score*100)))
    return sorted(results,key=lambda x:x[1],reverse=True)[:4]
