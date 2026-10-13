"""Real-time market data feed and dissemination."""

import time
from typing import Callable, Dict, List, Optional, Union

from chronosmatch.engine.book import OrderBook
from chronosmatch.protocol.messages import (
    BBOUpdateMsg,
    ExecutionReportMsg,
    TradeTickMsg,
    int_to_symbol,
    symbol_to_int,
)
from chronosmatch.protocol.types import ExecType, MsgType, fixed_to_price


class MarketDataFeed:
    """Disseminator for Top-of-Book (BBO), Level 2 Depth, and Trade Ticks."""

    def __init__(self) -> None:
        self._bbo_listeners: List[Callable[[BBOUpdateMsg], None]] = []
        self._trade_listeners: List[Callable[[TradeTickMsg], None]] = []
        self._trade_counter: int = 1

    def subscribe_bbo(self, callback: Callable[[BBOUpdateMsg], None]) -> None:
        """Register a callback for BBO top-of-book updates."""
        self._bbo_listeners.append(callback)

    def subscribe_trades(self, callback: Callable[[TradeTickMsg], None]) -> None:
        """Register a callback for public trade tick executions."""
        self._trade_listeners.append(callback)

    def publish_bbo(self, book: OrderBook) -> BBOUpdateMsg:
        """Generates and broadcasts BBO update for an order book."""
        bid, ask = book.get_bbo()
        bid_p, bid_q = bid if bid is not None else (0, 0)
        ask_p, ask_q = ask if ask is not None else (0, 0)

        msg = BBOUpdateMsg()
        msg.msg_type = MsgType.BBO_UPDATE
        msg.symbol_id = book.symbol_id
        msg.best_bid_price = bid_p
        msg.best_bid_qty = bid_q
        msg.best_ask_price = ask_p
        msg.best_ask_qty = ask_q
        msg.timestamp_ns = time.time_ns()

        for listener in self._bbo_listeners:
            listener(msg)

        return msg

    def publish_trade_from_exec(self, report: ExecutionReportMsg, taker_side: int) -> Optional[TradeTickMsg]:
        """Converts an engine trade ExecutionReport into a public TradeTickMsg."""
        if report.exec_type != ExecType.TRADE or report.matched_order_id == 0:
            return None

        trade = TradeTickMsg()
        trade.msg_type = MsgType.TRADE_TICK
        trade.side = taker_side
        trade.trade_id = self._trade_counter
        self._trade_counter += 1
        trade.maker_order_id = report.matched_order_id
        trade.taker_order_id = report.order_id
        trade.symbol_id = report.symbol_id
        trade.price = report.price
        trade.quantity = report.last_qty
        trade.timestamp_ns = report.timestamp_ns

        for listener in self._trade_listeners:
            listener(trade)

        return trade
