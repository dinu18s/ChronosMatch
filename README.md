# ChronosMatch: Zero-Copy High-Frequency Trading Engine

A high-throughput, ultra-low-latency electronic trading matching engine built in modern Python (3.12+), featuring:
- **Zero-Copy Memory Semantics**: Direct binary C-struct parsing via Python Buffer Protocol (`memoryview`, `ctypes.Structure.from_buffer`) without intermediary heap allocations or JSON/string conversions.
- **Price-Time Priority (FIFO) Matching**: Deterministic order matching with doubly linked list queues per price level and $O(1)$ order cancellation lookups.
- **Lockless Shared-Memory SPSC Ring Buffer**: Inter-process communication (IPC) for order ingestion and execution dissemination with cache-line padded sequence pointers.
- **Binary Write-Ahead Logging (WAL)**: Append-only persistent journal with deterministic state replay.
- **Microsecond Benchmarking & Profiling**: Latency percentile tracking ($p_{50}, p_{90}, p_{99}, p_{99.9}$) and tick-to-trade throughput measurement.

---

## Architecture Overview

```
+---------------------+           Shared Memory Ring Buffer          +-----------------------+
| Ingestion Gateway   |  ==========================================> | ChronosMatch Engine   |
| (Binary SBE Frames) |  (Zero-Copy memoryview / SPSC Circular Ring) | (Price-Time FIFO LOB) |
+---------------------+                                              +-----------------------+
                                                                                 |
                                                                   +-------------+-------------+
                                                                   |                           |
                                                                   v                           v
                                                         +-------------------+       +-------------------+
                                                         | Binary WAL Store  |       | Market Data Feed  |
                                                         | (mmap Persistence)|       | (L2 Depth / BBO)  |
                                                         +-------------------+       +-------------------+
```

---

## Quickstart & Execution

You can run any of the tools directly with Python or `uv`:

### 1. Run Live Market Simulation
Watch real-time order book depth, sweeps, and executions:
```bash
python run_simulation.py
```
*(or `uv run python run_simulation.py`)*

### 2. Run High-Frequency Benchmarks
Measures orders/sec throughput and microsecond latency percentiles ($p_{50}$, $p_{90}$, $p_{99}$, $p_{99.9}$):
```bash
python run_benchmarks.py
```
*(or individual benchmarks: `python benchmarks/benchmark_engine.py` / `python benchmarks/benchmark_ring_buffer.py`)*

### 3. Run Test Suite
Runs all 19 unit tests across protocols, order books, ring buffers, and WAL:
```bash
python run_tests.py
```
*(or `uv run pytest`)*
