from datetime import datetime, timezone
from typing import Optional

from fastapi import Query
from pydantic import BaseModel


class CreateGerty(BaseModel):
    name: str
    type: str
    refresh_time: int = Query(None)
    utc_offset: int = Query(None)
    wallet: str = Query(None)
    # Wallets to keep an eye on, {"wallet-id": "wallet-read-key, etc"}
    lnbits_wallets: str = Query(None)
    mempool_endpoint: str = Query(None)  # Mempool endpoint to use
    # BTC <-> Fiat exchange rate to pull ie "USD", in 0.0001 and sats
    exchange: str = Query(None)
    display_preferences: str = Query(None)
    urls: str = Query(None)


class Gerty(BaseModel):
    id: str
    name: str
    type: str
    utc_offset: int
    display_preferences: str
    refresh_time: Optional[int] = None
    wallet: Optional[str] = None
    lnbits_wallets: Optional[str] = None
    mempool_endpoint: Optional[str] = None
    exchange: Optional[str] = None
    urls: Optional[str] = None
    time: datetime = datetime.now(timezone.utc)


class MempoolEndpoint(BaseModel):
    fees_recommended: str = "/api/v1/fees/recommended"
    hashrate_1w: str = "/api/v1/mining/hashrate/1w"
    hashrate_1m: str = "/api/v1/mining/hashrate/1m"
    statistics: str = "/api/v1/lightning/statistics/latest"
    difficulty_adjustment: str = "/api/v1/difficulty-adjustment"
    tip_height: str = "/api/blocks/tip/height"
    mempool: str = "/api/mempool"


class Mempool(BaseModel):
    id: str = Query(None)
    mempool_endpoint: str = Query(None)
    endpoint: str = Query(None)
    data: str = Query(None)
    time: datetime = datetime.now(timezone.utc)
