import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("release_check", Path(__file__).parents[1] / "check-release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_rejects_private_and_placeholder_hosts(self):
        for host in ["localhost", "api.local", "192.168.1.2", "127.0.0.1", "[::1]", "[fc00::1]",
                     "169.254.1.1", "example.com", "api.example.org", "service.test", "laptop", "bad..host"]:
            with self.subTest(host=host):
                self.assertFalse(release.public_https("https://" + host))

    def test_rejects_insecure_or_credential_urls(self):
        for url in ["http://api.territory.run", "https://me:pw@api.territory.run", "https://api.territory.run:bad",
                    "https://api.territory.run:8000", "https://api.territory.run/#secret", ""]:
            with self.subTest(url=url):
                self.assertFalse(release.public_https(url))

    def test_api_root_and_document_paths(self):
        self.assertTrue(release.public_https("https://api.territory.run", root_only=True))
        self.assertFalse(release.public_https("https://api.territory.run/api/v1", root_only=True))
        self.assertFalse(release.public_https("https://api.territory.run?key=a", root_only=True))
        self.assertTrue(release.public_https("https://territory.run/privacy"))

    def test_sdk_and_configuration_requirements(self):
        values = dict(API_BASE_URL="https://api.territory.run", PRIVACY_POLICY_URL="https://territory.run/privacy",
                      SUPPORT_URL="https://territory.run/support", APP_BUNDLE_ID="com.runner.territory",
                      APPLE_TEAM_ID="AB12CD34EF", PUSH_ENABLED="NO", SDK_VERSION="26.0")
        self.assertEqual(release.validate(values, True), [])
        for key, value in [("APPLE_TEAM_ID", ""), ("APP_BUNDLE_ID", "com.territoryrun.app"),
                           ("PUSH_ENABLED", "YES"), ("SDK_VERSION", "18.5")]:
            with self.subTest(key=key):
                self.assertTrue(release.validate(dict(values, **{key: value}), True))
        self.assertTrue(release.validate({}))

    def test_xcconfig_url_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "Release.xcconfig"
            file.write_text("// Header\nAPI_BASE_URL = https:/$()/api.territory.run\nAPPLE_TEAM_ID = // later\n")
            self.assertEqual(release.read_config(file), dict(API_BASE_URL="https://api.territory.run", APPLE_TEAM_ID=""))


if __name__ == "__main__":
    unittest.main()
