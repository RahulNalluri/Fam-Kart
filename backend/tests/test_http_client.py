import asyncio

import httpx

from app.core.http import create_http_client
from app.main import app, lifespan


def test_create_http_client_disables_redirects_and_closes_cleanly() -> None:
    client = create_http_client()

    try:
        assert isinstance(client, httpx.AsyncClient)
        assert client.follow_redirects is False
    finally:
        asyncio.run(client.aclose())

    assert client.is_closed is True


class FakeHTTPClient:
    def __init__(self) -> None:
        self.was_closed = False

    async def aclose(self) -> None:
        self.was_closed = True


def test_lifespan_stores_and_closes_shared_http_client(monkeypatch) -> None:
    fake_client = FakeHTTPClient()
    monkeypatch.setattr("app.main.create_http_client", lambda: fake_client)

    async def run_lifespan() -> None:
        async with lifespan(app):
            assert app.state.http_client is fake_client
            assert fake_client.was_closed is False

    asyncio.run(run_lifespan())

    assert fake_client.was_closed is True
