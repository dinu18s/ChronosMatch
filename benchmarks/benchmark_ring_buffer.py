"""Microbenchmark measuring throughput and latency for SharedRingBuffer."""

import gc
import statistics
import time
import uuid
from typing import List

from chronosmatch.ipc import SharedRingBuffer
from chronosmatch.protocol import NewOrderMsg, OrderType, Side, price_to_fixed


def run_ring_buffer_benchmark(iterations: int = 200_000):
    print("=" * 70)
    print("  ChronosMatch: Shared Memory Zero-Copy Ring Buffer Benchmark")
    print("=" * 70)
    print(f"Total Iterations : {iterations:,} slot transfers")
    print("-" * 70)

    ring_name = f"cm_bench_ring_{uuid.uuid4().hex[:8]}"
    ring = SharedRingBuffer(name=ring_name, capacity=65536, slot_size=128, create=True)

    latencies_ns: List[int] = [0] * iterations

    gc.disable()
    t_start = time.perf_counter()
    for i in range(iterations):
        t0 = time.perf_counter_ns()

        # Producer: acquire slot directly in shared memory
        slot = ring.acquire_write_slot()
        if slot is None:
            # Drain if needed
            r_slot = ring.peek_read_slot()
            ring.advance_read()
            slot = ring.acquire_write_slot()

        # Zero-copy write
        order = NewOrderMsg.from_buffer(slot, 0)
        order.order_id = i + 1
        order.side = Side.BUY
        order.order_type = OrderType.LIMIT
        order.price = price_to_fixed(150.0)
        order.quantity = 100
        ring.commit_write()

        # Consumer: peek & consume
        r_slot = ring.peek_read_slot()
        r_order = NewOrderMsg.from_buffer(r_slot, 0)
        _ = r_order.order_id
        ring.advance_read()

        t1 = time.perf_counter_ns()
        latencies_ns[i] = t1 - t0

    t_end = time.perf_counter()
    gc.enable()

    del slot, order, r_slot, r_order
    gc.collect()
    ring.close()

    total_time = t_end - t_start
    throughput = iterations / total_time
    latencies_us = [x / 1_000.0 for x in latencies_ns]
    latencies_us.sort()

    print(f"Throughput       : {throughput:,.0f} transfers/sec")
    print(f"Total Duration   : {total_time:.4f} s")
    print(f"Mean Latency     : {statistics.mean(latencies_us):.2f} µs")
    print(f"p50 (Median)     : {latencies_us[int(iterations * 0.50)]:.2f} µs")
    print(f"p90 Latency      : {latencies_us[int(iterations * 0.90)]:.2f} µs")
    print(f"p99 Latency      : {latencies_us[int(iterations * 0.99)]:.2f} µs")
    print(f"p99.9 Latency    : {latencies_us[int(iterations * 0.999)]:.2f} µs")
    print(f"Max Latency      : {latencies_us[-1]:.2f} µs")
    print("=" * 70)


if __name__ == "__main__":
    run_ring_buffer_benchmark(200_000)
