import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from .access import visible,can_process
from .models import Category
from .ai import generate,AIUnavailable,AIBusy,AIInvalidResponse

def response(user,mode,source,categories):
    try:
        data=generate(user,mode,source,categories)
        if mode=='draft':
            if not data['title'] or not data['description']: raise AIInvalidResponse()
            data['category_name']=next((c['name'] for c in categories if c['id']==data['category_id']),None)
        return JsonResponse({'result':data})
    except AIBusy:
        return JsonResponse({'error':'Предыдущий запрос ещё выполняется. Подождите немного.'},status=429)
    except AIUnavailable:
        return JsonResponse({'error':'ИИ сейчас недоступен. Введённый текст не изменён. Повторите попытку позже.'},status=503)
    except AIInvalidResponse:
        return JsonResponse({'error':'Модель вернула неполный или некорректный ответ. Попробуйте ещё раз.'},status=502)

@login_required
@require_POST
def draft(request):
    if not hasattr(request.user,'profile'): return JsonResponse({'error':'Для подачи обращения нужен профиль с подразделением.'},status=403)
    if len(request.body)>64*1024: return JsonResponse({'error':'Текст слишком длинный.'},status=400)
    try:
        body=json.loads(request.body)
        if not isinstance(body,dict): raise ValueError()
        source={}
        for key,limit in [('title',180),('description',8000),('suggestion',4000)]:
            value=body.get(key,'')
            if not isinstance(value,str) or len(value)>limit: raise ValueError()
            source[key]=value.strip()
        if len(source['description'])<15:
            return JsonResponse({'error':'Сначала опишите ситуацию хотя бы в одном предложении (от 15 символов).'},status=400)
    except (ValueError,TypeError,UnicodeDecodeError):
        return JsonResponse({'error':'Проверьте текст: заголовок до 180, описание до 8000, решение до 4000 символов.'},status=400)
    categories=list(Category.objects.order_by('name').values('id','name')[:100])
    return response(request.user,'draft',source,categories)

@login_required
@require_POST
def analyze(request,pk):
    ticket=get_object_or_404(visible(request.user),pk=pk)
    source={'title':ticket.title,'description':ticket.description[:8000],
            'suggestion':ticket.suggestion[:4000],'category':ticket.category.name,
            'status':ticket.get_status_display(),'resolution':ticket.resolution[:2000],
            'comments':list(ticket.comments.order_by('-created_at').values_list('text',flat=True)[:5])}
    source['comments']=[text[:1000] for text in source['comments']]
    result=response(request.user,'analyze',source,[])
    if result.status_code==200 and not can_process(request.user,ticket):
        body=json.loads(result.content);body['result'].pop('reply_draft',None)
        return JsonResponse(body)
    return result
