import re
from collections.abc import Iterable
from typing import cast

NON_MATCHING_REGEX: re.Pattern[str] = re.compile(r"$.^")


def _clamp_top_n(top_n: int) -> int:
    return max(1, min(50, int(top_n)))


def normalize_trigger_text(s: object = None) -> str:
    if s is None:
        return ""
    return str(s).strip()


def compile_trigger_regex(pattern: object = None) -> re.Pattern[str]:
    try:
        text = "" if pattern is None else str(pattern).strip()
        if not text:
            return NON_MATCHING_REGEX
        return re.compile(text)
    except re.error:
        return NON_MATCHING_REGEX


def compute_leaderboard(
    users: Iterable[tuple[str, float]],
    holdings: Iterable[tuple[str, str, float]],
    prices: dict[str, float],
    top_n: int,
) -> list[dict[str, object]]:
    limit = _clamp_top_n(top_n)
    by_user: dict[str, dict[str, object]] = {}

    for user_id, balance in users:
        uid = str(user_id)
        cash = float(balance)
        by_user[uid] = {
            "user_id": uid,
            "balance": cash,
            "holdings_value": 0.0,
            "total": cash,
            "missing_symbols": set(),
        }

    for user_id, symbol, amount in holdings:
        uid = str(user_id)
        if uid not in by_user:
            continue
        qty = float(amount)
        if qty <= 0 or abs(qty) <= 0.0001:
            continue

        sym = str(symbol)
        if sym in prices:
            price = float(prices[sym])
        else:
            price = 0.0
            missing = cast(set[str], by_user[uid]["missing_symbols"])
            missing.add(sym)

        value = qty * price
        holdings_value = float(cast(float, by_user[uid]["holdings_value"])) + value
        by_user[uid]["holdings_value"] = holdings_value
        by_user[uid]["total"] = float(cast(float, by_user[uid]["balance"])) + holdings_value

    entries = list(by_user.values())
    entries.sort(key=lambda item: (-float(cast(float, item["total"])), str(item["user_id"])))
    entries = entries[:limit]

    for entry in entries:
        missing = cast(set[str], entry["missing_symbols"])
        entry["missing_symbols"] = sorted(missing)

    return entries


def format_leaderboard(
    entries: list[dict[str, object]],
    top_n: int,
    header_meta: object = None,
) -> str:
    limit = _clamp_top_n(top_n)
    shown = entries[:limit]

    first_line = "【总资产排名（按当前市价）】 全局榜"
    if isinstance(header_meta, dict):
        meta = cast(dict[str, object], header_meta)
        meta_parts: list[str] = []
        if "updated_at" in meta:
            meta_parts.append(f"更新时间: {str(meta['updated_at'])}")
        if "market_status" in meta:
            meta_parts.append(f"市场状态: {str(meta['market_status'])}")
        if meta_parts:
            first_line = first_line + "  " + "  ".join(meta_parts)

    lines = [first_line]
    all_missing_symbols: set[str] = set()

    for index, entry in enumerate(shown, 1):
        user_id = str(entry["user_id"])
        total = float(cast(float, entry["total"]))
        balance = float(cast(float, entry["balance"]))
        holdings_value = float(cast(float, entry["holdings_value"]))
        lines.append(f"{index}. {user_id}  总资产: {total:.2f}  现金: {balance:.2f}  持仓市值: {holdings_value:.2f}")

        missing_symbols = cast(list[str], entry.get("missing_symbols", []))
        for symbol in missing_symbols:
            all_missing_symbols.add(symbol)

    if all_missing_symbols:
        lines.append(f"注：以下币种暂无价格，按 0 计入：{', '.join(sorted(all_missing_symbols))}")

    return "\n".join(lines)


def cooldown_allow(last_ts: object, now_ts: float, cooldown_seconds: int) -> bool:
    if cooldown_seconds <= 0:
        return True
    if last_ts is None:
        return True
    return (float(now_ts) - float(cast(float, last_ts))) >= float(cooldown_seconds)
