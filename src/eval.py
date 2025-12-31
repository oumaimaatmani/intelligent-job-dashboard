from typing import List, Set, Dict, Callable, Tuple

def precision_at_k(recommended: List[str], relevant: Set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top_k = recommended[:k]
    if not top_k:
        return 0.0
    hit_count = sum(1 for r in top_k if r in relevant)
    return hit_count / len(top_k)


def recall_at_k(recommended: List[str], relevant: Set[str], k: int) -> float:
    if not relevant:
        return 0.0
    top_k = recommended[:k]
    hit_count = sum(1 for r in top_k if r in relevant)
    return hit_count / len(relevant)


def mrr(recommended: List[str], relevant: Set[str]) -> float:
    for idx, rec in enumerate(recommended, start=1):
        if rec in relevant:
            return 1.0 / idx
    return 0.0


def evaluate_recommender(
    recommender_fn: Callable[[str, int], List[str]],
    queries: List[str],
    ground_truth: Dict[str, Set[str]],
    ks: List[int] = [1, 5, 10],
) -> Dict[str, Dict[str, float]]:
    """Evaluate a recommender function.

    recommender_fn(query, k) -> list of recommended item ids (strings)
    ground_truth: mapping query -> set of relevant ids

    Returns aggregated metrics for each k and MRR.
    """
    results = {f"P@{k}": [] for k in ks}
    results.update({f"R@{k}": [] for k in ks})
    mrrs = []

    for q in queries:
        relevant = ground_truth.get(q, set())
        # ask recommender for max k
        max_k = max(ks)
        recs = recommender_fn(q, max_k)

        for k in ks:
            results[f"P@{k}"].append(precision_at_k(recs, relevant, k))
            results[f"R@{k}"].append(recall_at_k(recs, relevant, k))

        mrrs.append(mrr(recs, relevant))

    aggregated = {}
    for metric, vals in results.items():
        aggregated[metric] = float(sum(vals) / len(vals)) if vals else 0.0

    aggregated["MRR"] = float(sum(mrrs) / len(mrrs)) if mrrs else 0.0
    return aggregated


if __name__ == "__main__":
    # Example usage (pseudo):
    def dummy_recommender(q, k):
        # return item ids as strings
        return ["id1", "id2", "id3"]

    queries = ["data scientist", "data engineer"]
    gt = {"data scientist": {"id2"}, "data engineer": {"id3", "id4"}}
    print(evaluate_recommender(dummy_recommender, queries, gt))
