"""Pure rank fusion; never adds incompatible BM25 and cosine scores."""


def rrf(lists: list[list[dict]], top_k: int = 5, k: int = 60) -> list[dict]:
    if type(top_k) is not int or top_k < 1 or type(k) is not int or k < 1:
        raise ValueError("top_k and k must be positive integers")
    rows, scores = {}, {}
    for results in lists:
        seen = set()
        for row in results:
            identity = row["id"]
            if identity in seen:
                continue
            seen.add(identity)
            rows.setdefault(identity, row)
            scores[identity] = scores.get(identity, 0.0) + 1 / (k + len(seen))
    order = sorted(rows, key=lambda identity: -scores[identity])
    return [{**rows[identity], "score": scores[identity]} for identity in order[:top_k]]
