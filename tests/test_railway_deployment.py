from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RailwayDeploymentTests(unittest.TestCase):
    def test_dockerfile_is_railway_runtime_safe(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertNotIn("VOLUME", dockerfile)
        self.assertIn("SEGUE_DB_PATH=/data/segue_missions.sqlite3", dockerfile)
        self.assertIn("--host 0.0.0.0 --port ${PORT:-8000}", dockerfile)

    def test_railway_config_uses_root_dockerfile_and_healthcheck(self) -> None:
        config = (ROOT / "railway.toml").read_text(encoding="utf-8")
        self.assertIn('builder = "DOCKERFILE"', config)
        self.assertIn('dockerfilePath = "Dockerfile"', config)
        self.assertIn('healthcheckPath = "/health"', config)

    def test_runtime_sources_are_present_at_root(self) -> None:
        self.assertTrue((ROOT / "requirements.txt").exists())
        self.assertTrue((ROOT / "backend" / "segue_api" / "main.py").exists())
        self.assertTrue((ROOT / "frontend" / "index.html").exists())
        self.assertTrue((ROOT / "frontend" / "app.html").exists())


if __name__ == "__main__":
    unittest.main()
