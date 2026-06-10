import asyncpg
import asyncio
import datetime
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

pool = None

async def init_db():
    global pool
    pool = await asyncpg.create_pool(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        min_size=1,
        max_size=1,
        command_timeout=5
    )
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                state TEXT DEFAULT 'wait_agreement',
                name TEXT,
                birth_date TEXT,
                zodiac TEXT,
                credits INTEGER DEFAULT 3,
                is_vip INTEGER DEFAULT 0,
                last_bonus_date TEXT,
                last_passive_date TEXT,
                referrer_id TEXT,
                is_admin INTEGER DEFAULT 0,
                last_active_date TEXT,
                agreement_date TEXT,
                has_purchased INTEGER DEFAULT 0,
                vip_until TEXT
            )
        ''')

async def _execute(operation, *args):
    for attempt in range(3):
        try:
            async with pool.acquire() as conn:
                return await operation(conn, *args)
        except (asyncpg.exceptions.InterfaceError, asyncpg.exceptions.ConnectionDoesNotExistError):
            if attempt == 2:
                raise
            await asyncio.sleep(0.1)
            continue

async def get_user(user_id: str):
    async def _fetch(conn):
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", str(user_id))
        return dict(row) if row else None
    return await _execute(_fetch)

async def create_user(user_id: str, referrer_id: str = None):
    async def _insert(conn):
        await conn.execute(
            "INSERT INTO users (user_id, referrer_id, state) VALUES ($1, $2, 'wait_agreement') ON CONFLICT (user_id) DO NOTHING",
            str(user_id), referrer_id
        )
    await _execute(_insert)

async def update_user(user_id: str, **kwargs):
    if not kwargs:
        return
    async def _update(conn):
        set_parts = []
        values = []
        for i, (col, val) in enumerate(kwargs.items(), start=1):
            set_parts.append(f"{col} = ${i}")
            values.append(val)
        values.append(str(user_id))
        query = f"UPDATE users SET {', '.join(set_parts)} WHERE user_id = ${len(values)}"
        await conn.execute(query, *values)
    await _execute(_update)

async def add_credits(user_id: str, amount: int):
    async def _add(conn):
        await conn.execute(
            "UPDATE users SET credits = credits + $1 WHERE user_id = $2",
            amount, str(user_id)
        )
    await _execute(_add)

async def get_stats(today_str: str):
    async def _stats(conn):
        total = await conn.fetchval("SELECT COUNT(*) FROM users")
        vip = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_vip = 1")
        active = await conn.fetchval("SELECT COUNT(*) FROM users WHERE last_active_date = $1", today_str)
        return {"total": total, "vip": vip, "active": active}
    return await _execute(_stats)
