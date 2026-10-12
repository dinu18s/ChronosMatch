"""Unit tests for SharedRingBuffer."""

import gc
import uuid
import pytest
from chronosmatch.ipc import SharedRingBuffer
from chronosmatch.protocol import (
    NewOrderMsg,
    Side,
    OrderType,
    price_to_fixed,
)


@pytest.fixture
def ring_name():
    return f"cm_test_ring_{uuid.uuid4().hex[:8]}"


def test_ring_buffer_basic_rw(ring_name):
    ring = SharedRingBuffer(name=ring_name, capacity=8, slot_size=128, create=True)
    try:
        assert ring.is_empty()
        assert not ring.is_full()
        assert ring.size() == 0

        # Acquire slot and write NewOrderMsg directly into shared memory
        slot = ring.acquire_write_slot()
        assert slot is not None

        # Zero-copy cast directly over slot memoryview
        order_view = NewOrderMsg.from_buffer(slot, 0)
        order_view.order_id = 12345
        order_view.price = price_to_fixed(99.50)
        order_view.quantity = 100
        order_view.side = Side.BUY
        order_view.order_type = OrderType.LIMIT

        ring.commit_write()

        assert not ring.is_empty()
        assert ring.size() == 1

        # Read slot
        read_slot = ring.peek_read_slot()
        assert read_slot is not None

        read_order = NewOrderMsg.from_buffer(read_slot, 0)
        assert read_order.order_id == 12345
        assert read_order.price == price_to_fixed(99.50)
        assert read_order.quantity == 100
        assert read_order.side == Side.BUY

        ring.advance_read()
        assert ring.is_empty()
        assert ring.size() == 0

        del slot, order_view, read_slot, read_order
        gc.collect()
    finally:
        ring.close()


def test_ring_buffer_full_and_wraparound(ring_name):
    cap = 4
    ring = SharedRingBuffer(name=ring_name, capacity=cap, slot_size=64, create=True)
    try:
        # Fill buffer to capacity
        for i in range(cap):
            slot = ring.acquire_write_slot()
            assert slot is not None
            order = NewOrderMsg.from_buffer(slot, 0)
            order.order_id = i + 1
            ring.commit_write()
            del slot, order

        gc.collect()
        assert ring.is_full()
        assert ring.acquire_write_slot() is None

        # Consume 2 slots
        for expected_id in [1, 2]:
            slot = ring.peek_read_slot()
            assert slot is not None
            order = NewOrderMsg.from_buffer(slot, 0)
            assert order.order_id == expected_id
            ring.advance_read()
            del slot, order

        gc.collect()
        assert not ring.is_full()
        assert ring.size() == 2

        # Write 2 more (causes wrap-around of indices)
        for i in [5, 6]:
            slot = ring.acquire_write_slot()
            assert slot is not None
            order = NewOrderMsg.from_buffer(slot, 0)
            order.order_id = i
            ring.commit_write()
            del slot, order

        gc.collect()
        assert ring.size() == 4
        assert ring.is_full()

        # Consume remaining 4 in FIFO order
        for expected_id in [3, 4, 5, 6]:
            slot = ring.peek_read_slot()
            assert slot is not None
            order = NewOrderMsg.from_buffer(slot, 0)
            assert order.order_id == expected_id
            ring.advance_read()
            del slot, order

        gc.collect()
        assert ring.is_empty()
    finally:
        ring.close()


def test_multi_handle_shared_memory(ring_name):
    producer = SharedRingBuffer(name=ring_name, capacity=16, slot_size=128, create=True)
    consumer = SharedRingBuffer(name=ring_name, capacity=16, slot_size=128, create=False)
    try:
        slot = producer.acquire_write_slot()
        order = NewOrderMsg.from_buffer(slot, 0)
        order.order_id = 8888
        producer.commit_write()
        del slot, order
        gc.collect()

        assert consumer.size() == 1
        c_slot = consumer.peek_read_slot()
        c_order = NewOrderMsg.from_buffer(c_slot, 0)
        assert c_order.order_id == 8888
        consumer.advance_read()
        del c_slot, c_order
        gc.collect()

        assert producer.is_empty()
    finally:
        consumer.close()
        producer.close()
