import json
import time
from typing import List, Optional, Union

import httpx
from lnbits.db import Database
from lnbits.helpers import insert_query, update_query, urlsafe_short_hash
from loguru import logger

from .models import CreateGerty, Gerty, Mempool, MempoolEndpoint

db = Database("ext_gerty")


async def create_gerty(wallet_id: str, data: CreateGerty) -> Gerty:
    gerty_id = urlsafe_short_hash()
    gerty = Gerty(
        id=gerty_id,
        wallet=wallet_id,
        **data.dict(),
    )
    await db.execute(
        insert_query("gerty.gertys", gerty),
        gerty.dict(),
    )
    return gerty


async def update_gerty(gerty: Gerty) -> Gerty:
    await db.execute(
        update_query("gerty.gertys", gerty),
        gerty.dict(),
    )
    return gerty


async def get_gerty(gerty_id: str) -> Optional[Gerty]:
    row = await db.fetchone(
        "SELECT * FROM gerty.gertys WHERE id = :id", {"id": gerty_id}
    )
    return Gerty(**row) if row else None


async def get_gertys(wallet_ids: Union[str, List[str]]) -> List[Gerty]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]

    q = ",".join([f"'{wallet_id}'" for wallet_id in wallet_ids])
    rows = await db.fetchall(f"SELECT * FROM gerty.gertys WHERE wallet IN ({q})")

    return [Gerty(**row) for row in rows]


async def delete_gerty(gerty_id: str) -> None:
    await db.execute("DELETE FROM gerty.gertys WHERE id = :id", {"id": gerty_id})


async def get_mempool_info(end_point: str, gerty) -> dict:
    logger.debug(end_point)
    endpoints = MempoolEndpoint()
    url = ""
    for endpoint in endpoints:
        if end_point == endpoint[0]:
            url = endpoint[1]
    row = await db.fetchone(
        """
        SELECT * FROM gerty.mempool
        WHERE endpoint = :endpoint AND mempool_endpoint = :mempool_endpoint
        """,
        {"endpoint": end_point, "mempool_endpoint": gerty.mempool_endpoint},
    )
    if not row:
        async with httpx.AsyncClient() as client:
            response = await client.get(gerty.mempool_endpoint + url)
            mempool_id = urlsafe_short_hash()
            mempool = Mempool(
                id=mempool_id,
                data=json.dumps(response.json()),
                endpoint=end_point,
                time=int(time.time()),
                mempool_endpoint=gerty.mempool_endpoint,
            )
            await db.execute(
                insert_query("gerty.mempool", mempool),
                mempool.dict(),
            )
            return response.json()
    if float(time.time()) - row["time"] > 20:
        async with httpx.AsyncClient() as client:
            response = await client.get(gerty.mempool_endpoint + url)
            await db.execute(
                """
                UPDATE gerty.mempool SET data = :data, time = :time
                WHERE endpoint = :endpoint AND mempool_endpoint = :mempool_endpoint
                """,
                {
                    "data": json.dumps(response.json()),
                    "time": int(time.time()),
                    "endpoint": end_point,
                    "mempool_endpoint": gerty.mempool_endpoint,
                },
            )
            return response.json()
    return json.loads(row["data"])
