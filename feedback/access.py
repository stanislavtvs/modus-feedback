from django.db.models import Q
from .models import Ticket,Profile

def role(user):
    if user.is_superuser: return 'admin'
    try: return user.profile.role
    except Profile.DoesNotExist: return 'employee'
def visible(user):
    qs=Ticket.objects.select_related('author','assignee','category','department')
    if role(user)=='admin': return qs
    condition=Q(author=user)|Q(assignee=user)
    if role(user)=='manager': condition|=Q(department=user.profile.department)
    return qs.filter(condition).distinct()
def can_process(user,ticket):
    return role(user)=='admin' or (role(user)=='manager' and (ticket.department_id==user.profile.department_id or ticket.assignee_id==user.pk))
