from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CheckResult:
    name: str
    ok: bool
    message: str
    details: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SelfTestReport:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, result: CheckResult) -> None:
        self.results.append(result)

    @property
    def success(self) -> bool:
        return all(r.ok for r in self.results)
