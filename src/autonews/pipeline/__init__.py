from __future__ import annotations

from ..config import Settings
from ..db import finish_run, start_run
from .cluster import cluster
from .extract import extract
from .ingest import ingest
from .score import score_stories
from .summarize import draft_candidates

STAGES = {
    "ingest": ingest,
    "extract": extract,
    "cluster": cluster,
    "score": score_stories,
    "draft": draft_candidates,
}


def run_stage(settings: Settings, stage: str, **kwargs) -> dict:
    run_id = start_run(stage)
    try:
        counters = STAGES[stage](settings, **kwargs)
        finish_run(run_id, counters, list(counters.get("errors", [])))
        return counters
    except Exception as exc:
        finish_run(run_id, {}, [str(exc)])
        raise


def run_pipeline(settings: Settings, stages: list[str] | None = None) -> dict:
    results: dict[str, dict] = {}
    for stage in stages or list(STAGES):
        results[stage] = run_stage(settings, stage)
    return results
