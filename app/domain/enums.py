from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class ReportFormat(str, Enum):
    JSON = "json"
    MARKDOWN = "markdown"


class RebalanceFrequency(str, Enum):
    DAILY = "D"
    WEEKLY = "W"
    MONTHLY = "M"


class WeightingMethod(str, Enum):
    EQUAL = "equal"
    SCORE = "score"


class BenchmarkType(str, Enum):
    EQUAL_WEIGHT_UNIVERSE = "equal_weight_universe"
