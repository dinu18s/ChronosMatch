"""Convenience entry point to run all ChronosMatch performance benchmarks."""

import sys
from pathlib import Path

# Add src and benchmarks to sys.path
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "src"))
sys.path.insert(0, str(root / "benchmarks"))

from benchmark_engine import run_benchmark
from benchmark_ring_buffer import run_ring_buffer_benchmark

if __name__ == "__main__":
    print("\nStarting ChronosMatch Full Benchmark Suite...\n")
    run_benchmark(num_orders=100_000)
    print("\n")
    run_ring_buffer_benchmark(iterations=200_000)
    print("\nAll benchmarks completed successfully.\n")
