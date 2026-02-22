# AGENTS.md — astrbot_plugin_zirunbi

## Project Overview

AstrBot plugin for simulated multi-coin cryptocurrency trading in group chats. Built on the AstrBot plugin framework (`Star` base class). Provides chat commands (`/zrb`), a FastAPI web trading interface, SQLAlchemy-backed persistence, and matplotlib/mplfinance chart generation.

**Version**: 1.1.1 | **Author**: LumineStory | **Python**: 3.9+

## Build / Run / Test Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Database migration (standalone, run from plugin root)
python migrate.py

# No build step — plugin is loaded by AstrBot at runtime from data/plugins/
# No test suite exists — there are no test files in this project
# No linter or formatter is configured
```

**Important**: This plugin has NO tests and NO CI. When making changes, manually verify by reading `lsp_diagnostics` output and ensuring no import/syntax errors.

## Project Structure

```
astrbot_plugin_zirunbi/
  main.py            # Plugin entry point — ZRBTrader(Star) class, all /zrb commands
  database.py        # SQLAlchemy ORM models (User, Order, MarketHistory, etc.) and DB class
  market.py          # Market simulation engine — price updates, order matching, threading
  plotter.py         # Chart generation — K-line (mplfinance) and holdings pie (matplotlib)
  web_server.py      # FastAPI web server — REST API, auth, WebServer class
  migrate.py         # Standalone DB migration script (safe to run independently)
  __init__.py        # Empty (required for Python package)
  metadata.yaml      # AstrBot plugin metadata (name, author, version, repo)
  _conf_schema.json  # Plugin configuration schema (shown in AstrBot admin panel)
  requirements.txt   # Python dependencies
  web/index.html     # Single-page web frontend (Bootstrap 5 + ECharts)
  fonts/             # Bundled Chinese font (SourceHanSansSC-Regular.otf)
  data/              # AstrBot templates and runtime config
  zirunbi.db         # SQLite database (gitignored, auto-created)
```

## AstrBot Plugin Framework Conventions

### Plugin Registration
```python
from astrbot.api.star import Context, Star, register

@register("zrb_trader", "LumineStory", "模拟炒股插件", "1.1.1", "https://...")
class ZRBTrader(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        # config comes from _conf_schema.json defaults + user overrides
```

### Lifecycle
- `__init__(context, config)` — called on plugin load; start background threads here
- `async terminate()` — called on plugin unload; stop threads and servers here

### Command Handling
```python
@filter.command("zrb")
async def zrb(self, event: AstrMessageEvent):
    # Async generator — use `yield` to return results
    yield event.plain_result("text message")
    yield event.image_result("/path/to/image.png")
```

### Key AstrBot API Imports
```python
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.all import *  # wildcard import used in this project
```

### Configuration System
- `_conf_schema.json` defines config fields with `description`, `type`, `default`
- Supported types: `float`, `int`, `string`, `list`
- Config dict is passed to `__init__` and accessed via `self.config`

### Metadata
- `metadata.yaml` fields: `name`, `author`, `version`, `description`, `repo`

## Code Style Guidelines

### Naming
- **Classes**: PascalCase (`ZRBTrader`, `Market`, `WebServer`, `UserHolding`)
- **Functions/methods**: snake_case (`get_or_create_user`, `match_single_order`)
- **Private methods**: leading underscore (`_update_prices`, `_save_candles`, `_loop`)
- **Constants**: UPPER_SNAKE_CASE (`PLUGIN_DIR`, `DEFAULT_PLUGIN_FONT`, `FALLBACK_FONT_FAMILIES`)
- **Enum members**: UPPER_SNAKE_CASE (`OrderType.BUY`, `OrderStatus.PENDING`)

### Imports
This project uses a **dual-import pattern** for standalone testing compatibility:
```python
try:
    from .database import DB, User, ...   # Relative import (when loaded by AstrBot)
except ImportError:
    from database import DB, User, ...    # Absolute import (when run standalone)
```
Similarly for `astrbot.api.logger`:
```python
try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
```
**Always preserve this dual-import pattern when adding new modules.**

### Formatting
- 4-space indentation
- f-strings for string interpolation (no `.format()` or `%`)
- Line length: no enforced limit, but generally kept under ~120 chars
- No trailing commas convention
- Chinese strings for user-facing messages, English for logs and code comments

### Type Hints
- Minimal type hints — used sparingly on function signatures (mostly in `web_server.py`)
- SQLAlchemy models use Column types instead of Python type hints
- Pydantic models used only in `web_server.py` for FastAPI request validation

### Error Handling
- `try/except` with `logger.error()` or `logger.warning()` — never silently swallow
- Database sessions: manual `session.close()` in `finally` blocks or after use
- No custom exception classes — uses built-in exceptions and FastAPI `HTTPException`

### Docstrings
- Sparse — only a few methods have docstrings
- When present, use triple-quote one-liners: `"""Description"""`

## Architecture Notes

### Database Layer (`database.py`)
- SQLAlchemy ORM with `declarative_base()`
- Models: `User`, `UserHolding`, `Order`, `MarketHistory`, `MarketNews`
- `DB` class wraps engine + session factory + auto-migration on init
- All timestamps use `get_china_time()` (UTC+8 with network time sync)
- `get_or_create_user()` returns `(user, session)` tuple — caller must close session

### Market Engine (`market.py`)
- Runs in a daemon thread (`threading.Thread(daemon=True)`)
- 3-minute price update cycle (configurable via `update_interval`)
- Uses `threading.Lock` for thread-safe price/candle updates
- Trading hours: Mon-Fri 09:30-11:30, 13:00-15:00 (China time)
- Admin can override market open/close state
- Order matching: market orders execute immediately, limit orders wait for price

### Web Server (`web_server.py`)
- FastAPI app with uvicorn, runs in asyncio background task
- Cookie-based auth with in-memory session store (`_sessions` dict)
- Password hashing via passlib (`pbkdf2_sha256`)
- Module-level `app` and `pwd_context` — shared across the application
- API endpoints: `/api/login`, `/api/logout`, `/api/me`, `/api/market`, `/api/assets`, `/api/trade`, `/api/kline/{symbol}`

### Chart Generation (`plotter.py`)
- `plot_kline()` — generates K-line candlestick charts (red=up, green=down, China standard)
- `plot_holdings_multi()` — generates holdings pie chart
- Returns `io.BytesIO` buffers; caller saves to temp file via `_save_temp_image()`
- Font initialization: tries custom font > mplfonts > system fallback chain

## Common Pitfalls

1. **Session management**: `db.get_or_create_user()` returns an open session — always close it
2. **Thread safety**: Market price updates happen in a background thread — use `self.lock`
3. **Dual imports**: New modules MUST use the try/except import pattern
4. **Font paths**: Relative font paths resolve against `PLUGIN_DIR` (plugin root)
5. **Database file**: `zirunbi.db` is in plugin root, gitignored — backup before schema changes
6. **Web server port**: Check `web_port` config to avoid conflicts; port-in-use check exists
7. **Time handling**: Always use `get_china_time()` for timestamps, never `datetime.now()`

## Dependencies

| Package | Purpose |
|---------|---------|
| sqlalchemy | ORM and database management |
| mplfinance | K-line candlestick chart generation |
| pandas | Data manipulation for chart data |
| matplotlib | Base plotting + pie charts |
| mplfonts | Chinese font support for charts |
| fastapi | Web server framework |
| uvicorn | ASGI server for FastAPI |
| python-multipart | FastAPI form data support |
| passlib | Password hashing (pbkdf2_sha256) |
| httpx | HTTP client for network time sync |
