"""Persistent SQLite database manager for ChronosMatch Virtual Paper Trading."""

import datetime
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = Path(os.environ.get("CHRONOS_DB_PATH", Path(__file__).resolve().parent.parent.parent.parent / "chronos_paper_trading.db"))


class Database:
    """Thread-safe SQLite database manager for user accounts, portfolios, and virtual trading."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_db(self) -> None:
        """Create tables if they do not exist."""
        with self.get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    email TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    password TEXT NOT NULL,
                    color TEXT DEFAULT '#3b82f6',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS accounts (
                    email TEXT PRIMARY KEY,
                    cash_balance REAL NOT NULL DEFAULT 100000.00,
                    realized_pnl REAL NOT NULL DEFAULT 0.00,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (email) REFERENCES users (email) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS holdings (
                    email TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    avg_buy_price REAL NOT NULL,
                    total_invested REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (email, symbol),
                    FOREIGN KEY (email) REFERENCES users (email) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    total_value REAL NOT NULL,
                    realized_pnl REAL DEFAULT 0.00,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (email) REFERENCES users (email) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS watchlists (
                    email TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    PRIMARY KEY (email, symbol),
                    FOREIGN KEY (email) REFERENCES users (email) ON DELETE CASCADE
                );
            """)

    def register_or_login(self, email: str, name: str, password: str, color: Optional[str] = None) -> Dict[str, Any]:
        """Sign in or register a user, ensuring an account with ₹1,00,000 initial virtual cash."""
        email = email.strip().lower()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        color = color or "#3b82f6"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT email, name, password, color FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()

            if row:
                if row["password"] and row["password"] != password:
                    raise ValueError("Incorrect password. Please try again.")
                user_data = dict(row)
            else:
                cursor.execute(
                    "INSERT INTO users (email, name, password, color, created_at) VALUES (?, ?, ?, ?, ?)",
                    (email, name, password, color, now),
                )
                user_data = {"email": email, "name": name, "color": color}

            # Ensure account balance exists
            cursor.execute("SELECT cash_balance, realized_pnl FROM accounts WHERE email = ?", (email,))
            acct = cursor.fetchone()
            if not acct:
                cursor.execute(
                    "INSERT INTO accounts (email, cash_balance, realized_pnl, updated_at) VALUES (?, 100000.00, 0.00, ?)",
                    (email, now),
                )
                cash_balance = 100000.00
                realized_pnl = 0.00
            else:
                cash_balance = acct["cash_balance"]
                realized_pnl = acct["realized_pnl"]

            conn.commit()

        user_data["cash_balance"] = cash_balance
        user_data["realized_pnl"] = realized_pnl
        return user_data

    def get_account(self, email: str) -> Optional[Dict[str, Any]]:
        email = email.strip().lower()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT email, cash_balance, realized_pnl, updated_at FROM accounts WHERE email = ?", (email,))
            row = cursor.fetchone()
            if not row:
                return None
            return dict(row)

    def get_portfolio(self, email: str, prices_map: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """Calculate complete user portfolio, holdings, invested capital, and profit/loss."""
        email = email.strip().lower()
        prices_map = prices_map or {}

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT cash_balance, realized_pnl FROM accounts WHERE email = ?", (email,))
            acct = cursor.fetchone()
            if not acct:
                return {
                    "email": email,
                    "cash_balance": 100000.00,
                    "realized_pnl": 0.00,
                    "total_invested": 0.00,
                    "current_holdings_value": 0.00,
                    "unrealized_pnl": 0.00,
                    "unrealized_pnl_pct": 0.00,
                    "total_portfolio_value": 100000.00,
                    "holdings": [],
                }

            cash_balance = acct["cash_balance"]
            realized_pnl = acct["realized_pnl"]

            cursor.execute(
                "SELECT symbol, quantity, avg_buy_price, total_invested, updated_at FROM holdings WHERE email = ? AND quantity > 0",
                (email,),
            )
            rows = cursor.fetchall()

        holdings = []
        total_invested = 0.0
        current_holdings_value = 0.0

        for r in rows:
            sym = r["symbol"]
            qty = r["quantity"]
            avg_p = r["avg_buy_price"]
            inv = r["total_invested"]

            cur_p = prices_map.get(sym, avg_p)
            val = qty * cur_p
            pnl = val - inv
            pnl_pct = (pnl / inv * 100) if inv > 0 else 0.0

            total_invested += inv
            current_holdings_value += val

            holdings.append({
                "symbol": sym,
                "quantity": qty,
                "avg_buy_price": round(avg_p, 2),
                "current_price": round(cur_p, 2),
                "total_invested": round(inv, 2),
                "current_value": round(val, 2),
                "unrealized_pnl": round(pnl, 2),
                "unrealized_pnl_pct": round(pnl_pct, 2),
                "updated_at": r["updated_at"],
            })

        unrealized_pnl = current_holdings_value - total_invested
        unrealized_pnl_pct = (unrealized_pnl / total_invested * 100) if total_invested > 0 else 0.0
        total_portfolio_value = cash_balance + current_holdings_value

        return {
            "email": email,
            "cash_balance": round(cash_balance, 2),
            "realized_pnl": round(realized_pnl, 2),
            "total_invested": round(total_invested, 2),
            "current_holdings_value": round(current_holdings_value, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
            "total_portfolio_value": round(total_portfolio_value, 2),
            "holdings": holdings,
        }

    def execute_virtual_trade(
        self,
        email: str,
        symbol: str,
        action: str,
        order_type: str,
        price: float,
        quantity: float,
        order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Atomically validate and execute a virtual buy or sell order."""
        email = email.strip().lower()
        symbol = symbol.strip().upper()
        action = action.strip().upper()
        order_type = order_type.strip().upper()

        if action not in ("BUY", "SELL"):
            raise ValueError("Trade action must be 'BUY' or 'SELL'.")
        if quantity <= 0:
            raise ValueError("Order quantity must be greater than zero.")
        if price <= 0:
            raise ValueError("Order price must be greater than zero.")

        total_value = round(price * quantity, 2)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if not order_id:
            order_id = f"ORD-{int(datetime.datetime.now().timestamp() * 1000)}"

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Ensure user and account exist
            cursor.execute("INSERT OR IGNORE INTO users (email, name, password, color, created_at) VALUES (?, 'Trader', 'pass', '#3b82f6', ?)", (email, now))
            cursor.execute("SELECT cash_balance, realized_pnl FROM accounts WHERE email = ?", (email,))
            acct = cursor.fetchone()
            if not acct:
                cursor.execute(
                    "INSERT INTO accounts (email, cash_balance, realized_pnl, updated_at) VALUES (?, 100000.00, 0.00, ?)",
                    (email, now),
                )
                cash_balance = 100000.00
                realized_pnl = 0.00
            else:
                cash_balance = acct["cash_balance"]
                realized_pnl = acct["realized_pnl"]

            trade_realized_pnl = 0.0

            if action == "BUY":
                if cash_balance < total_value:
                    raise ValueError(
                        f"Insufficient virtual cash! Order requires INR {total_value:,.2f}, but available balance is INR {cash_balance:,.2f}."
                    )

                new_cash = cash_balance - total_value

                # Update or insert holding
                cursor.execute("SELECT quantity, avg_buy_price, total_invested FROM holdings WHERE email = ? AND symbol = ?", (email, symbol))
                cur_h = cursor.fetchone()

                if cur_h and cur_h["quantity"] > 0:
                    old_qty = cur_h["quantity"]
                    old_inv = cur_h["total_invested"]
                    new_qty = old_qty + quantity
                    new_inv = old_inv + total_value
                    new_avg = new_inv / new_qty
                    cursor.execute(
                        "UPDATE holdings SET quantity = ?, avg_buy_price = ?, total_invested = ?, updated_at = ? WHERE email = ? AND symbol = ?",
                        (new_qty, new_avg, new_inv, now, email, symbol),
                    )
                else:
                    cursor.execute(
                        "INSERT OR REPLACE INTO holdings (email, symbol, quantity, avg_buy_price, total_invested, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (email, symbol, quantity, price, total_value, now),
                    )

                cursor.execute(
                    "UPDATE accounts SET cash_balance = ?, updated_at = ? WHERE email = ?",
                    (new_cash, now, email),
                )

            elif action == "SELL":
                cursor.execute("SELECT quantity, avg_buy_price, total_invested FROM holdings WHERE email = ? AND symbol = ?", (email, symbol))
                cur_h = cursor.fetchone()

                if not cur_h or cur_h["quantity"] < quantity:
                    owned = cur_h["quantity"] if cur_h else 0.0
                    raise ValueError(
                        f"Insufficient shares! You own {owned:g} shares of {symbol}, but attempted to sell {quantity:g}."
                    )

                old_qty = cur_h["quantity"]
                avg_buy_price = cur_h["avg_buy_price"]
                old_inv = cur_h["total_invested"]

                trade_realized_pnl = (price - avg_buy_price) * quantity
                new_realized_pnl = realized_pnl + trade_realized_pnl
                new_cash = cash_balance + total_value

                new_qty = old_qty - quantity
                new_inv = max(0.0, old_inv - (avg_buy_price * quantity))

                if new_qty <= 0.000001:
                    cursor.execute("DELETE FROM holdings WHERE email = ? AND symbol = ?", (email, symbol))
                else:
                    cursor.execute(
                        "UPDATE holdings SET quantity = ?, total_invested = ?, updated_at = ? WHERE email = ? AND symbol = ?",
                        (new_qty, new_inv, now, email, symbol),
                    )

                cursor.execute(
                    "UPDATE accounts SET cash_balance = ?, realized_pnl = ?, updated_at = ? WHERE email = ?",
                    (new_cash, new_realized_pnl, now, email),
                )

            # Record order
            cursor.execute(
                """INSERT INTO orders
                   (order_id, email, symbol, action, order_type, price, quantity, total_value, realized_pnl, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Completed', ?)""",
                (order_id, email, symbol, action, order_type, price, quantity, total_value, trade_realized_pnl, now),
            )

            conn.commit()

        return {
            "order_id": order_id,
            "email": email,
            "symbol": symbol,
            "action": action,
            "order_type": order_type,
            "price": price,
            "quantity": quantity,
            "total_value": total_value,
            "realized_pnl": round(trade_realized_pnl, 2),
            "status": "Completed",
            "cash_balance": round(new_cash, 2),
            "created_at": now,
        }

    def get_orders(self, email: str, limit: int = 50) -> List[Dict[str, Any]]:
        email = email.strip().lower()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT order_id, email, symbol, action, order_type, price, quantity, total_value, realized_pnl, status, created_at FROM orders WHERE email = ? ORDER BY created_at DESC LIMIT ?",
                (email, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_watchlist(self, email: str) -> List[str]:
        email = email.strip().lower()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT symbol FROM watchlists WHERE email = ? ORDER BY added_at ASC", (email,))
            return [row["symbol"] for row in cursor.fetchall()]

    def toggle_watchlist(self, email: str, symbol: str) -> Dict[str, Any]:
        email = email.strip().lower()
        symbol = symbol.strip().upper()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO users (email, name, password, color, created_at) VALUES (?, 'Trader', 'pass', '#3b82f6', ?)", (email, now))
            cursor.execute("SELECT 1 FROM watchlists WHERE email = ? AND symbol = ?", (email, symbol))
            if cursor.fetchone():
                cursor.execute("DELETE FROM watchlists WHERE email = ? AND symbol = ?", (email, symbol))
                is_in_watchlist = False
            else:
                cursor.execute("INSERT INTO watchlists (email, symbol, added_at) VALUES (?, ?, ?)", (email, symbol, now))
                is_in_watchlist = True
            conn.commit()

        return {"email": email, "symbol": symbol, "in_watchlist": is_in_watchlist}


# Global default instance
db = Database()
