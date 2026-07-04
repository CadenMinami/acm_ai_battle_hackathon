import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.agent_process import AgentProcess

FIXTURE = [sys.executable, str(Path(__file__).resolve().parent / "fixtures" / "fixture_agent.py")]


def test_normal_response_is_returned():
    agent = AgentProcess(FIXTURE + ["echo"])
    try:
        response = agent.request({"request_id": 1}, deadline_seconds=1.0)
        assert response == {"request_id": 1, "action": "none"}
    finally:
        agent.close()


def test_slow_agent_times_out():
    agent = AgentProcess(FIXTURE + ["sleep"])
    try:
        response = agent.request({"request_id": 1}, deadline_seconds=0.05)
        assert response is None
    finally:
        agent.close()


def test_garbage_output_is_treated_as_miss():
    agent = AgentProcess(FIXTURE + ["garbage"])
    try:
        response = agent.request({"request_id": 1}, deadline_seconds=0.2)
        assert response is None
    finally:
        agent.close()


def test_stale_response_is_discarded_until_correct_id_arrives():
    agent = AgentProcess(FIXTURE + ["stale"])
    try:
        response = agent.request({"request_id": 1}, deadline_seconds=1.0)
        assert response == {"request_id": 1, "action": "none"}
    finally:
        agent.close()


def test_crashed_process_is_treated_as_miss():
    agent = AgentProcess(FIXTURE + ["crash"])
    try:
        response = agent.request({"request_id": 1}, deadline_seconds=0.2)
        assert response is None
    finally:
        agent.close()
