"""
Embedding Builder — generates semantic embeddings for all filing themes and meta-themes.

Uses sentence-transformers (all-MiniLM-L6-v2) — free, local, no API key required.
Embeddings are stored in the DB so they're computed once and reused.

Run this:
  - After Phase 1 (narrative_extractor) to embed new filing themes
  - After Phase 2 (meta_theme_builder clustering) to embed new meta-themes
  - Then run Phase 3 (score_stock_alignments) which uses cosine similarity

Typical runtime: ~2 min for 2,500 filings on CPU.
"""

import json
import os
import time

import numpy as np
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, text

load_dotenv(override=True)

MODEL_NAME = "all-MiniLM-L6-v2"
BATCH_SIZE = 256   # Encode in batches for speed


def get_engine():
    host = os.getenv("DB_HOST_IP", "localhost")
    password = os.getenv("DB_PASSWORD", "")
    user = os.getenv("DB_USER", "postgres")
    name = os.getenv("DB_NAME", "postgres")
    return create_engine(f"postgresql+psycopg2://{user}:{password}@{host}/{name}", pool_pre_ping=True)


def load_model():
    print(f"  Loading {MODEL_NAME}...")
    return SentenceTransformer(MODEL_NAME)


def themes_to_text(raw_themes_json) -> str:
    """Convert a filing's raw_themes list into a single string for embedding."""
    if isinstance(raw_themes_json, list):
        themes = raw_themes_json
    elif isinstance(raw_themes_json, str):
        try:
            themes = json.loads(raw_themes_json)
        except Exception:
            themes = [raw_themes_json]
    else:
        themes = []
    return " | ".join(t for t in themes if isinstance(t, str) and t.strip())


def embed_filing_themes(engine, model, force=False):
    """
    Embed all filing_themes that don't yet have an embedding.
    Set force=True to re-embed everything.
    """
    print("\n📄 Embedding filing themes...")

    with engine.connect() as conn:
        if force:
            rows = conn.execute(text("""
                SELECT id, raw_themes, trajectory, narrative_strength
                FROM filing_themes
                WHERE raw_themes IS NOT NULL
                ORDER BY filing_date DESC
            """)).fetchall()
        else:
            rows = conn.execute(text("""
                SELECT id, raw_themes, trajectory, narrative_strength
                FROM filing_themes
                WHERE raw_themes IS NOT NULL
                  AND embedding IS NULL
                ORDER BY filing_date DESC
            """)).fetchall()

    if not rows:
        print("  ✅ All filing themes already embedded")
        return

    print(f"  {len(rows)} filing themes to embed")

    # Build text strings — themes + trajectory context for richer embeddings
    ids = []
    texts = []
    for row_id, raw_themes_json, trajectory, strength in rows:
        theme_text = themes_to_text(raw_themes_json)
        if not theme_text:
            continue
        traj_suffix = f" [trajectory: {trajectory}]" if trajectory else ""
        ids.append(row_id)
        texts.append(theme_text + traj_suffix)

    # Batch encode
    start = time.time()
    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        normalize_embeddings=True,   # L2-normalised → dot product = cosine similarity
        convert_to_numpy=True,
    )
    print(f"  Encoded {len(embeddings)} in {time.time()-start:.1f}s")

    # Store
    with engine.connect() as conn:
        for row_id, emb in zip(ids, embeddings):
            conn.execute(text("""
                UPDATE filing_themes
                SET embedding = :emb
                WHERE id = :id
            """), {
                "id":  row_id,
                "emb": json.dumps(emb.tolist()),
            })
        conn.commit()

    print(f"  ✅ Stored {len(ids)} filing embeddings")


def embed_meta_themes(engine, model, force=False):
    """Embed all meta-themes that don't yet have an embedding."""
    print("\n🧠 Embedding meta-themes...")

    with engine.connect() as conn:
        if force:
            rows = conn.execute(text("SELECT id, name, description FROM meta_themes")).fetchall()
        else:
            rows = conn.execute(text("""
                SELECT id, name, description FROM meta_themes WHERE embedding IS NULL
            """)).fetchall()

    if not rows:
        print("  ✅ All meta-themes already embedded")
        return

    print(f"  {len(rows)} meta-themes to embed")

    ids = []
    texts = []
    for row_id, name, description in rows:
        # Use name + description for a richer semantic representation
        text_str = f"{name}: {description}" if description else name
        ids.append(row_id)
        texts.append(text_str)

    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    with engine.connect() as conn:
        for row_id, emb in zip(ids, embeddings):
            conn.execute(text("""
                UPDATE meta_themes SET embedding = :emb WHERE id = :id
            """), {"id": row_id, "emb": json.dumps(emb.tolist())})
        conn.commit()

    print(f"  ✅ Stored {len(ids)} meta-theme embeddings")


def run_embedding_build(force=False):
    """Main entry point. Embeds everything that hasn't been embedded yet."""
    print("=" * 70)
    print("EMBEDDING BUILDER — semantic vectors for filings + meta-themes")
    print("=" * 70)

    engine = get_engine()
    model = load_model()

    embed_filing_themes(engine, model, force=force)
    embed_meta_themes(engine, model, force=force)

    print("\n" + "=" * 70)
    print("✅ Embedding build complete")
    print("=" * 70)


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    run_embedding_build(force=force)
