from dataclasses import dataclass
@dataclass
class PkgRepo:
    api: str
    org: str
    repo: str
    branch: str | None = None
    commit: str | None = None
