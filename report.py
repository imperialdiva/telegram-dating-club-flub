import csv
import os
from typing import TYPE_CHECKING, List

from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from benchmark import RunResult


def _size_label(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes // 1024} KB"
    return f"{size_bytes // (1024 * 1024)} MB"


def _degraded_label(degraded: bool) -> str:
    return "[red]YES[/]" if degraded else "[green]no[/]"


def print_results_table(results: "List[RunResult]", console: Console) -> None:
    experiments = {r.experiment for r in results}
    experiment_labels = {
        "baseline": "1. Базовое сравнение",
        "msg_size": "2. Влияние размера сообщения",
        "rate": "3. Влияние интенсивности",
    }

    for exp_key in ("baseline", "msg_size", "rate"):
        exp_results = [r for r in results if r.experiment == exp_key]
        if not exp_results:
            continue

        table = Table(
            title=experiment_labels.get(exp_key, exp_key),
            show_lines=True,
            header_style="bold magenta",
        )
        table.add_column("Брокер", style="cyan", min_width=10)
        table.add_column("Размер", justify="right")
        table.add_column("Цель msg/s", justify="right")
        table.add_column("Отправлено", justify="right")
        table.add_column("Получено", justify="right")
        table.add_column("Потеряно", justify="right", style="red")
        table.add_column("Факт. send/s", justify="right")
        table.add_column("Факт. recv/s", justify="right")
        table.add_column("Avg lat, ms", justify="right")
        table.add_column("p95 lat, ms", justify="right")
        table.add_column("Max lat, ms", justify="right")
        table.add_column("Деградация", justify="center")

        for r in exp_results:
            lost_style = "[red]" if r.lost > 0 else ""
            table.add_row(
                r.broker,
                _size_label(r.msg_size_bytes),
                f"{r.target_rate:,}",
                f"{r.sent:,}",
                f"{r.received:,}",
                f"{lost_style}{r.lost:,}{'[/]' if lost_style else ''}",
                f"{r.actual_send_rate:,.1f}",
                f"{r.actual_recv_rate:,.1f}",
                f"{r.avg_latency_ms:.2f}",
                f"{r.p95_latency_ms:.2f}",
                f"{r.max_latency_ms:.2f}",
                _degraded_label(r.degraded),
            )

        console.print(table)
        console.print()

    _print_conclusions(results, console)


def _print_conclusions(results: "List[RunResult]", console: Console) -> None:
    console.rule("[bold yellow]Выводы[/]")

    rabbitmq_results = [r for r in results if r.broker == "RabbitMQ"]
    redis_results = [r for r in results if r.broker == "Redis"]

    def avg_recv_rate(rs):
        rates = [r.actual_recv_rate for r in rs if r.received > 0]
        return sum(rates) / len(rates) if rates else 0.0

    rmq_avg = avg_recv_rate(rabbitmq_results)
    redis_avg = avg_recv_rate(redis_results)

    winner_throughput = "RabbitMQ" if rmq_avg >= redis_avg else "Redis"
    console.print(
        f"  Пропускная способность: [bold cyan]{winner_throughput}[/] в среднем быстрее "
        f"(RabbitMQ {rmq_avg:,.0f} msg/s  vs  Redis {redis_avg:,.0f} msg/s)"
    )

    def avg_p95(rs):
        lats = [r.p95_latency_ms for r in rs if r.latencies_ms]
        return sum(lats) / len(lats) if lats else float("inf")

    rmq_p95 = avg_p95(rabbitmq_results)
    redis_p95 = avg_p95(redis_results)
    winner_latency = "RabbitMQ" if rmq_p95 <= redis_p95 else "Redis"
    console.print(
        f"  Latency p95: [bold cyan]{winner_latency}[/] меньше "
        f"(RabbitMQ {rmq_p95:.2f} ms  vs  Redis {redis_p95:.2f} ms)"
    )

    for broker_name, br_results in (("RabbitMQ", rabbitmq_results), ("Redis", redis_results)):
        degraded = [r for r in br_results if r.degraded]
        if degraded:
            rates = sorted({r.target_rate for r in degraded})
            console.print(
                f"  [bold]{broker_name}[/] начинает деградировать "
                f"при нагрузке >= [red]{rates[0]:,}[/] msg/s"
            )
        else:
            console.print(
                f"  [bold]{broker_name}[/] — деградации не зафиксировано в рамках теста"
            )

    console.print()


def save_csv(results: "List[RunResult]") -> None:
    os.makedirs("results", exist_ok=True)
    path = os.path.join("results", "report.csv")

    fieldnames = [
        "broker",
        "experiment",
        "msg_size_bytes",
        "target_rate",
        "duration_sec",
        "sent",
        "received",
        "lost",
        "actual_send_rate",
        "actual_recv_rate",
        "avg_latency_ms",
        "p95_latency_ms",
        "max_latency_ms",
        "degraded",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(
                {
                    "broker": r.broker,
                    "experiment": r.experiment,
                    "msg_size_bytes": r.msg_size_bytes,
                    "target_rate": r.target_rate,
                    "duration_sec": f"{r.duration_sec:.2f}",
                    "sent": r.sent,
                    "received": r.received,
                    "lost": r.lost,
                    "actual_send_rate": f"{r.actual_send_rate:.2f}",
                    "actual_recv_rate": f"{r.actual_recv_rate:.2f}",
                    "avg_latency_ms": f"{r.avg_latency_ms:.4f}",
                    "p95_latency_ms": f"{r.p95_latency_ms:.4f}",
                    "max_latency_ms": f"{r.max_latency_ms:.4f}",
                    "degraded": r.degraded,
                }
            )
