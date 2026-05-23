import logging

from transformers import (
    AutoModelForCausalLM,
    AutoModelForSequenceClassification,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, TaskType
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)

# The 7 intents the model was fine-tuned on
INTENTS = [
    "general_qa",
    "coding",
    "creative_writing",
    "email",
    "summarization",
    "learning",
    "planning",
]
label2id = {n: i for i, n in enumerate(INTENTS)}
id2label = {i: n for i, n in enumerate(INTENTS)}
NUM_LABELS = len(INTENTS)

# LoRA config matching the training setup
LORA_CONFIG = LoraConfig(
    r=32,
    lora_alpha=64,
    lora_dropout=0.05,
    bias="none",
    task_type=TaskType.SEQ_CLS,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
)


class LFMClassifier(nn.Module):

    def __init__(self, backbone, num_labels, id2label, label2id):
        super().__init__()
        self.backbone = backbone
        self.num_labels = num_labels
        self.id2label = id2label
        self.label2id = label2id
        hidden_size = backbone.config.hidden_size
        self.classifier = nn.Linear(hidden_size, num_labels)

    def forward(self, input_ids=None, attention_mask=None, labels=None):
        outputs = self.backbone(
            input_ids=input_ids,
            attention_mask=attention_mask,
            output_hidden_states=True,
        )
        last_hidden = outputs.hidden_states[-1]
        if attention_mask is not None:
            lengths = attention_mask.sum(dim=1) - 1
            batch_indices = torch.arange(last_hidden.size(0), device=last_hidden.device)
            pooled = last_hidden[batch_indices, lengths]
        else:
            pooled = last_hidden[:, -1, :]
        logits = self.classifier(pooled)
        loss = None
        if labels is not None:
            loss = nn.functional.cross_entropy(logits, labels)
        return {"loss": loss, "logits": logits}


class IntentClassifier:

    def __init__(
        self,
        base_model_name: str = "LiquidAI/LFM2.5-1.2B-Instruct",
        checkpoint_path: str = "lfm25_intent_cls_vanilla/pytorch_model.bin",
        fallback_model_path: str = "distilbert_intent_model",
        device: str = "auto",
    ):
        if device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        # --- DistilBERT label mapping (from label_mapping.csv) ---
        self._distil_id2label = {
            0: "coding", 1: "creative_writing", 2: "email",
            3: "general_qa", 4: "learning", 5: "planning", 6: "summarization",
        }

        # --- 1. Load 4-bit backbone (same bnb_config as training) ---
        logger.info("Loading 4-bit base model %s on %s …", base_model_name, self.device)
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        backbone = AutoModelForCausalLM.from_pretrained(
            base_model_name,
            quantization_config=bnb_config,
            device_map={"": 0} if self.device == "cuda" else None,
            trust_remote_code=True,
        )
        backbone.config.pad_token_id = backbone.config.eos_token_id
        backbone.config.use_cache = False

        # --- 2. Apply LoRA (same config as training) ---
        logger.info("Applying LoRA adapters …")
        backbone = prepare_model_for_kbit_training(backbone)
        backbone = get_peft_model(backbone, LORA_CONFIG)

        # --- 3. Wrap in classifier head ---
        logger.info("Building classifier head …")
        self.model = LFMClassifier(
            backbone=backbone,
            num_labels=NUM_LABELS,
            id2label=id2label,
            label2id=label2id,
        )

        # --- 4. Load trained weights ---
        logger.info("Loading trained weights from %s …", checkpoint_path)
        sd = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        self.model.load_state_dict(sd, strict=False)
        self.model.to(self.device)
        self.model.eval()

        # --- 5. Primary tokenizer ---
        logger.info("Loading tokenizer …")
        self.tokenizer = AutoTokenizer.from_pretrained(base_model_name, trust_remote_code=True)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # --- 6. Fallback DistilBERT ---
        logger.info("Loading fallback DistilBERT from %s …", fallback_model_path)
        self._fallback = AutoModelForSequenceClassification.from_pretrained(fallback_model_path)
        self._fallback.eval()
        self._fallback_tokenizer = AutoTokenizer.from_pretrained(fallback_model_path)

    def classify(self, query: str, max_length: int = 2048, confidence_threshold: float = 0.5) -> dict:

        # --- Primary model ---
        inputs = self.tokenizer(query, return_tensors="pt", truncation=True, max_length=max_length)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs["logits"]
            probs = torch.softmax(logits, dim=-1)
            pred_id = logits.argmax(dim=-1).item()
            primary_intent = id2label[pred_id]
            primary_confidence = probs[0, pred_id].item()
            intent = primary_intent
            confidence = primary_confidence

        # --- Fallback when primary is uncertain ---
        used_fallback = False
        if confidence < confidence_threshold:
            used_fallback = True
            logger.debug("Low confidence (%.3f < %.2f) for %s, running DistilBERT fallback",
                         confidence, confidence_threshold, intent)
            fb_inputs = self._fallback_tokenizer(
                query, return_tensors="pt", truncation=True, max_length=512
            )
            with torch.no_grad():
                fb_out = self._fallback(**fb_inputs)
                fb_probs = torch.softmax(fb_out.logits, dim=-1)
                fb_id = fb_out.logits.argmax(dim=-1).item()
                fb_intent = self._distil_id2label[fb_id]
                fb_confidence = fb_probs[0, fb_id].item()
                intent = fb_intent
                confidence = fb_confidence
            # If even the fallback is too uncertain, default to general_qa
            if confidence < confidence_threshold:
                logger.debug("Fallback also uncertain (%.3f < %.2f), defaulting to general_qa",
                             confidence, confidence_threshold)
                intent = "general_qa"
                confidence = 1.0
            logger.debug("Fallback DistilBERT: %s (confidence: %.3f)", intent, confidence)

        logger.debug("Intent: %s (confidence: %.3f) for query: %s", intent, confidence, query)

        return {
            "intent": intent,
            "confidence": round(confidence, 4),
            "raw_output": logits.cpu().tolist()[0],
            "lfm_intent": primary_intent,
            "lfm_confidence": round(primary_confidence, 4),
            "used_fallback": used_fallback,
            "distilbert_intent": fb_intent if used_fallback else None,
            "distilbert_confidence": round(fb_confidence, 4) if used_fallback else None,
        }
