"""Tiny shared formatter so CLI and UI print rupees the same way."""


def inr(amount: float | None) -> str:
    if amount is None:
        return "-"
    # Indian digit grouping: 1,23,456
    whole = f"{int(round(amount)):d}"
    head, tail = whole[:-3], whole[-3:]
    if head:
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return f"Rs {whole}"
