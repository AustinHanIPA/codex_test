"""
链上事件适配器。

把不同 webhook provider 的 payload 归一化成 OnchainEvent。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from models import OnchainEvent


def normalize_onchain_payload(payload: Any, source: str = "webhook") -> List[OnchainEvent]:
    """支持单条、批量、以及 Helius/QuickNode 常见包装结构。"""
    raw_items = _extract_items(payload)
    events = []
    for item in raw_items:
        if isinstance(item, dict):
            events.append(normalize_onchain_event(item, source=source))
    return events


def normalize_onchain_event(payload: Dict[str, Any], source: str = "webhook") -> OnchainEvent:
    provider = str(payload.get("source") or source)
    tx_signature = _first_text(
        payload,
        "tx_signature",
        "signature",
        "transactionSignature",
        "transactionHash",
        "hash",
    )
    event_id = _first_text(payload, "event_id", "id") or tx_signature or f"{provider}:{datetime.now().timestamp()}"
    event_type = _normalize_event_type(_first_text(payload, "event_type", "type", "eventType") or "WhaleTransfer")

    transfer = _first_dict(payload.get("tokenTransfers"), payload.get("nativeTransfers"), payload.get("transfers"))
    account = _first_dict(payload.get("accountData"), payload.get("accounts"))
    symbol = _first_text(payload, "symbol", "tokenSymbol", "mint", "asset") or _first_text(transfer, "symbol", "tokenSymbol", "mint")

    amount = _to_float(
        payload.get("amount")
        or payload.get("tokenAmount")
        or transfer.get("tokenAmount")
        or transfer.get("amount")
    )
    amount_usd = _to_float(
        payload.get("amount_usd")
        or payload.get("amountUsd")
        or payload.get("value_usd")
        or payload.get("valueUsd")
        or transfer.get("amountUsd")
        or transfer.get("valueUsd")
    )

    from_address = _first_text(payload, "address", "from", "owner", "fromUserAccount") or _first_text(
        transfer,
        "fromUserAccount",
        "from",
        "source",
    )
    to_address = _first_text(payload, "counterparty", "to", "destination", "toUserAccount") or _first_text(
        transfer,
        "toUserAccount",
        "to",
        "destination",
    )

    return OnchainEvent(
        event_id=event_id,
        source=provider,
        event_type=event_type,
        address=from_address or _first_text(account, "account", "address", "owner"),
        counterparty=to_address,
        symbol=symbol,
        amount=amount,
        amount_usd=amount_usd,
        direction=str(payload.get("direction") or _infer_direction(from_address, to_address)),
        tx_signature=tx_signature,
        description=_first_text(payload, "description", "summary") or _describe_event(event_type, symbol, amount_usd),
        observed_at=_first_text(payload, "observed_at", "timestamp", "blockTime") or datetime.now().isoformat(),
        raw=payload,
    )


def _extract_items(payload: Any) -> List[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("events", "data", "transactions", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return [payload]


def _first_dict(*values: Any) -> Dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
    return {}


def _first_text(payload: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _to_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_event_type(value: str) -> str:
    normalized = value.strip().replace(" ", "_")
    aliases = {
        "TRANSFER": "WhaleTransfer",
        "TOKEN_TRANSFER": "WhaleTransfer",
        "SWAP": "Swap",
        "CREATE_POOL": "NewPairCreated",
        "PAIR_CREATED": "NewPairCreated",
        "LIQUIDITY_LOCKED": "LiquidityLocked",
        "LIQUIDITY_BURNED": "LiquidityBurned",
    }
    return aliases.get(normalized.upper(), normalized)


def _infer_direction(from_address: str, to_address: str) -> str:
    if from_address and to_address:
        return "transfer"
    if to_address:
        return "in"
    if from_address:
        return "out"
    return "unknown"


def _describe_event(event_type: str, symbol: str, amount_usd: Optional[float]) -> str:
    amount = f"${amount_usd:,.2f}" if amount_usd is not None else "unknown USD"
    token = symbol or "unknown token"
    return f"{event_type} detected for {token}, amount {amount}"
