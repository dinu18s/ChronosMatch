"""Persistent SQLite database manager for ChronosMatch Virtual Paper Trading."""

import datetime
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

def _find_project_root() -> Path:
    p = Path(__file__).resolve().parent
    for _ in range(6):
        if (p / "pyproject.toml").exists() or (p / ".git").exists():
            return p
        p = p.parent
    return Path(__file__).resolve().parent

DB_PATH = Path(os.environ.get("CHRONOS_DB_PATH", _find_project_root() / "chronos_paper_trading.db"))


class Database:
    """Thread-safe SQLite database manager for user accounts, portfolios, virtual trading, and analytics."""

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
                    stop_price REAL DEFAULT 0.0,
                    quantity REAL NOT NULL,
                    filled_qty REAL DEFAULT 0.0,
                    leaves_qty REAL DEFAULT 0.0,
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

                CREATE TABLE IF NOT EXISTS journal_entries (
                    entry_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    order_id TEXT,
                    strategy TEXT,
                    sentiment TEXT,
                    notes TEXT NOT NULL,
                    lessons TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (email) REFERENCES users (email) ON DELETE CASCADE
                );
            """)

            # Automatic schema migration for existing databases
            for col_sql in [
                "ALTER TABLE orders ADD COLUMN stop_price REAL DEFAULT 0.0;",
                "ALTER TABLE orders ADD COLUMN filled_qty REAL DEFAULT 0.0;",
                "ALTER TABLE orders ADD COLUMN leaves_qty REAL DEFAULT 0.0;",
            ]:
                try:
                    conn.execute(col_sql)
                except sqlite3.OperationalError:
                    pass

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

    def reset_account(self, email: str, starting_balance: float = 100000.0) -> Dict[str, Any]:
        """Reset virtual portfolio balance, clear all active holdings and completed orders."""
        email = email.strip().lower()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO users (email, name, password, color, created_at) VALUES (?, 'Trader', 'pass', '#3b82f6', ?)",
                (email, now),
            )
            cursor.execute(
                "INSERT INTO accounts (email, cash_balance, realized_pnl, updated_at) VALUES (?, ?, 0.0, ?) ON CONFLICT(email) DO UPDATE SET cash_balance = ?, realized_pnl = 0.0, updated_at = ?",
                (email, starting_balance, now, starting_balance, now),
            )
            cursor.execute("DELETE FROM holdings WHERE email = ?", (email,))
            cursor.execute("DELETE FROM orders WHERE email = ?", (email,))
            conn.commit()

        return {
            "email": email,
            "cash_balance": round(starting_balance, 2),
            "realized_pnl": 0.0,
            "status": "reset",
            "message": f"Portfolio successfully reset to starting balance of INR {starting_balance:,.2f}.",
        }

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

            cursor.execute(
                "SELECT SUM(total_value) as locked FROM orders WHERE email = ? AND action = 'BUY' AND status IN ('Pending', 'Trigger Pending', 'Partially Filled')",
                (email,),
            )
            locked_row = cursor.fetchone()
            locked_cash = (locked_row["locked"] if locked_row and locked_row["locked"] else 0.0)

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
        total_portfolio_value = cash_balance + locked_cash + current_holdings_value

        return {
            "email": email,
            "cash_balance": round(cash_balance, 2),
            "locked_cash": round(locked_cash, 2),
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
        stop_price: float = 0.0,
        order_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Atomically validate and execute a virtual buy or sell order (Market, Limit, or Stop-Limit)."""
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

            # Prevent duplicate order submissions
            if order_id:
                cursor.execute("SELECT order_id FROM orders WHERE order_id = ?", (order_id,))
                if cursor.fetchone():
                    raise ValueError(f"Duplicate order submission: Order #{order_id} has already been processed.")

            # Ensure user and account exist
            cursor.execute(
                "INSERT OR IGNORE INTO users (email, name, password, color, created_at) VALUES (?, 'Trader', 'pass', '#3b82f6', ?)",
                (email, now),
            )
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

            # Determine order status
            if not status:
                if order_type == "STOP_LIMIT" and stop_price > 0:
                    status = "Trigger Pending"
                elif order_type == "LIMIT":
                    status = "Pending"
                else:
                    status = "Completed"

            is_pending = status in ("Pending", "Trigger Pending")
            filled_qty = quantity if not is_pending else 0.0
            leaves_qty = 0.0 if not is_pending else quantity

            if action == "BUY":
                if cash_balance < total_value:
                    raise ValueError(
                        f"Insufficient virtual cash! Order requires INR {total_value:,.2f}, but available balance is INR {cash_balance:,.2f}."
                    )

                new_cash = round(cash_balance - total_value, 2)

                if not is_pending:
                    # Update or insert holding
                    cursor.execute(
                        "SELECT quantity, avg_buy_price, total_invested FROM holdings WHERE email = ? AND symbol = ?",
                        (email, symbol),
                    )
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
                cursor.execute(
                    "SELECT quantity, avg_buy_price, total_invested FROM holdings WHERE email = ? AND symbol = ?",
                    (email, symbol),
                )
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

                if not is_pending:
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
                else:
                    new_cash = cash_balance
                    trade_realized_pnl = 0.0

            # Record order
            cursor.execute(
                """INSERT INTO orders
                   (order_id, email, symbol, action, order_type, price, stop_price, quantity, filled_qty, leaves_qty, total_value, realized_pnl, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (order_id, email, symbol, action, order_type, price, stop_price, quantity, filled_qty, leaves_qty, total_value, trade_realized_pnl, status, now),
            )

            conn.commit()

        return {
            "order_id": order_id,
            "email": email,
            "symbol": symbol,
            "action": action,
            "order_type": order_type,
            "price": price,
            "stop_price": stop_price,
            "quantity": quantity,
            "filled_qty": filled_qty,
            "leaves_qty": leaves_qty,
            "total_value": total_value,
            "realized_pnl": round(trade_realized_pnl, 2),
            "status": status,
            "cash_balance": round(new_cash, 2),
            "created_at": now,
        }

    def cancel_virtual_order(self, email: str, order_id: str) -> Dict[str, Any]:
        """Cancel an active resting virtual order (Pending or Trigger Pending) and refund reserved funds."""
        email = email.strip().lower()
        order_id = order_id.strip()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT order_id, email, symbol, action, order_type, price, quantity, filled_qty, leaves_qty, total_value, status FROM orders WHERE email = ? AND order_id = ?",
                (email, order_id),
            )
            order = cursor.fetchone()
            if not order:
                raise ValueError(f"Order #{order_id} not found.")

            cur_status = order["status"]
            if cur_status in ("Cancelled", "Filled", "Completed"):
                raise ValueError(f"Order #{order_id} cannot be cancelled because it is already {cur_status}.")

            action = order["action"]
            price = order["price"]
            leaves_q = order["leaves_qty"] if (order["leaves_qty"] and order["leaves_qty"] > 0) else order["quantity"]
            refund_amount = round(leaves_q * price, 2)

            if action == "BUY":
                cursor.execute("SELECT cash_balance FROM accounts WHERE email = ?", (email,))
                acct = cursor.fetchone()
                if acct:
                    new_balance = round(acct["cash_balance"] + refund_amount, 2)
                    cursor.execute(
                        "UPDATE accounts SET cash_balance = ?, updated_at = ? WHERE email = ?",
                        (new_balance, now, email),
                    )

            cursor.execute(
                "UPDATE orders SET status = 'Cancelled', leaves_qty = 0.0 WHERE email = ? AND order_id = ?",
                (email, order_id),
            )
            conn.commit()

        return {
            "order_id": order_id,
            "symbol": order["symbol"],
            "action": order["action"],
            "status": "Cancelled",
            "refunded_cash": refund_amount if action == "BUY" else 0.0,
        }

    def fill_virtual_order(
        self,
        email: str,
        order_id: str,
        fill_price: Optional[float] = None,
        fill_qty: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Execute a full or partial fill on a resting virtual order."""
        email = email.strip().lower()
        order_id = order_id.strip()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT order_id, email, symbol, action, order_type, price, quantity, filled_qty, leaves_qty, total_value, status FROM orders WHERE email = ? AND order_id = ?",
                (email, order_id),
            )
            order = cursor.fetchone()
            if not order:
                raise ValueError(f"Order #{order_id} not found.")

            cur_status = order["status"]
            if cur_status in ("Cancelled", "Filled", "Completed"):
                raise ValueError(f"Order #{order_id} is already {cur_status}.")

            action = order["action"]
            symbol = order["symbol"]
            order_p = order["price"]
            exec_price = fill_price if fill_price is not None else order_p
            remaining = order["leaves_qty"] if (order["leaves_qty"] and order["leaves_qty"] > 0) else order["quantity"]

            exec_qty = fill_qty if fill_qty is not None else remaining
            if exec_qty <= 0 or exec_qty > remaining:
                raise ValueError(f"Invalid fill quantity {exec_qty}. Remaining leaves quantity is {remaining}.")

            exec_value = round(exec_price * exec_qty, 2)
            new_leaves = round(remaining - exec_qty, 4)
            new_filled = round((order["filled_qty"] or 0.0) + exec_qty, 4)
            new_status = "Filled" if new_leaves <= 0.0001 else "Partially Filled"
            trade_realized_pnl = 0.0

            cursor.execute("SELECT cash_balance, realized_pnl FROM accounts WHERE email = ?", (email,))
            acct = cursor.fetchone()
            cash_balance = acct["cash_balance"] if acct else 100000.0
            realized_pnl = acct["realized_pnl"] if acct else 0.0

            if action == "BUY":
                cursor.execute(
                    "SELECT quantity, avg_buy_price, total_invested FROM holdings WHERE email = ? AND symbol = ?",
                    (email, symbol),
                )
                cur_h = cursor.fetchone()
                if cur_h and cur_h["quantity"] > 0:
                    old_qty = cur_h["quantity"]
                    old_inv = cur_h["total_invested"]
                    tot_q = old_qty + exec_qty
                    tot_i = old_inv + exec_value
                    avg_p = tot_i / tot_q
                    cursor.execute(
                        "UPDATE holdings SET quantity = ?, avg_buy_price = ?, total_invested = ?, updated_at = ? WHERE email = ? AND symbol = ?",
                        (tot_q, avg_p, tot_i, now, email, symbol),
                    )
                else:
                    cursor.execute(
                        "INSERT OR REPLACE INTO holdings (email, symbol, quantity, avg_buy_price, total_invested, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (email, symbol, exec_qty, exec_price, exec_value, now),
                    )
            elif action == "SELL":
                cursor.execute(
                    "SELECT quantity, avg_buy_price, total_invested FROM holdings WHERE email = ? AND symbol = ?",
                    (email, symbol),
                )
                cur_h = cursor.fetchone()
                if not cur_h or cur_h["quantity"] < exec_qty:
                    raise ValueError("Insufficient shares to execute sell fill.")

                old_q = cur_h["quantity"]
                old_i = cur_h["total_invested"]
                avg_buy_p = cur_h["avg_buy_price"]
                trade_realized_pnl = round((exec_price - avg_buy_p) * exec_qty, 2)
                new_q = old_q - exec_qty
                new_i = max(0.0, old_i - (avg_buy_p * exec_qty))
                new_cash = round(cash_balance + exec_value, 2)
                new_realized = round(realized_pnl + trade_realized_pnl, 2)

                if new_q <= 0.000001:
                    cursor.execute("DELETE FROM holdings WHERE email = ? AND symbol = ?", (email, symbol))
                else:
                    cursor.execute(
                        "UPDATE holdings SET quantity = ?, total_invested = ?, updated_at = ? WHERE email = ? AND symbol = ?",
                        (new_q, new_i, now, email, symbol),
                    )

                cursor.execute(
                    "UPDATE accounts SET cash_balance = ?, realized_pnl = ?, updated_at = ? WHERE email = ?",
                    (new_cash, new_realized, now, email),
                )

            cursor.execute(
                "UPDATE orders SET filled_qty = ?, leaves_qty = ?, status = ?, realized_pnl = realized_pnl + ? WHERE email = ? AND order_id = ?",
                (new_filled, new_leaves, new_status, trade_realized_pnl, email, order_id),
            )
            conn.commit()

        return {
            "order_id": order_id,
            "symbol": symbol,
            "action": action,
            "fill_price": exec_price,
            "fill_qty": exec_qty,
            "leaves_qty": new_leaves,
            "status": new_status,
            "realized_pnl": trade_realized_pnl,
        }

    def get_orders(self, email: str, limit: int = 100) -> List[Dict[str, Any]]:
        email = email.strip().lower()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT order_id, email, symbol, action, order_type, price, stop_price, quantity, filled_qty, leaves_qty, total_value, realized_pnl, status, created_at FROM orders WHERE email = ? ORDER BY created_at DESC LIMIT ?",
                (email, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_analytics(self, email: str) -> Dict[str, Any]:
        """Compute comprehensive win rate, trade metrics, and profit statistics."""
        orders = self.get_orders(email, limit=500)
        sells = [o for o in orders if o["action"] == "SELL" and o["status"] in ("Completed", "Filled", "Partially Filled")]

        total_trades = len(sells)
        wins = [o for o in sells if (o["realized_pnl"] or 0) > 0]
        losses = [o for o in sells if (o["realized_pnl"] or 0) < 0]

        win_rate = round((len(wins) / total_trades * 100), 2) if total_trades > 0 else 0.0
        gross_profit = sum(o["realized_pnl"] for o in wins)
        gross_loss = abs(sum(o["realized_pnl"] for o in losses))
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (round(gross_profit, 2) if gross_profit > 0 else 1.0)

        best_trade = max((o["realized_pnl"] for o in sells), default=0.0)
        worst_trade = min((o["realized_pnl"] for o in sells), default=0.0)
        avg_trade = round(sum(o["realized_pnl"] for o in sells) / total_trades, 2) if total_trades > 0 else 0.0

        return {
            "email": email,
            "total_trades": total_trades,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_pct": win_rate,
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "profit_factor": profit_factor,
            "best_trade": round(best_trade, 2),
            "worst_trade": round(worst_trade, 2),
            "average_trade": avg_trade,
        }

    def add_journal_entry(
        self,
        email: str,
        symbol: str,
        notes: str,
        strategy: str = "General",
        sentiment: str = "Bullish",
        order_id: Optional[str] = None,
        lessons: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record a user trading journal entry."""
        email = email.strip().lower()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        entry_id = f"JRN-{int(datetime.datetime.now().timestamp() * 1000)}"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO users (email, name, password, color, created_at) VALUES (?, 'Trader', 'pass', '#3b82f6', ?)",
                (email, now),
            )
            cursor.execute(
                """INSERT INTO journal_entries
                   (entry_id, email, symbol, order_id, strategy, sentiment, notes, lessons, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry_id, email, symbol.upper(), order_id, strategy, sentiment, notes, lessons, now),
            )
            conn.commit()

        return {
            "entry_id": entry_id,
            "email": email,
            "symbol": symbol.upper(),
            "strategy": strategy,
            "sentiment": sentiment,
            "notes": notes,
            "lessons": lessons,
            "created_at": now,
        }

    def get_journal_entries(self, email: str, limit: int = 50) -> List[Dict[str, Any]]:
        email = email.strip().lower()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT entry_id, email, symbol, order_id, strategy, sentiment, notes, lessons, created_at FROM journal_entries WHERE email = ? ORDER BY created_at DESC LIMIT ?",
                (email, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def delete_journal_entry(self, email: str, entry_id: str) -> bool:
        email = email.strip().lower()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM journal_entries WHERE email = ? AND entry_id = ?", (email, entry_id))
            conn.commit()
            return cursor.rowcount > 0

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
            cursor.execute(
                "INSERT OR IGNORE INTO users (email, name, password, color, created_at) VALUES (?, 'Trader', 'pass', '#3b82f6', ?)",
                (email, now),
            )
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
