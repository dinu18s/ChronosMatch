"""Limit Order Book with strict Price-Time priority (FIFO) and O(1) operations."""

import bisect
import time
from typing import Dict, List, Optional, Tuple, Union

from chronosmatch.engine.order import OrderNode, PriceLevel
from chronosmatch.protocol.messages import (
    CancelOrderMsg,
    ExecutionReportMsg,
    NewOrderMsg,
    int_to_symbol,
    symbol_to_int,
)
from chronosmatch.protocol.types import (
    ExecType,
    MatchStatus,
    OrderType,
    RejectCode,
    Side,
    TimeInForce,
    fixed_to_price,
)


class OrderBook:
    """Ultra-low latency limit order book implementing price-time priority matching."""

    __slots__ = (
        "symbol_id",
        "symbol_name",
        "_bid_levels",
        "_ask_levels",
        "_bid_prices",
        "_ask_prices",
        "_orders",
        "_next_exec_id",
        "_next_trade_id",
    )

    def __init__(self, symbol: Union[str, int]) -> None:
        if isinstance(symbol, str):
            self.symbol_id: int = symbol_to_int(symbol)
            self.symbol_name: str = symbol
        else:
            self.symbol_id = symbol
            self.symbol_name = int_to_symbol(symbol)

        # Mapping price -> PriceLevel
        self._bid_levels: Dict[int, PriceLevel] = {}
        self._ask_levels: Dict[int, PriceLevel] = {}

        # Sorted lists of unique prices (ascending order)
        # Best bid is at _bid_prices[-1] (highest price)
        # Best ask is at _ask_prices[0] (lowest price)
        self._bid_prices: List[int] = []
        self._ask_prices: List[int] = []

        # Order ID index for O(1) cancellations and updates
        self._orders: Dict[int, OrderNode] = {}

        self._next_exec_id: int = 1
        self._next_trade_id: int = 1

    @property
    def order_count(self) -> int:
        return len(self._orders)

    def best_bid(self) -> Optional[Tuple[int, int]]:
        """Returns (price, aggregated_volume) for top-of-book bid, or None."""
        if not self._bid_prices:
            return None
        price = self._bid_prices[-1]
        return price, self._bid_levels[price].total_volume

    def best_ask(self) -> Optional[Tuple[int, int]]:
        """Returns (price, aggregated_volume) for top-of-book ask, or None."""
        if not self._ask_prices:
            return None
        price = self._ask_prices[0]
        return price, self._ask_levels[price].total_volume

    def get_bbo(self) -> Tuple[Optional[Tuple[int, int]], Optional[Tuple[int, int]]]:
        """Returns (best_bid, best_ask) tuples with fixed-point prices and quantities."""
        return self.best_bid(), self.best_ask()

    def get_l2_depth(
        self, depth: int = 10
    ) -> Tuple[List[Tuple[float, int]], List[Tuple[float, int]]]:
        """Returns formatted L2 book depth (bids, asks) with prices as floats."""
        bids: List[Tuple[float, int]] = []
        for p in reversed(self._bid_prices[-depth:]):
            bids.append((fixed_to_price(p), self._bid_levels[p].total_volume))

        asks: List[Tuple[float, int]] = []
        for p in self._ask_prices[:depth]:
            asks.append((fixed_to_price(p), self._ask_levels[p].total_volume))

        return bids, asks

    def process_order(self, order_msg: NewOrderMsg) -> List[ExecutionReportMsg]:
        """Processes an incoming NewOrderMsg and executes matching logic."""
        side = Side(order_msg.side)
        order_type = OrderType(order_msg.order_type)
        tif = TimeInForce(order_msg.tif)
        price = order_msg.price
        qty = order_msg.quantity
        order_id = order_msg.order_id
        ts = order_msg.timestamp_ns if order_msg.timestamp_ns > 0 else time.time_ns()

        reports: List[ExecutionReportMsg] = []

        # Validation
        if qty <= 0:
            reports.append(self._make_reject(order_msg, RejectCode.INVALID_QUANTITY, ts))
            return reports

        if order_type == OrderType.LIMIT and price <= 0:
            reports.append(self._make_reject(order_msg, RejectCode.INVALID_PRICE, ts))
            return reports

        if order_id in self._orders:
            reports.append(self._make_reject(order_msg, RejectCode.DUPLICATE_ORDER_ID, ts))
            return reports

        # Check FOK fillability upfront
        if tif == TimeInForce.FOK:
            if not self._can_fill_fok(side, order_type, price, qty):
                reports.append(self._make_reject(order_msg, RejectCode.FOK_CANNOT_FILL, ts))
                return reports

        # Execute matching against resting orders
        leaves_qty = qty
        cum_qty = 0

        if side == Side.BUY:
            leaves_qty, cum_qty = self._match_buy(
                order_id=order_id,
                order_type=order_type,
                limit_price=price,
                leaves_qty=leaves_qty,
                cum_qty=cum_qty,
                ts=ts,
                reports=reports,
            )
        else:
            leaves_qty, cum_qty = self._match_sell(
                order_id=order_id,
                order_type=order_type,
                limit_price=price,
                leaves_qty=leaves_qty,
                cum_qty=cum_qty,
                ts=ts,
                reports=reports,
            )

        # Handle remaining quantity
        if leaves_qty > 0:
            if tif in (TimeInForce.IOC, TimeInForce.FOK) or order_type == OrderType.MARKET:
                # Expire unexecuted remainder
                reports.append(
                    ExecutionReportMsg.create(
                        exec_id=self._next_exec_id,
                        order_id=order_id,
                        matched_order_id=0,
                        symbol=self.symbol_id,
                        side=side,
                        exec_type=ExecType.EXPIRED,
                        match_status=MatchStatus.FULL if cum_qty == qty else (
                            MatchStatus.PARTIAL if cum_qty > 0 else MatchStatus.NONE
                        ),
                        price_fixed=price,
                        last_qty=0,
                        leaves_qty=0,
                        cum_qty=cum_qty,
                        timestamp_ns=ts,
                    )
                )
                self._next_exec_id += 1
            else:
                # Rest in book (GTC LIMIT order)
                node = OrderNode(
                    order_id=order_id,
                    client_id=order_msg.client_id,
                    side=side,
                    price=price,
                    quantity=qty,
                    tif=tif,
                    timestamp_ns=ts,
                )
                node.leaves_qty = leaves_qty
                node.cum_qty = cum_qty

                self._orders[order_id] = node
                self._insert_to_book(node)

                # Acceptance report if not fully matched
                match_stat = MatchStatus.NONE if cum_qty == 0 else MatchStatus.PARTIAL
                reports.append(
                    ExecutionReportMsg.create(
                        exec_id=self._next_exec_id,
                        order_id=order_id,
                        matched_order_id=0,
                        symbol=self.symbol_id,
                        side=side,
                        exec_type=ExecType.NEW,
                        match_status=match_stat,
                        price_fixed=price,
                        last_qty=0,
                        leaves_qty=leaves_qty,
                        cum_qty=cum_qty,
                        timestamp_ns=ts,
                    )
                )
                self._next_exec_id += 1

        return reports

    def cancel_order(self, cancel_msg: CancelOrderMsg) -> ExecutionReportMsg:
        """Cancels a resting order in O(1) time."""
        order_id = cancel_msg.order_id
        ts = cancel_msg.timestamp_ns if cancel_msg.timestamp_ns > 0 else time.time_ns()

        node = self._orders.get(order_id)
        if node is None:
            report = ExecutionReportMsg.create(
                exec_id=self._next_exec_id,
                order_id=order_id,
                matched_order_id=0,
                symbol=self.symbol_id,
                side=Side.UNKNOWN,
                exec_type=ExecType.REJECTED,
                match_status=MatchStatus.NONE,
                price_fixed=0,
                last_qty=0,
                leaves_qty=0,
                cum_qty=0,
                reject_code=RejectCode.ORDER_NOT_FOUND,
                timestamp_ns=ts,
            )
            self._next_exec_id += 1
            return report

        # Remove from book and index
        self._remove_from_book(node)
        del self._orders[order_id]

        report = ExecutionReportMsg.create(
            exec_id=self._next_exec_id,
            order_id=order_id,
            matched_order_id=0,
            symbol=self.symbol_id,
            side=node.side,
            exec_type=ExecType.CANCELLED,
            match_status=MatchStatus.FULL if node.cum_qty == node.quantity else MatchStatus.PARTIAL,
            price_fixed=node.price,
            last_qty=0,
            leaves_qty=0,
            cum_qty=node.cum_qty,
            timestamp_ns=ts,
        )
        self._next_exec_id += 1
        return report

    def _match_buy(
        self,
        order_id: int,
        order_type: OrderType,
        limit_price: int,
        leaves_qty: int,
        cum_qty: int,
        ts: int,
        reports: List[ExecutionReportMsg],
    ) -> Tuple[int, int]:
        """Matches a BUY order against the ask ladder (ascending)."""
        while leaves_qty > 0 and self._ask_prices:
            best_ask_price = self._ask_prices[0]
            if order_type == OrderType.LIMIT and limit_price < best_ask_price:
                break  # No more crossed prices

            level = self._ask_levels[best_ask_price]
            while leaves_qty > 0 and level.head is not None:
                maker_node = level.head
                match_qty = min(leaves_qty, maker_node.leaves_qty)

                leaves_qty -= match_qty
                cum_qty += match_qty
                maker_node.leaves_qty -= match_qty
                maker_node.cum_qty += match_qty
                level.total_volume -= match_qty

                # Trade report for taker (incoming BUY order)
                taker_status = MatchStatus.FULL if leaves_qty == 0 else MatchStatus.PARTIAL
                reports.append(
                    ExecutionReportMsg.create(
                        exec_id=self._next_exec_id,
                        order_id=order_id,
                        matched_order_id=maker_node.order_id,
                        symbol=self.symbol_id,
                        side=Side.BUY,
                        exec_type=ExecType.TRADE,
                        match_status=taker_status,
                        price_fixed=best_ask_price,
                        last_qty=match_qty,
                        leaves_qty=leaves_qty,
                        cum_qty=cum_qty,
                        timestamp_ns=ts,
                    )
                )
                self._next_exec_id += 1

                # Trade report for maker (resting SELL order)
                maker_status = MatchStatus.FULL if maker_node.leaves_qty == 0 else MatchStatus.PARTIAL
                reports.append(
                    ExecutionReportMsg.create(
                        exec_id=self._next_exec_id,
                        order_id=maker_node.order_id,
                        matched_order_id=order_id,
                        symbol=self.symbol_id,
                        side=Side.SELL,
                        exec_type=ExecType.TRADE,
                        match_status=maker_status,
                        price_fixed=best_ask_price,
                        last_qty=match_qty,
                        leaves_qty=maker_node.leaves_qty,
                        cum_qty=maker_node.cum_qty,
                        timestamp_ns=ts,
                    )
                )
                self._next_exec_id += 1
                self._next_trade_id += 1

                # If resting order is filled, remove it
                if maker_node.leaves_qty == 0:
                    level.remove(maker_node)
                    del self._orders[maker_node.order_id]

            if level.is_empty():
                del self._ask_levels[best_ask_price]
                del self._ask_prices[0]

        return leaves_qty, cum_qty

    def _match_sell(
        self,
        order_id: int,
        order_type: OrderType,
        limit_price: int,
        leaves_qty: int,
        cum_qty: int,
        ts: int,
        reports: List[ExecutionReportMsg],
    ) -> Tuple[int, int]:
        """Matches a SELL order against the bid ladder (descending: _bid_prices[-1])."""
        while leaves_qty > 0 and self._bid_prices:
            best_bid_price = self._bid_prices[-1]
            if order_type == OrderType.LIMIT and limit_price > best_bid_price:
                break

            level = self._bid_levels[best_bid_price]
            while leaves_qty > 0 and level.head is not None:
                maker_node = level.head
                match_qty = min(leaves_qty, maker_node.leaves_qty)

                leaves_qty -= match_qty
                cum_qty += match_qty
                maker_node.leaves_qty -= match_qty
                maker_node.cum_qty += match_qty
                level.total_volume -= match_qty

                # Trade report for taker (incoming SELL order)
                taker_status = MatchStatus.FULL if leaves_qty == 0 else MatchStatus.PARTIAL
                reports.append(
                    ExecutionReportMsg.create(
                        exec_id=self._next_exec_id,
                        order_id=order_id,
                        matched_order_id=maker_node.order_id,
                        symbol=self.symbol_id,
                        side=Side.SELL,
                        exec_type=ExecType.TRADE,
                        match_status=taker_status,
                        price_fixed=best_bid_price,
                        last_qty=match_qty,
                        leaves_qty=leaves_qty,
                        cum_qty=cum_qty,
                        timestamp_ns=ts,
                    )
                )
                self._next_exec_id += 1

                # Trade report for maker (resting BUY order)
                maker_status = MatchStatus.FULL if maker_node.leaves_qty == 0 else MatchStatus.PARTIAL
                reports.append(
                    ExecutionReportMsg.create(
                        exec_id=self._next_exec_id,
                        order_id=maker_node.order_id,
                        matched_order_id=order_id,
                        symbol=self.symbol_id,
                        side=Side.BUY,
                        exec_type=ExecType.TRADE,
                        match_status=maker_status,
                        price_fixed=best_bid_price,
                        last_qty=match_qty,
                        leaves_qty=maker_node.leaves_qty,
                        cum_qty=maker_node.cum_qty,
                        timestamp_ns=ts,
                    )
                )
                self._next_exec_id += 1
                self._next_trade_id += 1

                if maker_node.leaves_qty == 0:
                    level.remove(maker_node)
                    del self._orders[maker_node.order_id]

            if level.is_empty():
                del self._bid_levels[best_bid_price]
                del self._bid_prices[-1]

        return leaves_qty, cum_qty

    def _insert_to_book(self, node: OrderNode) -> None:
        """Inserts a resting order into the price ladder."""
        if node.side == Side.BUY:
            level = self._bid_levels.get(node.price)
            if level is None:
                level = PriceLevel(node.price)
                self._bid_levels[node.price] = level
                bisect.insort_left(self._bid_prices, node.price)
            level.append(node)
        else:
            level = self._ask_levels.get(node.price)
            if level is None:
                level = PriceLevel(node.price)
                self._ask_levels[node.price] = level
                bisect.insort_left(self._ask_prices, node.price)
            level.append(node)

    def _remove_from_book(self, node: OrderNode) -> None:
        """Removes a resting order from its price level and clears empty levels."""
        level = node.price_level
        if level is not None:
            level.remove(node)
            if level.is_empty():
                if node.side == Side.BUY:
                    del self._bid_levels[level.price]
                    idx = bisect.bisect_left(self._bid_prices, level.price)
                    if idx < len(self._bid_prices) and self._bid_prices[idx] == level.price:
                        del self._bid_prices[idx]
                else:
                    del self._ask_levels[level.price]
                    idx = bisect.bisect_left(self._ask_prices, level.price)
                    if idx < len(self._ask_prices) and self._ask_prices[idx] == level.price:
                        del self._ask_prices[idx]

    def _can_fill_fok(
        self, side: Side, order_type: OrderType, limit_price: int, target_qty: int
    ) -> bool:
        """Determines if a FOK order can be filled in its entirety against current depth."""
        available_qty = 0
        if side == Side.BUY:
            for p in self._ask_prices:
                if order_type == OrderType.LIMIT and limit_price < p:
                    break
                available_qty += self._ask_levels[p].total_volume
                if available_qty >= target_qty:
                    return True
        else:
            for p in reversed(self._bid_prices):
                if order_type == OrderType.LIMIT and limit_price > p:
                    break
                available_qty += self._bid_levels[p].total_volume
                if available_qty >= target_qty:
                    return True
        return available_qty >= target_qty

    def _make_reject(
        self, order_msg: NewOrderMsg, code: RejectCode, ts: int
    ) -> ExecutionReportMsg:
        report = ExecutionReportMsg.create(
            exec_id=self._next_exec_id,
            order_id=order_msg.order_id,
            matched_order_id=0,
            symbol=self.symbol_id,
            side=Side(order_msg.side),
            exec_type=ExecType.REJECTED,
            match_status=MatchStatus.NONE,
            price_fixed=order_msg.price,
            last_qty=0,
            leaves_qty=0,
            cum_qty=0,
            reject_code=code,
            timestamp_ns=ts,
        )
        self._next_exec_id += 1
        return report
