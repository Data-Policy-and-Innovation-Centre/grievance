"""Reusable two-stage language detection utilities for pipeline workflows."""

from __future__ import annotations

import re
from re import Pattern

from lingua import Language, LanguageDetectorBuilder


class TwoStageLanguageDetector:
    """Two-stage language detector with script pre-filter + Lingua confidence."""

    def __init__(
        self,
        confidence_threshold: float,
        script_pattern: str | Pattern[str],
        lingua_languages: tuple[Language, ...],
        target_language: Language = Language.ENGLISH,
        en_label: str = "en",
        non_en_label: str = "non_en",
        minimum_relative_distance: float = 0.2,
        non_target_markers: tuple[str, ...] | None = None,
        marker_min_hits: int = 2,
    ) -> None:
        """
        Initialize the detector.

        Parameters
        ----------
        confidence_threshold : float
            Minimum confidence required to classify text as `en_label`.
        script_pattern : str | Pattern[str]
            Regex (or compiled regex) for scripts to classify directly as `non_en_label`.
        lingua_languages : tuple[Language, ...]
            Languages passed into Lingua detector construction.
        target_language : Language
            Lingua target language for confidence scoring.
        en_label : str
            Output label for target language.
        non_en_label : str
            Output label for non-target language.
        minimum_relative_distance : float
            Lingua minimum relative distance parameter.
        non_target_markers : tuple[str, ...] | None
            Optional lexical markers to classify text as non-target language
            before Lingua scoring (useful for romanized local-language text).
        marker_min_hits : int
            Minimum marker hits required to trigger non-target classification.
        """
        self.script_re = (
            re.compile(script_pattern)
            if isinstance(script_pattern, str)
            else script_pattern
        )

        self.detector = (
            LanguageDetectorBuilder
            .from_languages(*lingua_languages)
            .with_minimum_relative_distance(minimum_relative_distance)
            .build()
        )

        self.target_language = target_language
        self.threshold = confidence_threshold  # Backward-compatible attribute name
        self.en_label = en_label
        self.non_en_label = non_en_label
        self.non_target_markers = tuple(m.lower() for m in (non_target_markers or ()))
        self.marker_min_hits = marker_min_hits

    def _has_non_target_markers(self, text: str) -> bool:
        """Check whether a text contains enough configured non-target markers."""
        if not self.non_target_markers:
            return False

        tokens = set(re.findall(r"\b[a-z]{2,}\b", text.lower()))
        hits = sum(1 for marker in self.non_target_markers if marker in tokens)
        return hits >= self.marker_min_hits

    def detect_batch(
        self,
        texts: list[str | None],
    ) -> tuple[list[str | None], dict[str, int]]:
        """
        Detect language labels for a batch of texts.

        Returns
        -------
        labels : list[str | None]
            One label per input: `en_label`, `non_en_label`, or None for null/blank.
        stats : dict[str, int]
            Method-wise counters preserved for compatibility.
        """
        labels: list[str | None] = [None] * len(texts)
        stats = {
            "script_filtered": 0,
            "lingua_high_conf": 0,
            "lingua_low_conf": 0,
            "null": 0,
        }

        latin_candidates: list[tuple[int, str]] = []
        for i, text in enumerate(texts):
            if text is None or not str(text).strip():
                stats["null"] += 1
                continue

            value = str(text)
            if self.script_re.search(value):
                labels[i] = self.non_en_label
                stats["script_filtered"] += 1
            elif self._has_non_target_markers(value):
                # Keep compatibility with historical stats keys by counting these
                # as low-confidence non-English outcomes.
                labels[i] = self.non_en_label
                stats["lingua_low_conf"] += 1
            else:
                latin_candidates.append((i, value))

        if not latin_candidates:
            return labels, stats

        idxs, vals = zip(*latin_candidates)
        scores = self.detector.compute_language_confidence_in_parallel(
            list(vals),
            self.target_language,
        )

        for idx, score in zip(idxs, scores):
            if score >= self.threshold:
                labels[idx] = self.en_label
                stats["lingua_high_conf"] += 1
            else:
                labels[idx] = self.non_en_label
                stats["lingua_low_conf"] += 1

        return labels, stats
