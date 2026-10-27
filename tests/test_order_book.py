"""Comprehensive test suite for Limit Order Book and Matching Engine."""

import pytest
from chronosmatch.engine import MatchingEngine, OrderBook
from chronosmatch.protocol import (
    ExecType,
    MatchStatus,
    NewOrderMsg,
    OrderType,
    RejectCode,
    Side,
    TimeInForce,
    price_to_fixed,
)


@pytest.fixture
def book():
    return OrderBook("AAPL")


def test_resting_limit_orders(book):
    order1 = NewOrderMsg.create(
        order_id=1,
        client_id=10,
        symbol="AAPL",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        price=100.0,
        quantity=50,
    )
    reports = book.process_order(order1)
    assert len(reports) == 1
    assert reports[0].exec_type == ExecType.NEW
    assert reports[0].leaves_qty == 50

    bbo = book.get_bbo()
    assert bbo[0] == (price_to_fixed(100.0), 50)  # Best Bid
    assert bbo[1] is None  # No asks


def test_fifo_price_time_priority(book):
    # Place two bids at the same price (100.0)
    order1 = NewOrderMsg.create(
        order_id=1,
        client_id=10,
        symbol="AAPL",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        price=100.0,
        quantity=50,
    )
    order2 = NewOrderMsg.create(
        order_id=2,
        client_id=20,
        symbol="AAPL",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        price=100.0,
        quantity=30,
    )
    book.process_order(order1)
    book.process_order(order2)

    assert book.best_bid() == (price_to_fixed(100.0), 80)

    # Aggressive sell order for 60 units at 100.0
    sell_order = NewOrderMsg.create(
        order_id=3,
        client_id=30,
        symbol="AAPL",
        side=Side.SELL,
        order_type=OrderType.LIMIT,
        price=100.0,
        quantity=60,
    )
    reports = book.process_order(sell_order)

    # Should generate:
    # 1. Taker trade for 50 vs Order 1
    # 2. Maker trade for 50 on Order 1 (Order 1 FULLY FILLED)
    # 3. Taker trade for 10 vs Order 2
    # 4. Maker trade for 10 on Order 2 (Order 2 PARTIALLY FILLED: leaves 20)
    assert len(reports) == 4

    # Check maker reports
    maker_1_rep = [r for r in reports if r.order_id == 1][0]
    assert maker_1_rep.exec_type == ExecType.TRADE
    assert maker_1_rep.last_qty == 50
    assert maker_1_rep.leaves_qty == 0
    assert maker_1_rep.match_status == MatchStatus.FULL

    maker_2_rep = [r for r in reports if r.order_id == 2][0]
    assert maker_2_rep.exec_type == ExecType.TRADE
    assert maker_2_rep.last_qty == 10
    assert maker_2_rep.leaves_qty == 20
    assert maker_2_rep.match_status == MatchStatus.PARTIAL

    # Remaining in book: 20 units at 100.0 (from Order 2)
    assert book.best_bid() == (price_to_fixed(100.0), 20)


def test_price_priority(book):
    # Higher price bid has priority over lower price bid
    b1 = NewOrderMsg.create(
        order_id=1, client_id=1, symbol="AAPL", side=Side.BUY, order_type=OrderType.LIMIT, price=99.0, quantity=100
    )
    b2 = NewOrderMsg.create(
        order_id=2, client_id=2, symbol="AAPL", side=Side.BUY, order_type=OrderType.LIMIT, price=101.0, quantity=40
    )
    book.process_order(b1)
    book.process_order(b2)

    assert book.best_bid() == (price_to_fixed(101.0), 40)

    # Incoming sell at 98.0 for 30 units matches with b2 (price 101.0) first
    sell = NewOrderMsg.create(
        order_id=3, client_id=3, symbol="AAPL", side=Side.SELL, order_type=OrderType.LIMIT, price=98.0, quantity=30
    )
    reports = book.process_order(sell)
    assert len(reports) == 2
    taker_trade = reports[0]
    assert taker_trade.matched_order_id == 2
    assert taker_trade.price == price_to_fixed(101.0)
    assert taker_trade.last_qty == 30

    # Remaining at 101.0 is 10
    assert book.best_bid() == (price_to_fixed(101.0), 10)


def test_market_order_sweeping_depth(book):
    # Populate asks
    book.process_order(
        NewOrderMsg.create(order_id=1, client_id=1, symbol="AAPL", side=Side.SELL, order_type=OrderType.LIMIT, price=100.0, quantity=10)
    )
    book.process_order(
        NewOrderMsg.create(order_id=2, client_id=2, symbol="AAPL", side=Side.SELL, order_type=OrderType.LIMIT, price=101.0, quantity=20)
    )

    # Market BUY order for 25 units
    mkt = NewOrderMsg.create(
        order_id=3, client_id=3, symbol="AAPL", side=Side.BUY, order_type=OrderType.MARKET, price=0.0, quantity=25
    )
    reports = book.process_order(mkt)

    # Matches 10 at 100.0, 15 at 101.0
    taker_trades = [r for r in reports if r.order_id == 3 and r.exec_type == ExecType.TRADE]
    assert len(taker_trades) == 2
    assert taker_trades[0].price == price_to_fixed(100.0)
    assert taker_trades[0].last_qty == 10
    assert taker_trades[1].price == price_to_fixed(101.0)
    assert taker_trades[1].last_qty == 15

    # Ask remaining: 5 at 101.0
    assert book.best_ask() == (price_to_fixed(101.0), 5)


def test_ioc_order(book):
    # Only 10 units available at 50.0
    book.process_order(
        NewOrderMsg.create(order_id=1, client_id=1, symbol="AAPL", side=Side.SELL, order_type=OrderType.LIMIT, price=50.0, quantity=10)
    )

    # IOC order for 25 units at 50.0
    ioc = NewOrderMsg.create(
        order_id=2,
        client_id=2,
        symbol="AAPL",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        price=50.0,
        quantity=25,
        tif=TimeInForce.IOC,
    )
    reports = book.process_order(ioc)

    # Trades 10, then expires remaining 15
    trades = [r for r in reports if r.order_id == 2 and r.exec_type == ExecType.TRADE]
    assert len(trades) == 1
    assert trades[0].last_qty == 10

    expired = [r for r in reports if r.order_id == 2 and r.exec_type == ExecType.EXPIRED]
    assert len(expired) == 1
    assert expired[0].cum_qty == 10

    # Book should now have no bids resting
    assert book.best_bid() is None


def test_fok_order(book):
    book.process_order(
        NewOrderMsg.create(order_id=1, client_id=1, symbol="AAPL", side=Side.SELL, order_type=OrderType.LIMIT, price=50.0, quantity=10)
    )

    # FOK order for 20 units (only 10 available) -> should be rejected immediately
    fok = NewOrderMsg.create(
        order_id=2,
        client_id=2,
        symbol="AAPL",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        price=50.0,
        quantity=20,
        tif=TimeInForce.FOK,
    )
    reports = book.process_order(fok)
    assert len(reports) == 1
    assert reports[0].exec_type == ExecType.REJECTED
    assert reports[0].reject_code == RejectCode.FOK_CANNOT_FILL

    # Ask at 50.0 should remain intact
    assert book.best_ask() == (price_to_fixed(50.0), 10)


def test_order_cancellation(book):
    from chronosmatch.protocol import CancelOrderMsg

    order = NewOrderMsg.create(
        order_id=42, client_id=1, symbol="AAPL", side=Side.BUY, order_type=OrderType.LIMIT, price=105.0, quantity=100
    )
    book.process_order(order)
    assert book.best_bid() == (price_to_fixed(105.0), 100)

    cancel = CancelOrderMsg.create(order_id=42, client_id=1, symbol="AAPL")
    rep = book.cancel_order(cancel)
    assert rep.exec_type == ExecType.CANCELLED
    assert rep.order_id == 42
    assert book.best_bid() is None
    assert book.order_count == 0


def test_matching_engine_multi_symbol():
    engine = MatchingEngine()

    o_aapl = NewOrderMsg.create(order_id=1, client_id=1, symbol="AAPL", side=Side.BUY, order_type=OrderType.LIMIT, price=150.0, quantity=10)
    o_msft = NewOrderMsg.create(order_id=2, client_id=2, symbol="MSFT", side=Side.BUY, order_type=OrderType.LIMIT, price=300.0, quantity=20)

    rep_aapl = engine.process_new_order(o_aapl)
    rep_msft = engine.process_new_order(o_msft)

    assert rep_aapl[0].exec_type == ExecType.NEW
    assert rep_msft[0].exec_type == ExecType.NEW

    bbo_aapl = engine.get_bbo_msg("AAPL")
    bbo_msft = engine.get_bbo_msg("MSFT")

    assert bbo_aapl.best_bid_price == price_to_fixed(150.0)
    assert bbo_msft.best_bid_price == price_to_fixed(300.0)
