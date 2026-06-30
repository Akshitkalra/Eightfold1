"""End-to-end pipeline wiring: detect -> extract -> normalize -> merge ->
confidence -> project -> validate.

Kept separate from the CLI so it can be called from tests and any UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .adapters import github
from .canonical import RawRecord
from .detect import load_path
from .merge import merge_records
from .project import project_all
from .validate import validate_all


@dataclass
class PipelineResult:
    profiles: list[dict]
    warnings: list[str] = field(default_factory=list)
    validation: dict = field(default_factory=dict)  # {index: [errors]}


def run(
    input_paths: list[str],
    github_logins: list[str] | None = None,
    config: dict | None = None,
) -> PipelineResult:
    """Run the full pipeline. Robust: bad/missing sources warn, never crash."""
    config = config or {}
    warnings: list[str] = []
    raws: list[RawRecord] = []

    # Structured + unstructured file sources.
    for path in input_paths or []:
        raws.extend(load_path(path, warnings))

    # Live GitHub source(s).
    for login in github_logins or []:
        fetched = github.fetch(login)
        if not fetched:
            warnings.append(f"no data from github source: {login}")
        raws.extend(fetched)

    canon = merge_records(raws)
    outputs = project_all(canon, config)
    validation = validate_all(outputs, config)
    return PipelineResult(profiles=outputs, warnings=warnings, validation=validation)
