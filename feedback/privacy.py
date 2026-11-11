"""Local heuristic inspection. No text is sent to Ollama until a reviewed snapshot matches."""
import hashlib,json,re
from collections import Counter
from urllib.parse import urlsplit
from django.conf import settings
from django.core import signing
from django.http import JsonResponse

PATTERNS=[
    ('email',re.compile(r'(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+',re.I),'[EMAIL СКРЫТ]'),
    ('телефон',re.compile(r'(?<!\w)(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)'),'[ТЕЛЕФОН СКРЫТ]'),
    ('идентификатор из 12 цифр',re.compile(r'(?<!\d)\d{12}(?!\d)'),'[ИДЕНТИФИКАТОР СКРЫТ]'),
    ('паспорт',re.compile(r'\b\d{2}\s?\d{2}\s+\d{6}\b'),'[ПАСПОРТ СКРЫТ]'),
]

def inspect(packet):
    counts=Counter()
    def mask(value):
        if isinstance(value,str):
            for label,pattern,replacement in PATTERNS:
                value,count=pattern.subn(replacement,value);counts[label]+=count
            return value
        if isinstance(value,list): return [mask(item) for item in value]
        if isinstance(value,dict): return {key:mask(item) for key,item in value.items()}
        return value
    masked=mask(packet)
    return masked,[{'label':label,'count':count} for label,count in counts.items() if count]

def reviewed_packet(request,mode,source,categories,body):
    packet={'source':source,'categories':categories}
    digest=hashlib.sha256(json.dumps(packet,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    expected={'user':request.user.pk,'mode':mode,'digest':digest}
    token=body.get('privacy_token')
    if token:
        try:
            if signing.loads(token,salt='ai-preview',max_age=300)!=expected: raise signing.BadSignature()
            if type(body.get('hide_sensitive')) is not bool: raise signing.BadSignature()
        except (signing.BadSignature,TypeError,ValueError):
            return None,JsonResponse({'error':'Текст, доступ или срок проверки изменились. Откройте предварительный просмотр заново.'},status=409)
        return (inspect(packet)[0] if body['hide_sensitive'] else packet),None
    masked,findings=inspect(packet)
    destination=urlsplit(settings.OLLAMA_URL)
    return None,JsonResponse({'preview':{'original':packet,'masked':masked,'findings':findings,'destination':f'{destination.scheme}://{destination.hostname}'+(f':{destination.port}' if destination.port else ''),'model':settings.OLLAMA_MODEL},'privacy_token':signing.dumps(expected,salt='ai-preview')},status=409)

def json_body(request):
    if len(request.body)>64*1024: raise ValueError()
    if request.content_type=='application/json':
        body=json.loads(request.body or '{}')
        if not isinstance(body,dict): raise ValueError()
        return body
    return {'privacy_token':request.POST.get('privacy_token'),'hide_sensitive':{'true':True,'false':False}.get(request.POST.get('hide_sensitive'))}
