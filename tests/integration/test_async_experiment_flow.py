import time

from fastapi.testclient import TestClient

from app.main import app


def test_async_experiment_is_accepted_and_trackable() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/experiments",
            json={
                "start_date": "20240101",
                "end_date": "20241231",
                "factors": ["momentum_20d", "pe"],
                "horizons": [20],
                "tickers": ["sh600519", "sz000858", "sz300750", "sz000001", "sh600036"],
                "report_format": "json",
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        task_id = data["task"]["task_id"]

        observed = []
        for _ in range(10):
            current_resp = client.get(f"/api/tasks/{task_id}")
            assert current_resp.status_code == 200
            current = current_resp.json()["data"]
            observed.append((current["status"], current["stage"]))
            if current["status"] in {"completed", "failed", "interrupted"}:
                break
            time.sleep(0.1)

        assert observed
        assert observed[0][0] in {"running", "completed"}
