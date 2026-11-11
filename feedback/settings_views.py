from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from .access import role
from .forms import CategoryForm
from .models import Category, Department


@login_required
@require_http_methods(['GET', 'POST'])
def routing_settings(request, pk=None):
    if role(request.user) != 'admin':
        return HttpResponseForbidden('Настройки доступны только администратору системы.')
    category = get_object_or_404(Category, pk=pk) if pk is not None else None
    form = CategoryForm(request.POST if request.method == 'POST' else None, instance=category)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        messages.success(request, f'Категория «{saved.name}» ' + ('обновлена.' if category else 'создана.'))
        return redirect('settings')
    categories = Category.objects.select_related('responsible__profile__department').annotate(ticket_count=Count('ticket')).order_by('name')
    return render(request, 'feedback/settings.html', {
        'form': form, 'editing': category, 'categories': categories,
        'category_count': categories.count(),
        'departments': Department.objects.annotate(manager_count=Count('profile', filter=Q(profile__role='manager', profile__user__is_active=True))).order_by('name'),
    })
