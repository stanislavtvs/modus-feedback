"""Idempotent in-app reminders; ticket locks serialize competing workers."""
import hashlib
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q,Max
from django.utils import timezone
from .models import Ticket,FollowUpPolicy,FollowUpAlert,Notification
from .services import route
from .access import can_process

FINAL=['implemented','rejected','closed']

def check_followups(now=None):
    now=now or timezone.now()
    policy,_=FollowUpPolicy.objects.get_or_create(pk=1)
    counts={'reminded':0,'escalated':0,'resolved':0}
    if not policy.enabled: return counts
    admins=get_user_model().objects.filter(is_active=True).filter(Q(is_superuser=True)|Q(profile__role='admin')).distinct()
    for pk in Ticket.objects.values_list('pk',flat=True).iterator():
        with transaction.atomic():
            ticket=Ticket.objects.select_for_update(of=('self',)).select_related('category','assignee','author').get(pk=pk)
            alert=FollowUpAlert.objects.filter(ticket=ticket,resolved_at__isnull=True).first()
            comment=ticket.comments.aggregate(value=Max('created_at'))['value']
            event=ticket.events.aggregate(value=Max('created_at'))['value']
            last=max(x for x in [ticket.created_at,ticket.updated_at,comment,event] if x)
            kind=None; anchor=None
            if ticket.status not in FINAL:
                if not ticket.first_response_at and now>=ticket.created_at+timedelta(hours=policy.first_response_hours):
                    kind='no_response';anchor=ticket.created_at
                elif now>=last+timedelta(hours=policy.inactivity_hours):
                    kind='stale';anchor=last
                elif ticket.due_at<now and now>=last+timedelta(hours=1):
                    kind='overdue';anchor=f'{ticket.due_at}:{last}'
            episode=hashlib.sha256(f'{kind}:{anchor}'.encode()).hexdigest() if kind else None
            if alert and (not kind or alert.kind!=kind or alert.episode!=episode):
                alert.resolved_at=now;alert.save(update_fields=['resolved_at']);counts['resolved']+=1;alert=None
            if not kind: continue
            if alert is None:
                alert=FollowUpAlert.objects.create(ticket=ticket,kind=kind,episode=episode,reminded_at=now)
                if ticket.status=='clarify': recipients=[ticket.author]
                else:
                    assigned=ticket.assignee
                    if not assigned or not assigned.is_active or not can_process(assigned,ticket): assigned=route(ticket)
                    if assigned and not can_process(assigned,ticket): assigned=None
                    recipients=[assigned] if assigned else list(admins)
                Notification.objects.bulk_create([Notification(recipient=user,ticket=ticket,text=f'Напоминание: {ticket.reference} · {alert.get_kind_display()}',created_at=now) for user in recipients])
                counts['reminded']+=1
            elif not alert.escalated_at and now>=alert.reminded_at+timedelta(hours=policy.escalation_hours):
                Notification.objects.bulk_create([Notification(recipient=user,ticket=ticket,text=f'Требует внимания администратора: {ticket.reference} · {alert.get_kind_display()}',created_at=now) for user in admins])
                alert.escalated_at=now;alert.save(update_fields=['escalated_at']);counts['escalated']+=1
    return counts
