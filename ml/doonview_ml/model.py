"""Multi-task review classifier: one encoder, three heads (sentiment, spam, aspects)."""
import json
from pathlib import Path

import torch
from torch import nn
from transformers import AutoModel, AutoTokenizer

from .labels import ASPECT_VALUES, ASPECTS, SENTIMENTS


class MultiTaskModel(nn.Module):
    def __init__(self, encoder: nn.Module, n_aspects: int = len(ASPECTS)):
        super().__init__()
        self.encoder = encoder
        hidden = encoder.config.hidden_size
        self.dropout = nn.Dropout(0.1)
        self.sentiment_head = nn.Linear(hidden, len(SENTIMENTS))
        self.spam_head = nn.Linear(hidden, 1)
        self.aspect_head = nn.Linear(hidden, n_aspects * len(ASPECT_VALUES))
        self.n_aspects = n_aspects

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor):
        states = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        # Mean pooling over real tokens
        mask = attention_mask.unsqueeze(-1).to(states.dtype)
        pooled = self.dropout((states * mask).sum(1) / mask.sum(1).clamp(min=1.0))
        return (self.sentiment_head(pooled), self.spam_head(pooled).squeeze(-1),
                self.aspect_head(pooled).view(-1, self.n_aspects, len(ASPECT_VALUES)))

    def save(self, out_dir: Path, tokenizer, config: dict) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        self.encoder.save_pretrained(out_dir / "encoder")
        tokenizer.save_pretrained(out_dir / "encoder")
        torch.save({k: v for k, v in self.state_dict().items() if not k.startswith("encoder.")}, out_dir / "heads.pt")
        (out_dir / "config.json").write_text(json.dumps(config, indent=2))

    @classmethod
    def load(cls, run_dir: Path, device: str = "cpu"):
        config = json.loads((run_dir / "config.json").read_text())
        encoder = AutoModel.from_pretrained(run_dir / "encoder", dtype=torch.float32)
        model = cls(encoder, n_aspects=len(config["aspects"]))
        missing, unexpected = model.load_state_dict(
            torch.load(run_dir / "heads.pt", map_location=device, weights_only=True), strict=False)
        if unexpected or any(not k.startswith("encoder.") for k in missing):
            raise RuntimeError(f"heads.pt mismatch: missing={missing} unexpected={unexpected}")
        return model.to(device).eval(), AutoTokenizer.from_pretrained(run_dir / "encoder"), config
