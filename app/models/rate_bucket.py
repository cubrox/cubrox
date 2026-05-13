"""RateBucket model.

A single row per rate-limit key (e.g. `"login:ip:1.2.3.4"`,
`"login:email:user@example.com"`). The bucket is a classic
token-bucket: `tokens` is the current credit balance, `refilled_at`
is the wall-clock at the last balance update.

Refill is linear: 10 tokens per hour means one token every 360
seconds. When a request lands, we compute how many tokens have
accrued since `refilled_at`, cap at the bucket size, decrement one,
and write back. See `app/services/rate_limit.py` for the math.

Postgres-backed (per ADR — Redis when traffic justifies). No
foreign keys: keys are opaque strings owned by the service.
"""

from datetime import datetime

from sqlmodel import Field, SQLModel


class RateBucket(SQLModel, table=True):
    __tablename__ = "rate_bucket"

    key: str = Field(primary_key=True)
    tokens: float
    refilled_at: datetime
