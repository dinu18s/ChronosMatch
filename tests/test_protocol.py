"""Unit tests for binary wire protocol and zero-copy buffer casting."""

import ctypes
from chronosmatch.protocol import (
    Side,
    OrderType,
    TimeInForce,
    MsgType,
    ExecType,
    MatchStatus,
    NewOrderMsg,
    CancelOrderMsg,
    ExecutionReportMsg,
    symbol_to_int,
    int_to_symbol,
    price_to_fixed,
    fixed_to_price,
    NEW_ORDER_MSG_SIZE,
    CANCEL_ORDER_MSG_SIZE,
    EXECUTION_REPORT_MSG_SIZE,
)


def test_symbol_encoding_roundtrip():
    for sym in ["AAPL", "BTCUSDT", "GOOGL", "MSFT", "INFY"]:
        encoded = symbol_to_int(sym)
        assert isinstance(encoded, int)
        decoded = int_to_symbol(encoded)
        assert decoded == sym


def test_fixed_point_conversion():
    assert price_to_fixed(100.25) == 1_002_500
    assert fixed_to_price(1_002_500) == 100.25
    assert price_to_fixed(0.0001) == 1
    assert fixed_to_price(1) == 0.0001


def test_new_order_msg_creation_and_size():
    order = NewOrderMsg.create(
        order_id=101,
        client_id=1,
        symbol="AAPL",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        price=150.50,
        quantity=500,
        tif=TimeInForce.GTC,
        timestamp_ns=1_000_000_000,
    )

    assert ctypes.sizeof(order) == NEW_ORDER_MSG_SIZE
    assert order.msg_type == MsgType.NEW_ORDER
    assert order.side == Side.BUY
    assert order.order_id == 101
    assert order.client_id == 1
    assert int_to_symbol(order.symbol_id) == "AAPL"
    assert fixed_to_price(order.price) == 150.50
    assert order.quantity == 500


def test_zero_copy_buffer_mutation():
    """Verify that ctypes.from_buffer provides true zero-copy mutation over pre-allocated memory."""
    raw_buffer = bytearray(NEW_ORDER_MSG_SIZE * 2)

    # Map the first 56 bytes to NewOrderMsg without copy
    msg_view = NewOrderMsg.from_buffer(raw_buffer, 0)
    msg_view.msg_type = MsgType.NEW_ORDER
    msg_view.order_id = 9999
    msg_view.price = price_to_fixed(200.75)
    msg_view.quantity = 150

    # Read from raw buffer at offset 0
    second_view = NewOrderMsg.from_buffer(raw_buffer, 0)
    assert second_view.order_id == 9999
    assert second_view.price == price_to_fixed(200.75)
    assert second_view.quantity == 150

    # Modify through second view and check first view
    second_view.quantity = 250
    assert msg_view.quantity == 250


def test_cancel_order_msg():
    cancel = CancelOrderMsg.create(
        order_id=42,
        client_id=5,
        symbol="BTCUSDT",
        timestamp_ns=999_888_777,
    )
    assert ctypes.sizeof(cancel) == CANCEL_ORDER_MSG_SIZE
    assert cancel.msg_type == MsgType.CANCEL_ORDER
    assert cancel.order_id == 42
    assert cancel.client_id == 5
    assert int_to_symbol(cancel.symbol_id) == "BTCUSDT"


def test_execution_report_msg():
    report = ExecutionReportMsg.create(
        exec_id=1,
        order_id=101,
        matched_order_id=202,
        symbol="AAPL",
        side=Side.BUY,
        exec_type=ExecType.TRADE,
        match_status=MatchStatus.FULL,
        price_fixed=price_to_fixed(150.50),
        last_qty=500,
        leaves_qty=0,
        cum_qty=500,
    )
    assert ctypes.sizeof(report) == EXECUTION_REPORT_MSG_SIZE
    assert report.msg_type == MsgType.EXECUTION_REPORT
    assert report.exec_type == ExecType.TRADE
    assert report.match_status == MatchStatus.FULL
    assert report.last_qty == 500
    assert report.leaves_qty == 0
    assert report.cum_qty == 500
