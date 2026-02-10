"""Language detection utilities for ORTPS pipeline."""

from __future__ import annotations

import re

from lingua import Language, LanguageDetectorBuilder


class ImprovedLanguageDetector:
    """
    Improved two-stage language detection with tuned threshold.

    Stage 1: Non-Latin script detection via regex
    Stage 2: Lingua confidence threshold (lowered to 0.85 for better recall)
    """

    def __init__(self, confidence_threshold: float = 0.85):
        """
        Initialize language detector.

        Parameters
        ----------
        confidence_threshold : float
            Minimum confidence for English classification (default: 0.85)
        """
        # Non-Latin script patterns (Odia, Devanagari)
        self.script_re = re.compile(r'[\u0B00-\u0B7F\u0900-\u097F]')

        # Lingua detector with explicit language support
        # Note: Odia is detected via script regex in Stage 1
        self.detector = (
            LanguageDetectorBuilder
            .from_languages(Language.ENGLISH, Language.HINDI)
            .with_minimum_relative_distance(0.2)
            .build()
        )

        self.threshold = confidence_threshold

    def detect_batch(
        self,
        texts: list[str | None]
    ) -> tuple[list[str | None], dict[str, int]]:
        """
        Detect language for batch of texts.

        Parameters
        ----------
        texts : list[str | None]
            List of text strings to classify

        Returns
        -------
        labels : list[str | None]
            Language labels: 'en', 'non_en', or None
        stats : dict[str, int]
            Detection method distribution statistics
        """
        labels = [None] * len(texts)
        stats = {
            "script_filtered": 0,
            "lingua_high_conf": 0,
            "lingua_low_conf": 0,
            "null": 0
        }

        # Stage 1: Script detection
        latin_candidates = []
        for i, t in enumerate(texts):
            if t is None or not str(t).strip():
                stats["null"] += 1
                continue

            s = str(t)
            if self.script_re.search(s):
                labels[i] = 'non_en'
                stats["script_filtered"] += 1
            else:
                latin_candidates.append((i, s))

        if not latin_candidates:
            return labels, stats

        # Stage 2: Lingua batch processing
        idxs, vals = zip(*latin_candidates)
        en_scores = self.detector.compute_language_confidence_in_parallel(
            list(vals), Language.ENGLISH
        )

        for i, score in zip(idxs, en_scores):
            if score >= self.threshold:
                labels[i] = 'en'
                stats["lingua_high_conf"] += 1
            else:
                labels[i] = 'non_en'
                stats["lingua_low_conf"] += 1

        return labels, stats
