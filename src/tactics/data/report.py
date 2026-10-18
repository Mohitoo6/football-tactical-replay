"""A quality report: the checks an input passed or failed, so the system can refuse instead of guessing.

Used by every way data enters the system (drone video, uploaded coordinate files).
"""

from dataclasses import dataclass, field


@dataclass
class Check:
    name: str
    passed: bool
    value: str
    requirement: str
    blocking: bool = True  # a failed blocking check rejects the clip; a non-blocking one only warns


@dataclass
class QualityReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, passed: bool, value: str, requirement: str, blocking: bool = True) -> None:
        self.checks.append(Check(name, bool(passed), value, requirement, blocking))

    @property
    def status(self) -> str:
        if any(not c.passed and c.blocking for c in self.checks):
            return "rejected"
        return "warning" if any(not c.passed for c in self.checks) else "ok"

    def summary(self) -> str:
        lines = [f"Quality: {self.status.upper()}"]
        for c in self.checks:
            mark = "ok  " if c.passed else ("FAIL" if c.blocking else "warn")
            lines.append(f"  [{mark}] {c.name}: {c.value} (needs {c.requirement})")
        return "\n".join(lines)
