from fastapi.testclient import TestClient

from app.main import app


def test_create_experiment_rejects_invalid_date_order() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/experiments",
            json={
                "start_date": "20241231",
                "end_date": "20240101",
                "tickers": ["sh600519"],
            },
        )
        assert response.status_code == 422
        assert "end_date must be >= start_date" in response.text


def test_create_experiment_rejects_negative_horizon() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/experiments",
            json={
                "start_date": "20240101",
                "end_date": "20241231",
                "tickers": ["sh600519"],
                "horizons": [-5],
            },
        )
        assert response.status_code == 422
        assert "horizons must be positive integers" in response.text


def test_create_experiment_rejects_invalid_weighting() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/experiments",
            json={
                "start_date": "20240101",
                "end_date": "20241231",
                "tickers": ["sh600519"],
                "weighting": "random",
            },
        )
        assert response.status_code == 422
        assert "weighting must be one of" in response.text


def test_create_experiment_rejects_missing_tickers_and_universe() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/experiments",
            json={
                "start_date": "20240101",
                "end_date": "20241231",
            },
        )
        assert response.status_code == 422
        assert "either tickers or universe is required" in response.text
