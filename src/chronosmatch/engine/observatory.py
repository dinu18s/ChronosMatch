"""Order-Book Event Observatory & Microstructure Liquidity Lab Engine.

Provides:
- Event-by-event order book tracking with immutable event snapshots
- Price impact laboratory (expected price, VWAP, slippage, level consumption)
- Order-book imbalance at configurable depths (K=1, 3, 5, 10)
- Deterministic repeatable experiments using configurable pseudorandom seeds
- Comprehensive microstructure research report metrics and microsecond benchmarks
"""

import math
import random
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from chronosmatch.engine.book import OrderBook
from chronosmatch.protocol.messages import (
    CancelOrderMsg,
    ExecutionReportMsg,
    NewOrderMsg,
)
from chronosmatch.protocol.types import (
    ExecType,
    MatchStatus,
    OrderType,
    Side,
    TimeInForce,
    fixed_to_price,
    price_to_fixed,
)


def _compute_bbo_summary(book: OrderBook, depth: int = 5) -> Dict[str, Any]:
    """Extract BBO, spread, mid-price, and imbalance metrics from an order book."""
    bid_bbo, ask_bbo = book.get_bbo()
    best_bid_p = fixed_to_price(bid_bbo[0]) if bid_bbo else None
    best_bid_q = bid_bbo[1] if bid_bbo else 0
    best_ask_p = fixed_to_price(ask_bbo[0]) if ask_bbo else None
    best_ask_q = ask_bbo[1] if ask_bbo else 0

    spread = round(best_ask_p - best_bid_p, 4) if (best_bid_p is not None and best_ask_p is not None) else None
    if best_bid_p is not None and best_ask_p is not None:
        mid_price = round((best_bid_p + best_ask_p) / 2.0, 4)
        spread_bps = round((spread / mid_price) * 10_000, 2) if mid_price > 0 else 0.0
    else:
        mid_price = best_bid_p if best_bid_p is not None else (best_ask_p if best_ask_p is not None else 0.0)
        spread_bps = 0.0

    # Imbalance calculations at K=1 and K=depth
    bids_l2, asks_l2 = book.get_l2_depth(depth=depth)
    
    # K=1
    q_b1 = bids_l2[0][1] if bids_l2 else 0
    q_a1 = asks_l2[0][1] if asks_l2 else 0
    tot_1 = q_b1 + q_a1
    imbalance_1 = round((q_b1 - q_a1) / tot_1, 4) if tot_1 > 0 else 0.0

    # K=depth
    tot_b_k = sum(q for _, q in bids_l2)
    tot_a_k = sum(q for _, q in asks_l2)
    tot_k = tot_b_k + tot_a_k
    imbalance_k = round((tot_b_k - tot_a_k) / tot_k, 4) if tot_k > 0 else 0.0

    return {
        "best_bid": best_bid_p,
        "best_bid_qty": best_bid_q,
        "best_ask": best_ask_p,
        "best_ask_qty": best_ask_q,
        "spread": spread,
        "spread_bps": spread_bps,
        "mid_price": mid_price,
        "imbalance_1": imbalance_1,
        "imbalance_depth": imbalance_k,
        "total_bid_depth": tot_b_k,
        "total_ask_depth": tot_a_k,
        "order_count": book.order_count,
    }


def _snapshot_depth(book: OrderBook, depth: int = 10) -> Dict[str, Any]:
    """Capture current Level 2 depth snapshot."""
    bids, asks = book.get_l2_depth(depth=depth)
    return {
        "bids": [{"price": round(p, 2), "quantity": q} for p, q in bids],
        "asks": [{"price": round(p, 2), "quantity": q} for p, q in asks],
    }


class EventObservatoryEngine:
    """Instruments an OrderBook to capture immutable, event-by-event microstructure changes."""

    def __init__(self, symbol: str) -> None:
        self.symbol: str = symbol.upper()
        self.book: OrderBook = OrderBook(self.symbol)
        self.events: List[Dict[str, Any]] = []
        self._event_counter: int = 1

    def process_order_with_event(self, order_msg: NewOrderMsg) -> List[Dict[str, Any]]:
        """Process incoming order, recording before/after snapshots and delta events."""
        bbo_before = _compute_bbo_summary(self.book)
        depth_before = _snapshot_depth(self.book, depth=8)

        side_str = "BUY" if order_msg.side == 1 else "SELL"
        order_price = fixed_to_price(order_msg.price)
        requested_qty = order_msg.quantity

        reports: List[ExecutionReportMsg] = self.book.process_order(order_msg)

        bbo_after = _compute_bbo_summary(self.book)
        depth_after = _snapshot_depth(self.book, depth=8)

        bid_changed = (
            bbo_after["best_bid"] != bbo_before["best_bid"]
            or bbo_after["best_bid_qty"] != bbo_before["best_bid_qty"]
        )
        ask_changed = (
            bbo_after["best_ask"] != bbo_before["best_ask"]
            or bbo_after["best_ask_qty"] != bbo_before["best_ask_qty"]
        )
        spread_diff = round((bbo_after["spread"] or 0.0) - (bbo_before["spread"] or 0.0), 4)

        created_events: List[Dict[str, Any]] = []

        for rep in reports:
            et = rep.exec_type
            rep_price = fixed_to_price(rep.price)

            if et == ExecType.NEW:
                # Limit order accepted and resting in book (Liquidity Added)
                desc = (
                    f"New Limit {side_str} rested on book: {rep.leaves_qty} units @ {order_price:.2f}. "
                    f"BBO: {bbo_after['best_bid']} / {bbo_after['best_ask']} (Spread: {bbo_after['spread']})."
                )
                delta = {
                    "liquidity_change": rep.leaves_qty,
                    "bid_levels_changed": bid_changed,
                    "ask_levels_changed": ask_changed,
                    "spread_change": spread_diff,
                }
                ev = {
                    "event_id": self._event_counter,
                    "timestamp_ns": rep.timestamp_ns or time.time_ns(),
                    "timestamp_str": time.strftime("%H:%M:%S", time.localtime()),
                    "instrument": self.symbol,
                    "event_type": "NEW_LIMIT",
                    "side": side_str,
                    "price": order_price,
                    "quantity": rep.leaves_qty,
                    "liquidity_delta": rep.leaves_qty,  # Added
                    "delta": delta,
                    "order_id": rep.order_id,
                    "matched_order_id": 0,
                    "resulting_change": desc,
                    "bbo_before": bbo_before,
                    "bbo_after": bbo_after,
                    "depth_before": depth_before,
                    "depth_after": depth_after,
                }
                self._event_counter += 1
                self.events.append(ev)
                created_events.append(ev)

            elif et == ExecType.TRADE:
                # Only record taker report to prevent double-counting maker + taker execution
                if rep.order_id != order_msg.order_id:
                    continue

                # Match / Fill occurred (Liquidity Removed / Consumed)
                is_full = rep.match_status == MatchStatus.FULL
                ev_type = "TRADE_FULL" if is_full else "TRADE_PARTIAL"
                desc = (
                    f"Execution {side_str} fill: {rep.last_qty} units @ {rep_price:.2f} "
                    f"(Taker #{rep.order_id} x Maker #{rep.matched_order_id}). "
                    f"Remaining leaves: {rep.leaves_qty}."
                )
                delta = {
                    "liquidity_change": -rep.last_qty,
                    "bid_levels_changed": bid_changed,
                    "ask_levels_changed": ask_changed,
                    "spread_change": spread_diff,
                }
                ev = {
                    "event_id": self._event_counter,
                    "timestamp_ns": rep.timestamp_ns or time.time_ns(),
                    "timestamp_str": time.strftime("%H:%M:%S", time.localtime()),
                    "instrument": self.symbol,
                    "event_type": ev_type,
                    "side": side_str,
                    "price": rep_price,
                    "quantity": rep.last_qty,
                    "liquidity_delta": -rep.last_qty,  # Consumed
                    "delta": delta,
                    "order_id": rep.order_id,
                    "matched_order_id": rep.matched_order_id,
                    "resulting_change": desc,
                    "bbo_before": bbo_before,
                    "bbo_after": bbo_after,
                    "depth_before": depth_before,
                    "depth_after": depth_after,
                }
                self._event_counter += 1
                self.events.append(ev)
                created_events.append(ev)

            elif et == ExecType.EXPIRED:
                desc = f"Order #{rep.order_id} unexecuted remainder ({requested_qty - rep.cum_qty} units) expired."
                delta = {
                    "liquidity_change": 0,
                    "bid_levels_changed": bid_changed,
                    "ask_levels_changed": ask_changed,
                    "spread_change": spread_diff,
                }
                ev = {
                    "event_id": self._event_counter,
                    "timestamp_ns": rep.timestamp_ns or time.time_ns(),
                    "timestamp_str": time.strftime("%H:%M:%S", time.localtime()),
                    "instrument": self.symbol,
                    "event_type": "EXPIRED",
                    "side": side_str,
                    "price": order_price,
                    "quantity": requested_qty - rep.cum_qty,
                    "liquidity_delta": 0,
                    "delta": delta,
                    "order_id": rep.order_id,
                    "matched_order_id": 0,
                    "resulting_change": desc,
                    "bbo_before": bbo_before,
                    "bbo_after": bbo_after,
                    "depth_before": depth_before,
                    "depth_after": depth_after,
                }
                self._event_counter += 1
                self.events.append(ev)
                created_events.append(ev)

        return created_events

    def cancel_order_with_event(self, cancel_msg: CancelOrderMsg) -> Optional[Dict[str, Any]]:
        """Cancel resting order, generating cancellation event with before/after state."""
        bbo_before = _compute_bbo_summary(self.book)
        depth_before = _snapshot_depth(self.book, depth=8)

        # Lookup resting node to record price and quantity cancelled
        node = self.book._orders.get(cancel_msg.order_id)
        if not node:
            return None

        cancelled_qty = node.leaves_qty
        cancelled_price = fixed_to_price(node.price)
        cancelled_side = "BUY" if node.side == 1 else "SELL"

        rep = self.book.cancel_order(cancel_msg)
        if rep.exec_type != ExecType.CANCELLED:
            return None

        bbo_after = _compute_bbo_summary(self.book)
        depth_after = _snapshot_depth(self.book, depth=8)

        desc = (
            f"Cancelled resting {cancelled_side} Limit Order #{cancel_msg.order_id}: "
            f"{cancelled_qty} units @ {cancelled_price:.2f}. "
            f"Book depth reduced. Spread: {bbo_after['spread']}."
        )

        bid_changed = (
            bbo_after["best_bid"] != bbo_before["best_bid"]
            or bbo_after["best_bid_qty"] != bbo_before["best_bid_qty"]
        )
        ask_changed = (
            bbo_after["best_ask"] != bbo_before["best_ask"]
            or bbo_after["best_ask_qty"] != bbo_before["best_ask_qty"]
        )
        spread_diff = round((bbo_after["spread"] or 0.0) - (bbo_before["spread"] or 0.0), 4)

        delta = {
            "liquidity_change": -cancelled_qty,
            "bid_levels_changed": bid_changed,
            "ask_levels_changed": ask_changed,
            "spread_change": spread_diff,
        }

        ev = {
            "event_id": self._event_counter,
            "timestamp_ns": rep.timestamp_ns or time.time_ns(),
            "timestamp_str": time.strftime("%H:%M:%S", time.localtime()),
            "instrument": self.symbol,
            "event_type": "CANCEL",
            "side": cancelled_side,
            "price": cancelled_price,
            "quantity": cancelled_qty,
            "liquidity_delta": -cancelled_qty,  # Removed
            "delta": delta,
            "order_id": cancel_msg.order_id,
            "matched_order_id": 0,
            "resulting_change": desc,
            "bbo_before": bbo_before,
            "bbo_after": bbo_after,
            "depth_before": depth_before,
            "depth_after": depth_after,
        }
        self._event_counter += 1
        self.events.append(ev)
        return ev

    def process_cancel_with_event(self, cancel_msg: CancelOrderMsg) -> List[Dict[str, Any]]:
        """Cancel resting order and return list containing generated cancellation event."""
        ev = self.cancel_order_with_event(cancel_msg)
        return [ev] if ev else []


def simulate_price_impact(
    depth_data: Dict[str, Any],
    side: str,
    quantity: int,
) -> Dict[str, Any]:
    """Calculate price impact, VWAP, slippage, and levels consumed for a market order.

    Args:
        depth_data: Dict with 'bids' and 'asks' lists of {'price': float, 'quantity': int}.
        side: 'BUY' (crosses asks) or 'SELL' (crosses bids).
        quantity: Order quantity to simulate.

    Returns:
        Structured impact assessment metrics.
    """
    if quantity <= 0:
        raise ValueError("Simulation quantity must be greater than zero.")

    is_buy = side.upper() == "BUY"
    target_levels = depth_data.get("asks" if is_buy else "bids", [])

    if not target_levels:
        return {
            "side": side.upper(),
            "requested_quantity": quantity,
            "filled_quantity": 0,
            "unfilled_quantity": quantity,
            "expected_price": 0.0,
            "vwap": 0.0,
            "mid_price": 0.0,
            "slippage_pct": 0.0,
            "slippage_bps": 0.0,
            "levels_consumed": 0,
            "remaining_book_liquidity": 0,
            "ladder_fills": [],
            "status": "INSUFFICIENT_LIQUIDITY",
        }

    # Derive mid-price from top levels
    top_bid = depth_data.get("bids", [{}])[0].get("price", 0.0) if depth_data.get("bids") else 0.0
    top_ask = depth_data.get("asks", [{}])[0].get("price", 0.0) if depth_data.get("asks") else 0.0
    if top_bid > 0 and top_ask > 0:
        mid_price = round((top_bid + top_ask) / 2.0, 4)
    else:
        mid_price = target_levels[0]["price"]

    expected_price = target_levels[0]["price"]

    rem_qty = quantity
    total_cost = 0.0
    filled_qty = 0
    levels_consumed = 0
    ladder_fills = []

    for level in target_levels:
        lvl_price = level["price"]
        lvl_qty = level["quantity"]

        if rem_qty <= 0:
            break

        fill_qty = min(rem_qty, lvl_qty)
        cost = fill_qty * lvl_price
        total_cost += cost
        filled_qty += fill_qty
        rem_qty -= fill_qty
        levels_consumed += 1

        ladder_fills.append({
            "level": levels_consumed,
            "price": lvl_price,
            "filled_quantity": fill_qty,
            "level_initial_quantity": lvl_qty,
            "level_remaining_quantity": lvl_qty - fill_qty,
            "cumulative_cost": round(total_cost, 2),
        })

    vwap = round(total_cost / filled_qty, 4) if filled_qty > 0 else 0.0
    slippage_pct = round((abs(vwap - mid_price) / mid_price) * 100.0, 4) if mid_price > 0 else 0.0
    slippage_bps = round(slippage_pct * 100.0, 2)

    total_available_liquidity = sum(l["quantity"] for l in target_levels)
    remaining_liquidity = max(0, total_available_liquidity - filled_qty)

    return {
        "side": side.upper(),
        "requested_quantity": quantity,
        "filled_quantity": filled_qty,
        "unfilled_quantity": rem_qty,
        "expected_price": expected_price,
        "vwap": vwap,
        "mid_price": mid_price,
        "slippage_pct": slippage_pct,
        "slippage_bps": slippage_bps,
        "levels_consumed": levels_consumed,
        "remaining_liquidity": remaining_liquidity,
        "remaining_book_liquidity": remaining_liquidity,
        "ladder_fills": ladder_fills,
        "status": "FILLED" if rem_qty == 0 else "PARTIAL_FILL",
    }


def run_deterministic_experiment(
    seed: int = 42,
    instrument: str = "BTCUSDT",
    num_events: int = 50,
    arrival_rate: Union[int, float] = 25,
    price_spread_pct: float = 0.2,
    min_qty: int = 5,
    max_qty: int = 30,
    cancel_rate_pct: float = 20.0,
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a reproducible synthetic microstructure experiment using a deterministic random seed.

    Args:
        seed: Integer seed guaranteeing 100% reproducible order flow.
        instrument: Symbol to simulate (e.g. BTCUSDT, RELIANCE, TCS, AAPL).
        num_events: Total sequence length of synthetic market events.
        arrival_rate: Nominal orders per second parameter.
        price_spread_pct: Half-spread pricing dispersion factor.
        min_qty: Minimum random order quantity.
        max_qty: Maximum random order quantity.
        cancel_rate_pct: Percentage probability of generating a cancellation event.
        symbol: Optional alias for instrument.

    Returns:
        Dictionary containing the full event stream, timeline curves, and research report.
    """
    sym = (symbol or instrument).upper()
    rng = random.Random(seed)

    base_prices = {
        "BTCUSDT": 65000.0,
        "ETHUSDT": 3500.0,
        "RELIANCE": 1184.50,
        "TCS": 2506.90,
        "INFY": 1153.35,
        "AAPL": 185.00,
        "HDFCBANK": 694.05,
    }
    base_p = base_prices.get(sym, 1000.0)

    obs = EventObservatoryEngine(sym)
    active_order_ids: List[int] = []
    order_id_seq = 1

    # 1. Initialize Seed Book with 5 passive bids and 5 passive asks
    spread_step = max(0.05, round(base_p * (price_spread_pct / 100.0) / 4.0, 2))
    for i in range(1, 6):
        bid_p = round(base_p - (i * spread_step), 2)
        ask_p = round(base_p + (i * spread_step), 2)
        q_bid = rng.randint(10, 50)
        q_ask = rng.randint(10, 50)

        # Pre-seed Bids
        order_msg = NewOrderMsg.create(
            order_id=order_id_seq,
            client_id=1,
            symbol=sym,
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=bid_p,
            quantity=q_bid,
        )
        obs.process_order_with_event(order_msg)
        active_order_ids.append(order_id_seq)
        order_id_seq += 1

        # Pre-seed Asks
        order_msg = NewOrderMsg.create(
            order_id=order_id_seq,
            client_id=2,
            symbol=sym,
            side=Side.SELL,
            order_type=OrderType.LIMIT,
            price=ask_p,
            quantity=q_ask,
        )
        obs.process_order_with_event(order_msg)
        active_order_ids.append(order_id_seq)
        order_id_seq += 1

    # Clear pre-seed events so experiment timeline starts from Event 1
    obs.events.clear()
    obs._event_counter = 1

    # Timeline measurement & benchmark tracking
    bench_start = time.perf_counter_ns()
    submitted_orders_count = 0
    total_submitted_qty = 0
    total_executed_qty = 0
    total_cancelled_qty = 0
    liquidity_added_qty = 0
    liquidity_consumed_qty = 0
    spread_history: List[float] = []
    depth_history: List[int] = []

    timeline_points: List[Dict[str, Any]] = []

    # 2. Generate Deterministic Synthetic Events
    while len(obs.events) < num_events:
        action_roll = rng.random() * 100.0

        if action_roll < cancel_rate_pct and active_order_ids:
            # Deterministic cancellation
            idx = rng.randrange(len(active_order_ids))
            target_oid = active_order_ids.pop(idx)
            cancel_msg = CancelOrderMsg.create(order_id=target_oid, client_id=1, symbol=sym)
            ev = obs.cancel_order_with_event(cancel_msg)
            if ev:
                total_cancelled_qty += ev["quantity"]
                liquidity_consumed_qty += ev["quantity"]

        elif action_roll < 35.0:
            # Aggressive Crossing Market Order (Execution)
            side = Side.BUY if rng.random() < 0.5 else Side.SELL
            qty = rng.randint(min_qty, min(max_qty, 20))
            submitted_orders_count += 1
            total_submitted_qty += qty

            order_msg = NewOrderMsg.create(
                order_id=order_id_seq,
                client_id=10,
                symbol=sym,
                side=side,
                order_type=OrderType.MARKET,
                price=0.0,
                quantity=qty,
            )
            order_id_seq += 1
            evs = obs.process_order_with_event(order_msg)
            for ev in evs:
                if "TRADE" in ev["event_type"]:
                    total_executed_qty += ev["quantity"]
                    liquidity_consumed_qty += ev["quantity"]

        else:
            # Passive Resting Limit Order (Liquidity Provision)
            side = Side.BUY if rng.random() < 0.52 else Side.SELL
            bbo = _compute_bbo_summary(obs.book)
            mid = bbo["mid_price"] or base_p

            offset = rng.uniform(0.2, 1.8) * spread_step
            if side == Side.BUY:
                price = round((bbo["best_bid"] or (mid - spread_step)) + (offset * 0.4) - offset, 2)
            else:
                price = round((bbo["best_ask"] or (mid + spread_step)) - (offset * 0.4) + offset, 2)

            qty = rng.randint(min_qty, max_qty)
            submitted_orders_count += 1
            total_submitted_qty += qty

            order_msg = NewOrderMsg.create(
                order_id=order_id_seq,
                client_id=20,
                symbol=sym,
                side=side,
                order_type=OrderType.LIMIT,
                price=price,
                quantity=qty,
            )
            active_order_ids.append(order_id_seq)
            order_id_seq += 1
            evs = obs.process_order_with_event(order_msg)
            for ev in evs:
                if ev["event_type"] == "NEW_LIMIT":
                    liquidity_added_qty += ev["quantity"]
                elif "TRADE" in ev["event_type"]:
                    total_executed_qty += ev["quantity"]
                    liquidity_consumed_qty += ev["quantity"]

        # Track timeline after latest event
        if obs.events:
            last_ev = obs.events[-1]
            bbo_now = last_ev["bbo_after"]
            sp = bbo_now["spread"] if bbo_now["spread"] is not None else spread_step
            spread_history.append(sp)
            tot_depth = bbo_now["total_bid_depth"] + bbo_now["total_ask_depth"]
            depth_history.append(tot_depth)

            timeline_points.append({
                "event_id": last_ev["event_id"],
                "mid_price": bbo_now["mid_price"],
                "spread": sp,
                "imbalance_1": bbo_now["imbalance_1"],
                "imbalance_5": bbo_now["imbalance_depth"],
                "total_bid_depth": bbo_now["total_bid_depth"],
                "total_ask_depth": bbo_now["total_ask_depth"],
            })

    bench_elapsed_ns = max(1, time.perf_counter_ns() - bench_start)
    events_count = len(obs.events)

    # 3. Calculate Microstructure Research Metrics
    throughput_ops = round((events_count / (bench_elapsed_ns / 1_000_000_000.0)), 0)
    mean_latency_us = round((bench_elapsed_ns / events_count) / 1000.0, 2)

    fill_rate_pct = round((total_executed_qty / total_submitted_qty * 100.0), 2) if total_submitted_qty > 0 else 0.0

    sorted_spreads = sorted(spread_history) if spread_history else [0.0]
    min_spread = sorted_spreads[0]
    max_spread = sorted_spreads[-1]
    mean_spread = round(sum(sorted_spreads) / len(sorted_spreads), 4)
    median_spread = sorted_spreads[len(sorted_spreads) // 2]

    avg_depth = round(sum(depth_history) / len(depth_history), 1) if depth_history else 0
    max_depth = max(depth_history) if depth_history else 0

    # Calculate average execution slippage across recorded trades
    trade_events = [e for e in obs.events if "TRADE" in e["event_type"]]
    slippage_samples = []
    for t in trade_events:
        mid = t["bbo_before"]["mid_price"]
        if mid > 0:
            slip_bps = abs(t["price"] - mid) / mid * 10_000
            slippage_samples.append(slip_bps)
    avg_slippage_bps = round(sum(slippage_samples) / len(slippage_samples), 2) if slippage_samples else 0.0

    research_report = {
        "seed": seed,
        "instrument": sym,
        "total_events_processed": events_count,
        "total_orders_submitted": submitted_orders_count,
        "total_submitted_quantity": total_submitted_qty,
        "total_executed_quantity": total_executed_qty,
        "total_cancelled_quantity": total_cancelled_qty,
        "fill_rate_pct": fill_rate_pct,
        "average_execution_slippage_bps": avg_slippage_bps,
        "spread_distribution": {
            "min_spread": min_spread,
            "max_spread": max_spread,
            "mean_spread": mean_spread,
            "median_spread": median_spread,
        },
        "liquidity": {
            "total_liquidity_added": liquidity_added_qty,
            "total_liquidity_consumed": liquidity_consumed_qty,
            "net_liquidity_change": liquidity_added_qty - liquidity_consumed_qty,
            "average_displayed_depth": avg_depth,
            "max_displayed_depth": max_depth,
        },
        "measured_benchmark": {
            "elapsed_ms": round(bench_elapsed_ns / 1_000_000.0, 3),
            "throughput_events_per_sec": int(throughput_ops),
            "mean_latency_microseconds": mean_latency_us,
            "benchmark_methodology": "High-resolution monotonic timer measuring in-memory order-book processing and state transitions.",
        },
        "metric_explanations": {
            "fill_rate_pct": "Percentage of total requested shares successfully matched into trades.",
            "average_execution_slippage_bps": "Mean basis points (1 bp = 0.01%) paid above/below mid-price at time of execution.",
            "spread_distribution": "Distribution of gap between Best Bid and Best Ask rungs over the experiment.",
            "liquidity_added_vs_consumed": "Units provided by resting passive limit orders vs. swept by aggressive orders or cancellations.",
            "throughput_events_per_sec": "Real measured engine event processing throughput.",
        },
    }

    # Final order book snapshot for interactive price impact testing
    final_depth = _snapshot_depth(obs.book, depth=10)
    final_bbo = _compute_bbo_summary(obs.book)

    return {
        "status": "success",
        "parameters": {
            "seed": seed,
            "instrument": sym,
            "num_events": num_events,
            "arrival_rate": arrival_rate,
            "price_spread_pct": price_spread_pct,
            "cancel_rate_pct": cancel_rate_pct,
        },
        "events": obs.events,
        "timeline_series": timeline_points,
        "research_report": research_report,
        "final_book": {
            "bbo": final_bbo,
            "depth": final_depth,
        },
        "data_notice": "SYNTHETIC EXPERIMENT DATA — GENERATED BY DETERMINISTIC MATCHING ENGINE SIMULATION — NOT REAL-TIME MARKET ORDERS",
    }
