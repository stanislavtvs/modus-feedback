from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model


@override_settings(
    SECURE_SSL_REDIRECT=True,
    SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
)
class HTTPSDeploymentTests(TestCase):
    def test_proxy_https_login_has_no_redirect_loop_and_secure_csrf(self):
        response = self.client.get('/accounts/login/', HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.cookies['csrftoken']['secure'])

    def test_plain_http_redirects_but_internal_health_remains_available(self):
        response = self.client.get('/accounts/login/', HTTP_HOST='testserver:8443')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], 'https://testserver:8443/accounts/login/')
        response = self.client.get('/health/')
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'status': 'ok'})

    @override_settings(SESSION_COOKIE_NAME='modus_session', CSRF_COOKIE_NAME='modus_csrf')
    def test_server_cookie_names_allow_csrf_login_without_other_app_cookies(self):
        get_user_model().objects.create_user('server-user', password='server-login-test-123')
        client = Client(enforce_csrf_checks=True)
        page = client.get('/accounts/login/', HTTP_X_FORWARDED_PROTO='https')
        token = page.cookies['modus_csrf'].value
        response = client.post('/accounts/login/', {
            'username': 'server-user', 'password': 'server-login-test-123',
            'csrfmiddlewaretoken': token,
        }, HTTP_X_FORWARDED_PROTO='https', HTTP_HOST='testserver:8443',
           HTTP_ORIGIN='https://testserver:8443')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.cookies['modus_session']['secure'])
        self.assertNotIn('sessionid', response.cookies)
        self.assertNotIn('csrftoken', response.cookies)
