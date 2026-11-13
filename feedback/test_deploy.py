from django.test import TestCase, override_settings


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
