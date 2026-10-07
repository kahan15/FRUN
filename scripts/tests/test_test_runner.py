"""Exercise cleanup without contacting Docker or touching pre-existing resources."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class TestRunnerSafetyTests(unittest.TestCase):
    def run_fixture(self, folder, exit_code, script="test.sh"):
        fake_docker = folder / "docker"
        fake_docker.write_text("""#!/usr/bin/env python3
import json, os, sys
with open(os.environ['TEST_DOCKER_LOG'], 'a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\\n')
if 'up' in sys.argv:
    raise SystemExit(int(os.environ['TEST_DOCKER_EXIT']))
""")
        fake_docker.chmod(0o700)
        log = folder / (script + str(exit_code) + ".jsonl")
        env = dict(
            os.environ,
            PATH=str(folder) + os.pathsep + os.environ["PATH"],
            TEST_DOCKER_LOG=str(log),
            TEST_DOCKER_EXIT=str(exit_code),
        )
        result = subprocess.run(
            ["bash", str(Path(__file__).parents[1] / script)],
            env=env,
            capture_output=True,
            text=True,
        )
        commands = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(result.returncode, exit_code, result.stderr)
        self.assertEqual(
            len(commands), 3 if script == "smoke-test.sh" and exit_code == 0 else 2
        )
        first, cleanup = commands[0], commands[-1]
        self.assertEqual(first[:2], ["compose", "--project-name"])
        prefix = (
            "territory-run-smoke-"
            if script == "smoke-test.sh"
            else "territory-run-tests-"
        )
        self.assertTrue(first[2].startswith(prefix))
        base = first[: first.index("up")]
        self.assertEqual(cleanup, base + ["down", "--volumes"])
        if script == "smoke-test.sh":
            self.assertIn("--wait", first)
            if exit_code == 0:
                self.assertEqual(
                    commands[1], base + ["exec", "-T", "api", "python", "-"]
                )
        else:
            self.assertIn("--exit-code-from", first)
        return first[2]

    def test_success_and_failure_clean_only_their_own_projects(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            succeeded = self.run_fixture(folder, 0)
            failed = self.run_fixture(folder, 42)
            self.assertNotEqual(succeeded, failed)

    def test_smoke_success_and_startup_failure_clean_only_their_own_projects(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            succeeded = self.run_fixture(folder, 0, "smoke-test.sh")
            failed = self.run_fixture(folder, 42, "smoke-test.sh")
            self.assertNotEqual(succeeded, failed)


if __name__ == "__main__":
    unittest.main()
