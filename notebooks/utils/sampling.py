"""
Sampling utilities for large CSV files.

Key design decision: SEQUENTIAL streaming, not parallel.

Why? The previous parallel approach loaded entire byte ranges (~6 GB each)
into memory before chunking them — that's what caused the OOM crashes.

For a single-disk, I/O-bound workload, a sequential streamer that reads
one small chunk at a time is:
  - Memory-safe: only 1 chunk (~25K rows × ~134 cols ≈ 30 MB) in RAM at a time
  - Actually faster: no disk seek thrashing from parallel reads
  - Simpler: no multiprocessing serialization overhead
"""

import os
import re
import json
import subprocess
import time
import gc

import pandas as pd


def discover_columns(filepath: str, sep: str = '\t') -> list[str]:
    """Read just the header line to get all column names (zero data loaded)."""
    with open(filepath, 'r') as f:
        return f.readline().strip().split(sep)


def select_analysis_columns(all_columns: list[str]) -> list[str]:
    """
    Apply the column-selection pipeline:
    1. Drop metadata columns (urls, timestamps, images, etc.)
    2. Keep: identifiers + nutrition + tag columns + special columns
    3. Return only columns that exist in the file.
    """
    # --- Step 1: Drop metadata columns ---
    meta_pattern = r'_t$|datetime|modified|updated|url|image|owner|creator'
    cols_after_meta_drop = [
        c for c in all_columns
        if not re.search(meta_pattern, c.lower())
    ]

    # --- Step 2: Build final column set ---
    id_cols = ['code', 'product_name']

    nutrition_cols = [c for c in cols_after_meta_drop if c.endswith('_100g')]

    keywords = ["categor", "brand", "label", "origin", "countr", "ingredient", ]
    seg_tags = [
        col for col in cols_after_meta_drop
        if any(kw in col.lower() for kw in keywords)
        and (col.endswith('_tags') or col == 'ingredients_analysis_tags')
    ]

    special_cols = [
        'stores',
        'nova_group',
        'main_category_en',
        'nutriscore_score',        # numeric score (-15 best → +40 worst)
        'nutriscore_grade',        # letter grade: a (best) → e (worst)
        'nutrient_levels_tags',    # e.g. "en:fat-in-high-quantity,en:sugars-in-low-quantity"
        'no_nutrition_data',       # flag: '1' if product has no nutrition info at all
        'created_datetime',
    ]

    # Deduplicate and filter to columns that actually exist
    selected = list(set(id_cols + nutrition_cols + seg_tags + special_cols))
    selected = [c for c in selected if c in all_columns]

    return selected


def count_rows(filepath: str) -> int:
    """Count total data rows using wc -l (fast, doesn't load data)."""
    result = subprocess.run(
        ['wc', '-l', filepath],
        capture_output=True, text=True
    )
    return int(result.stdout.strip().split()[0]) - 1  # minus header


def convert_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Convert string columns to proper numeric/datetime types."""
    numeric_cols = [c for c in df.columns if c.endswith('_100g') or c == 'nova_group']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


def load_or_sample(
    filepath: str,
    output_csv: str,
    output_meta: str,
    sample_size: int = 1_000_000,
    seed: int = 42,
    chunk_size: int = 25_000,
) -> pd.DataFrame:
    """
    Load a cached sample, or stream-sample from the source file.

    Memory usage: ~30-50 MB peak per chunk, regardless of file size.

    The algorithm:
    1. Read just the header to discover columns
    2. Apply column-selection rules (drops ~80 of 210 columns)
    3. Count total rows (wc -l, instant)
    4. Calculate sampling fraction = sample_size / total_rows
    5. Stream through file in small chunks (25K rows each):
       - pd.read_csv with chunksize + usecols = pandas only loads 25K
         rows of selected columns into memory at a time
       - Sample each chunk at the calculated fraction
       - Discard the full chunk immediately (only sampled rows kept)
    6. Concatenate sampled rows, trim to exact size, save

    This NEVER loads the full file into memory — peak RAM is just
    one chunk (~30 MB) + the accumulated sampled rows.

    Parameters
    ----------
    filepath : str
        Path to the source CSV (tab-separated).
    output_csv : str
        Path to save the sampled CSV.
    output_meta : str
        Path to save the sampling parameters (for cache validation).
    sample_size : int
        Target number of rows in the final sample.
    seed : int
        Random seed for reproducibility.
    chunk_size : int
        Number of rows per streaming chunk. Smaller = less memory,
        slightly slower. 25K is a good balance.

    Returns
    -------
    pd.DataFrame
        The sampled DataFrame with proper dtypes.
    """
    # --- Discover and select columns ---
    all_columns = discover_columns(filepath)
    use_columns = select_analysis_columns(all_columns)

    current_params = {
        "sample_size": sample_size,
        "seed": seed,
        "chunk_size": chunk_size,
        "columns": sorted(use_columns),
        "source": filepath,
    }

    # --- Check cache ---
    if os.path.exists(output_csv) and os.path.exists(output_meta):
        with open(output_meta, 'r') as f:
            saved_params = json.load(f)
        if saved_params == current_params:
            print("✅ Cached sample found — loading from disk.")
            df = pd.read_csv(output_csv, low_memory=False)
            print(f"   Shape: {df.shape}")
            mem_mb = df.memory_usage(deep=True).sum() / 1024**2
            print(f"   🧠 Memory: {mem_mb:.0f} MB")
            return df
        else:
            print("⚠️  Parameters changed — re-sampling...")
    else:
        print("📊 No cache — sampling from source...")

    # --- Count rows ---
    total_rows = count_rows(filepath)
    print(f"📏 Total rows in file: {total_rows:,}")
    print(f"📋 Loading {len(use_columns)} of {len(all_columns)} columns")

    if sample_size >= total_rows:
        print("⚠️  Requested more rows than file has — loading all.")
        df = pd.read_csv(
            filepath, sep='\t', low_memory=True,
            usecols=lambda c: c in use_columns,
            on_bad_lines='skip', dtype='str',
        )
        df = convert_dtypes(df)
    else:
        # Oversample by 5% to account for rounding, then trim
        sampling_fraction = min((sample_size / total_rows) * 1.05, 1.0)
        print(f"🎯 Sampling ~{sampling_fraction*100:.1f}% from each chunk "
              f"({chunk_size:,} rows/chunk)")

        # ────────────────────────────────────────────────────
        #  THE KEY: pd.read_csv with chunksize streams the file.
        #  It only loads `chunk_size` rows at a time.
        #  Combined with `usecols`, peak memory is tiny.
        #  No byte-range reading. No multiprocessing.
        #  Just a simple, memory-safe streaming loop.
        # ────────────────────────────────────────────────────
        sampled_chunks = []
        t0 = time.time()

        reader = pd.read_csv(
            filepath,
            sep='\t',
            chunksize=chunk_size,
            usecols=lambda c: c in use_columns,
            low_memory=True,
            on_bad_lines='skip',
            dtype='str',  # Read as string first to avoid mixed-dtype issues
        )

        for i, chunk in enumerate(reader):
            sampled = chunk.sample(frac=sampling_fraction, random_state=seed + i)
            sampled_chunks.append(sampled)
            del chunk  # Free immediately — don't accumulate the full chunk

            # Progress update every 20 chunks
            if (i + 1) % 20 == 0:
                elapsed = time.time() - t0
                rows_read = (i + 1) * chunk_size
                pct = min(rows_read / total_rows * 100, 100)
                collected_so_far = sum(len(c) for c in sampled_chunks)
                print(f"   ... {pct:.0f}% read | "
                      f"collected {collected_so_far:,} rows | "
                      f"{elapsed:.0f}s elapsed")

        # No early exit — we always read the ENTIRE file.
        # The 5% oversample ensures we end up with >= sample_size rows,
        # then trim to exactly sample_size at the end.

        elapsed = time.time() - t0
        print(f"\n⏱️  Streaming done in {elapsed:.1f}s")

        df = pd.concat(sampled_chunks, ignore_index=True)
        del sampled_chunks
        gc.collect()

        print(f"📦 Collected {len(df):,} rows")

        # Trim to exact size
        if len(df) > sample_size:
            df = df.sample(n=sample_size, random_state=seed)
            print(f"✂️  Trimmed to {len(df):,} rows")

        # Convert dtypes
        df = convert_dtypes(df)

    # --- Save ---
    df.to_csv(output_csv, index=False)
    with open(output_meta, 'w') as f:
        json.dump(current_params, f, indent=2)

    mem_mb = df.memory_usage(deep=True).sum() / 1024**2
    print(f"\n💾 Saved to {output_csv}")
    print(f"   Final Shape: {df.shape}")
    print(f"   🧠 Memory: {mem_mb:.0f} MB")

    return df
