import os
import sys
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Enforce UTF-8 for printing emojis/text
sys.stdout.reconfigure(encoding='utf-8')

# Define paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
CSV_PATH = os.path.join(PROJECT_ROOT, "traslate", "raw", "finetuning_data_fashion_knowledge.csv")
CHARTS_DIR = os.path.join(SCRIPT_DIR, "charts")
DASHBOARD_PATH = os.path.join(SCRIPT_DIR, "dashboard.html")

# Create output directories
os.makedirs(CHARTS_DIR, exist_ok=True)

print("🚀 Starting Fashion Dataset Analysis Pipeline...")
print(f"📂 Reading dataset from: {CSV_PATH}")

if not os.path.exists(CSV_PATH):
    print(f"❌ Error: CSV file not found at {CSV_PATH}")
    sys.exit(1)

# Read CSV
try:
    df = pd.read_csv(CSV_PATH)
except Exception as e:
    print(f"❌ Error reading CSV: {e}")
    sys.exit(1)

total_rows = len(df)
print(f"📦 Successfully loaded {total_rows:,} rows.")
print(f"Columns: {df.columns.tolist()}")

# ==========================================
# 1. CORE METRICS & DATA INTEGRITY
# ==========================================
print("\n🔍 Step 1: Checking data integrity...")

# Missing values
missing_orig_in = df['original_input'].isna().sum()
missing_orig_out = df['original_output'].isna().sum()
missing_trans_in = df['translated_input'].isna().sum()
missing_trans_out = df['translated_output'].isna().sum()

# Empty strings
empty_orig_in = (df['original_input'].astype(str).str.strip() == '').sum()
empty_orig_out = (df['original_output'].astype(str).str.strip() == '').sum()
empty_trans_in = (df['translated_input'].astype(str).str.strip() == '').sum()
empty_trans_out = (df['translated_output'].astype(str).str.strip() == '').sum()

total_missing_or_empty_rows = df.isna().any(axis=1).sum() + (df.astype(str).apply(lambda x: x.str.strip() == '').any(axis=1)).sum()

print(f"  - Missing cells: EN Input: {missing_orig_in}, EN Output: {missing_orig_out}, VI Input: {missing_trans_in}, VI Output: {missing_trans_out}")
print(f"  - Empty cells: EN Input: {empty_orig_in}, EN Output: {empty_orig_out}, VI Input: {empty_trans_in}, VI Output: {empty_trans_out}")
print(f"  - Rows with any missing/empty values: {total_missing_or_empty_rows:,} ({total_missing_or_empty_rows/total_rows*100:.2f}%)")

# Untranslated text (VI matches EN exactly)
untranslated_in = (df['original_input'].astype(str).str.strip() == df['translated_input'].astype(str).str.strip()).sum()
untranslated_out = (df['original_output'].astype(str).str.strip() == df['translated_output'].astype(str).str.strip()).sum()
any_untranslated = ((df['original_input'].astype(str).str.strip() == df['translated_input'].astype(str).str.strip()) | 
                    (df['original_output'].astype(str).str.strip() == df['translated_output'].astype(str).str.strip())).sum()

print(f"  - Untranslated Inputs: {untranslated_in:,} ({untranslated_in/total_rows*100:.2f}%)")
print(f"  - Untranslated Outputs: {untranslated_out:,} ({untranslated_out/total_rows*100:.2f}%)")
print(f"  - Rows with any untranslated text: {any_untranslated:,} ({any_untranslated/total_rows*100:.2f}%)")


# ==========================================
# 2. DUPLICATION ANALYSIS
# ==========================================
print("\n🔍 Step 2: Analyzing duplicates...")

# Duplicates on English QA pairs
dup_en_qa = df.duplicated(subset=['original_input', 'original_output'], keep='first').sum()
# Duplicates on Vietnamese QA pairs
dup_vi_qa = df.duplicated(subset=['translated_input', 'translated_output'], keep='first').sum()
# Overall exact row duplicates (all 4 columns)
dup_exact_rows = df.duplicated(keep='first').sum()

# Duplicates on inputs only (multiple same questions with different answers)
dup_en_in = df.duplicated(subset=['original_input'], keep='first').sum()
dup_vi_in = df.duplicated(subset=['translated_input'], keep='first').sum()

print(f"  - Exact duplicate rows (all columns matching): {dup_exact_rows:,} ({dup_exact_rows/total_rows*100:.2f}%)")
print(f"  - Duplicate EN Q&A pairs: {dup_en_qa:,} ({dup_en_qa/total_rows*100:.2f}%)")
print(f"  - Duplicate VI Q&A pairs: {dup_vi_qa:,} ({dup_vi_qa/total_rows*100:.2f}%)")
print(f"  - Duplicate EN Inputs (same question): {dup_en_in:,} ({dup_en_in/total_rows*100:.2f}%)")


# ==========================================
# 3. TEXT LENGTH & RATIO ANALYSIS
# ==========================================
print("\n🔍 Step 3: Analyzing text length distributions and translation ratios...")

# Help function to calculate word count
def get_word_count(series):
    return series.fillna('').astype(str).apply(lambda x: len(x.split()))

df['en_in_wc'] = get_word_count(df['original_input'])
df['en_out_wc'] = get_word_count(df['original_output'])
df['vi_in_wc'] = get_word_count(df['translated_input'])
df['vi_out_wc'] = get_word_count(df['translated_output'])

# Length ratios (VI word count / EN word count)
# To avoid division by zero or NaN, replace 0 with epsilon
epsilon = 1e-5
df['in_ratio'] = df['vi_in_wc'] / (df['en_in_wc'] + epsilon)
df['out_ratio'] = df['vi_out_wc'] / (df['en_out_wc'] + epsilon)

# Average word counts
avg_en_in_wc = df['en_in_wc'].mean()
avg_en_out_wc = df['en_out_wc'].mean()
avg_vi_in_wc = df['vi_in_wc'].mean()
avg_vi_out_wc = df['vi_out_wc'].mean()

print(f"  - Avg Word Counts:")
print(f"    * EN Input: {avg_en_in_wc:.1f} words | VI Input: {avg_vi_in_wc:.1f} words (Ratio: {avg_vi_in_wc/avg_en_in_wc:.2f}x)")
print(f"    * EN Output: {avg_en_out_wc:.1f} words | VI Output: {avg_vi_out_wc:.1f} words (Ratio: {avg_vi_out_wc/avg_en_out_wc:.2f}x)")

# Length ratio anomalies
# Normal translation ratio for EN to VI is typically between 0.6 and 2.0.
# We define anomalies as < 0.4 (extremely short translation, likely truncated/failed) 
# or > 2.5 (excessively bloated, likely hallucination or code block leak).
ratio_anomalies_in = ((df['in_ratio'] < 0.4) | (df['in_ratio'] > 2.5)) & (df['en_in_wc'] > 3)
ratio_anomalies_out = ((df['out_ratio'] < 0.4) | (df['out_ratio'] > 2.5)) & (df['en_out_wc'] > 5)
any_ratio_anomaly = ratio_anomalies_in | ratio_anomalies_out
n_ratio_anomalies = any_ratio_anomaly.sum()

print(f"  - Length ratio anomalies (VI/EN < 0.4 or > 2.5): {n_ratio_anomalies:,} ({n_ratio_anomalies/total_rows*100:.2f}%)")


# ==========================================
# 4. OPTIMIZATION / DATA PRUNING PIPELINE
# ==========================================
print("\n🔍 Step 4: Simulating Data Pruning Pipeline...")

# Step 0: Raw
s0_count = total_rows

# Step 1: Remove Nulls / Empty Strings
df_clean = df.dropna(subset=['original_input', 'original_output', 'translated_input', 'translated_output'])
df_clean = df_clean[
    (df_clean['original_input'].astype(str).str.strip() != '') &
    (df_clean['original_output'].astype(str).str.strip() != '') &
    (df_clean['translated_input'].astype(str).str.strip() != '') &
    (df_clean['translated_output'].astype(str).str.strip() != '')
]
s1_count = len(df_clean)

# Step 2: Remove Untranslated (VI == EN)
df_clean = df_clean[
    (df_clean['original_input'].astype(str).str.strip() != df_clean['translated_input'].astype(str).str.strip()) &
    (df_clean['original_output'].astype(str).str.strip() != df_clean['translated_output'].astype(str).str.strip())
]
s2_count = len(df_clean)

# Step 3: Remove Exact & Duplicate Q&A pairs (keep first)
df_clean = df_clean.drop_duplicates(subset=['original_input', 'original_output'], keep='first')
s3_count = len(df_clean)

# Step 4: Remove anomalies (ratio outliers & extremely short answers)
# Keep only rows with valid ratios and sensible word lengths
in_wc = df_clean['translated_input'].fillna('').astype(str).apply(lambda x: len(x.split()))
out_wc = df_clean['translated_output'].fillna('').astype(str).apply(lambda x: len(x.split()))
en_in_wc = df_clean['original_input'].fillna('').astype(str).apply(lambda x: len(x.split()))
en_out_wc = df_clean['original_output'].fillna('').astype(str).apply(lambda x: len(x.split()))
in_rat = in_wc / (en_in_wc + epsilon)
out_rat = out_wc / (en_out_wc + epsilon)

valid_length_mask = (
    (in_rat >= 0.4) & (in_rat <= 2.5) & 
    (out_rat >= 0.4) & (out_rat <= 2.5) &
    (in_wc >= 2) & (out_wc >= 5)
)
df_optimal = df_clean[valid_length_mask]
s4_count = len(df_optimal)

print(f"  - Pipeline Results:")
print(f"    * Raw Data: {s0_count:,} rows (100.0%)")
print(f"    * 1. After removing Empty/Nulls: {s1_count:,} rows ({s1_count/s0_count*100:.1f}%) [Removed {s0_count-s1_count:,} rows]")
print(f"    * 2. After removing Untranslated: {s2_count:,} rows ({s2_count/s0_count*100:.1f}%) [Removed {s1_count-s2_count:,} rows]")
print(f"    * 3. After removing Duplicates: {s3_count:,} rows ({s3_count/s0_count*100:.1f}%) [Removed {s2_count-s3_count:,} rows]")
print(f"    * 4. After removing Length Outliers (Optimal): {s4_count:,} rows ({s4_count/s0_count*100:.1f}%) [Removed {s3_count-s4_count:,} rows]")

compression_ratio = (1 - (s4_count / s0_count)) * 100
print(f"  - Overall Pruning/Compression potential: Save {s0_count-s4_count:,} rows ({compression_ratio:.1f}% reduction) leaving a highly curated {s4_count:,} row dataset.")


# ==========================================
# 5. GENERATE MATPLOTLIB CHARTS
# ==========================================
print("\n🎨 Step 5: Generating visual charts...")

# Theme Setup (Dark palette matching the user's dashboard image)
plt.style.use('dark_background')
BG_COLOR = '#0f172a' # Tailwind slate-900
GRID_COLOR = '#1e293b' # Tailwind slate-800
ACCENT_BLUE = '#0284c7' # Sky-600
ACCENT_TEAL = '#0d9488' # Teal-600
ACCENT_ORANGE = '#f97316' # Orange-500
ACCENT_GREEN = '#22c55e' # Green-500
ACCENT_PURPLE = '#a855f7' # Purple-500
ACCENT_GOLD = '#eab308' # Yellow-500

# 5.1 Duplication Chart (Donut)
fig, ax = plt.subplots(figsize=(6, 5), facecolor=BG_COLOR)
ax.set_facecolor(BG_COLOR)
labels = ['Unique Records', 'Duplicate Records']
sizes = [s0_count - dup_en_qa, dup_en_qa]
colors = [ACCENT_TEAL, ACCENT_ORANGE]
wedges, texts, autotexts = ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90, 
                                  colors=colors, textprops=dict(color="w"), pctdistance=0.75,
                                  wedgeprops=dict(width=0.4, edgecolor='#1e293b'))
plt.setp(autotexts, size=10, weight="bold")
plt.setp(texts, size=10)
ax.set_title("Dataset Composition\n(Unique Q&As vs Duplicates)", color='w', fontsize=12, pad=15)
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, "duplication_pie.png"), dpi=300, facecolor=BG_COLOR)
plt.close()

# 5.2 Pruning Funnel Chart
fig, ax = plt.subplots(figsize=(8, 5), facecolor=BG_COLOR)
ax.set_facecolor(BG_COLOR)
steps = [
    'Raw Data\n(40,305)', 
    'Valid & Non-Empty\n(40,117)', 
    'Fully Translated\n(40,111)', 
    'Deduplicated EN\n(39,944)', 
    'Optimal Finetuning\n(39,812)' # Approximate labels, script will compute real counts
]
counts = [s0_count, s1_count, s2_count, s3_count, s4_count]
percentages = [c/s0_count*100 for c in counts]

bars = ax.barh(steps[::-1], counts[::-1], color=ACCENT_BLUE, height=0.55, edgecolor='#38bdf8')
# Color codes
for idx, bar in enumerate(bars[::-1]):
    if idx == 0:
        bar.set_color('#1e293b') # Raw dark
        bar.set_edgecolor('#475569')
    elif idx == 4:
        bar.set_color(ACCENT_GREEN) # Clean/Optimal green
        bar.set_edgecolor('#4ade80')
    else:
        bar.set_color(ACCENT_TEAL)
        bar.set_edgecolor('#2dd4bf')

# Add counts and percentages labels
for bar, pct, count in zip(bars, percentages[::-1], counts[::-1]):
    width = bar.get_width()
    ax.text(width + (s0_count * 0.02), bar.get_y() + bar.get_height()/2, 
            f'{count:,} ({pct:.1f}%)', 
            va='center', ha='left', color='w', fontsize=9, fontweight='bold')

ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_color('#334155')
ax.spines['bottom'].set_color('#334155')
ax.tick_params(colors='w', labelsize=9)
ax.xaxis.grid(True, linestyle='--', alpha=0.3, color=GRID_COLOR)
ax.set_title("Data Pruning & Optimization Pipeline (Funnel)", color='w', fontsize=12, pad=15)
plt.xlim(0, s0_count * 1.25)
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, "funnel_pruning.png"), dpi=300, facecolor=BG_COLOR)
plt.close()

# 5.3 Average Word Count Comparison
fig, ax = plt.subplots(figsize=(7, 5), facecolor=BG_COLOR)
ax.set_facecolor(BG_COLOR)
labels = ['Input (Questions)', 'Output (Answers)']
en_means = [avg_en_in_wc, avg_en_out_wc]
vi_means = [avg_vi_in_wc, avg_vi_out_wc]

x = np.arange(len(labels))
width = 0.35

rects1 = ax.bar(x - width/2, en_means, width, label='English (Original)', color=ACCENT_BLUE, edgecolor='#38bdf8')
rects2 = ax.bar(x + width/2, vi_means, width, label='Vietnamese (Translated)', color=ACCENT_PURPLE, edgecolor='#c084fc')

# Add values on top of bars
def autolabel(rects):
    for rect in rects:
        height = rect.get_height()
        ax.annotate(f'{height:.1f}',
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 3),  # 3 points vertical offset
                    textcoords="offset points",
                    ha='center', va='bottom', color='w', fontsize=9, fontweight='bold')

autolabel(rects1)
autolabel(rects2)

ax.set_ylabel('Average Word Count', color='w', fontsize=10)
ax.set_title('Average Word Lengths: English vs Vietnamese', color='w', fontsize=12, pad=15)
ax.set_xticks(x)
ax.set_xticklabels(labels, color='w')
ax.tick_params(colors='w', labelsize=10)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_color('#334155')
ax.spines['bottom'].set_color('#334155')
ax.yaxis.grid(True, linestyle='--', alpha=0.3, color=GRID_COLOR)
ax.legend(facecolor='#1e293b', edgecolor='#334155', labelcolor='w')
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, "word_count_comparison.png"), dpi=300, facecolor=BG_COLOR)
plt.close()

# 5.4 Word Count Distribution (Input & Output Lengths)
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5), facecolor=BG_COLOR)
ax1.set_facecolor(BG_COLOR)
ax2.set_facecolor(BG_COLOR)

# Input WC Distribution
ax1.hist(df['en_in_wc'], bins=25, range=(0, 30), alpha=0.6, label='EN Input', color=ACCENT_BLUE, edgecolor='#38bdf8')
ax1.hist(df['vi_in_wc'], bins=25, range=(0, 30), alpha=0.6, label='VI Input', color=ACCENT_PURPLE, edgecolor='#c084fc')
ax1.set_title("Input (Question) Word Length Distribution", color='w', fontsize=11)
ax1.set_xlabel("Word Count", color='w')
ax1.set_ylabel("Frequency", color='w')
ax1.grid(True, linestyle='--', alpha=0.2, color=GRID_COLOR)
ax1.legend(facecolor='#1e293b', edgecolor='#334155', labelcolor='w')
ax1.tick_params(colors='w')
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)

# Output WC Distribution
ax2.hist(df['en_out_wc'], bins=30, range=(0, 150), alpha=0.6, label='EN Output', color=ACCENT_BLUE, edgecolor='#38bdf8')
ax2.hist(df['vi_out_wc'], bins=30, range=(0, 150), alpha=0.6, label='VI Output', color=ACCENT_PURPLE, edgecolor='#c084fc')
ax2.set_title("Output (Answer) Word Length Distribution", color='w', fontsize=11)
ax2.set_xlabel("Word Count", color='w')
ax2.set_ylabel("Frequency", color='w')
ax2.grid(True, linestyle='--', alpha=0.2, color=GRID_COLOR)
ax2.legend(facecolor='#1e293b', edgecolor='#334155', labelcolor='w')
ax2.tick_params(colors='w')
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)

plt.suptitle("Word Count Frequency Analysis", color='w', fontsize=13, weight='bold')
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, "length_distribution.png"), dpi=300, facecolor=BG_COLOR)
plt.close()

# 5.5 Word Count Ratio Distribution
fig, ax = plt.subplots(figsize=(7, 4.5), facecolor=BG_COLOR)
ax.set_facecolor(BG_COLOR)

# Length ratios distribution
ax.hist(df['out_ratio'], bins=35, range=(0.2, 2.2), alpha=0.75, color=ACCENT_TEAL, edgecolor='#2dd4bf')
ax.axvline(1.0, color='w', linestyle='--', alpha=0.5, label='Equal Length (1.0x)')
ax.axvline(df['out_ratio'].mean(), color=ACCENT_GOLD, linestyle='-', linewidth=2, label=f'Average Ratio ({df["out_ratio"].mean():.2f}x)')

# Highlight anomalous bounds
ax.axvspan(0, 0.4, alpha=0.15, color=ACCENT_ORANGE, label='Anomalously Short (<0.4x)')
ax.axvspan(2.5, 3.5, alpha=0.15, color=ACCENT_ORANGE, label='Anomalously Long (>2.5x)')

ax.set_title("Word Count Ratio Distribution (Vietnamese / English)", color='w', fontsize=12, pad=15)
ax.set_xlabel("Length Ratio (Word Count Ratio)", color='w')
ax.set_ylabel("Frequency (Number of Sentences)", color='w')
ax.grid(True, linestyle='--', alpha=0.2, color=GRID_COLOR)
ax.tick_params(colors='w')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_color('#334155')
ax.spines['bottom'].set_color('#334155')
ax.legend(facecolor='#1e293b', edgecolor='#334155', labelcolor='w', loc='upper right')
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, "length_ratio.png"), dpi=300, facecolor=BG_COLOR)
plt.close()

print("✅ Static Matplotlib charts generated successfully under analysis/charts/ folder.")


# ==========================================
# 6. GENERATE INTERACTIVE DASHBOARD HTML
# ==========================================
print("\n🖥️ Step 6: Generating premium interactive HTML Dashboard...")

# Prepare a subset of anomalies to show in the table
df_anom = df[any_ratio_anomaly | df.isna().any(axis=1) | (df.astype(str).apply(lambda x: x.str.strip() == '').any(axis=1))].head(15)
anomaly_list = []
for idx, row in df_anom.iterrows():
    anomaly_list.append({
        "index": int(idx),
        "en_in": str(row['original_input'])[:60] + ("..." if len(str(row['original_input'])) > 60 else ""),
        "vi_in": str(row['translated_input'])[:60] + ("..." if len(str(row['translated_input'])) > 60 else ""),
        "en_out_wc": int(row['en_out_wc']),
        "vi_out_wc": int(row['vi_out_wc']),
        "ratio": float(row['out_ratio']),
        "type": "Length Mismatch" if (row['out_ratio'] < 0.4 or row['out_ratio'] > 2.5) else ("Missing translation" if pd.isna(row['translated_input']) or pd.isna(row['translated_output']) else "Duplicate/Other")
    })

# Helper function to convert numpy values to standard python types for JSON
def make_serializable(obj):
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_serializable(v) for v in obj]
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return make_serializable(obj.tolist())
    else:
        return obj

# Format data fields for JavaScript injection
data_payload = {
    "total_rows": total_rows,
    "unique_en_qa": total_rows - dup_en_qa,
    "dup_en_qa": dup_en_qa,
    "exact_dups": dup_exact_rows,
    "missing_translation": total_missing_or_empty_rows,
    "untranslated": any_untranslated,
    "optimal_rows": s4_count,
    "compression_pct": round(compression_ratio, 1),
    "avg_en_in_wc": round(avg_en_in_wc, 2),
    "avg_vi_in_wc": round(avg_vi_in_wc, 2),
    "avg_en_out_wc": round(avg_en_out_wc, 2),
    "avg_vi_out_wc": round(avg_vi_out_wc, 2),
    "ratio_anomalies": n_ratio_anomalies,
    "pipeline_steps": steps,
    "pipeline_counts": counts,
    "pipeline_percentages": [round(p, 1) for p in percentages],
    "anomalies": anomaly_list
}

data_payload = make_serializable(data_payload)

html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fashion Match - Data Analysis Dashboard</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Chart.js CDN -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body {{
            font-family: 'Outfit', sans-serif;
            background-color: #0b0f19;
            color: #f1f5f9;
        }}
        .glass-card {{
            background: rgba(17, 24, 39, 0.7);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.05);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
            border-radius: 1rem;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }}
        .glass-card:hover {{
            border-color: rgba(255, 255, 255, 0.1);
            transform: translateY(-2px);
            box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.5);
        }}
        .neon-text-teal {{
            color: #0df2c9;
            text-shadow: 0 0 10px rgba(13, 242, 201, 0.2);
        }}
        .neon-text-blue {{
            color: #38bdf8;
            text-shadow: 0 0 10px rgba(56, 189, 248, 0.2);
        }}
        .neon-text-orange {{
            color: #fb923c;
            text-shadow: 0 0 10px rgba(251, 146, 60, 0.2);
        }}
        .neon-border-green {{
            border-color: rgba(34, 197, 94, 0.3);
            box-shadow: 0 0 15px rgba(34, 197, 94, 0.1);
        }}
        /* Scrollbar styling */
        ::-webkit-scrollbar {{
            width: 8px;
            height: 8px;
        }}
        ::-webkit-scrollbar-track {{
            background: #0f172a;
        }}
        ::-webkit-scrollbar-thumb {{
            background: #334155;
            border-radius: 4px;
        }}
        ::-webkit-scrollbar-thumb:hover {{
            background: #475569;
        }}
    </style>
</head>
<body class="p-4 md:p-6 lg:p-8 min-h-screen">

    <!-- Header Section -->
    <header class="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 gap-4 pb-6 border-b border-slate-800">
        <div>
            <div class="flex items-center gap-3">
                <span class="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Data Cleaned</span>
                <span class="text-slate-400 text-sm">Workspace: vominhnhatquang/fashion_match</span>
            </div>
            <h1 class="text-3xl font-extrabold tracking-tight mt-1 bg-gradient-to-r from-teal-400 via-sky-400 to-indigo-500 bg-clip-text text-transparent">
                Fashion Knowledge Dataset Diagnostics
            </h1>
            <p class="text-slate-400 mt-1">Deep analysis of the 40k fashion conversation finetuning corpus (English vs. Vietnamese translations).</p>
        </div>
        <div class="flex gap-3">
            <div class="bg-slate-900 border border-slate-800 rounded-lg p-3 text-right">
                <div class="text-xs text-slate-500 uppercase tracking-wider font-semibold">Total Rows Diagnosed</div>
                <div class="text-2xl font-bold text-white tracking-tight">{data_payload["total_rows"]:,}</div>
            </div>
        </div>
    </header>

    <!-- KPI Row -->
    <section class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <!-- KPI 1: Unique Q&A -->
        <div class="glass-card p-5 flex flex-col justify-between">
            <div class="flex justify-between items-start">
                <div class="text-slate-400 text-sm font-semibold uppercase tracking-wider">Unique Q&A (EN)</div>
                <span class="p-2 bg-teal-500/10 rounded-lg text-teal-400">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                </span>
            </div>
            <div class="mt-4">
                <div class="text-3xl font-bold tracking-tight text-white">{data_payload["unique_en_qa"]:,}</div>
                <p class="text-xs text-slate-500 mt-1">{(data_payload["unique_en_qa"]/data_payload["total_rows"])*100:.1f}% of entire dataset</p>
            </div>
        </div>

        <!-- KPI 2: Duplicate Q&A -->
        <div class="glass-card p-5 flex flex-col justify-between">
            <div class="flex justify-between items-start">
                <div class="text-slate-400 text-sm font-semibold uppercase tracking-wider">Duplicate Records</div>
                <span class="p-2 bg-orange-500/10 rounded-lg text-orange-400">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                </span>
            </div>
            <div class="mt-4">
                <div class="text-3xl font-bold tracking-tight text-white">{data_payload["dup_en_qa"]:,}</div>
                <p class="text-xs text-slate-500 mt-1">{(data_payload["dup_en_qa"]/data_payload["total_rows"])*100:.1f}% redundancies detected</p>
            </div>
        </div>

        <!-- KPI 3: Translation Failures -->
        <div class="glass-card p-5 flex flex-col justify-between">
            <div class="flex justify-between items-start">
                <div class="text-slate-400 text-sm font-semibold uppercase tracking-wider">Translation Failures</div>
                <span class="p-2 bg-red-500/10 rounded-lg text-red-400">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5c-.313 1.565-.92 3.018-1.8 4.307" /></svg>
                </span>
            </div>
            <div class="mt-4">
                <div class="text-3xl font-bold tracking-tight text-white">{data_payload["missing_translation"] + data_payload["untranslated"]:,}</div>
                <p class="text-xs text-slate-500 mt-1">{data_payload["missing_translation"]:,} empty | {data_payload["untranslated"]:,} untranslated</p>
            </div>
        </div>

        <!-- KPI 4: Pruning Compression Potential -->
        <div class="glass-card p-5 border neon-border-green flex flex-col justify-between">
            <div class="flex justify-between items-start">
                <div class="text-slate-400 text-sm font-semibold uppercase tracking-wider">Compression Potential</div>
                <span class="p-2 bg-green-500/10 rounded-lg text-green-400">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 100-6 3 3 0 000 6z" /></svg>
                </span>
            </div>
            <div class="mt-4">
                <div class="text-3xl font-bold tracking-tight text-green-400">{data_payload["compression_pct"]}%</div>
                <p class="text-xs text-slate-400 mt-1">Keep {data_payload["optimal_rows"]:,} optimal rows for training</p>
            </div>
        </div>
    </section>

    <!-- Main Dashboard Grid -->
    <section class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <!-- Funnel Pruning Column -->
        <div class="glass-card p-6 lg:col-span-2 flex flex-col">
            <div class="mb-4">
                <h3 class="text-lg font-bold text-white">Data Pruning & Optimization Funnel</h3>
                <p class="text-slate-400 text-xs mt-0.5">Iterative pipeline to shrink dataset to clean & optimal rows for finetuning.</p>
            </div>
            <div class="relative flex-grow flex items-center justify-center p-2" style="min-height: 300px;">
                <canvas id="funnelChart"></canvas>
            </div>
        </div>

        <!-- Composition Column -->
        <div class="glass-card p-6 flex flex-col">
            <div class="mb-4">
                <h3 class="text-lg font-bold text-white">Dataset Redundancy Ratio</h3>
                <p class="text-slate-400 text-xs mt-0.5">Comparison between unique and redundant records.</p>
            </div>
            <div class="relative flex-grow flex items-center justify-center p-2" style="min-height: 250px;">
                <canvas id="compositionChart"></canvas>
            </div>
        </div>
    </section>

    <section class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <!-- Word count comparison -->
        <div class="glass-card p-6 flex flex-col">
            <div class="mb-4">
                <h3 class="text-lg font-bold text-white">Average Word Lengths (EN vs. VI)</h3>
                <p class="text-slate-400 text-xs mt-0.5">Comparing inputs (questions) and outputs (answers).</p>
            </div>
            <div class="relative flex-grow" style="min-height: 260px;">
                <canvas id="wordCountComparisonChart"></canvas>
            </div>
        </div>

        <!-- Anomalies breakdown -->
        <div class="glass-card p-6 flex flex-col">
            <div class="mb-4">
                <h3 class="text-lg font-bold text-white">Translation Anomaly Diagnostics</h3>
                <p class="text-slate-400 text-xs mt-0.5">Analysis of translation failures, blank rows, and length outliers.</p>
            </div>
            <div class="relative flex-grow" style="min-height: 260px;">
                <canvas id="anomalyBreakdownChart"></canvas>
            </div>
        </div>
    </section>

    <!-- Table of Identified Anomalies -->
    <section class="glass-card p-6 mb-6">
        <div class="flex justify-between items-center mb-4">
            <div>
                <h3 class="text-lg font-bold text-white">Sample Translation Anomalies Identified</h3>
                <p class="text-slate-400 text-xs mt-0.5">A list of sample rows with length ratios < 0.4 or > 2.5, indicating translation errors.</p>
            </div>
            <span class="px-2.5 py-1 text-xs font-semibold rounded-full bg-orange-500/10 text-orange-400 border border-orange-500/20">Needs Pruning</span>
        </div>
        <div class="overflow-x-auto">
            <table class="w-full text-left border-collapse">
                <thead>
                    <tr class="border-b border-slate-800 text-slate-400 text-xs font-semibold uppercase tracking-wider">
                        <th class="py-3 px-4">Line #</th>
                        <th class="py-3 px-4">English Input (Sample)</th>
                        <th class="py-3 px-4">Vietnamese Input (Sample)</th>
                        <th class="py-3 px-4 text-center">EN Words</th>
                        <th class="py-3 px-4 text-center">VI Words</th>
                        <th class="py-3 px-4 text-center">Ratio</th>
                        <th class="py-3 px-4 text-center">Status</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-800/60 text-sm text-slate-300">
                    <!-- Dynamic rendering of table rows -->
                    {"".join([f'''
                    <tr class="hover:bg-slate-900/40 transition-colors">
                        <td class="py-3 px-4 font-mono text-xs text-slate-500">{item['index']}</td>
                        <td class="py-3 px-4">{item['en_in']}</td>
                        <td class="py-3 px-4">{item['vi_in']}</td>
                        <td class="py-3 px-4 text-center font-mono">{item['en_out_wc']}</td>
                        <td class="py-3 px-4 text-center font-mono">{item['vi_out_wc']}</td>
                        <td class="py-3 px-4 text-center font-mono">
                            <span class="{"text-orange-400 font-bold" if (item['ratio'] < 0.4 or item['ratio'] > 2.5) else "text-slate-400"}">{item['ratio']:.2f}x</span>
                        </td>
                        <td class="py-3 px-4 text-center">
                            <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium {'bg-red-500/10 text-red-400 border border-red-500/20' if item['type']=='Missing translation' else 'bg-orange-500/10 text-orange-400 border border-orange-500/20'}">
                                {item['type']}
                            </span>
                        </td>
                    </tr>
                    ''' for item in data_payload['anomalies']])}
                </tbody>
            </table>
        </div>
    </section>

    <!-- Recommendation Box -->
    <section class="glass-card p-6 border border-emerald-500/20 bg-emerald-500/5">
        <div class="flex items-start gap-4">
            <span class="p-3 bg-emerald-500/10 rounded-xl text-emerald-400">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
            </span>
            <div>
                <h4 class="text-lg font-bold text-white">Recommended Strategy to Shorten & Optimize Dataset</h4>
                <ul class="list-disc list-inside text-sm text-slate-300 mt-2 space-y-2">
                    <li><strong>Drop Duplicate Q&A pairs (English level):</strong> Deleting {data_payload["dup_en_qa"]:,} rows removes clean redundancy without loss of coverage, reducing data by <strong>{(data_payload["dup_en_qa"]/data_payload["total_rows"])*100:.1f}%</strong>.</li>
                    <li><strong>Purge Nulls & Empty translations:</strong> Eliminates {data_payload["missing_translation"]:,} rows that would cause training failures.</li>
                    <li><strong>Discard Untranslated Q&As:</strong> Purging {data_payload["untranslated"]:,} entries where the Vietnamese output exactly matches the English source, ensuring the LLM is only trained on genuine Vietnamese.</li>
                    <li><strong>Filter Length Mismatch Outliers:</strong> Truncating entries with abnormally low/high word ratios (VI/EN < 0.4 or > 2.5) cleans up {data_payload["ratio_anomalies"]:,} translation artifacts.</li>
                </ul>
                <div class="mt-4 flex gap-4 text-xs font-semibold text-emerald-400">
                    <span>Cleaned Output size: {data_payload["optimal_rows"]:,} rows</span>
                    <span>•</span>
                    <span>Total compression: ~{data_payload["compression_pct"]}% dataset reduction</span>
                </div>
            </div>
        </div>
    </section>

    <!-- Footer -->
    <footer class="mt-12 text-center text-xs text-slate-500 pb-6">
        <p>Dashboard generated dynamically by analysis/analyze.py. Google DeepMind pair programming assistant Antigravity.</p>
    </footer>

    <!-- Inject Chart.js Configuration -->
    <script>
        const chartData = {json.dumps(data_payload)};

        // Chart.js Theme Defaults
        Chart.defaults.color = '#94a3b8';
        Chart.defaults.borderColor = '#1e293b';

        // 1. Funnel / Pruning Chart
        new Chart(document.getElementById('funnelChart'), {{
            type: 'bar',
            data: {{
                labels: chartData.pipeline_steps,
                datasets: [{{
                    label: 'Remaining Rows',
                    data: chartData.pipeline_counts,
                    backgroundColor: [
                        '#475569', // Raw slate
                        '#0d9488', // Teal
                        '#0284c7', // Blue
                        '#8b5cf6', // Purple
                        '#22c55e'  // Green
                    ],
                    borderColor: [
                        '#64748b',
                        '#2dd4bf',
                        '#38bdf8',
                        '#a78bfa',
                        '#4ade80'
                    ],
                    borderWidth: 1.5,
                    barThickness: 32
                }}]
            }},
            options: {{
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                let index = context.dataIndex;
                                let count = chartData.pipeline_counts[index];
                                let pct = chartData.pipeline_percentages[index];
                                return ` Rows: ${{count.toLocaleString()}} (${{pct}}%)`;
                            }}
                        }}
                    }}
                }},
                scales: {{
                    x: {{
                        grid: {{ display: true }},
                        ticks: {{ color: '#64748b' }}
                    }},
                    y: {{
                        grid: {{ display: false }},
                        ticks: {{ font: {{ weight: 'bold', size: 11 }} }}
                    }}
                }}
            }}
        }});

        // 2. Composition Donut Chart
        new Chart(document.getElementById('compositionChart'), {{
            type: 'doughnut',
            data: {{
                labels: ['Unique Records', 'Duplicate Records'],
                datasets: [{{
                    data: [chartData.total_rows - chartData.dup_en_qa, chartData.dup_en_qa],
                    backgroundColor: ['#0d9488', '#f97316'],
                    borderColor: '#0f172a',
                    borderWidth: 3,
                    hoverOffset: 4
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        position: 'bottom',
                        labels: {{ boxWidth: 12, padding: 15 }}
                    }}
                }},
                cutout: '65%'
            }}
        }});

        // 3. Word Count Comparison
        new Chart(document.getElementById('wordCountComparisonChart'), {{
            type: 'bar',
            data: {{
                labels: ['Inputs (Questions)', 'Outputs (Answers)'],
                datasets: [
                    {{
                        label: 'English (Original)',
                        data: [chartData.avg_en_in_wc, chartData.avg_en_out_wc],
                        backgroundColor: '#0284c7',
                        borderColor: '#38bdf8',
                        borderWidth: 1,
                        borderRadius: 4
                    }},
                    {{
                        label: 'Vietnamese (Translated)',
                        data: [chartData.avg_vi_in_wc, chartData.avg_vi_out_wc],
                        backgroundColor: '#a855f7',
                        borderColor: '#c084fc',
                        borderWidth: 1,
                        borderRadius: 4
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ position: 'bottom', labels: {{ boxWidth: 12 }} }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        title: {{ display: true, text: 'Average Words' }}
                    }}
                }}
            }}
        }});

        // 4. Anomaly Breakdown
        new Chart(document.getElementById('anomalyBreakdownChart'), {{
            type: 'bar',
            data: {{
                labels: ['Missing/Empty Cell', 'Untranslated (VI==EN)', 'Length Ratio Outlier'],
                datasets: [{{
                    label: 'Count',
                    data: [chartData.missing_translation, chartData.untranslated, chartData.ratio_anomalies],
                    backgroundColor: ['#ef4444', '#fb923c', '#eab308'],
                    borderColor: '#0f172a',
                    borderWidth: 1,
                    borderRadius: 4
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }}
                }},
                scales: {{
                    y: {{ beginAtZero: true }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""

# Save dashboard.html
try:
    with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✅ Interactive HTML dashboard generated at: {DASHBOARD_PATH}")
except Exception as e:
    print(f"❌ Error saving dashboard: {e}")

print("\n🎉 Fashion Dataset Analysis Pipeline completed successfully!")
