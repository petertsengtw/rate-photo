import json

from app.models import Criteria


def compute_weighted_total(criteria_scores: dict[str, int], criteria_list: list[Criteria]) -> float:
    total_weight = sum(c.weight for c in criteria_list)
    if total_weight == 0:
        return 0.0
    weighted_sum = sum(criteria_scores.get(c.name, 0) * c.weight for c in criteria_list)
    return round(weighted_sum / total_weight, 4)


def parse_criteria_json(raw: str) -> dict[str, int]:
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in data.items()} if isinstance(data, dict) else {}
