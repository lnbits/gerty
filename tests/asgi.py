"""Bridge Starlette's mapping messages to HTTPX's dictionary message types."""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from starlette.types import ASGIApp, Message, Receive


def asgi_transport(app: ASGIApp) -> httpx.ASGITransport:
    async def wrapped_app(
        scope: dict[str, Any],
        receive: Receive,
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        async def send_message(message: Message) -> None:
            await send(dict(message))

        await app(scope, receive, send_message)

    return httpx.ASGITransport(app=wrapped_app)
