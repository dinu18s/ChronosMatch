"""Exchange Simulation Control Center & Chaos/Resilience Laboratory Engine.

Provides:
- Configurable isolated virtual exchange simulation (order arrival rate, participants,
  cancellation rate, liquidity depth, engine throughput capacity, network delay).
- Presets: Normal, High Load, Liquidity Shock, Network Delay, and Recovery.
- Failure Injections: Traffic Spike, Engine Pause, Delayed Processing, Liquidity Dry-Up,
  Duplicate Order Submission, Invalid Order Payload, Data-Feed Interruption.
- Active Safeguards: Idempotency Filter, Input Payload Validator, Rate Limiter/Queue Guard,
  and Circuit Breaker.
- Automated Invariant & Recovery Verification: Zero duplicate executions, solvency conservation,
  order lifecycle correctness, book-to-store consistency, and recovery duration measurement.
- Real microsecond benchmarking, detailed incident timeline logs, side-by-side comparison,
  and educational post-mortem incident reports.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from chronosmatch.engine.book import OrderBook
from chronosmatch.protocol.messages import (
    CancelOrderMsg,
    ExecutionReportMsg,
    NewOrderMsg,
)
from chronosmatch.protocol.types import (
    ExecType,
    MatchStatus,
    OrderType,
    RejectCode,
    Side,
    TimeInForce,
    fixed_to_price,
    price_to_fixed,
)


# =====================================================================
# ENUMS AND CONFIGURATION MODELS
# =====================================================================
class SimulationScenario(str, Enum):
    NORMAL = "NORMAL"
    HIGH_LOAD = "HIGH_LOAD"
    LIQUIDITY_SHOCK = "LIQUIDITY_SHOCK"
    NETWORK_DELAY = "NETWORK_DELAY"
    RECOVERY = "RECOVERY"


class FailureType(str, Enum):
    NONE = "NONE"
    TRAFFIC_SPIKE = "TRAFFIC_SPIKE"
    ENGINE_PAUSE = "ENGINE_PAUSE"
    DELAYED_PROCESSING = "DELAYED_PROCESSING"
    LIQUIDITY_DRYUP = "LIQUIDITY_DRYUP"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    INVALID_PAYLOAD = "INVALID_PAYLOAD"
    FEED_DISRUPTION = "FEED_DISRUPTION"


@dataclass
class ChaosConfig:
    seed: int = 42
    symbol: str = "BTCUSDT"
    num_events: int = 120
    incoming_rate: float = 1000.0  # orders/second
    num_participants: int = 10
    cancel_rate_pct: float = 15.0
    liquidity_depth: int = 20
    processing_capacity: float = 2500.0  # orders/second capacity of engine
    network_delay_ms: float = 5.0
    queue_capacity: int = 100  # maximum queue capacity before shedding
    scenario: SimulationScenario = SimulationScenario.NORMAL
    failure_type: FailureType = FailureType.NONE
    failure_start_pct: float = 0.35  # inject at 35% mark
    failure_duration_events: int = 25  # lasts for 25 events


# Preset definitions
SCENARIO_PRESETS: Dict[str, Dict[str, Any]] = {
    "NORMAL": {
        "incoming_rate": 800.0,
        "num_participants": 10,
        "cancel_rate_pct": 12.0,
        "liquidity_depth": 25,
        "processing_capacity": 2500.0,
        "network_delay_ms": 4.0,
        "queue_capacity": 100,
        "failure_type": "NONE",
        "description": "Standard market conditions with balanced order flow, stable book depth, and low queue latency.",
    },
    "HIGH_LOAD": {
        "incoming_rate": 3200.0,
        "num_participants": 25,
        "cancel_rate_pct": 20.0,
        "liquidity_depth": 35,
        "processing_capacity": 2000.0,
        "network_delay_ms": 15.0,
        "queue_capacity": 120,
        "failure_type": "NONE",
        "description": "Stress test where arrival rate exceeds engine capacity, building up event queue depth and tail latency.",
    },
    "LIQUIDITY_SHOCK": {
        "incoming_rate": 900.0,
        "num_participants": 8,
        "cancel_rate_pct": 55.0,
        "liquidity_depth": 6,
        "processing_capacity": 2500.0,
        "network_delay_ms": 5.0,
        "queue_capacity": 100,
        "failure_type": "LIQUIDITY_DRYUP",
        "description": "Rapid liquidity withdrawal and aggressive cancels causing wide spreads and triggering volatility protections.",
    },
    "NETWORK_DELAY": {
        "incoming_rate": 700.0,
        "num_participants": 12,
        "cancel_rate_pct": 10.0,
        "liquidity_depth": 20,
        "processing_capacity": 2500.0,
        "network_delay_ms": 85.0,
        "queue_capacity": 100,
        "failure_type": "FEED_DISRUPTION",
        "description": "Severe network delay and jitter resulting in packet burstiness and telemetry lag.",
    },
    "RECOVERY": {
        "incoming_rate": 2800.0,
        "num_participants": 20,
        "cancel_rate_pct": 15.0,
        "liquidity_depth": 25,
        "processing_capacity": 2500.0,
        "network_delay_ms": 8.0,
        "queue_capacity": 100,
        "failure_type": "ENGINE_PAUSE",
        "description": "Matching engine stalls temporarily under load, accumulates a heavy backlog, then drains cleanly back to zero.",
    },
}


# =====================================================================
# VIRTUAL PARTICIPANT ACCOUNT (ISOLATED)
# =====================================================================
@dataclass
class VirtualParticipant:
    participant_id: int
    cash: float = 1_000_000.0
    holdings: float = 20.0
    initial_cash: float = 1_000_000.0
    initial_holdings: float = 20.0

    def can_buy(self, cost: float) -> bool:
        return self.cash >= cost

    def can_sell(self, qty: float) -> bool:
        return self.holdings >= qty

    def execute_buy(self, cost: float, qty: float) -> None:
        self.cash -= cost
        self.holdings += qty

    def execute_sell(self, proceeds: float, qty: float) -> None:
        self.cash += proceeds
        self.holdings -= qty


# =====================================================================
# SAFEGUARDS SYSTEM
# =====================================================================
class SafeguardSystem:
    """Active runtime defense guards protecting the virtual matching engine."""

    def __init__(self, queue_capacity: int = 100, max_spread_bps: float = 400.0) -> None:
        self.queue_capacity = queue_capacity
        self.max_spread_bps = max_spread_bps
        self.seen_client_orders: Set[str] = set()
        self.circuit_breaker_tripped: bool = False
        self.shed_order_count: int = 0
        self.duplicate_blocked_count: int = 0
        self.invalid_payload_count: int = 0
        self.circuit_breaker_trips: int = 0

    def check_idempotency(self, client_id: int, client_order_id: int) -> Tuple[bool, Optional[str]]:
        """Idempotency guard: prevents duplicate order submissions."""
        key = f"{client_id}:{client_order_id}"
        if key in self.seen_client_orders:
            self.duplicate_blocked_count += 1
            return False, f"Duplicate order key '{key}' detected. Blocked by Idempotency Filter."
        self.seen_client_orders.add(key)
        return True, None

    def validate_payload(
        self,
        symbol: str,
        side: str,
        order_type: str,
        price: float,
        quantity: int,
    ) -> Tuple[bool, Optional[str]]:
        """Payload validator: rejects malformed or corrupted inputs."""
        if price <= 0 and order_type != "MARKET":
            self.invalid_payload_count += 1
            return False, f"Invalid price {price}. Must be strictly positive for LIMIT orders."
        if quantity <= 0:
            self.invalid_payload_count += 1
            return False, f"Invalid quantity {quantity}. Must be strictly positive integer."
        if side not in ("BUY", "SELL"):
            self.invalid_payload_count += 1
            return False, f"Invalid side '{side}'. Must be BUY or SELL."
        if not symbol or len(symbol) > 12:
            self.invalid_payload_count += 1
            return False, f"Malformed symbol '{symbol}'."
        return True, None

    def check_queue_capacity(self, current_queue_size: int) -> Tuple[bool, Optional[str]]:
        """Rate limiter & queue guard: sheds excess orders when backlog exceeds buffer capacity."""
        if current_queue_size >= self.queue_capacity:
            self.shed_order_count += 1
            return False, f"Queue backlog ({current_queue_size}) reached capacity ({self.queue_capacity}). Order shed by Rate Limiter."
        return True, None

    def evaluate_circuit_breaker(self, spread_bps: float, depth: int) -> Tuple[bool, Optional[str]]:
        """Circuit breaker: triggers protection when spread widens excessively or liquidity collapses."""
        if spread_bps > self.max_spread_bps or depth == 0:
            if not self.circuit_breaker_tripped:
                self.circuit_breaker_tripped = True
                self.circuit_breaker_trips += 1
                return False, f"Market spread {spread_bps:.1f} bps exceeded limit {self.max_spread_bps:.1f} bps. Circuit Breaker TRIPPED."
        else:
            if self.circuit_breaker_tripped:
                self.circuit_breaker_tripped = False  # Reset on stabilization
        return True, None


# =====================================================================
# INVARIANT VERIFICATION ENGINE
# =====================================================================
class InvariantVerifier:
    """Formal consistency verifier checking state integrity across all trades and orders."""

    @staticmethod
    def verify(
        orders_store: Dict[int, Dict[str, Any]],
        participants: Dict[int, VirtualParticipant],
        book: OrderBook,
        executions: List[Dict[str, Any]],
        queue_remaining: int,
        recovery_duration_ms: float,
    ) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []

        # -------------------------------------------------------------
        # Invariant 1: No Duplicate Executions
        # -------------------------------------------------------------
        exec_ids_seen = set()
        duplicate_exec_found = False
        exec_violation_detail = None

        for ex in executions:
            eid = ex["exec_id"]
            if eid in exec_ids_seen:
                duplicate_exec_found = True
                exec_violation_detail = f"Duplicate execution ID #{eid} detected."
                break
            exec_ids_seen.add(eid)

        # Check that no order's filled_qty exceeds its original_qty
        overfill_found = False
        for oid, o in orders_store.items():
            if o["filled_qty"] > o["original_qty"]:
                overfill_found = True
                exec_violation_detail = f"Order #{oid} overfilled: {o['filled_qty']} > {o['original_qty']}."
                break

        inv1_passed = (not duplicate_exec_found) and (not overfill_found)
        results.append({
            "name": "No Duplicate Executions",
            "passed": inv1_passed,
            "description": "Guarantees zero duplicate fills and that no order fills beyond original requested quantity.",
            "details": exec_violation_detail if not inv1_passed else f"Verified {len(executions)} fills without duplication or overfill.",
        })

        # -------------------------------------------------------------
        # Invariant 2: Solvency & Balance Conservation
        # -------------------------------------------------------------
        negative_balance_found = False
        balance_violation_detail = None
        for pid, p in participants.items():
            if p.cash < -1e-6:
                negative_balance_found = True
                balance_violation_detail = f"Participant #{pid} has negative cash: ${p.cash:,.2f}."
                break
            if p.holdings < -1e-6:
                negative_balance_found = True
                balance_violation_detail = f"Participant #{pid} has negative holdings: {p.holdings:,.4f} units."
                break

        # Conservation of cash and stock across all participants
        total_cash_now = sum(p.cash for p in participants.values())
        total_cash_init = sum(p.initial_cash for p in participants.values())
        total_holdings_now = sum(p.holdings for p in participants.values())
        total_holdings_init = sum(p.initial_holdings for p in participants.values())

        cash_conserved = abs(total_cash_now - total_cash_init) < 1e-4
        holdings_conserved = abs(total_holdings_now - total_holdings_init) < 1e-4

        inv2_passed = (not negative_balance_found) and cash_conserved and holdings_conserved
        if not inv2_passed and not balance_violation_detail:
            balance_violation_detail = f"Asset conservation mismatch: Cash Delta=${total_cash_now - total_cash_init:,.2f}, Holdings Delta={total_holdings_now - total_holdings_init:,.4f}."

        results.append({
            "name": "Solvency & Asset Conservation",
            "passed": inv2_passed,
            "description": "Verifies no participant balance goes negative and total cash & holdings are conserved across trades.",
            "details": balance_violation_detail if not inv2_passed else f"Total Cash: ${total_cash_now:,.2f} (Delta: 0.00), Holdings: {total_holdings_now:,.2f} (Delta: 0.00).",
        })

        # -------------------------------------------------------------
        # Invariant 3: Order Lifecycle Status Correctness
        # -------------------------------------------------------------
        status_inconsistent = False
        status_detail = None

        for oid, o in orders_store.items():
            status = o["status"]
            orig = o["original_qty"]
            filled = o["filled_qty"]
            leaves = o["leaves_qty"]
            ot = o.get("order_type", "LIMIT")

            if status == "FILLED" and leaves != 0:
                status_inconsistent = True
                status_detail = f"Order #{oid} marked FILLED but has leaves_qty={leaves}."
                break
            elif status == "PARTIALLY_FILLED" and filled == 0:
                status_inconsistent = True
                status_detail = f"Order #{oid} marked PARTIALLY_FILLED with filled=0."
                break
            elif status == "PARTIALLY_FILLED" and ot == "LIMIT" and leaves == 0:
                status_inconsistent = True
                status_detail = f"Limit order #{oid} marked PARTIALLY_FILLED with leaves=0."
                break
            elif status == "REJECTED" and filled > 0:
                status_inconsistent = True
                status_detail = f"Order #{oid} marked REJECTED but executed {filled} units."
                break
            elif status == "CANCELLED" and (filled + leaves > orig):
                status_inconsistent = True
                status_detail = f"Order #{oid} CANCELLED with filled={filled} + leaves={leaves} > orig={orig}."
                break

        inv3_passed = not status_inconsistent
        results.append({
            "name": "Order Lifecycle Status Correctness",
            "passed": inv3_passed,
            "description": "Verifies terminal states (FILLED, PARTIAL, CANCELLED, REJECTED) accurately match fill quantities.",
            "details": status_detail if not inv3_passed else f"All {len(orders_store)} orders have mathematically consistent statuses.",
        })

        # -------------------------------------------------------------
        # Invariant 4: Book & Order Store Consistency
        # -------------------------------------------------------------
        # Resting orders in store vs book order count
        active_in_store = sum(1 for o in orders_store.values() if o.get("is_resting", False))
        book_count = book.order_count
        inv4_passed = (book_count == active_in_store)
        inv4_detail = None if inv4_passed else f"Order book count ({book_count}) does not match active store count ({active_in_store})."

        results.append({
            "name": "Order Book & Store Consistency",
            "passed": inv4_passed,
            "description": "Verifies resting levels and queue depths in the matching engine match active orders in the store.",
            "details": inv4_detail if not inv4_passed else f"Resting book count ({book_count}) perfectly matches active store orders.",
        })

        # -------------------------------------------------------------
        # Invariant 5: Queue Backlog Drained & System Recovered
        # -------------------------------------------------------------
        inv5_passed = (queue_remaining == 0)
        inv5_detail = f"Pending queue backlog not fully drained: {queue_remaining} remaining." if not inv5_passed else f"Queue fully drained to 0 in {recovery_duration_ms:.2f} ms."

        results.append({
            "name": "Queue Backlog Drained & System Recovered",
            "passed": inv5_passed,
            "description": "Verifies the simulated exchange cleared all buffered events and restored normal processing latency.",
            "details": inv5_detail,
        })

        all_passed = all(r["passed"] for r in results)
        return {
            "all_passed": all_passed,
            "checks": results,
            "recovery_duration_ms": round(recovery_duration_ms, 2),
            "total_checks": len(results),
            "passed_count": sum(1 for r in results if r["passed"]),
        }


# =====================================================================
# CHAOS SIMULATION ENGINE (ISOLATED)
# =====================================================================
class ChaosSimulationEngine:
    """Executes a high-fidelity isolated virtual exchange simulation with chaos fault injection."""

    def __init__(self, config: ChaosConfig) -> None:
        self.config = config
        self.rng = random.Random(config.seed)
        self.book = OrderBook(config.symbol)
        self.safeguards = SafeguardSystem(queue_capacity=config.queue_capacity)

        # Isolated virtual participant accounts
        self.participants: Dict[int, VirtualParticipant] = {
            pid: VirtualParticipant(participant_id=pid)
            for pid in range(1, config.num_participants + 1)
        }

        # Order storage & executions
        self.orders_store: Dict[int, Dict[str, Any]] = {}
        self.executions: List[Dict[str, Any]] = []
        self.event_timeline: List[Dict[str, Any]] = []
        self.telemetry_samples: List[Dict[str, Any]] = []
        self.latencies_us: List[float] = []

        self._exec_id_counter = 1000
        self._order_id_counter = 5000
        self._sim_time_ms = 0.0

        # Prime initial liquidity depth
        self._seed_initial_liquidity()

    def _seed_initial_liquidity(self) -> None:
        """Seed the order book with initial resting liquidity for the simulated market."""
        base_price = 65000.0 if "BTC" in self.config.symbol else 3000.0
        depth = max(5, self.config.liquidity_depth)

        for i in range(1, depth + 1):
            # Resting bid
            bid_p = round(base_price - (i * 5.0), 2)
            bid_q = self.rng.randint(2, 8)
            bid_oid = 1000 + i
            msg_b = NewOrderMsg.create(
                order_id=bid_oid,
                client_id=1,
                symbol=self.config.symbol,
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                price=bid_p,
                quantity=bid_q,
            )
            self.book.process_order(msg_b)
            self.orders_store[bid_oid] = {
                "order_id": bid_oid,
                "client_id": 1,
                "symbol": self.config.symbol,
                "side": "BUY",
                "order_type": "LIMIT",
                "price": bid_p,
                "original_qty": bid_q,
                "filled_qty": 0,
                "leaves_qty": bid_q,
                "status": "NEW",
                "is_resting": True,
            }

            # Resting ask
            ask_p = round(base_price + (i * 5.0), 2)
            ask_q = self.rng.randint(2, 8)
            ask_oid = 2000 + i
            msg_a = NewOrderMsg.create(
                order_id=ask_oid,
                client_id=2,
                symbol=self.config.symbol,
                side=Side.SELL,
                order_type=OrderType.LIMIT,
                price=ask_p,
                quantity=ask_q,
            )
            self.book.process_order(msg_a)
            self.orders_store[ask_oid] = {
                "order_id": ask_oid,
                "client_id": 2,
                "symbol": self.config.symbol,
                "side": "SELL",
                "order_type": "LIMIT",
                "price": ask_p,
                "original_qty": ask_q,
                "filled_qty": 0,
                "leaves_qty": ask_q,
                "status": "NEW",
                "is_resting": True,
            }

    def run(self) -> Dict[str, Any]:
        """Execute the complete chaos experiment, telemetry generation, and invariant verification."""
        t_bench_start = time.perf_counter()

        # Generate incoming scheduled events
        scheduled_events = self._generate_scheduled_events()

        # Event processing loop with queue tracking and fault injection
        pending_queue: List[Dict[str, Any]] = []
        failure_active = False
        failure_start_event = int(self.config.num_events * self.config.failure_start_pct)
        failure_end_event = failure_start_event + self.config.failure_duration_events
        recovery_start_time_ms: Optional[float] = None
        recovery_duration_ms: float = 0.0

        processed_count = 0
        rejected_count = 0
        cancelled_count = 0

        sim_interval_ms = 1000.0 / max(1.0, self.config.incoming_rate)
        service_capacity_interval_ms = 1000.0 / max(1.0, self.config.processing_capacity)
        service_accumulator = 0.0

        for event_idx, raw_event in enumerate(scheduled_events):
            dt_ms = self.rng.uniform(sim_interval_ms * 0.7, sim_interval_ms * 1.3)

            # Failure window check
            if failure_start_event <= event_idx < failure_end_event:
                failure_active = True
                self._apply_in_flight_failure(raw_event, event_idx)
                if self.config.failure_type == FailureType.TRAFFIC_SPIKE:
                    dt_ms *= 0.05  # 20x burst ingress compression
            elif event_idx >= failure_end_event and failure_active:
                failure_active = False
                recovery_start_time_ms = self._sim_time_ms

            self._sim_time_ms += dt_ms

            # Rate Limiter & Queue Guard at Ingress
            q_ok, q_err = self.safeguards.check_queue_capacity(len(pending_queue))
            if not q_ok:
                rejected_count += 1
                oid = raw_event["order_id"]
                self.orders_store[oid] = {
                    "order_id": oid,
                    "client_id": raw_event.get("client_id", 1),
                    "symbol": self.config.symbol,
                    "side": raw_event.get("side", "BUY"),
                    "order_type": raw_event.get("order_type", "LIMIT"),
                    "price": raw_event.get("price", 0.0),
                    "original_qty": raw_event.get("quantity", 1),
                    "filled_qty": 0,
                    "leaves_qty": 0,
                    "status": "REJECTED",
                    "is_resting": False,
                }
                self._record_timeline_event(
                    event_idx=event_idx,
                    raw_event=raw_event,
                    status="REJECTED",
                    queue_depth=len(pending_queue),
                    latency_us=round(self.config.network_delay_ms * 1000.0, 1),
                    safeguard="QUEUE_OVERFLOW_SHED",
                    details=q_err or "Ingress order shed: queue buffer capacity reached.",
                )
                self._sample_telemetry(len(pending_queue), incoming_delta=1, processed_delta=0)
                continue

            # Add to pending event queue
            pending_queue.append(raw_event)

            # Under ENGINE_PAUSE failure, processing stalls completely during failure window
            if failure_active and self.config.failure_type == FailureType.ENGINE_PAUSE:
                self._record_timeline_event(
                    event_idx=event_idx,
                    raw_event=raw_event,
                    status="QUEUED",
                    queue_depth=len(pending_queue),
                    latency_us=round(self.config.network_delay_ms * 1000.0, 1),
                    safeguard=None,
                    details=f"Engine paused during failure window. Event #{raw_event['order_id']} buffered in queue.",
                )
                self._sample_telemetry(len(pending_queue), incoming_delta=1, processed_delta=0)
                continue

            # Accumulate service capacity based on simulated time and processing capacity
            eff_capacity = self.config.processing_capacity
            if failure_active and self.config.failure_type == FailureType.DELAYED_PROCESSING:
                eff_capacity *= 0.15  # 85% processing degradation

            service_accumulator += dt_ms * (eff_capacity / 1000.0)
            orders_to_drain = int(service_accumulator)
            if orders_to_drain > 0:
                service_accumulator -= orders_to_drain

            drained = 0
            while pending_queue and drained < orders_to_drain:
                ev = pending_queue.pop(0)
                drained += 1

                t_proc_start = time.perf_counter()
                success, status, safeguard_msg, details = self._process_single_event(ev)
                t_proc_us = (time.perf_counter() - t_proc_start) * 1_000_000.0

                queue_delay_ms = len(pending_queue) * service_capacity_interval_ms
                total_latency_us = round((self.config.network_delay_ms + queue_delay_ms) * 1000.0 + t_proc_us, 1)
                self.latencies_us.append(total_latency_us)

                if status == "REJECTED":
                    rejected_count += 1
                elif status == "CANCELLED":
                    cancelled_count += 1
                else:
                    processed_count += 1

                self._record_timeline_event(
                    event_idx=event_idx,
                    raw_event=ev,
                    status=status,
                    queue_depth=len(pending_queue),
                    latency_us=total_latency_us,
                    safeguard=safeguard_msg,
                    details=details,
                )

            self._sample_telemetry(len(pending_queue), incoming_delta=1, processed_delta=drained)

        # Drain any remaining events in queue after scheduled events to measure recovery duration
        drain_steps = 0
        while pending_queue and drain_steps < 500:
            drain_steps += 1
            self._sim_time_ms += service_capacity_interval_ms
            ev = pending_queue.pop(0)
            t_proc_start = time.perf_counter()
            success, status, safeguard_msg, details = self._process_single_event(ev)
            t_proc_us = (time.perf_counter() - t_proc_start) * 1_000_000.0

            total_latency_us = round(self.config.network_delay_ms * 1000.0 + t_proc_us, 1)
            self.latencies_us.append(total_latency_us)

            if status == "REJECTED":
                rejected_count += 1
            elif status == "CANCELLED":
                cancelled_count += 1
            else:
                processed_count += 1

            self._record_timeline_event(
                event_idx=len(scheduled_events) + drain_steps,
                raw_event=ev,
                status=status,
                queue_depth=len(pending_queue),
                latency_us=total_latency_us,
                safeguard=safeguard_msg,
                details=f"[Recovery Drain] {details}",
            )
            self._sample_telemetry(len(pending_queue), incoming_delta=0, processed_delta=1)

        # Recovery duration calculation
        if recovery_start_time_ms is not None:
            recovery_duration_ms = max(0.0, self._sim_time_ms - recovery_start_time_ms)
        else:
            recovery_duration_ms = 0.0

        t_bench_wall_ms = (time.perf_counter() - t_bench_start) * 1000.0

        # Invariant Verification
        invariant_results = InvariantVerifier.verify(
            orders_store=self.orders_store,
            participants=self.participants,
            book=self.book,
            executions=self.executions,
            queue_remaining=len(pending_queue),
            recovery_duration_ms=recovery_duration_ms,
        )

        # Health Telemetry summary
        telemetry_summary = self._compute_telemetry_summary(
            total_incoming=len(scheduled_events),
            processed_count=processed_count,
            rejected_count=rejected_count,
            cancelled_count=cancelled_count,
            queue_remaining=len(pending_queue),
            wall_time_ms=t_bench_wall_ms,
        )

        # Educational Incident Report
        incident_report = self._generate_incident_report(
            invariant_results=invariant_results,
            telemetry_summary=telemetry_summary,
            recovery_duration_ms=recovery_duration_ms,
        )

        return {
            "status": "success",
            "is_simulated": True,
            "disclaimer": "All figures produced in an isolated virtual sandbox. Zero effect on paper trading balances.",
            "config": asdict(self.config),
            "telemetry": telemetry_summary,
            "invariants": invariant_results,
            "incident_report": incident_report,
            "telemetry_samples": self.telemetry_samples,
            "event_timeline": self.event_timeline[:150],  # bounded sample for payload efficiency
            "total_timeline_events": len(self.event_timeline),
            "order_book_bbo": self._get_current_bbo(),
        }

    def _generate_scheduled_events(self) -> List[Dict[str, Any]]:
        """Pre-generate pseudo-random events based on configuration and random seed."""
        events: List[Dict[str, Any]] = []
        base_price = 65000.0 if "BTC" in self.config.symbol else 3000.0
        pids = list(self.participants.keys())

        for i in range(1, self.config.num_events + 1):
            self._order_id_counter += 1
            oid = self._order_id_counter
            client_id = self.rng.choice(pids)

            # Determine whether event is an aggressive trade or limit/cancel
            is_cancel = (self.rng.uniform(0, 100) < self.config.cancel_rate_pct) and (len(self.orders_store) > 10)
            side = self.rng.choice(["BUY", "SELL"])
            qty = self.rng.randint(1, 5)

            if is_cancel:
                # Pick an existing resting order to cancel
                candid_oids = [k for k, v in self.orders_store.items() if v.get("is_resting", False)]
                target_cancel_oid = self.rng.choice(candid_oids) if candid_oids else oid
                events.append({
                    "event_type": "CANCEL",
                    "order_id": target_cancel_oid,
                    "client_id": client_id,
                    "symbol": self.config.symbol,
                    "side": side,
                    "price": 0.0,
                    "quantity": 0,
                    "order_type": "CANCEL",
                })
            else:
                is_market = self.rng.random() < 0.25
                if is_market:
                    events.append({
                        "event_type": "MARKET_ORDER",
                        "order_id": oid,
                        "client_id": client_id,
                        "symbol": self.config.symbol,
                        "side": side,
                        "price": 0.0,
                        "quantity": qty,
                        "order_type": "MARKET",
                    })
                else:
                    offset = self.rng.uniform(1.0, 15.0)
                    price = round(base_price - offset if side == "BUY" else base_price + offset, 2)
                    events.append({
                        "event_type": "LIMIT_ORDER",
                        "order_id": oid,
                        "client_id": client_id,
                        "symbol": self.config.symbol,
                        "side": side,
                        "price": price,
                        "quantity": qty,
                        "order_type": "LIMIT",
                    })

        return events

    def _apply_in_flight_failure(self, raw_event: Dict[str, Any], event_idx: int) -> None:
        """Inject the selected failure mode into the raw event stream."""
        ft = self.config.failure_type

        if ft == FailureType.DUPLICATE_ORDER:
            existing_oids = list(self.safeguards.seen_client_orders)
            if existing_oids and self.rng.random() < 0.65:
                chosen_key = self.rng.choice(existing_oids)
                cid, orig_oid = chosen_key.split(":")
                raw_event["client_id"] = int(cid)
                raw_event["order_id"] = int(orig_oid)
                raw_event["_injected_duplicate"] = True

        elif ft == FailureType.INVALID_PAYLOAD:
            corruption_type = self.rng.choice(["NEGATIVE_PRICE", "ZERO_QTY", "CORRUPT_SIDE", "INVALID_SYMBOL"])
            if corruption_type == "NEGATIVE_PRICE":
                raw_event["price"] = -50.0
                raw_event["order_type"] = "LIMIT"
            elif corruption_type == "ZERO_QTY":
                raw_event["quantity"] = 0
            elif corruption_type == "CORRUPT_SIDE":
                raw_event["side"] = "INVALID_SIDE_FLIP"
            elif corruption_type == "INVALID_SYMBOL":
                raw_event["symbol"] = "MALFORMED_SYMBOL_XYZ_OVERFLOW"
            raw_event["_injected_invalid"] = True

        elif ft == FailureType.LIQUIDITY_DRYUP:
            raw_event["event_type"] = "CANCEL"
            raw_event["order_type"] = "CANCEL"
            candid_oids = [k for k, v in self.orders_store.items() if v.get("is_resting", False)]
            if candid_oids:
                raw_event["order_id"] = self.rng.choice(candid_oids)

    def _process_single_event(self, ev: Dict[str, Any]) -> Tuple[bool, str, Optional[str], str]:
        """Process one event through safeguards, matching engine, and participant balance updates."""
        oid = ev["order_id"]
        cid = ev["client_id"]
        side_str = ev["side"]
        price = ev.get("price", 0.0)
        qty = ev.get("quantity", 0)
        order_type_str = ev.get("order_type", "LIMIT")
        participant = self.participants.get(cid, self.participants[1])

        # 1. Idempotency guard check (only for new orders)
        if order_type_str != "CANCEL":
            idemp_ok, idemp_err = self.safeguards.check_idempotency(cid, oid)
            if not idemp_ok:
                # Reject duplicate submission without mutating original order state in store
                return False, "REJECTED", "IDEMPOTENCY_FILTER_BLOCKED", idemp_err or "Duplicate order blocked"

        # 2. Payload validation check (only for new orders)
        if order_type_str != "CANCEL":
            val_ok, val_err = self.safeguards.validate_payload(
                symbol=ev["symbol"],
                side=side_str,
                order_type=order_type_str,
                price=price,
                quantity=qty,
            )
            if not val_ok:
                self.orders_store[oid] = {
                    "order_id": oid,
                    "client_id": cid,
                    "symbol": self.config.symbol,
                    "side": side_str,
                    "order_type": order_type_str,
                    "price": price,
                    "original_qty": qty,
                    "filled_qty": 0,
                    "leaves_qty": 0,
                    "status": "REJECTED",
                    "is_resting": False,
                }
                return False, "REJECTED", "INPUT_VALIDATOR_REJECTED", val_err or "Payload validation failed"

        # 3. Solvency pre-trade verification for virtual participant
        if order_type_str != "CANCEL":
            est_cost = (price if price > 0 else 65000.0) * qty
            if side_str == "BUY" and not participant.can_buy(est_cost):
                return False, "REJECTED", "SOLVENCY_GUARD_REJECTED", f"Insufficient virtual cash (${participant.cash:,.2f}) for order cost (${est_cost:,.2f})"
            elif side_str == "SELL" and not participant.can_sell(qty):
                return False, "REJECTED", "SOLVENCY_GUARD_REJECTED", f"Insufficient virtual holdings ({participant.holdings} units) to sell {qty}"

        # 4. Process CANCEL order
        if order_type_str == "CANCEL":
            if oid in self.orders_store:
                c_msg = CancelOrderMsg.create(order_id=oid, client_id=cid, symbol=self.config.symbol)
                rep = self.book.cancel_order(c_msg)
                if rep and rep.exec_type == ExecType.CANCELLED:
                    stored = self.orders_store[oid]
                    stored["status"] = "CANCELLED"
                    stored["leaves_qty"] = 0
                    stored["is_resting"] = False
                    return True, "CANCELLED", None, f"Order #{oid} cancelled cleanly."
                return False, "REJECTED", None, f"Order #{oid} cancellation rejected by book."
            return False, "REJECTED", None, f"Cancel target #{oid} not found in store."

        # 5. Process NEW ORDER (LIMIT or MARKET)
        side_enum = Side.BUY if side_str == "BUY" else Side.SELL
        ot_enum = OrderType.MARKET if order_type_str == "MARKET" else OrderType.LIMIT
        order_msg = NewOrderMsg.create(
            order_id=oid,
            client_id=cid,
            symbol=self.config.symbol,
            side=side_enum,
            order_type=ot_enum,
            price=price,
            quantity=qty,
            tif=TimeInForce.GTC,
        )

        exec_reports = self.book.process_order(order_msg)

        # Update order store and virtual participant holdings
        filled_qty = 0
        leaves_qty = qty
        executed_trades = []

        for r in exec_reports:
            # Only process trade execution reports for the incoming taker order
            if r.exec_type == ExecType.TRADE and r.order_id == oid:
                self._exec_id_counter += 1
                eid = self._exec_id_counter
                trade_price = fixed_to_price(r.price)
                trade_qty = r.last_qty
                filled_qty += trade_qty
                leaves_qty = r.leaves_qty

                # Update resting maker order in store
                maker_oid = r.matched_order_id
                maker_pid = 2
                if maker_oid in self.orders_store:
                    maker_o = self.orders_store[maker_oid]
                    maker_pid = maker_o["client_id"]
                    maker_o["filled_qty"] += trade_qty
                    maker_o["leaves_qty"] = max(0, maker_o["leaves_qty"] - trade_qty)
                    maker_o["is_resting"] = (maker_o["leaves_qty"] > 0)
                    maker_o["status"] = "FILLED" if maker_o["leaves_qty"] == 0 else "PARTIALLY_FILLED"

                taker_pid = cid
                trade_cost = trade_price * trade_qty

                if side_str == "BUY":
                    self.participants[taker_pid].execute_buy(trade_cost, trade_qty)
                    self.participants[maker_pid].execute_sell(trade_cost, trade_qty)
                else:
                    self.participants[taker_pid].execute_sell(trade_cost, trade_qty)
                    self.participants[maker_pid].execute_buy(trade_cost, trade_qty)

                ex_record = {
                    "exec_id": eid,
                    "order_id": oid,
                    "matched_order_id": maker_oid,
                    "price": trade_price,
                    "quantity": trade_qty,
                    "taker_pid": taker_pid,
                    "maker_pid": maker_pid,
                    "timestamp_ms": round(self._sim_time_ms, 2),
                }
                self.executions.append(ex_record)
                executed_trades.append(ex_record)

        # Determine terminal status and resting state
        if ot_enum == OrderType.MARKET:
            leaves_qty = 0  # Market order unfilled portion expires, never rests
            if filled_qty == qty:
                final_status = "FILLED"
            elif filled_qty > 0:
                final_status = "PARTIALLY_FILLED"
            else:
                final_status = "REJECTED"
            is_resting = False
        else:
            # Limit order
            leaves_qty = qty - filled_qty
            if filled_qty == qty:
                final_status = "FILLED"
                is_resting = False
            elif filled_qty > 0:
                final_status = "PARTIALLY_FILLED"
                is_resting = True
            else:
                final_status = "NEW"
                is_resting = True

        self.orders_store[oid] = {
            "order_id": oid,
            "client_id": cid,
            "symbol": self.config.symbol,
            "side": side_str,
            "order_type": order_type_str,
            "price": price,
            "original_qty": qty,
            "filled_qty": filled_qty,
            "leaves_qty": leaves_qty,
            "status": final_status,
            "is_resting": is_resting,
        }

        # Circuit breaker spread check
        bbo = self._get_current_bbo()
        cb_ok, cb_msg = self.safeguards.evaluate_circuit_breaker(bbo["spread_bps"], bbo["total_depth"])

        detail_text = f"Order #{oid} {side_str} {qty}x@{price:.2f} -> {final_status} ({filled_qty}/{qty} filled)."
        if cb_msg:
            detail_text += f" [{cb_msg}]"

        return True, final_status, "CIRCUIT_BREAKER_ACTIVE" if cb_msg else None, detail_text

    def _record_timeline_event(
        self,
        event_idx: int,
        raw_event: Dict[str, Any],
        status: str,
        queue_depth: int,
        latency_us: float,
        safeguard: Optional[str],
        details: str,
    ) -> None:
        """Append an event snapshot to the chronological incident trace."""
        self.event_timeline.append({
            "step": event_idx,
            "sim_time_ms": round(self._sim_time_ms, 2),
            "event_type": raw_event.get("event_type", "ORDER"),
            "order_id": raw_event.get("order_id", 0),
            "client_id": raw_event.get("client_id", 1),
            "side": raw_event.get("side", "N/A"),
            "price": raw_event.get("price", 0.0),
            "quantity": raw_event.get("quantity", 0),
            "status": status,
            "queue_depth": queue_depth,
            "latency_us": latency_us,
            "safeguard_triggered": safeguard,
            "details": details,
        })

    def _sample_telemetry(self, current_queue: int, incoming_delta: int, processed_delta: int) -> None:
        """Sample periodic telemetry for health charts and latency metrics."""
        bbo = self._get_current_bbo()
        recent_latencies = self.latencies_us[-10:] if self.latencies_us else [100.0]
        p50 = float(sorted(recent_latencies)[len(recent_latencies) // 2])

        self.telemetry_samples.append({
            "sim_time_ms": round(self._sim_time_ms, 1),
            "queue_depth": current_queue,
            "incoming_rate": self.config.incoming_rate,
            "processed_delta": processed_delta,
            "spread_bps": bbo["spread_bps"],
            "total_depth": bbo["total_depth"],
            "p50_latency_us": p50,
        })

    def _get_current_bbo(self) -> Dict[str, Any]:
        """Compute current BBO, spread bps, and total depth."""
        bid_bbo, ask_bbo = self.book.get_bbo()
        best_bid = fixed_to_price(bid_bbo[0]) if bid_bbo else None
        best_ask = fixed_to_price(ask_bbo[0]) if ask_bbo else None
        spread = round(best_ask - best_bid, 2) if (best_bid and best_ask) else 0.0
        mid = (best_bid + best_ask) / 2.0 if (best_bid and best_ask) else 65000.0
        spread_bps = round((spread / mid) * 10000.0, 1) if mid > 0 else 0.0
        bids_l2, asks_l2 = self.book.get_l2_depth(depth=10)
        tot_depth = sum(q for _, q in bids_l2) + sum(q for _, q in asks_l2)
        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "spread_bps": spread_bps,
            "mid_price": round(mid, 2),
            "total_depth": tot_depth,
        }

    def _compute_telemetry_summary(
        self,
        total_incoming: int,
        processed_count: int,
        rejected_count: int,
        cancelled_count: int,
        queue_remaining: int,
        wall_time_ms: float,
    ) -> Dict[str, Any]:
        """Aggregate high-level health telemetry and percentiles."""
        lats = sorted(self.latencies_us) if self.latencies_us else [50.0]
        n = len(lats)
        p50 = lats[int(n * 0.50)]
        p90 = lats[min(n - 1, int(n * 0.90))]
        p99 = lats[min(n - 1, int(n * 0.99))]
        max_lat = lats[-1]
        mean_lat = sum(lats) / n

        max_queue = max((s["queue_depth"] for s in self.telemetry_samples), default=0)
        engine_utilization = min(100.0, (self.config.incoming_rate / max(1.0, self.config.processing_capacity)) * 100.0)

        throughput_ops = round((processed_count / (wall_time_ms / 1000.0)), 1) if wall_time_ms > 0 else 0.0

        return {
            "total_incoming_orders": total_incoming,
            "total_processed_orders": processed_count,
            "total_rejected_orders": rejected_count,
            "total_cancelled_orders": cancelled_count,
            "max_queue_depth": max_queue,
            "final_queue_depth": queue_remaining,
            "engine_utilization_pct": round(engine_utilization, 1),
            "measured_throughput_ops": throughput_ops,
            "latency": {
                "min_us": round(lats[0], 1),
                "mean_us": round(mean_lat, 1),
                "p50_us": round(p50, 1),
                "p90_us": round(p90, 1),
                "p99_us": round(p99, 1),
                "max_us": round(max_lat, 1),
            },
            "safeguards_triggered": {
                "idempotency_blocked": self.safeguards.duplicate_blocked_count,
                "invalid_payload_rejected": self.safeguards.invalid_payload_count,
                "queue_overflow_shed": self.safeguards.shed_order_count,
                "circuit_breaker_trips": self.safeguards.circuit_breaker_trips,
            },
            "wall_clock_bench_ms": round(wall_time_ms, 2),
        }

    def _generate_incident_report(
        self,
        invariant_results: Dict[str, Any],
        telemetry_summary: Dict[str, Any],
        recovery_duration_ms: float,
    ) -> Dict[str, Any]:
        """Produce an educational post-mortem incident report."""
        ft = self.config.failure_type
        all_passed = invariant_results["all_passed"]

        if ft == FailureType.NONE:
            trigger_title = "Normal Controlled Operation"
            trigger_desc = "Baseline simulation executed under nominal conditions without synthetic faults."
        elif ft == FailureType.TRAFFIC_SPIKE:
            trigger_title = "Ingress Traffic Spike (Queue Saturation)"
            trigger_desc = "Incoming order rate surged abruptly, testing event buffer bounds and backpressure mechanisms."
        elif ft == FailureType.ENGINE_PAUSE:
            trigger_title = "Transient Matching Engine Stall (Processing Freeze)"
            trigger_desc = "Simulation engine paused event matching temporarily, testing recovery backlog drainage and latency resumption."
        elif ft == FailureType.DUPLICATE_ORDER:
            trigger_title = "Network Packet Re-transmission / Duplicate Submission"
            trigger_desc = "Client re-submitted identical order identifiers in rapid succession, probing idempotency defenses."
        elif ft == FailureType.INVALID_PAYLOAD:
            trigger_title = "Malformed Payload Injection"
            trigger_desc = "Corrupted order structures (negative price, null quantities, invalid side) submitted to test input boundary sanitation."
        elif ft == FailureType.LIQUIDITY_DRYUP:
            trigger_title = "Sudden Liquidity Withdrawal Shock"
            trigger_desc = "Bulk cancellations emptied top order book tiers, testing spread blowout detection and circuit breaker tripwire."
        else:
            trigger_title = f"Simulated Fault: {ft.value}"
            trigger_desc = "Controlled disruption injected into isolated matching queue."

        sg = telemetry_summary["safeguards_triggered"]
        safeguard_notes = []
        if sg["idempotency_blocked"] > 0:
            safeguard_notes.append(f"Idempotency filter neutralized {sg['idempotency_blocked']} duplicate order submissions, preserving strict single-execution semantics.")
        if sg["invalid_payload_rejected"] > 0:
            safeguard_notes.append(f"Payload validation barrier intercepted {sg['invalid_payload_rejected']} malformed messages before reaching the core book.")
        if sg["queue_overflow_shed"] > 0:
            safeguard_notes.append(f"Rate limiting queue guard shed {sg['queue_overflow_shed']} overflowing events, defending memory stability.")
        if sg["circuit_breaker_trips"] > 0:
            safeguard_notes.append(f"Volatility Circuit Breaker tripped {sg['circuit_breaker_trips']} times to protect execution quality during spread widening.")
        if not safeguard_notes:
            safeguard_notes.append("System operated within safety thresholds; no defensive overrides were required.")

        recommendations = [
            "Maintain deterministic idempotency keys on client-side requests using UUIDv4 or client sequence numbers.",
            "Enforce strict payload boundaries (positive quantities, validated tick sizes) at gateway reverse proxies before ring-buffer ingestion.",
            "Implement active backpressure shedding (drop low-priority market data ticks or rate-limit aggressive cancels) during traffic bursts.",
            "Deploy auto-recovering circuit breakers that allow gradual un-halting via test auctions or liquidity auctions.",
        ]

        recovery_status = "FULL_RECOVERY" if all_passed else "INVARIANT_BREACH"

        return {
            "title": f"Incident Analysis: {trigger_title}",
            "scenario": self.config.scenario.value,
            "failure_mode": ft.value,
            "recovery_status": recovery_status,
            "trigger_summary": trigger_desc,
            "safeguard_effectiveness": safeguard_notes,
            "recovery_duration_ms": round(recovery_duration_ms, 2),
            "tail_latency_p99_us": telemetry_summary["latency"]["p99_us"],
            "all_invariants_preserved": all_passed,
            "recommendations": recommendations,
        }


# =====================================================================
# PUBLIC HIGH-LEVEL CONVENIENCE RUNNERS
# =====================================================================
def run_chaos_simulation(
    seed: int = 42,
    symbol: str = "BTCUSDT",
    num_events: int = 120,
    incoming_rate: float = 1000.0,
    num_participants: int = 10,
    cancel_rate_pct: float = 15.0,
    liquidity_depth: int = 20,
    processing_capacity: float = 2500.0,
    network_delay_ms: float = 5.0,
    queue_capacity: int = 100,
    scenario: str = "NORMAL",
    failure_type: str = "NONE",
) -> Dict[str, Any]:
    """Execute a single chaos simulation experiment with real measured telemetry."""
    sc_enum = SimulationScenario(scenario.upper()) if scenario.upper() in SimulationScenario._value2member_map_ else SimulationScenario.NORMAL
    ft_enum = FailureType(failure_type.upper()) if failure_type.upper() in FailureType._value2member_map_ else FailureType.NONE

    config = ChaosConfig(
        seed=seed,
        symbol=symbol.upper(),
        num_events=num_events,
        incoming_rate=incoming_rate,
        num_participants=num_participants,
        cancel_rate_pct=cancel_rate_pct,
        liquidity_depth=liquidity_depth,
        processing_capacity=processing_capacity,
        network_delay_ms=network_delay_ms,
        queue_capacity=queue_capacity,
        scenario=sc_enum,
        failure_type=ft_enum,
    )

    engine = ChaosSimulationEngine(config)
    return engine.run()


def compare_chaos_scenarios(
    seed: int = 42,
    symbol: str = "BTCUSDT",
    num_events: int = 120,
    baseline_scenario: str = "NORMAL",
    stressed_scenario: str = "HIGH_LOAD",
    failure_type: str = "ENGINE_PAUSE",
) -> Dict[str, Any]:
    """Compare baseline vs stressed/failure experiment using identical pseudorandom seeds."""
    base_res = run_chaos_simulation(
        seed=seed,
        symbol=symbol,
        num_events=num_events,
        scenario=baseline_scenario,
        failure_type="NONE",
    )

    stress_res = run_chaos_simulation(
        seed=seed,
        symbol=symbol,
        num_events=num_events,
        scenario=stressed_scenario,
        failure_type=failure_type,
    )

    t_base = base_res["telemetry"]
    t_stress = stress_res["telemetry"]

    diff_table = {
        "throughput_delta_ops": round(t_stress["measured_throughput_ops"] - t_base["measured_throughput_ops"], 1),
        "p50_latency_delta_us": round(t_stress["latency"]["p50_us"] - t_base["latency"]["p50_us"], 1),
        "p99_latency_delta_us": round(t_stress["latency"]["p99_us"] - t_base["latency"]["p99_us"], 1),
        "max_queue_depth_delta": t_stress["max_queue_depth"] - t_base["max_queue_depth"],
        "rejection_rate_base_pct": round((t_base["total_rejected_orders"] / max(1, t_base["total_incoming_orders"])) * 100.0, 1),
        "rejection_rate_stress_pct": round((t_stress["total_rejected_orders"] / max(1, t_stress["total_incoming_orders"])) * 100.0, 1),
        "recovery_duration_delta_ms": round(stress_res["invariants"]["recovery_duration_ms"] - base_res["invariants"]["recovery_duration_ms"], 2),
        "baseline_invariants_passed": base_res["invariants"]["all_passed"],
        "stressed_invariants_passed": stress_res["invariants"]["all_passed"],
    }

    return {
        "status": "success",
        "seed": seed,
        "symbol": symbol,
        "baseline": base_res,
        "stressed": stress_res,
        "comparison_deltas": diff_table,
    }
