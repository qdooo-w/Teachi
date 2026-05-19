from typing import Literal, cast


SameSiteType = Literal["lax", "strict", "none"]


def env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    return int(value)


def env_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    return float(value)


def env_csv(value: str | None, default: str) -> list[str]:
    raw = value if value is not None else default
    return [item.strip() for item in raw.split(",") if item.strip()]


def normalize_samesite(raw_value: str | None, default: SameSiteType = "lax") -> SameSiteType:
    value = (raw_value or default).strip().lower()
    if value in ("lax", "strict", "none"):
        return cast(SameSiteType, value)
    return default
