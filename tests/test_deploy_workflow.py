"""Le déploiement GitHub Pages doit rester relançable (« Re-run ») sans conflit d'artefacts."""
import re
import unittest
from pathlib import Path

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "deploy.yml"


def step_inputs(workflow, action):
    """Return the `with:` inputs of the step using `action`, or {} if there are none."""
    match = re.search(
        rf"uses: {re.escape(action)}@\S+\n(?P<indent> +)with:\n(?P<body>(?:(?P=indent) +\S.*(?:\n|$))+)",
        workflow,
    )
    if match is None:
        return {}
    return dict(re.findall(r"^ +([\w-]+): *(.+?) *$", match.group("body"), re.MULTILINE))


class DeployWorkflowTest(unittest.TestCase):
    def setUp(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.uploaded_name = step_inputs(workflow, "actions/upload-pages-artifact").get("name")
        self.deployed_name = step_inputs(workflow, "actions/deploy-pages").get("artifact_name")

    def test_deploys_the_artifact_it_uploads(self):
        self.assertIsNotNone(self.uploaded_name)
        self.assertEqual(self.deployed_name, self.uploaded_name)

    def test_artifact_name_is_unique_per_run_attempt(self):
        self.assertIn("${{ github.run_attempt }}", self.uploaded_name or "")


if __name__ == "__main__":
    unittest.main()
