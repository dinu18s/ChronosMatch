"""Order and PriceLevel data structures optimized for low overhead and O(1) ops."""

from typing import Optional
from chronosmatch.protocol.types import Side, TimeInForce


class OrderNode:
    """Intrusive doubly-linked list node representing an active resting order."""

    __slots__ = (
        "order_id",
        "client_id",
        "side",
        "price",
        "quantity",
        "leaves_qty",
        "cum_qty",
        "tif",
        "timestamp_ns",
        "price_level",
        "prev",
        "next",
    )

    def __init__(
        self,
        order_id: int,
        client_id: int,
        side: Side,
        price: int,
        quantity: int,
        tif: TimeInForce = TimeInForce.GTC,
        timestamp_ns: int = 0,
    ) -> None:
        self.order_id: int = order_id
        self.client_id: int = client_id
        self.side: Side = side
        self.price: int = price
        self.quantity: int = quantity
        self.leaves_qty: int = quantity
        self.cum_qty: int = 0
        self.tif: TimeInForce = tif
        self.timestamp_ns: int = timestamp_ns
        self.price_level: Optional["PriceLevel"] = None
        self.prev: Optional["OrderNode"] = None
        self.next: Optional["OrderNode"] = None

    def __repr__(self) -> str:
        return (
            f"OrderNode(id={self.order_id}, side={self.side.name}, price={self.price}, "
            f"leaves={self.leaves_qty}/{self.quantity})"
        )


class PriceLevel:
    """Maintains a FIFO queue of resting orders at a discrete price level."""

    __slots__ = (
        "price",
        "total_volume",
        "order_count",
        "head",
        "tail",
    )

    def __init__(self, price: int) -> None:
        self.price: int = price
        self.total_volume: int = 0
        self.order_count: int = 0
        self.head: Optional[OrderNode] = None
        self.tail: Optional[OrderNode] = None

    def append(self, order: OrderNode) -> None:
        """Appends an order to the tail of the FIFO queue in O(1)."""
        order.price_level = self
        order.prev = self.tail
        order.next = None

        if self.tail is not None:
            self.tail.next = order
        else:
            self.head = order

        self.tail = order
        self.total_volume += order.leaves_qty
        self.order_count += 1

    def remove(self, order: OrderNode) -> None:
        """Removes an order node from the queue in O(1)."""
        if order.prev is not None:
            order.prev.next = order.next
        else:
            self.head = order.next

        if order.next is not None:
            order.next.prev = order.prev
        else:
            self.tail = order.prev

        self.total_volume -= order.leaves_qty
        self.order_count -= 1
        order.prev = None
        order.next = None
        order.price_level = None

    def is_empty(self) -> bool:
        """Returns True if this price level contains no orders."""
        return self.head is None or self.order_count == 0

    def __repr__(self) -> str:
        return f"PriceLevel(price={self.price}, volume={self.total_volume}, orders={self.order_count})"
