from dataclasses import dataclass, field
from typing import List


@dataclass
class BrokerConfig:
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_queue: str = "benchmark_queue"
    redis_url: str = "redis://localhost:6379"
    redis_stream: str = "benchmark_stream"
    redis_group: str = "benchmark_group"
    redis_consumer: str = "consumer_1"


@dataclass
class TestConfig:
    # длительность одного прогона в секундах
    run_duration_sec: int = 30

    # порог отставания consumer (сообщений в backlog) для фиксации точки деградации
    degradation_backlog_threshold: int = 1000

    # размеры сообщений в байтах
    message_sizes: List[int] = field(default_factory=lambda: [128, 1024, 10_240, 102_400])

    # целевые интенсивности в сообщениях/сек
    rates_msg_per_sec: List[int] = field(default_factory=lambda: [1_000, 5_000, 10_000])

    # базовые значения для сравнительного теста
    baseline_size_bytes: int = 1024
    baseline_rate_msg_per_sec: int = 1_000

    # интервал сбора метрик (сек) для расчёта rolling-throughput
    metrics_window_sec: float = 1.0


BROKER = BrokerConfig()
TEST = TestConfig()
