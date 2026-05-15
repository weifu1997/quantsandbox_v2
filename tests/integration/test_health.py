from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_get_experiment() -> None:
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
        body = response.json()
        assert body["status"] == "accepted"
        exp_id = body["data"]["experiment"]["experiment_id"]
        task_id = body["data"]["task"]["task_id"]

        exp_resp = client.get(f"/api/experiments/{exp_id}")
        assert exp_resp.status_code == 200
        assert exp_resp.json()["data"]["experiment_id"] == exp_id

        task_resp = client.get(f"/api/tasks/{task_id}")
        assert task_resp.status_code == 200
        task_data = task_resp.json()["data"]
        assert task_data["task_id"] == task_id
        assert task_data["status"] in {"running", "completed"}


def test_create_experiment_with_universe_only() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/experiments",
            json={
                "start_date": "20240101",
                "end_date": "20240131",
                "universe": "main_board",
                "factors": ["momentum_20d"],
                "horizons": [20],
                "report_format": "json",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "accepted"
        assert body["data"]["experiment"]["universe"] == "main_board"
