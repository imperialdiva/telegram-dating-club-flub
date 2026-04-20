import asyncio
import statistics
import time
from dataclasses import dataclass, field
from typing import List, Type

from rich.console import Console
from rich.live import Live
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.text import Text

from brokers.rabbitmq_broker import RabbitMQBroker
from brokers.redis_broker import RedisBroker
from config import BROKER, TEST
from report import print_results_table, save_csv

console = Console()


@dataclass
class RunResult:
    broker: str
    experiment: str
    msg_size_bytes: int
    target_rate: int
    duration_sec: float
    sent: int
    received: int
    latencies_ms: List[float]
    degraded: bool = False

    @property
    def lost(self) -> int:
        return max(0, self.sent - self.received)

    @property
    def avg_latency_ms(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def p95_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_l = sorted(self.latencies_ms)
        idx = int(len(sorted_l) * 0.95)
        return sorted_l[min(idx, len(sorted_l) - 1)]

    @property
    def max_latency_ms(self) -> float:
        return max(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def actual_send_rate(self) -> float:
        return self.sent / self.duration_sec if self.duration_sec > 0 else 0.0

    @property
    def actual_recv_rate(self) -> float:
        return self.received / self.duration_sec if self.duration_sec > 0 else 0.0


async def run_single(
    broker_cls: Type,
    experiment: str,
    msg_size: int,
    rate: int,
    duration: float,
    progress: Progress,
    task_id,
) -> RunResult:
    broker = broker_cls()
    await broker.connect()
    await broker.purge()

    sent_counter = [0]
    recv_counter = [0]
    latencies: List[float] = []
    stop_event = asyncio.Event()

    degraded = False
    degradation_time: float | None = None

    async def _monitor() -> None:
        nonlocal degraded, degradation_time
        await asyncio.sleep(1.0)
        while not stop_event.is_set():
            backlog = sent_counter[0] - recv_counter[0]
            if backlog > TEST.degradation_backlog_threshold and not degraded:
                degraded = True
                degradation_time = time.monotonic()
            await asyncio.sleep(TEST.metrics_window_sec)

    async def _progress_updater() -> None:
        while not stop_event.is_set():
            progress.advance(task_id, advance=0)
            progress.update(
                task_id,
                description=(
                    f"[cyan]{broker.name}[/] [{experiment}] "
                    f"{msg_size}B @{rate}msg/s  "
                    f"sent=[green]{sent_counter[0]}[/] "
                    f"recv=[blue]{recv_counter[0]}[/]"
                ),
            )
            await asyncio.sleep(0.5)

    t0 = time.monotonic()

    producer_task = asyncio.create_task(
        broker.produce(msg_size, rate, duration, sent_counter, stop_event)
    )
    consumer_task = asyncio.create_task(
        broker.consume(latencies, recv_counter, stop_event)
    )
    monitor_task = asyncio.create_task(_monitor())
    progress_task = asyncio.create_task(_progress_updater())

    await producer_task

    try:
        await asyncio.wait_for(consumer_task, timeout=5.0)
    except asyncio.TimeoutError:
        consumer_task.cancel()

    monitor_task.cancel()
    progress_task.cancel()

    elapsed = time.monotonic() - t0
    await broker.close()

    return RunResult(
        broker=broker.name,
        experiment=experiment,
        msg_size_bytes=msg_size,
        target_rate=rate,
        duration_sec=elapsed,
        sent=sent_counter[0],
        received=recv_counter[0],
        latencies_ms=latencies,
        degraded=degraded,
    )


async def experiment_baseline(progress: Progress) -> List[RunResult]:
    results = []
    size = TEST.baseline_size_bytes
    rate = TEST.baseline_rate_msg_per_sec
    dur = float(TEST.run_duration_sec)

    for broker_cls in (RabbitMQBroker, RedisBroker):
        task_id = progress.add_task("", total=None)
        r = await run_single(broker_cls, "baseline", size, rate, dur, progress, task_id)
        results.append(r)
        progress.remove_task(task_id)

    return results


async def experiment_message_sizes(progress: Progress) -> List[RunResult]:
    results = []
    rate = TEST.baseline_rate_msg_per_sec
    dur = float(TEST.run_duration_sec)

    for size in TEST.message_sizes:
        for broker_cls in (RabbitMQBroker, RedisBroker):
            task_id = progress.add_task("", total=None)
            r = await run_single(broker_cls, "msg_size", size, rate, dur, progress, task_id)
            results.append(r)
            progress.remove_task(task_id)

    return results


async def experiment_rates(progress: Progress) -> List[RunResult]:
    results = []
    size = TEST.baseline_size_bytes
    dur = float(TEST.run_duration_sec)

    for rate in TEST.rates_msg_per_sec:
        for broker_cls in (RabbitMQBroker, RedisBroker):
            task_id = progress.add_task("", total=None)
            r = await run_single(broker_cls, "rate", size, rate, dur, progress, task_id)
            results.append(r)
            progress.remove_task(task_id)

    return results


async def main() -> None:
    console.rule("[bold yellow]Broker Benchmark: RabbitMQ vs Redis[/]")

    progress = Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )

    all_results: List[RunResult] = []

    with progress:
        console.print("\n[bold]Эксперимент 1: Базовое сравнение[/]")
        all_results += await experiment_baseline(progress)

        console.print("\n[bold]Эксперимент 2: Влияние размера сообщения[/]")
        all_results += await experiment_message_sizes(progress)

        console.print("\n[bold]Эксперимент 3: Влияние интенсивности потока[/]")
        all_results += await experiment_rates(progress)

    console.print()
    print_results_table(all_results, console)
    save_csv(all_results)
    console.print("\n[green]Результаты сохранены в results/report.csv[/]")


if __name__ == "__main__":
    asyncio.run(main())
