"""Unit tests for WriteAheadLog persistence and replay."""

import os
import tempfile
import pytest
from chronosmatch.persistence import WriteAheadLog
from chronosmatch.protocol import (
    NewOrderMsg,
    ExecutionReportMsg,
    Side,
    OrderType,
    ExecType,
    MatchStatus,
    MsgType,
    price_to_fixed,
    fixed_to_price,
)
from chronosmatch.engine import MatchingEngine


def test_wal_write_and_read():
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = os.path.join(tmpdir, "engine.wal")
        wal = WriteAheadLog(wal_path)

        # Append NewOrderMsg
        order = NewOrderMsg.create(
            order_id=1,
            client_id=10,
            symbol="BTCUSDT",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=60_000.0,
            quantity=2,
        )
        seq1 = wal.append(order)
        assert seq1 == 1

        # Append ExecutionReportMsg
        report = ExecutionReportMsg.create(
            exec_id=100,
            order_id=1,
            matched_order_id=0,
            symbol="BTCUSDT",
            side=Side.BUY,
            exec_type=ExecType.NEW,
            match_status=MatchStatus.NONE,
            price_fixed=price_to_fixed(60_000.0),
            last_qty=0,
            leaves_qty=2,
            cum_qty=0,
        )
        seq2 = wal.append(report)
        assert seq2 == 2

        wal.flush()
        wal.close()

        # Read back records
        records = list(WriteAheadLog.read_records(wal_path))
        assert len(records) == 2

        r1_seq, r1_type, r1_bytes = records[0]
        assert r1_seq == 1
        assert r1_type == MsgType.NEW_ORDER
        o_read = NewOrderMsg.from_buffer_copy(r1_bytes)
        assert o_read.order_id == 1
        assert o_read.quantity == 2
        assert fixed_to_price(o_read.price) == 60_000.0

        r2_seq, r2_type, r2_bytes = records[1]
        assert r2_seq == 2
        assert r2_type == MsgType.EXECUTION_REPORT
        rep_read = ExecutionReportMsg.from_buffer_copy(r2_bytes)
        assert rep_read.exec_id == 100
        assert rep_read.order_id == 1


def test_wal_replay_to_engine():
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = os.path.join(tmpdir, "trade_session.wal")
        wal = WriteAheadLog(wal_path)

        # Place resting orders in original engine
        engine = MatchingEngine()
        o1 = NewOrderMsg.create(order_id=1, client_id=1, symbol="AAPL", side=Side.BUY, order_type=OrderType.LIMIT, price=150.0, quantity=100)
        o2 = NewOrderMsg.create(order_id=2, client_id=2, symbol="AAPL", side=Side.SELL, order_type=OrderType.LIMIT, price=155.0, quantity=200)

        wal.append(o1)
        wal.append(o2)
        engine.process_new_order(o1)
        engine.process_new_order(o2)

        wal.flush()
        wal.close()

        # Recover into a fresh engine via replay
        recovered_engine = MatchingEngine()
        for seq, msg_type, payload in WriteAheadLog.read_records(wal_path):
            if msg_type == MsgType.NEW_ORDER:
                recovered_order = NewOrderMsg.from_buffer_copy(payload)
                recovered_engine.process_new_order(recovered_order)

        # Verify state was restored identically
        orig_book = engine.get_book("AAPL")
        rec_book = recovered_engine.get_book("AAPL")

        assert rec_book.order_count == orig_book.order_count
        assert rec_book.best_bid() == orig_book.best_bid()
        assert rec_book.best_ask() == orig_book.best_ask()
