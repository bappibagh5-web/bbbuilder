from django.test import SimpleTestCase


class HealthEndpointTests(SimpleTestCase):
    def test_health_endpoint_returns_ok(self):
        response = self.client.get("/api/v1/health/")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_endpoint_rejects_non_get_requests(self):
        response = self.client.post("/api/v1/health/")

        assert response.status_code == 405
