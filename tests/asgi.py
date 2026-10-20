"""Bridge Starlette's mapping messages to HTTPX's dictionary message types."""

import httpx
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def asgi_transport(app: ASGIApp) -> httpx.ASGITransport:
    async def wrapped_app(
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        async def send_message(message: Message) -> None:
            await send(dict(message))

        await app(scope, receive, send_message)

    return httpx.ASGITransport(app=wrapped_app)
