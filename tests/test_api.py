import unittest

import httpx

from app.api import app


class FakeAnswerer:
    async def answer(self, question):
        return {
            "plan": {"question": question, "intent": "test"},
            "answer": {"direct_answer": "Test answer", "reasons": ["Test evidence"]},
            "data_summary": {},
            "template": {"name": "test"},
        }


class ApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.lifespan = app.router.lifespan_context(app)
        await self.lifespan.__aenter__()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.lifespan.__aexit__(None, None, None)

    async def test_project_info_and_health(self):
        project = await self.client.get("/")
        health = await self.client.get("/health")

        self.assertEqual(project.status_code, 200)
        self.assertEqual(project.json()["name"], "Premier League Analytics API")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

    async def test_endpoint_catalog_is_exposed(self):
        response = await self.client.get("/api/v1/endpoints")

        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.json()["endpoints"]}
        self.assertIn("league_table", names)
        self.assertIn("match_shots", names)

    async def test_unknown_endpoint_returns_404(self):
        response = await self.client.get("/api/v1/endpoints/not-real")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "endpoint_not_found")

    async def test_endpoint_params_are_validated_before_upstream_call(self):
        response = await self.client.post(
            "/api/v1/endpoints/league_table",
            json={"params": {"league_name": "EPL"}},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "invalid_parameters")

    async def test_ask_uses_the_analytics_service(self):
        app.state.answerer = FakeAnswerer()
        response = await self.client.post(
            "/api/v1/ask",
            json={"question": "Compare Arsenal vs Liverpool"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"]["direct_answer"], "Test answer")

    async def test_question_validation_rejects_empty_input(self):
        response = await self.client.post("/api/v1/ask", json={"question": ""})

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
