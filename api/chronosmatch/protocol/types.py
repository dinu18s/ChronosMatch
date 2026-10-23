"""Enumerations, constants, and fixed-point pricing conversions."""

from enum import IntEnum

PRICE_SCALE: int = 10_000
QTY_SCALE: int = 1


def price_to_fixed(price: float) -> int:
    """Converts a float price to fixed-point integer (scaled by 10,000)."""
    return int(round(price * PRICE_SCALE))


def fixed_to_price(fixed_price: int) -> float:
    """Converts a fixed-point integer to float price."""
    return fixed_price / PRICE_SCALE


class Side(IntEnum):
    """Trading side."""
    UNKNOWN = 0
    BUY = 1
    SELL = 2

    def opposite(self) -> "Side":
        if self == Side.BUY:
            return Side.SELL
        elif self == Side.SELL:
            return Side.BUY
        return Side.UNKNOWN


class OrderType(IntEnum):
    """Order type classification."""
    LIMIT = 1
    MARKET = 2
    STOP_LIMIT = 3


class TimeInForce(IntEnum):
    """Time in force policy."""
    GTC = 1  # Good 'Til Cancelled
    IOC = 2  # Immediate Or Cancel
    FOK = 3  # Fill Or Kill


class MsgType(IntEnum):
    """Binary Wire Protocol message types."""
    # Inbound Client Messages (0x01 - 0x0F)
    NEW_ORDER = 0x01
    CANCEL_ORDER = 0x02
    FLUSH_BOOK = 0x03

    # Outbound Engine Reports (0x10 - 0x1F)
    EXECUTION_REPORT = 0x10
    ORDER_ACCEPTED = 0x11
    ORDER_REJECTED = 0x12
    ORDER_CANCELLED = 0x13

    # Market Data Feeds (0x20 - 0x2F)
    BBO_UPDATE = 0x20
    DEPTH_UPDATE = 0x21
    TRADE_TICK = 0x22


class ExecType(IntEnum):
    """Execution report event type."""
    NEW = 1
    TRADE = 2
    CANCELLED = 3
    REJECTED = 4
    EXPIRED = 5


class MatchStatus(IntEnum):
    """Status of order fulfillment in execution report."""
    NONE = 0
    PARTIAL = 1
    FULL = 2


class RejectCode(IntEnum):
    """Reason codes for order rejection."""
    NONE = 0
    INVALID_PRICE = 1
    INVALID_QUANTITY = 2
    ORDER_NOT_FOUND = 3
    UNKNOWN_SYMBOL = 4
    IOC_NOT_FILLED = 5
    FOK_CANNOT_FILL = 6
    DUPLICATE_ORDER_ID = 7
