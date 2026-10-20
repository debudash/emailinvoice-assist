"""Settings, read once from the environment (and .env when running locally)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    model: str = os.getenv("LLM_MODEL", "claude-opus-5-5")
    ref_mcp_url: str = os.getenv("REF_MCP_URL", "http://localhost:8200/mcp")
    clinrun_url: str = os.getenv("CLINRUN_URL", "http://localhost:8100")
    db_path: Path = Path(os.getenv("APP_DB", "data/app.db"))
    inbox_dir: Path = Path(os.getenv("INBOX_DIR", "inbox"))
    poll_seconds: float = float(os.getenv("POLL_SECONDS", "3"))
    hub_refresh_seconds: float = float(os.getenv("HUB_REFRESH_SECONDS", "3"))  # 0 turns auto-refresh off
    # Context Confidence floor, one per field (ADR-0004); tuned on the labelled samples in S3.
    threshold_sponsor: float = float(os.getenv("THRESHOLD_SPONSOR", "0.85"))
    threshold_study: float = float(os.getenv("THRESHOLD_STUDY", "0.85"))
    threshold_site: float = float(os.getenv("THRESHOLD_SITE", "0.85"))

    # Price tolerance as a fraction of the catalog price; 0 means exact to the cent (decisions.md 5a).
    price_tolerance: float = float(os.getenv("PRICE_TOLERANCE", "0"))

    # Manual baseline for "time saved" (D4): an assumption, shown on screen.
    minutes_per_invoice: float = float(os.getenv("MANUAL_MINUTES_PER_INVOICE", "5"))
    minutes_per_line: float = float(os.getenv("MANUAL_MINUTES_PER_LINE", "1"))

    def threshold(self, field: str) -> float:
        return getattr(self, f"threshold_{field}")


settings = Settings()
