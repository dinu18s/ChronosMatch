"""Interactive real-time market simulation demonstrating order book depth and live trades."""

import random
import time
from chronosmatch.engine import MatchingEngine
from chronosmatch.protocol import (
    CancelOrderMsg,
    ExecType,
    NewOrderMsg,
    OrderType,
    Side,
    fixed_to_price,
)


def run_simulation(symbol: str = "BTCUSDT", duration_sec: int = 5, orders_per_sec: int = 20):
    engine = MatchingEngine()
    book = engine.get_or_create_book(symbol)

    print("\n" + "=" * 65)
    print(f" ChronosMatch Live Simulation : {symbol}")
    print("=" * 65)

    base_price = 65_000.0
    order_id = 1
    active_orders = []

    start_time = time.time()
    last_print = 0

    while time.time() - start_time < duration_sec:
        action = random.random()

        if action < 0.65 or not active_orders:
            # Place Limit Order
            side = Side.BUY if random.random() < 0.5 else Side.SELL
            offset = random.uniform(0.5, 15.0)
            price = round(base_price - offset if side == Side.BUY else base_price + offset, 2)
            qty = random.randint(1, 10)

            order = NewOrderMsg.create(
                order_id=order_id,
                client_id=1,
                symbol=symbol,
                side=side,
                order_type=OrderType.LIMIT,
                price=price,
                quantity=qty,
            )
            reports = book.process_order(order)
            active_orders.append((order_id, side, price))
            order_id += 1

            for rep in reports:
                if rep.exec_type == ExecType.TRADE:
                    t_side = "BUY " if rep.side == 1 else "SELL"
                    print(
                        f"  [TRADE] Match! {t_side} {rep.last_qty} @ {fixed_to_price(rep.price):.2f} "
                        f"(Taker #{rep.order_id} x Maker #{rep.matched_order_id})"
                    )

        elif action < 0.85 and active_orders:
            # Cancel Random Resting Order
            oid, _, _ = active_orders.pop(random.randrange(len(active_orders)))
            cancel = CancelOrderMsg.create(order_id=oid, client_id=1, symbol=symbol)
            rep = book.cancel_order(cancel)
            if rep.exec_type == ExecType.CANCELLED:
                print(f"  [CANCEL] Order #{oid} cancelled")

        else:
            # Aggressive Market Order
            side = Side.BUY if random.random() < 0.5 else Side.SELL
            qty = random.randint(2, 8)
            mkt = NewOrderMsg.create(
                order_id=order_id,
                client_id=2,
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET,
                price=0.0,
                quantity=qty,
            )
            reports = book.process_order(mkt)
            order_id += 1
            for rep in reports:
                if rep.exec_type == ExecType.TRADE:
                    t_side = "BUY " if rep.side == 1 else "SELL"
                    print(
                        f"  [SWEEP] Market {t_side} filled {rep.last_qty} @ {fixed_to_price(rep.price):.2f}"
                    )

        time.sleep(1.0 / orders_per_sec)

        # Print L2 Snapshot periodically
        if time.time() - last_print > 1.5:
            last_print = time.time()
            bids, asks = book.get_l2_depth(depth=5)
            print("-" * 65)
            print("  --- ORDER BOOK SNAPSHOT (Top 5 Levels) ---")
            for p, q in reversed(asks):
                print(f"         ASK | Price: {p:10.2f} | Size: {q:4d}")
            print("  ------------------- SPREAD -------------------")
            for p, q in bids:
                print(f"  BID        | Price: {p:10.2f} | Size: {q:4d}")
            print("-" * 65)

    print("\nSimulation complete. Active resting orders in book:", book.order_count)


if __name__ == "__main__":
    run_simulation(duration_sec=3, orders_per_sec=30)
