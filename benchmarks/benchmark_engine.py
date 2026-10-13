import gc
import os
from pathlib import Path
import statistics
import sys
import time
from typing import List

# Ensure src is in sys.path when running script directly from command line
ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from chronosmatch.engine import MatchingEngine
from chronosmatch.protocol import (
    CancelOrderMsg,
    NewOrderMsg,
    OrderType,
    Side,
    symbol_to_int,
)


def run_benchmark(num_orders: int = 100_000):
    print("=" * 70)
    print("  ChronosMatch: High-Frequency Trading Engine Microbenchmark")
    print("=" * 70)
    print(f"Total Test Iterations : {num_orders:,} orders per test")
    print(f"Python Runtime         : CPython (Zero-Copy Buffer & Struct Opts)")
    print("-" * 70)

    engine = MatchingEngine()
    sym_id = symbol_to_int("AAPL")

    # -------------------------------------------------------------
    # 1. Benchmark Resting Limit Orders (Book Building)
    # -------------------------------------------------------------
    gc.disable()
    latencies_ns: List[int] = [0] * num_orders

    # Pre-generate messages to isolate pure engine matching time
    orders = [
        NewOrderMsg.create(
            order_id=i + 1,
            client_id=1,
            symbol=sym_id,
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=100.0 + (i % 500) * 0.01,
            quantity=10,
        )
        for i in range(num_orders)
    ]

    t_start = time.perf_counter()
    for i in range(num_orders):
        t0 = time.perf_counter_ns()
        engine.process_new_order(orders[i])
        t1 = time.perf_counter_ns()
        latencies_ns[i] = t1 - t0
    t_end = time.perf_counter()
    gc.enable()

    total_time = t_end - t_start
    throughput = num_orders / total_time
    latencies_us = [x / 1_000.0 for x in latencies_ns]
    latencies_us.sort()

    print("\n>>> TEST 1: Resting Limit Orders (Book Building)")
    print(f"Throughput       : {throughput:,.0f} orders/sec")
    print(f"Total Duration   : {total_time:.4f} s")
    print(f"Mean Latency     : {statistics.mean(latencies_us):.2f} us")
    print(f"p50 (Median)     : {latencies_us[int(num_orders * 0.50)]:.2f} us")
    print(f"p90 Latency      : {latencies_us[int(num_orders * 0.90)]:.2f} us")
    print(f"p99 Latency      : {latencies_us[int(num_orders * 0.99)]:.2f} us")
    print(f"p99.9 Latency    : {latencies_us[int(num_orders * 0.999)]:.2f} us")
    print(f"Max Latency      : {latencies_us[-1]:.2f} us")

    # -------------------------------------------------------------
    # 2. Benchmark Aggressive Crossing Orders (Execution Matching)
    # -------------------------------------------------------------
    gc.disable()
    match_latencies_ns: List[int] = [0] * num_orders

    # Aggressive SELL orders that immediately cross and execute
    crossing_orders = [
        NewOrderMsg.create(
            order_id=num_orders + i + 1,
            client_id=2,
            symbol=sym_id,
            side=Side.SELL,
            order_type=OrderType.LIMIT,
            price=100.0 + (i % 500) * 0.01,
            quantity=10,
        )
        for i in range(num_orders)
    ]

    t_start = time.perf_counter()
    for i in range(num_orders):
        t0 = time.perf_counter_ns()
        engine.process_new_order(crossing_orders[i])
        t1 = time.perf_counter_ns()
        match_latencies_ns[i] = t1 - t0
    t_end = time.perf_counter()
    gc.enable()

    total_time_m = t_end - t_start
    throughput_m = num_orders / total_time_m
    m_latencies_us = [x / 1_000.0 for x in match_latencies_ns]
    m_latencies_us.sort()

    print("\n>>> TEST 2: Aggressive Crossing Orders (Trades & Execution Matching)")
    print(f"Throughput       : {throughput_m:,.0f} orders/sec")
    print(f"Total Duration   : {total_time_m:.4f} s")
    print(f"Mean Latency     : {statistics.mean(m_latencies_us):.2f} us")
    print(f"p50 (Median)     : {m_latencies_us[int(num_orders * 0.50)]:.2f} us")
    print(f"p90 Latency      : {m_latencies_us[int(num_orders * 0.90)]:.2f} us")
    print(f"p99 Latency      : {m_latencies_us[int(num_orders * 0.99)]:.2f} us")
    print(f"p99.9 Latency    : {m_latencies_us[int(num_orders * 0.999)]:.2f} us")
    print(f"Max Latency      : {m_latencies_us[-1]:.2f} us")

    # -------------------------------------------------------------
    # 3. Benchmark Order Cancellations (O(1) Hash Map & DLL Unlink)
    # -------------------------------------------------------------
    # Insert 50,000 resting orders first
    cancel_count = 50_000
    for i in range(cancel_count):
        engine.process_new_order(
            NewOrderMsg.create(
                order_id=2_000_000 + i,
                client_id=1,
                symbol=sym_id,
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                price=50.0 + (i % 100) * 0.1,
                quantity=10,
            )
        )

    cancels = [
        CancelOrderMsg.create(order_id=2_000_000 + i, client_id=1, symbol=sym_id)
        for i in range(cancel_count)
    ]

    gc.disable()
    cancel_latencies_ns: List[int] = [0] * cancel_count
    t_start = time.perf_counter()
    for i in range(cancel_count):
        t0 = time.perf_counter_ns()
        engine.process_cancel_order(cancels[i])
        t1 = time.perf_counter_ns()
        cancel_latencies_ns[i] = t1 - t0
    t_end = time.perf_counter()
    gc.enable()

    total_time_c = t_end - t_start
    throughput_c = cancel_count / total_time_c
    c_latencies_us = [x / 1_000.0 for x in cancel_latencies_ns]
    c_latencies_us.sort()

    print("\n>>> TEST 3: Order Cancellations (O(1) Index Lookup & Doubly-Linked Unlink)")
    print(f"Throughput       : {throughput_c:,.0f} cancels/sec")
    print(f"Total Duration   : {total_time_c:.4f} s")
    print(f"Mean Latency     : {statistics.mean(c_latencies_us):.2f} us")
    print(f"p50 (Median)     : {c_latencies_us[int(cancel_count * 0.50)]:.2f} us")
    print(f"p90 Latency      : {c_latencies_us[int(cancel_count * 0.90)]:.2f} us")
    print(f"p99 Latency      : {c_latencies_us[int(cancel_count * 0.99)]:.2f} us")
    print(f"p99.9 Latency    : {c_latencies_us[int(cancel_count * 0.999)]:.2f} us")
    print(f"Max Latency      : {c_latencies_us[-1]:.2f} us")
    print("=" * 70)


def main():
    run_benchmark(100_000)


if __name__ == "__main__":
    main()
