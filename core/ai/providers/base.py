from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field


@dataclass
class ProviderConfig:
    name: str
    type: str  # "openai", "anthropic", "google", "ollama"
    api_key: str = ""
    base_url: str = ""
    default_model: str = ""
    models: list[str] = field(default_factory=list)
    enabled: bool = True
    extra: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["api_key"] = self.api_key
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ProviderConfig":
        return cls(
            name=data.get("name", ""),
            type=data.get("type", ""),
            api_key=data.get("api_key", ""),
            base_url=data.get("base_url", ""),
            default_model=data.get("default_model", ""),
            models=data.get("models", []),
            enabled=data.get("enabled", True),
            extra=data.get("extra", {}),
        )


class BaseProvider(ABC):
    def __init__(self, config: ProviderConfig):
        self.config = config

    @abstractmethod
    def complete(
        self,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        temp: float = 0.1,
        json_mode: bool = False,
        timeout: int = 120,
    ) -> str:
        ...

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        ...

    def get_models(self) -> list[str]:
        return self.config.models or [self.config.default_model] if self.config.default_model else []

    def to_dict(self) -> dict:
        return self.config.to_dict()
