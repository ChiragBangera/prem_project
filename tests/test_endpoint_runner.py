import asyncio
import unittest

from app.endpoint_runner import EndpointRunner


class FakeClient:
    async def get_league_data(self, league_name, season):
        return {"league": league_name, "season": season}


class EndpointRunnerTestCase(unittest.TestCase):
    def test_runner_rejects_missing_required_params(self):
        async def run():
            runner = EndpointRunner(client=FakeClient())
            with self.assertRaisesRegex(ValueError, "Missing required params"):
                await runner.run("league_data", league_name="EPL")

        asyncio.run(run())

    def test_runner_rejects_unexpected_params(self):
        async def run():
            runner = EndpointRunner(client=FakeClient())
            with self.assertRaisesRegex(ValueError, "Unexpected params"):
                await runner.run(
                    "league_data",
                    league_name="EPL",
                    season=2025,
                    typo=True,
                )

        asyncio.run(run())

    def test_runner_executes_manifest_method(self):
        async def run():
            runner = EndpointRunner(client=FakeClient())
            result = await runner.run(
                "league_data",
                league_name="EPL",
                season=2025,
            )
            self.assertEqual(result, {"league": "EPL", "season": 2025})

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
