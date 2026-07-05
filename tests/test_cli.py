import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE = f"{sys.executable} {REPO_ROOT / 'agents' / 'baseline_random' / 'agent.py'}"
MISSING_COMMAND = "definitely-not-a-real-agent-command-for-cli-test"


def test_cli_reports_clean_error_when_agent_command_cannot_start():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.cli",
            "--agent-a",
            MISSING_COMMAND,
            "--agent-b",
            BASELINE,
            "--seed",
            "1",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "Could not start agent command" in result.stderr
