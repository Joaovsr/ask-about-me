from asyncio import timeout
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine


class Database:
    def __init__(self, url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(
            url,
            pool_pre_ping=True,
            pool_timeout=2,
            connect_args={
                "connect_timeout": 2,
                "options": "-c statement_timeout=2000",
            },
        )

    async def ping(self) -> None:
        async with timeout(2):
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[AsyncConnection]:
        async with self._engine.connect() as connection:
            yield connection

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncConnection]:
        async with self._engine.begin() as connection:
            yield connection

    async def close(self) -> None:
        await self._engine.dispose()
