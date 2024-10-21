import json
import time
from datetime import datetime, timezone
from typing import List, Optional, Union

import httpx
from lnbits.db import Database
from lnbits.helpers import urlsafe_short_hash

from .models import CreateGerty, Gerty, Mempool, MempoolEndpoint

db = Database("ext_gerty")


async def create_gerty(wallet_id: str, data: CreateGerty) -> Gerty:
    gerty_id = urlsafe_short_hash()
    gerty = Gerty(
        id=gerty_id,
        wallet=wallet_id,
        **data.dict(),
    )
    await db.insert("gerty.gertys", gerty)
    return gerty


async def update_gerty(gerty: Gerty) -> Gerty:
    await db.update("gerty.gertys", gerty)
    return gerty


async def get_gerty(gerty_id: str) -> Optional[Gerty]:
    return await db.fetchone(
        "SELECT * FROM gerty.gertys WHERE id = :id",
        {"id": gerty_id},
        Gerty,
    )


async def get_gertys(wallet_ids: Union[str, List[str]]) -> List[Gerty]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]
    q = ",".join([f"'{wallet_id}'" for wallet_id in wallet_ids])
    return await db.fetchall(
        f"SELECT * FROM gerty.gertys WHERE wallet IN ({q})", model=Gerty
    )


async def delete_gerty(gerty_id: str) -> None:
    await db.execute("DELETE FROM gerty.gertys WHERE id = :id", {"id": gerty_id})


async def get_mempool_info(end_point: str, gerty) -> dict:
    endpoints = MempoolEndpoint()
    url = ""
    for endpoint in endpoints:
        if end_point == endpoint[0]:
            url = endpoint[1]
    mempool = await db.fetchone(
        """
        SELECT * FROM gerty.mempool
        WHERE endpoint = :endpoint AND mempool_endpoint = :mempool_endpoint
        """,
        {"endpoint": end_point, "mempool_endpoint": gerty.mempool_endpoint},
        Mempool,
    )
    if not mempool:
        async with httpx.AsyncClient() as client:
            response = await client.get(gerty.mempool_endpoint + url)
            mempool_id = urlsafe_short_hash()
            mempool = Mempool(
                id=mempool_id,
                data=json.dumps(response.json()),
                endpoint=end_point,
                mempool_endpoint=gerty.mempool_endpoint,
            )
            await db.insert("gerty.mempool", mempool)
            return response.json()

    if float(time.time()) - gerty.time.timestamp() > 20:
        async with httpx.AsyncClient() as client:
            response = await client.get(gerty.mempool_endpoint + url)
            mempool.data = json.dumps(response.json())
            mempool.time = datetime.now(timezone.utc)
            mempool.endpoint = end_point
            mempool.mempool_endpoint = gerty.mempool_endpoint
            await db.update("gerty.mempool", mempool)
            return response.json()

    return json.loads(mempool.data)
