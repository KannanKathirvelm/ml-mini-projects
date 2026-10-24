"""Count tracked objects crossing a virtual line.

Detection alone can't count "how many cars passed" - the same car appears in
many frames. With tracking each object keeps an ID, so we only need to notice
when an ID's centre moves from one side of the line to the other. The side is
the sign of a 2-D cross product, which works for any line angle.
"""
from __future__ import annotations

from collections import defaultdict

import cv2

from detector import Detection


class LineCounter:
    def __init__(self, p1: tuple[int, int], p2: tuple[int, int]):
        self.p1, self.p2 = p1, p2
        self._last_side: dict[int, int] = {}
        self._counted: set[int] = set()
        self.forward = defaultdict(int)   # crossed from negative to positive side
        self.backward = defaultdict(int)

    @classmethod
    def vertical_center(cls, width: int, height: int) -> "LineCounter":
        return cls((width // 2, 0), (width // 2, height))

    @classmethod
    def horizontal_center(cls, width: int, height: int) -> "LineCounter":
        return cls((0, height // 2), (width, height // 2))

    def _side(self, x: float, y: float) -> int:
        (x1, y1), (x2, y2) = self.p1, self.p2
        cross = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
        return 1 if cross > 0 else -1 if cross < 0 else 0

    def update(self, detections: list[Detection]) -> None:
        for d in detections:
            if d.track_id is None:
                continue
            cx, cy = (d.box[0] + d.box[2]) / 2, (d.box[1] + d.box[3]) / 2
            side = self._side(cx, cy)
            prev = self._last_side.get(d.track_id)
            if side != 0:
                self._last_side[d.track_id] = side
            # Count each ID once so jitter around the line doesn't double count.
            if prev and side and prev != side and d.track_id not in self._counted:
                self._counted.add(d.track_id)
                (self.forward if side > 0 else self.backward)[d.cls_name] += 1

    @property
    def totals(self) -> dict[str, int]:
        keys = set(self.forward) | set(self.backward)
        return {k: self.forward.get(k, 0) + self.backward.get(k, 0) for k in sorted(keys)}

    def draw(self, frame) -> None:
        cv2.line(frame, self.p1, self.p2, (0, 255, 255), 2)
        text = "Crossed: " + (", ".join(f"{k} {v}" for k, v in self.totals.items()) or "0")
        cv2.putText(frame, text, (10, frame.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, text, (10, frame.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (0, 255, 255), 2, cv2.LINE_AA)
