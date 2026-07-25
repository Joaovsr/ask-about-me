from socketserver import BaseRequestHandler, ThreadingTCPServer
from threading import Event, Thread
from time import monotonic
from typing import cast

from fastapi.testclient import TestClient

from ask_about_me.app import create_app
from ask_about_me.config import Settings


def test_liveness_does_not_depend_on_postgres() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://ask_about_me:ask_about_me@127.0.0.1:1/missing"
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_postgres_as_available(test_database_url: str) -> None:
    settings = Settings(database_url=test_database_url)

    with TestClient(create_app(settings)) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "available"}


def test_readiness_fails_within_deadline_when_postgres_stalls() -> None:
    release_connection = Event()

    class StallingConnection(BaseRequestHandler):
        def handle(self) -> None:
            release_connection.wait(timeout=5)

    server = ThreadingTCPServer(("127.0.0.1", 0), StallingConnection)
    server.daemon_threads = True
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    port = cast(tuple[str, int], server.server_address)[1]
    settings = Settings(
        database_url=(f"postgresql+psycopg://ask_about_me:ask_about_me@127.0.0.1:{port}/missing")
    )

    try:
        started_at = monotonic()
        with TestClient(create_app(settings)) as client:
            response = client.get("/health/ready")
        elapsed = monotonic() - started_at
    finally:
        release_connection.set()
        server.shutdown()
        server.server_close()

    assert elapsed < 3
    assert response.status_code == 503
    assert response.json() == {"detail": {"status": "unavailable", "dependency": "database"}}
