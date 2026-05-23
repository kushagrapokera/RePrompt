import logging

from src.cleanup import cleanup
from src.intent_classifier import IntentClassifier
from src.enhancer import PromptEnhancer

logger = logging.getLogger(__name__)


class RePrompt:
    """Full RePrompt pipeline."""

    def __init__(
        self,
        base_model: str = "LiquidAI/LFM2.5-1.2B-Instruct",
        checkpoint_path: str = "lfm25_intent_cls_vanilla/pytorch_model.bin",
        device: str = "auto",
    ):
        logger.info("Initialising RePrompt pipeline …")
        self._classifier: IntentClassifier | None = None
        self._enhancer: PromptEnhancer | None = None
        self._base_model = base_model
        self._checkpoint_path = checkpoint_path
        self._device = device

    @property
    def classifier(self) -> IntentClassifier:
        if self._classifier is None:
            self._classifier = IntentClassifier(
                base_model_name=self._base_model,
                checkpoint_path=self._checkpoint_path,
                device=self._device,
            )
        return self._classifier

    @property
    def enhancer(self) -> PromptEnhancer:
        if self._enhancer is None:
            self._enhancer = PromptEnhancer(
                model_name=self._base_model,
                device=self._device,
            )
        return self._enhancer

    def run(
        self,
        query: str,
        *,
        skip_cleanup: bool = False,
        skip_spellfix: bool = False,
        skip_enhance: bool = False,
    ) -> dict:

        # Stage 1 — regex cleanup
        cleaned = query
        if not skip_cleanup:
            cleaned = cleanup(cleaned)

        # Stage 2 + 3 — intent classification + confidence/fallback check
        classification = self.classifier.classify(cleaned)

        # Stage 5 — intent-aware prompt enhancement
        enhanced = None
        if not skip_enhance:
            enhanced = self.enhancer.enhance(
                cleaned, classification["intent"]
            )

        return {
            "original": query,
            "cleaned": cleaned,
            "intent": classification["intent"],
            "confidence": classification["confidence"],
            "lfm_intent": classification.get("lfm_intent"),
            "lfm_confidence": classification.get("lfm_confidence"),
            "used_fallback": classification.get("used_fallback", False),
            "distilbert_intent": classification.get("distilbert_intent"),
            "distilbert_confidence": classification.get("distilbert_confidence"),
            "enhanced": enhanced,
        }
