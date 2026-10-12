"""Fixed-size binary message structures with zero-copy buffer casting."""

import ctypes
import struct
import time
from typing import Union

from chronosmatch.protocol.types import (
    ExecType,
    MatchStatus,
    MsgType,
    OrderType,
    RejectCode,
    Side,
    TimeInForce,
    fixed_to_price,
    price_to_fixed,
)


def symbol_to_int(symbol: str) -> int:
    """Encode an up-to-8 character ASCII symbol into a 64-bit unsigned integer."""
    raw = symbol.encode("ascii")[:8].ljust(8, b"\x00")
    return struct.unpack(">Q", raw)[0]


def int_to_symbol(val: int) -> str:
    """Decode a 64-bit unsigned integer into an ASCII symbol string."""
    raw = struct.pack(">Q", val)
    return raw.rstrip(b"\x00").decode("ascii", errors="replace")


class NewOrderMsg(ctypes.BigEndianStructure):
    """Zero-copy binary frame for inbound order submission (56 bytes)."""
    _pack_ = 8
    _fields_ = [
        ("msg_type", ctypes.c_uint8),       # MsgType.NEW_ORDER (0x01)
        ("side", ctypes.c_uint8),           # Side (1=BUY, 2=SELL)
        ("order_type", ctypes.c_uint8),     # OrderType (1=LMT, 2=MKT)
        ("tif", ctypes.c_uint8),            # TimeInForce (1=GTC, 2=IOC, 3=FOK)
        ("_pad", ctypes.c_uint32),          # 4 bytes padding for 8-byte alignment
        ("order_id", ctypes.c_uint64),      # Unique order identifier
        ("client_id", ctypes.c_uint64),     # Client / Participant identifier
        ("symbol_id", ctypes.c_uint64),     # ASCII packed 8-byte symbol
        ("price", ctypes.c_int64),          # Fixed-point price (scaled 10,000)
        ("quantity", ctypes.c_uint64),      # Order quantity
        ("timestamp_ns", ctypes.c_uint64),  # Nanoseconds epoch timestamp
    ]

    @classmethod
    def create(
        cls,
        order_id: int,
        client_id: int,
        symbol: Union[str, int],
        side: Side,
        order_type: OrderType,
        price: float,
        quantity: int,
        tif: TimeInForce = TimeInForce.GTC,
        timestamp_ns: int = 0,
    ) -> "NewOrderMsg":
        """Factory method creating an initialized NewOrderMsg structure."""
        sym_id = symbol_to_int(symbol) if isinstance(symbol, str) else symbol
        ts = timestamp_ns if timestamp_ns > 0 else time.time_ns()
        fixed_p = price_to_fixed(price) if order_type == OrderType.LIMIT else 0
        return cls(
            msg_type=MsgType.NEW_ORDER,
            side=int(side),
            order_type=int(order_type),
            tif=int(tif),
            _pad=0,
            order_id=order_id,
            client_id=client_id,
            symbol_id=sym_id,
            price=fixed_p,
            quantity=quantity,
            timestamp_ns=ts,
        )

    def __repr__(self) -> str:
        sym = int_to_symbol(self.symbol_id)
        side_name = Side(self.side).name if self.side in (1, 2) else str(self.side)
        ot_name = OrderType(self.order_type).name if self.order_type in (1, 2) else str(self.order_type)
        return (
            f"<NewOrderMsg id={self.order_id} client={self.client_id} sym={sym} "
            f"side={side_name} type={ot_name} price={fixed_to_price(self.price):.4f} "
            f"qty={self.quantity} ts={self.timestamp_ns}>"
        )


class CancelOrderMsg(ctypes.BigEndianStructure):
    """Zero-copy binary frame for order cancellation request (40 bytes)."""
    _pack_ = 8
    _fields_ = [
        ("msg_type", ctypes.c_uint8),       # MsgType.CANCEL_ORDER (0x02)
        ("_pad1", ctypes.c_uint8 * 7),      # 7 bytes alignment padding
        ("order_id", ctypes.c_uint64),      # Order to cancel
        ("client_id", ctypes.c_uint64),     # Client identifier
        ("symbol_id", ctypes.c_uint64),     # Target symbol
        ("timestamp_ns", ctypes.c_uint64),  # Request timestamp
    ]

    @classmethod
    def create(
        cls,
        order_id: int,
        client_id: int,
        symbol: Union[str, int],
        timestamp_ns: int = 0,
    ) -> "CancelOrderMsg":
        sym_id = symbol_to_int(symbol) if isinstance(symbol, str) else symbol
        ts = timestamp_ns if timestamp_ns > 0 else time.time_ns()
        pad = (ctypes.c_uint8 * 7)()
        return cls(
            msg_type=MsgType.CANCEL_ORDER,
            _pad1=pad,
            order_id=order_id,
            client_id=client_id,
            symbol_id=sym_id,
            timestamp_ns=ts,
        )

    def __repr__(self) -> str:
        sym = int_to_symbol(self.symbol_id)
        return f"<CancelOrderMsg id={self.order_id} client={self.client_id} sym={sym}>"


class ExecutionReportMsg(ctypes.BigEndianStructure):
    """Outbound binary execution and trade report (80 bytes)."""
    _pack_ = 8
    _fields_ = [
        ("msg_type", ctypes.c_uint8),         # MsgType.EXECUTION_REPORT (0x10)
        ("exec_type", ctypes.c_uint8),        # ExecType (NEW, TRADE, CANCELLED, etc.)
        ("side", ctypes.c_uint8),             # Side of the reported order
        ("match_status", ctypes.c_uint8),     # MatchStatus (NONE, PARTIAL, FULL)
        ("reject_code", ctypes.c_uint32),     # RejectCode enum value
        ("exec_id", ctypes.c_uint64),         # Monotonically increasing execution ID
        ("order_id", ctypes.c_uint64),        # Order ID
        ("matched_order_id", ctypes.c_uint64),# Counterparty order ID (0 if non-trade)
        ("symbol_id", ctypes.c_uint64),       # Symbol
        ("price", ctypes.c_int64),            # Execution price (fixed point)
        ("last_qty", ctypes.c_uint64),        # Traded quantity in this event
        ("leaves_qty", ctypes.c_uint64),      # Open quantity remaining in book
        ("cum_qty", ctypes.c_uint64),         # Total executed quantity to date
        ("timestamp_ns", ctypes.c_uint64),    # Engine timestamp
    ]

    @classmethod
    def create(
        cls,
        exec_id: int,
        order_id: int,
        matched_order_id: int,
        symbol: Union[str, int],
        side: Side,
        exec_type: ExecType,
        match_status: MatchStatus,
        price_fixed: int,
        last_qty: int,
        leaves_qty: int,
        cum_qty: int,
        reject_code: RejectCode = RejectCode.NONE,
        timestamp_ns: int = 0,
    ) -> "ExecutionReportMsg":
        sym_id = symbol_to_int(symbol) if isinstance(symbol, str) else symbol
        ts = timestamp_ns if timestamp_ns > 0 else time.time_ns()
        return cls(
            msg_type=MsgType.EXECUTION_REPORT,
            exec_type=int(exec_type),
            side=int(side),
            match_status=int(match_status),
            reject_code=int(reject_code),
            exec_id=exec_id,
            order_id=order_id,
            matched_order_id=matched_order_id,
            symbol_id=sym_id,
            price=price_fixed,
            last_qty=last_qty,
            leaves_qty=leaves_qty,
            cum_qty=cum_qty,
            timestamp_ns=ts,
        )

    def __repr__(self) -> str:
        sym = int_to_symbol(self.symbol_id)
        et = ExecType(self.exec_type).name if self.exec_type in ExecType._value2member_map_ else str(self.exec_type)
        return (
            f"<ExecutionReport id={self.exec_id} order={self.order_id} counter={self.matched_order_id} "
            f"type={et} sym={sym} price={fixed_to_price(self.price):.4f} "
            f"last_qty={self.last_qty} leaves={self.leaves_qty} cum={self.cum_qty}>"
        )


class BBOUpdateMsg(ctypes.BigEndianStructure):
    """Best Bid & Offer top-of-book market data frame (56 bytes)."""
    _pack_ = 8
    _fields_ = [
        ("msg_type", ctypes.c_uint8),         # MsgType.BBO_UPDATE (0x20)
        ("_pad", ctypes.c_uint8 * 7),         # 7 bytes alignment padding
        ("symbol_id", ctypes.c_uint64),       # Symbol
        ("best_bid_price", ctypes.c_int64),   # Highest buy price
        ("best_bid_qty", ctypes.c_uint64),    # Aggregated quantity at best bid
        ("best_ask_price", ctypes.c_int64),   # Lowest sell price
        ("best_ask_qty", ctypes.c_uint64),    # Aggregated quantity at best ask
        ("timestamp_ns", ctypes.c_uint64),    # Engine dissemination timestamp
    ]

    def __repr__(self) -> str:
        sym = int_to_symbol(self.symbol_id)
        bb = fixed_to_price(self.best_bid_price) if self.best_bid_price > 0 else 0.0
        ba = fixed_to_price(self.best_ask_price) if self.best_ask_price > 0 else 0.0
        return (
            f"<BBOUpdate sym={sym} Bid={bb:.4f}x{self.best_bid_qty} "
            f"Ask={ba:.4f}x{self.best_ask_qty} ts={self.timestamp_ns}>"
        )


class TradeTickMsg(ctypes.BigEndianStructure):
    """Public trade execution broadcast frame (64 bytes)."""
    _pack_ = 8
    _fields_ = [
        ("msg_type", ctypes.c_uint8),         # MsgType.TRADE_TICK (0x22)
        ("side", ctypes.c_uint8),             # Aggressive taker side
        ("_pad", ctypes.c_uint8 * 6),         # 6 bytes padding
        ("trade_id", ctypes.c_uint64),        # Unique trade ID
        ("maker_order_id", ctypes.c_uint64),  # Resting maker order
        ("taker_order_id", ctypes.c_uint64),  # Aggressive taker order
        ("symbol_id", ctypes.c_uint64),       # Symbol
        ("price", ctypes.c_int64),            # Fixed point executed price
        ("quantity", ctypes.c_uint64),        # Executed volume
        ("timestamp_ns", ctypes.c_uint64),    # Execution timestamp
    ]

    def __repr__(self) -> str:
        sym = int_to_symbol(self.symbol_id)
        return (
            f"<TradeTick id={self.trade_id} sym={sym} price={fixed_to_price(self.price):.4f} "
            f"qty={self.quantity} maker={self.maker_order_id} taker={self.taker_order_id}>"
        )


# Size constants for buffer bounds and ring buffer allocation
NEW_ORDER_MSG_SIZE: int = ctypes.sizeof(NewOrderMsg)
CANCEL_ORDER_MSG_SIZE: int = ctypes.sizeof(CancelOrderMsg)
EXECUTION_REPORT_MSG_SIZE: int = ctypes.sizeof(ExecutionReportMsg)
BBO_UPDATE_MSG_SIZE: int = ctypes.sizeof(BBOUpdateMsg)
TRADE_TICK_MSG_SIZE: int = ctypes.sizeof(TradeTickMsg)
MAX_MESSAGE_SIZE: int = max(
    NEW_ORDER_MSG_SIZE,
    CANCEL_ORDER_MSG_SIZE,
    EXECUTION_REPORT_MSG_SIZE,
    BBO_UPDATE_MSG_SIZE,
    TRADE_TICK_MSG_SIZE,
)
