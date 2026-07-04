import time
import uuid
import base64

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

TOTAL_ORDERS = 53
RATE_LIMIT = 19
WINDOW = 10  # seconds

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# In-memory stores
# -------------------------

# Idempotency store
idempotency_store = {}

# Rate limiter
client_requests = {}


# -------------------------
# Rate limiting middleware
# -------------------------

@app.middleware("http")
async def rate_limit(request: Request, call_next):

    client = request.headers.get("X-Client-Id", "anonymous")

    now = time.time()

    timestamps = client_requests.setdefault(client, [])

    # Remove expired timestamps
    timestamps[:] = [t for t in timestamps if now - t < WINDOW]

    if len(timestamps) >= RATE_LIMIT:

        retry_after = WINDOW - (now - timestamps[0])

        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={
                "Retry-After": str(max(1, int(retry_after)))
            }
        )

    timestamps.append(now)

    return await call_next(request)


# -------------------------
# Idempotent POST
# -------------------------

@app.post("/orders", status_code=201)
def create_order(
    request: dict,
    idempotency_key: str = Header(None, alias="Idempotency-Key")
):

    if not idempotency_key:
        raise HTTPException(400, "Missing Idempotency-Key")

    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    order = {
        "id": str(uuid.uuid4()),
        "payload": request
    }

    idempotency_store[idempotency_key] = order

    return order


# -------------------------
# Cursor Pagination
# -------------------------

@app.get("/orders")
def list_orders(limit: int = 10, cursor: str = None):

    if limit <= 0:
        limit = 10

    start = 1

    if cursor:
        start = int(base64.b64decode(cursor).decode())

    end = min(start + limit - 1, TOTAL_ORDERS)

    items = [
        {
            "id": i
        }
        for i in range(start, end + 1)
    ]

    if end >= TOTAL_ORDERS:
        next_cursor = None
    else:
        next_cursor = base64.b64encode(
            str(end + 1).encode()
        ).decode()

    return {
        "items": items,
        "next_cursor": next_cursor
    }
