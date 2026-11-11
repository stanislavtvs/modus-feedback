from .models import Notification
from .access import role


def navigation(request):
    route = request.resolver_match.url_name if request.resolver_match else ''
    titles = {'dashboard': 'Обзор', 'tickets': 'Обращения', 'create': 'Новое обращение',
              'detail': 'Карточка обращения', 'analytics': 'Аналитика',
              'notifications': 'Уведомления', 'login': 'Вход', 'settings': 'Настройки и маршрутизация', 'category_edit': 'Настройки и маршрутизация'}
    nav = 'settings' if route == 'category_edit' else route
    if route == 'tickets':
        if request.GET.get('mine'):
            nav = 'mine'
        elif request.GET.get('assigned'):
            nav = 'assigned'
    context = {'page_title': titles.get(route, 'Модус'), 'active_nav': nav}
    if request.user.is_authenticated:
        user_role = role(request.user)
        context.update(unread_count=Notification.objects.filter(recipient=request.user, read=False).count(),
                       user_role=user_role,
                       role_label={'employee': 'Сотрудник', 'manager': 'Руководитель', 'admin': 'Администратор'}[user_role])
    return context
