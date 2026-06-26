"""
Generate one-line earnings/filing synopses from already-extracted filing_themes data.
Uses Haiku for speed and cost (~$0.0002 per call).
Results are cached in the filings table's llm_analysis->>'synopsis' key.
"""
import json
from sqlalchemy import text

MODEL = "claude-haiku-4-5"


def _build_prompt(symbol: str, filing_type: str, title: str,
                  trajectory: str, tone: str, catalysts: list, risks: list) -> str:
    cats = "; ".join(catalysts[:3]) if catalysts else "none noted"
    rsks = "; ".join(risks[:2]) if risks else "none noted"
    return (
        f"Stock: {symbol} | Filing: {filing_type} | {title}\n"
        f"Trajectory: {trajectory} | Management tone: {tone}\n"
        f"Key positives: {cats}\n"
        f"Key risks: {rsks}\n\n"
        "Write a single sentence (max 18 words) summarising whether results were strong, mixed, or disappointing, "
        "and the single most important reason. Be direct and specific. No filler phrases like 'the company reported'."
    )


def generate_synopsis(symbol: str, filing_type: str, title: str,
                      trajectory: str, tone: str,
                      catalysts: list, risks: list) -> str:
    """Return a one-line synopsis. Falls back to a rule-based string on error."""
    try:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=MODEL,
            max_tokens=60,
            messages=[{"role": "user", "content": _build_prompt(
                symbol, filing_type, title, trajectory, tone, catalysts, risks
            )}],
        )
        return msg.content[0].text.strip()
    except Exception:
        # Fallback: rule-based from trajectory
        if trajectory in ("accelerating", "improving"):
            return f"Results beat expectations with improving momentum."
        if trajectory in ("decelerating", "declining"):
            return f"Results disappointed; execution headwinds persist."
        return "Mixed results; trajectory stable."


def get_or_generate_synopsis(engine, filing_id: int, symbol: str,
                              filing_type: str, title: str, llm_analysis,
                              trajectory: str, tone: str,
                              catalysts, risks) -> str:
    """Return cached synopsis or generate + cache it."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT llm_analysis FROM filings WHERE id = :id"),
            {"id": filing_id}
        ).fetchone()

    existing = {}
    if row and row[0]:
        try:
            existing = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        except Exception:
            existing = {}

    if existing.get("synopsis"):
        return existing["synopsis"]

    cats = catalysts if isinstance(catalysts, list) else (json.loads(catalysts) if catalysts else [])
    rsks = risks if isinstance(risks, list) else (json.loads(risks) if risks else [])

    synopsis = generate_synopsis(symbol, filing_type, title, trajectory, tone, cats, rsks)

    existing["synopsis"] = synopsis
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE filings SET llm_analysis = :v WHERE id = :id"),
            {"v": json.dumps(existing), "id": filing_id}
        )

    return synopsis
