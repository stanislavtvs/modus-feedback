# Серверная установка

Основной адрес: https://modus-feedback.duckdns.org. Резервный адрес: https://95.57.206.92:8443. Каталог `/home/handyapp/modus-feedback`, Compose-проект `modus-server`. База и вложения находятся в отдельных именованных томах. ИИ отключён по решению владельца: AI_ENABLED=0. Для совместной работы с TOU Events используются отдельные имена cookies: SESSION_COOKIE_NAME=modus_session и CSRF_COOKIE_NAME=modus_csrf.

```sh
cd /home/handyapp/modus-feedback
sudo docker compose -p modus-server -f compose.yaml -f deploy/compose.server.yaml ps
sudo docker compose -p modus-server -f compose.yaml -f deploy/compose.server.yaml logs --tail=80 web followups
```

Параметры `.env`: HTTPS=1, TRUST_PROXY_HEADERS=1, WEB_PORT=8018, ALLOWED_HOSTS=95.57.206.92,localhost,127.0.0.1,modus-feedback.duckdns.org; CSRF_TRUSTED_ORIGINS=https://95.57.206.92:8443,https://modus-feedback.duckdns.org. SECRET_KEY и пароли создаются случайно на сервере. `.env` и пароли не входят в Git.

Порт приложения доступен только на 127.0.0.1. Входной nginx перезаписывает X-Forwarded-Proto, поэтому Django может доверять этому заголовку. Не публикуйте порт контейнера напрямую при TRUST_PROXY_HEADERS=1.

`nginx-modus.conf` — отдельный блок в действующем `student-rector-events/edge.conf`; Для домена выпущен отдельный сертификат Let’s Encrypt; резервный адрес использует сертификат IP. Сертификаты автоматически продлевает существующий tou-events-renew.timer с перезагрузкой nginx. Перед изменением конфигурации сохраняется копия, затем выполняются nginx -t и reload. Сайты TOU Events на 80/443 сохраняются. В UFW разрешён дополнительный 8443/tcp на IP сервера.

Docker уже включён при загрузке ОС; сервисы проекта имеют restart: unless-stopped. `modus-backup.timer` ежедневно в 03:40 по времени сервера (Asia/Almaty) запускает резервное копирование PostgreSQL и вложений в `/var/backups/modus`; срок хранения 14 дней. Отдельный пароль доступа к резервным копиям не требуется: каталог предназначен для root.

Проверка и ручная копия:

```sh
sudo systemctl status modus-backup.timer
sudo systemctl start modus-backup.service
sudo ls -lh /var/backups/modus
```

Восстановление выполняется в остановленную/новую установку после проверки дампа; автоматический откат с удалением текущей базы не выполняется. Сохраняйте также защищённую копию `.env` и актуального исходного кода.
