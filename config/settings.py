import os
from pathlib import Path
BASE_DIR=Path(__file__).resolve().parent.parent
DEBUG=os.getenv('DEBUG','0')=='1'
SECRET_KEY=os.environ.get('SECRET_KEY','local-tests-only-not-for-production')
if not DEBUG and SECRET_KEY=='local-tests-only-not-for-production' and os.getenv('DB_ENGINE')!='sqlite':
    raise RuntimeError('Set SECRET_KEY')
ALLOWED_HOSTS=os.getenv('ALLOWED_HOSTS','localhost,127.0.0.1,testserver').split(',')
CSRF_TRUSTED_ORIGINS=[v for v in os.getenv('CSRF_TRUSTED_ORIGINS','').split(',') if v]
INSTALLED_APPS=['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','feedback']
MIDDLEWARE=['django.middleware.security.SecurityMiddleware','whitenoise.middleware.WhiteNoiseMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF='config.urls'
TEMPLATES=[{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'templates'],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages','feedback.context.navigation']}}]
WSGI_APPLICATION='config.wsgi.application'
DATABASES={'default':{'ENGINE':'django.db.backends.postgresql','NAME':os.getenv('POSTGRES_DB','modus'),'USER':os.getenv('POSTGRES_USER','modus'),'PASSWORD':os.getenv('POSTGRES_PASSWORD',''),'HOST':os.getenv('POSTGRES_HOST','db'),'PORT':os.getenv('POSTGRES_PORT','5432')}}
if os.getenv('DB_ENGINE')=='sqlite': DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':BASE_DIR/'local.sqlite3'}}
AUTH_PASSWORD_VALIDATORS=[{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator'},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE='ru-ru'
TIME_ZONE='Asia/Almaty'
USE_I18N=True
USE_TZ=True
STATIC_URL='/static/'
STATIC_ROOT=BASE_DIR/'staticfiles'
STATICFILES_DIRS=[BASE_DIR/'static']
MEDIA_ROOT=BASE_DIR/'private_uploads'
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
LOGIN_URL='login'
LOGIN_REDIRECT_URL='dashboard'
LOGOUT_REDIRECT_URL='login'
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SECURE=os.getenv('HTTPS','0')=='1'
CSRF_COOKIE_SECURE=SESSION_COOKIE_SECURE
SECURE_SSL_REDIRECT=SESSION_COOKIE_SECURE
SECURE_HSTS_SECONDS=31536000 if SESSION_COOKIE_SECURE else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS=SESSION_COOKIE_SECURE
SECURE_HSTS_PRELOAD=SESSION_COOKIE_SECURE
SECURE_CONTENT_TYPE_NOSNIFF=True
X_FRAME_OPTIONS='DENY'
DATA_UPLOAD_MAX_MEMORY_SIZE=12*1024*1024
FILE_UPLOAD_MAX_MEMORY_SIZE=2*1024*1024

# Ollama is called only by the backend; never accept a URL from the browser.
AI_ENABLED=os.getenv('AI_ENABLED','1')=='1'
OLLAMA_URL=os.getenv('OLLAMA_URL','http://10.0.0.7:11434').rstrip('/')
OLLAMA_MODEL=os.getenv('OLLAMA_MODEL','gemma-4-26B-A4B-it-UD-Q8_K_XL:latest')
OLLAMA_TIMEOUT=min(max(int(os.getenv('OLLAMA_TIMEOUT','75')),5),90)
