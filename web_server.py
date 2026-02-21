from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, Cookie
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from typing import Optional
import uvicorn
import asyncio
import os
import secrets
import socket

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

try:
    from .database import DB, User, UserHolding, Order, OrderType, OrderStatus, MarketHistory, get_china_time
    from .market import Market
except ImportError:
    from database import DB, User, UserHolding, Order, OrderType, OrderStatus, MarketHistory, get_china_time
    from market import Market

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

app = FastAPI()

static_path = os.path.join(os.path.dirname(__file__), "web")
app.mount("/static", StaticFiles(directory=static_path), name="static")

# In-memory session store: token -> user_id
_sessions: dict[str, str] = {}


def get_db():
    db = app.state.db_instance
    session = db.get_session()
    try:
        yield session
    finally:
        session.close()


def get_current_user(zrb_session: Optional[str] = Cookie(None)) -> str:
    if not zrb_session or zrb_session not in _sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _sessions[zrb_session]


class LoginModel(BaseModel):
    user_id: str
    password: str


class TradeModel(BaseModel):
    symbol: str
    amount: float
    price: Optional[float] = None
    action: str


@app.post("/api/login")
async def login(data: LoginModel, response: Response, session: Session = Depends(get_db)):
    user = session.query(User).filter_by(user_id=data.user_id).first()
    if not user or not user.password_hash:
        raise HTTPException(status_code=400, detail="User not found or password not set")

    if not pwd_context.verify(data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect password")

    token = secrets.token_urlsafe(32)
    _sessions[token] = str(user.user_id)

    response.set_cookie(
        key="zrb_session",
        value=token,
        httponly=True,
        samesite="strict",
        max_age=86400 * 7,
    )

    return {"status": "success", "user_id": user.user_id, "balance": user.balance}


@app.post("/api/logout")
async def logout(response: Response, zrb_session: Optional[str] = Cookie(None)):
    if zrb_session and zrb_session in _sessions:
        del _sessions[zrb_session]
    response.delete_cookie("zrb_session")
    return {"status": "success"}


@app.get("/api/me")
async def get_me(user_id: str = Depends(get_current_user)):
    return {"user_id": user_id}


@app.get("/api/market")
async def get_market_data():
    market: Market = app.state.market_instance
    return {"prices": market.prices, "is_open": market.is_open}


@app.get("/api/assets")
async def get_assets(
    user_id: str = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    user = session.query(User).filter_by(user_id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    holdings = session.query(UserHolding).filter_by(user_id=user_id).all()
    holdings_list = [
        {"symbol": h.symbol, "amount": h.amount}
        for h in holdings
        if h.amount > 0.0001
    ]

    return {"balance": user.balance, "holdings": holdings_list}


@app.post("/api/trade")
async def trade(
    data: TradeModel,
    user_id: str = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    market: Market = app.state.market_instance

    if not market.is_open:
        raise HTTPException(status_code=400, detail="Market is closed")

    user = session.query(User).filter_by(user_id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    symbol = data.symbol.upper()
    if symbol not in market.symbols:
        raise HTTPException(status_code=400, detail="Invalid symbol")

    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    if data.action == "buy":
        est_price = data.price if data.price else market.prices[symbol]
        cost = est_price * data.amount * 1.001
        if user.balance < cost:
            raise HTTPException(status_code=400, detail=f"Insufficient balance. Need {cost:.2f}")
    elif data.action == "sell":
        holding = session.query(UserHolding).filter_by(user_id=user_id, symbol=symbol).first()
        if not holding or holding.amount < data.amount:
            raise HTTPException(status_code=400, detail="Insufficient holding")
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    order_type = OrderType.BUY if data.action == "buy" else OrderType.SELL
    order = Order(
        user_id=user_id,
        symbol=symbol,
        order_type=order_type,
        price=data.price,
        amount=data.amount,
    )
    session.add(order)
    session.commit()
    order_id = order.id

    market.match_single_order(order_id)

    session.refresh(order)
    return {
        "status": "success",
        "order_id": order_id,
        "order_status": order.status.value,
        "message": "Order submitted",
    }


@app.get("/api/kline/{symbol}")
async def get_kline(
    symbol: str,
    since: Optional[str] = None,
    limit: int = 5000,
    session: Session = Depends(get_db),
):
    symbol = symbol.upper()
    limit = min(max(1, limit), 5000)

    query = session.query(MarketHistory).filter_by(symbol=symbol)

    if since:
        from datetime import datetime
        try:
            since_dt = datetime.strptime(since, '%Y-%m-%d %H:%M')
            query = query.filter(MarketHistory.timestamp > since_dt)
        except ValueError:
            pass

    history = query.order_by(MarketHistory.timestamp.asc()).limit(limit).all()

    data = []
    for h in history:
        data.append({
            "time": h.timestamp.strftime('%Y-%m-%d %H:%M'),
            "open": h.open,
            "high": h.high,
            "low": h.low,
            "close": h.close,
            "volume": h.volume,
        })
    return {"symbol": symbol, "data": data}


@app.get("/")
async def index():
    with open(os.path.join(static_path, "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


class WebServer:
    def __init__(self, db: DB, market: Market, host="0.0.0.0", port=8000):
        self.config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        self.server = uvicorn.Server(self.config)
        self.host = host
        self.port = port

        app.state.db_instance = db
        app.state.market_instance = market

    def is_port_in_use(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                return s.connect_ex(('localhost', self.port)) == 0
            except Exception:
                return False

    async def start(self):
        if self.is_port_in_use():
            logger.error(f"[Zirunbi] Web Server Error: Port {self.port} is already in use!")
            logger.error(f"[Zirunbi] Please change 'web_port' in plugin config or close the application using this port.")
            return

        try:
            await self.server.serve()
        except BaseException as e:
            if isinstance(e, SystemExit):
                logger.warning("[Zirunbi] Web Server stopped (SystemExit).")
            else:
                logger.error(f"[Zirunbi] Web Server runtime error: {e}")

    async def stop(self):
        self.server.should_exit = True

    def run_in_background(self):
        loop = asyncio.get_event_loop()
        loop.create_task(self.start())
