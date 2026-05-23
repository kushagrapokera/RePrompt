
import logging
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import torch

logger = logging.getLogger(__name__)

# Intent-specific instructions — each tells the LFM how to rewrite the query.
INTENT_INSTRUCTIONS = {
    "coding": (
        "The user's intent is CODING.\n\n"
        "Rewrite the query below into a clear, natural question for another LLM.\n\n"
        "Rules:\n"
        "- Preserve the original meaning exactly.\n"
        "- Correct grammar and spelling.\n"
        "- Keep the same intent and level of detail.\n"
        "- Do not add or remove requirements.\n"
        "- Do not answer the question.\n"
        "- Do not solve the task.\n"
        "- Output only the rewritten prompt."
    ),
    "creative_writing": (
        "The user's intent is CREATIVE WRITING.\n\n"
        "Rewrite the query below into a clear creative writing task for another LLM.\n\n"
        "Rules:\n"
        "- Preserve the original creative request exactly.\n"
        "- Fix grammar, spelling, and awkward phrasing.\n"
        "- Keep all creative elements (genre, tone, characters, setting) unchanged.\n"
        "- Do not add new plot points, characters, or creative elements.\n"
        "- Do not write the story or poem yourself.\n"
        "- Output only the rewritten prompt."
    ),
    "email": (
        "The user's intent is EMAIL.\n\n"
        "Rewrite the query below into a clear email drafting task for another LLM.\n\n"
        "Rules:\n"
        "- Preserve the original email request exactly.\n"
        "- Fix grammar, spelling, and awkward phrasing.\n"
        "- Keep recipient details, tone preference, and purpose unchanged.\n"
        "- Do not add missing recipients or invent context.\n"
        "- Do not draft the email yourself.\n"
        "- Output only the rewritten prompt."
    ),
    "general_qa": (
        "The user's intent is GENERAL_QA.\n\n"
        "Rewrite the query below by fixing grammar and spelling only.\n"
        "Do NOT change the type of request — if the user is confirming something, "
        "keep it a confirmation. If they are asking a question, keep it a question.\n\n"
        "Rules:\n"
        "- Preserve the original meaning and request type exactly.\n"
        "- Correct grammar and spelling.\n"
        "- Keep the same intent and level of detail.\n"
        "- Do not add or remove requirements.\n"
        "- Do not add context or details not present in the query.\n"
        "- Do not answer the query.\n"
        "- Do not solve the task.\n"
        "- Output only the rewritten prompt."
    ),
    "summarization": (
        "The user's intent is SUMMARIZATION.\n\n"
        "Analyze whether the query is asking for summarization. If not, simply improve the grammar and clarity; otherwise, rewrite it into a concise and effective summary.\n\n"
        "Rules:\n"
        "- Preserve the original summarization request exactly.\n"
        "- Fix grammar, spelling, and clarity.\n"
        "- Keep any specified length, format, or focus requirements unchanged.\n"
        "- Do not add extra sections or topics to summarize.\n"
        "- Do not write the summary yourself.\n"
        "- Output only the rewritten prompt."
    ),
    "learning": (
        "The user's intent is LEARNING.\n\n"
        "Rewrite the query below into a clear learning/explanation request for another LLM.\n\n"
        "Rules:\n"
        "- Preserve the original learning topic exactly.\n"
        "- Fix grammar, spelling, and phrasing.\n"
        "- Keep the user's stated knowledge level and preferred explanation style.\n"
        "- Do not change the topic or add prerequisite topics.\n"
        "- Do not explain the concept yourself.\n"
        "- Output only the rewritten prompt."
    ),
    "planning": (
        "The user's intent is PLANNING.\n\n"
        "Analyze whether the query is actually asking for planning. If not, simply improve the grammar and clarity; otherwise, continue with planning and structuring." 
        "Rules:\n"
        "- Preserve the original planning request exactly.\n"
        "- Fix grammar, spelling, and clarity.\n"
        "- Keep constraints, timeline, budget, and priorities unchanged.\n"
        "- Do not add steps, items, or constraints the user didn't mention.\n"
        "- Do not create the plan yourself.\n"
        "- Output only the rewritten prompt."
    ),
}

SYSTEM_TEMPLATE = """You are a prompt rewriter. Your only job is to clean up and restructure user queries into clear prompts for another LLM.

{intent_instruction}

Query:
"{query}"""

class PromptEnhancer:

    def __init__(
        self,
        model_name: str = "LiquidAI/LFM2.5-1.2B-Instruct",
        device: str = "auto",
    ):
        if device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        logger.info("Loading enhancement model %s on %s …", model_name, self.device)

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            quantization_config=bnb_config,
            device_map={"": 0} if self.device == "cuda" else None,
            trust_remote_code=True,
        )
        self.model.eval()

        self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

    def _llm_rewrite(self, text: str, intent: str, max_new_tokens: int = 256) -> str:
        """Send *text* to the LFM for intent-specific rewrite."""
        instruction = INTENT_INSTRUCTIONS.get(intent, INTENT_INSTRUCTIONS["general_qa"])
        prompt = SYSTEM_TEMPLATE.format(intent_instruction=instruction, query=text)

        messages = [{"role": "user", "content": prompt}]
        formatted = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(formatted, return_tensors="pt", truncation=True, max_length=2048)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )

        return self.tokenizer.decode(
            output_ids[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        ).strip()

    def enhance(self, query: str, intent: str, max_new_tokens: int = 256) -> str:
        """Rewrite *query* using intent-specific instructions."""
        return self._llm_rewrite(query, intent, max_new_tokens)
