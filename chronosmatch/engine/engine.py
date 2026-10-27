"""Multi-symbol Matching Engine coordinator."""

import time
from typing import Dict, List, Optional, Union

from chronosmatch.engine.book import OrderBook
from chronosmatch.protocol.messages import (
    BBOUpdateMsg,
    CancelOrderMsg,
    ExecutionReportMsg,
    NewOrderMsg,
    symbol_to_int,
)
from chronosmatch.protocol.types import (
    ExecType,
    MatchStatus,
    MsgType,
    RejectCode,
    Side,
)


class MatchingEngine:
    """Core trading matching engine managing multiple instrument books."""

    def __init__(self) -> None:
        self._books: Dict[int, OrderBook] = {}

    def get_or_create_book(self, symbol: Union[str, int]) -> OrderBook:
        """Retrieves or registers an OrderBook for the given symbol."""
        sym_id = symbol_to_int(symbol) if isinstance(symbol, str) else symbol
        book = self._books.get(sym_id)
        if book is None:
            book = OrderBook(sym_id)
            self._books[sym_id] = book
        return book

    def get_book(self, symbol: Union[str, int]) -> Optional[OrderBook]:
        sym_id = symbol_to_int(symbol) if isinstance(symbol, str) else symbol
        return self._books.get(sym_id)

    def process_new_order(self, order_msg: NewOrderMsg) -> List[ExecutionReportMsg]:
        """Routes NewOrderMsg to target order book and executes."""
        book = self.get_or_create_book(order_msg.symbol_id)
        return book.process_order(order_msg)

    def process_cancel_order(self, cancel_msg: CancelOrderMsg) -> ExecutionReportMsg:
        """Routes CancelOrderMsg to target order book and cancels."""
        book = self._books.get(cancel_msg.symbol_id)
        if book is None:
            ts = cancel_msg.timestamp_ns if cancel_msg.timestamp_ns > 0 else time.time_ns()
            return ExecutionReportMsg.create(
                exec_id=0,
                order_id=cancel_msg.order_id,
                matched_order_id=0,
                symbol=cancel_msg.symbol_id,
                side=Side.UNKNOWN,
                exec_type=ExecType.REJECTED,
                match_status=MatchStatus.NONE,
                price_fixed=0,
                last_qty=0,
                leaves_qty=0,
                cum_qty=0,
                reject_code=RejectCode.UNKNOWN_SYMBOL,
                timestamp_ns=ts,
            )
        return book.cancel_order(cancel_msg)

    def get_bbo_msg(self, symbol: Union[str, int]) -> Optional[BBOUpdateMsg]:
        """Generates a binary BBOUpdateMsg for the given symbol."""
        sym_id = symbol_to_int(symbol) if isinstance(symbol, str) else symbol
        book = self._books.get(sym_id)
        if book is None:
            return None

        bid, ask = book.get_bbo()
        bid_p, bid_q = bid if bid else (0, 0)
        ask_p, ask_q = ask if ask else (0, 0)

        bbo = BBOUpdateMsg()
        bbo.msg_type = MsgType.BBO_UPDATE
        bbo.symbol_id = sym_id
        bbo.best_bid_price = bid_p
        bbo.best_bid_qty = bid_q
        bbo.best_ask_price = ask_p
        bbo.best_ask_qty = ask_q
        bbo.timestamp_ns = time.time_ns()
        return bbo
