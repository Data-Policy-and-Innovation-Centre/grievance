from dataclasses import dataclass, field
from app.config import directories

@dataclass
class ClientStats:
    endpoint: str
    total_requests: int = 0
    times: list[float] = field(default_factory=list)
    success_count: int = 0
    error_count: int = 0
    error_types: list[str] = field(default_factory=list)
    
    @property
    def latency(self) -> float:
        return sum(self.times) / self.total_requests if self.total_requests > 0 else 0
    
    @property
    def error_rate(self) -> float:
        return self.error_count / self.total_requests if self.total_requests > 0 else 0
    
    @property
    def success_rate(self) -> float:
        return self.success_count / self.total_requests if self.total_requests > 0 else 0
    
    def __str__(self) -> str:
        return f"ClientStats(endpoint={self.endpoint}, total_requests={self.total_requests}, total_time={self.total_time}, success_count={self.success_count}, error_count={self.error_count})"
    
    def __repr__(self) -> str:
        return self.__str__()
    
    def add_timing(self, response_time: float, success: bool, error_type: str):
        if success:
            self.success_count += 1
        else:
            self.error_count += 1
            self.error_types.append(error_type)
        self.times.append(response_time)
        self.total_requests += 1

    def _get_summary(self) -> dict:
        return {
            "endpoint": self.endpoint,
            "total_requests": self.total_requests,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "error_types": self.error_types,
            "latency": self.latency,
            "error_rate": self.error_rate,
            "success_rate": self.success_rate
        }
    
    def format_summary(self) -> str:
        summary = self._get_summary()
        lines = [
            f"Endpoint: {summary['endpoint']}",
            f"Total Requests: {summary['total_requests']}",
            f"Success Count: {summary['success_count']}",
            f"Error Count: {summary['error_count']}",
            f"Success Rate: {summary['success_rate']:.2%}",
            f"Error Rate: {summary['error_rate']:.2%}",
            f"Average Latency: {summary['latency']:.3f} seconds",
        ]
        if summary["error_types"]:
            lines.append(f"Error Types: {', '.join(summary['error_types'])}")
        summary = "\n".join(lines) + "\n\n"
        return summary
    
    def save_summary(self, file_name: str):
        with open(directories.LOGS / file_name, "w") as f:
            f.write(self.format_summary())