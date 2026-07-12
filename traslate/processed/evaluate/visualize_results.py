import os
import json
import sys
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Fix Windows console encoding issues
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Thiết lập phong cách hiển thị biểu đồ
sns.set_theme(style="whitegrid")
plt.rcParams['font.family'] = 'DejaVu Sans'  # Font an toàn có hỗ trợ Unicode cơ bản
plt.rcParams['figure.figsize'] = (12, 6)

# Đường dẫn thư mục hiện tại
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Định nghĩa các mô hình và file đánh giá tương ứng
eval_files = {
    "Qwen3-VL-8B (Thinking)": os.path.join(BASE_DIR, "evaluated", "qwen3vl8b-thinking-lora-p1_eval.json"),
    "Qwen3.5-9B": os.path.join(BASE_DIR, "evaluated", "qwen35-9b-bnb4-lora-p1_eval.json"),
    "Qwen3-VL-8B (Instruct)": os.path.join(BASE_DIR, "evaluated", "qwen3vl8b-instruct-lora-p1_eval.json"),
    "Gemma": os.path.join(BASE_DIR, "evaluated", "gemma4-12b-it-lora-p1_eval.json")
}

# Đọc dữ liệu
records = []
for model_name, file_path in eval_files.items():
    if not os.path.exists(file_path):
        print(f"⚠️ Không tìm thấy file checkpoint: {file_path}")
        continue
        
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    for item in data:
        if 'evaluation' in item:
            eval_data = item['evaluation']
            criteria_cols = ['context_utilization', 'trend_compliance', 'fashion_knowledge_qa', 'faithfulness', 'hallucination']
            score = sum(eval_data.get(k, 0.0) for k in criteria_cols) / len(criteria_cols)
            row = {
                "Model": model_name,
                "Prompt": item.get('question') or item.get('prompt', ''),
                "Score": score
            }
            for k in criteria_cols:
                row[k] = eval_data.get(k, 0.0)
            records.append(row)
        elif 'judge_score' in item:
            row = {
                "Model": model_name,
                "Prompt": item.get('prompt', ''),
                "Score": item['judge_score'] / 5.0
            }
            for k in ['context_utilization', 'trend_compliance', 'fashion_knowledge_qa', 'faithfulness', 'hallucination']:
                row[k] = item.get(k, item['judge_score']) / 5.0
            records.append(row)

df = pd.DataFrame(records)

if df.empty:
    print("❌ Không có dữ liệu đánh giá để vẽ biểu đồ.")
    exit(1)

print(f"Đã load thành công {len(df)} mẫu đánh giá.")

# ----------------------------------------------------
# BIỂU ĐỒ 1: SO SÁNH ĐIỂM TRUNG BÌNH (Average Scores Comparison)
# ----------------------------------------------------
plt.figure(figsize=(10, 6))
avg_scores = df.groupby("Model")["Score"].mean().reset_index().sort_values(by="Score", ascending=False)
palette = sns.color_palette("viridis", len(avg_scores))

ax = sns.barplot(
    x="Score", 
    y="Model", 
    data=avg_scores, 
    palette=palette, 
    hue="Model", 
    legend=False
)

# Thêm nhãn điểm số trên các cột
for i, p in enumerate(ax.patches):
    width = p.get_width()
    ax.text(
        width + 0.05, 
        p.get_y() + p.get_height() / 2, 
        f'{width:.2f}', 
        ha='left', 
        va='center', 
        fontsize=12, 
        fontweight='bold'
    )

plt.title("So Sánh Điểm Số Đánh Giá Trung Bình Của Các Mô Hình (Thang 0-1)", fontsize=14, fontweight='bold', pad=15)
plt.xlabel("Điểm đánh giá trung bình", fontsize=12)
plt.ylabel("Mô hình", fontsize=12)
plt.xlim(0, 1.15)
plt.tight_layout()

output_avg = os.path.join(BASE_DIR, "benchmark_average_scores.png")
plt.savefig(output_avg, dpi=300)
plt.close()
print(f"Đã lưu biểu đồ điểm trung bình tại: {output_avg}")

# ----------------------------------------------------
# BIỂU ĐỒ 2: PHÂN PHỐI ĐIỂM SỐ (Score Distribution Grouped Bar Chart)
# ----------------------------------------------------
plt.figure(figsize=(12, 6))

# Phân nhóm điểm số thành 5 khoảng chất lượng tương ứng với Rubric
bins = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
labels = ["0.0 - 0.2\n(Rất kém)", "0.2 - 0.4\n(Yếu)", "0.4 - 0.6\n(Trung bình)", "0.6 - 0.8\n(Tốt)", "0.8 - 1.0\n(Xuất sắc)"]
df["ScoreRange"] = pd.cut(df["Score"], bins=bins, labels=labels, include_lowest=True)

# Đếm tần suất mỗi khoảng điểm cho mỗi model
dist_df = df.groupby(["Model", "ScoreRange"], observed=False).size().reset_index(name="Count")
# Tính tỷ lệ phần trăm
total_per_model = df.groupby("Model").size().reset_index(name="Total")
dist_df = dist_df.merge(total_per_model, on="Model")
dist_df["Percentage"] = (dist_df["Count"] / dist_df["Total"]) * 100

ax2 = sns.barplot(
    x="ScoreRange", 
    y="Percentage", 
    hue="Model", 
    data=dist_df, 
    palette="muted"
)

# Thêm nhãn phần trăm lên cột
for p in ax2.patches:
    height = p.get_height()
    if height > 0:
        ax2.text(
            p.get_x() + p.get_width() / 2, 
            height + 1, 
            f'{height:.1f}%', 
            ha='center', 
            va='bottom', 
            fontsize=9
        )

plt.title("Phần Trăm Phân Phối Điểm Số (Thang 0-1) Của Từng Mô Hình", fontsize=14, fontweight='bold', pad=15)
plt.xlabel("Khoảng điểm số (Judge Score)", fontsize=12)
plt.ylabel("Tỷ lệ (%)", fontsize=12)
plt.ylim(0, 105)
plt.legend(title="Mô hình", bbox_to_anchor=(1.05, 1), loc='upper left')
plt.tight_layout()

output_dist = os.path.join(BASE_DIR, "benchmark_score_distribution.png")
plt.savefig(output_dist, dpi=300)
plt.close()
print(f"Đã lưu biểu đồ phân phối điểm số tại: {output_dist}")

# ----------------------------------------------------
# BIỂU ĐỒ 3: HỢP PHÂN PHỐI (Box & Violin Combined Plot)
# ----------------------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(16, 7))

# Violin Plot
sns.violinplot(
    x="Model", 
    y="Score", 
    data=df, 
    ax=axes[0], 
    palette="pastel", 
    hue="Model", 
    legend=False,
    inner="quartile"
)
axes[0].set_title("Biểu đồ Violin Phân Phối Điểm Số", fontsize=12, fontweight='bold')
axes[0].set_xlabel("Mô hình")
axes[0].set_ylabel("Điểm số")
axes[0].set_ylim(-0.05, 1.05)
axes[0].tick_params(axis='x', rotation=15)

# Box Plot
sns.boxplot(
    x="Model", 
    y="Score", 
    data=df, 
    ax=axes[1], 
    palette="coolwarm",
    hue="Model",
    legend=False
)
axes[1].set_title("Biểu đồ Box Plot So Sánh Độ Dao Động", fontsize=12, fontweight='bold')
axes[1].set_xlabel("Mô hình")
axes[1].set_ylabel("Điểm số")
axes[1].set_ylim(-0.05, 1.05)
axes[1].tick_params(axis='x', rotation=15)

plt.suptitle("Phân Tích Chi Tiết Biểu Đồ Hộp & Biểu Đồ Violin", fontsize=15, fontweight='bold', y=0.98)
plt.tight_layout()

output_combined = os.path.join(BASE_DIR, "benchmark_box_violin_plots.png")
plt.savefig(output_combined, dpi=300)
plt.close()
print(f"Đã lưu biểu đồ phân bố chi tiết tại: {output_combined}")

# ----------------------------------------------------
# BIỂU ĐỒ 4: SO SÁNH CHI TIẾT THEO 5 TIÊU CHÍ (Criteria Comparison Grouped Bar Chart)
# ----------------------------------------------------
criteria_cols = ['context_utilization', 'trend_compliance', 'fashion_knowledge_qa', 'faithfulness', 'hallucination']
has_criteria = all(col in df.columns for col in criteria_cols)

if has_criteria:
    # Melt dataframe về dạng long format
    melted_df = df.melt(
        id_vars=["Model"],
        value_vars=criteria_cols,
        var_name="Criterion",
        value_name="CriteriaScore"
    )
    # Ánh xạ tên tiếng Việt/Anh đẹp mắt
    criteria_names_map = {
        'context_utilization': 'Context Utilization',
        'trend_compliance': 'Trend Compliance',
        'fashion_knowledge_qa': 'Fashion QA',
        'faithfulness': 'Faithfulness',
        'hallucination': 'Hallucination'
    }
    melted_df["Criterion"] = melted_df["Criterion"].map(criteria_names_map)
    
    # Tính điểm trung bình của mỗi model cho từng tiêu chí
    criterion_means = melted_df.groupby(["Model", "Criterion"])["CriteriaScore"].mean().reset_index()
    
    plt.figure(figsize=(14, 7))
    ax3 = sns.barplot(
        x="Criterion",
        y="CriteriaScore",
        hue="Model",
        data=criterion_means,
        palette="Set2"
    )
    
    # Thêm giá trị số trên đầu mỗi cột
    for p in ax3.patches:
        height = p.get_height()
        if height > 0:
            ax3.text(
                p.get_x() + p.get_width() / 2.,
                height + 0.05,
                f'{height:.2f}',
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight='bold'
            )
            
    plt.title("So Sánh Các Mô Hình Qua 5 Tiêu Chí Đánh Giá Chi Tiết", fontsize=14, fontweight='bold', pad=15)
    plt.xlabel("Tiêu chí đánh giá", fontsize=12)
    plt.ylabel("Điểm trung bình (Thang 0-1)", fontsize=12)
    plt.ylim(0, 1.1)
    plt.legend(title="Mô hình", bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    
    output_detail = os.path.join(BASE_DIR, "benchmark_criteria_comparison.png")
    plt.savefig(output_detail, dpi=300)
    plt.close()
    print(f"Đã lưu biểu đồ so sánh chi tiết các tiêu chí tại: {output_detail}")
else:
    print("ℹ️ Bỏ qua biểu đồ so sánh tiêu chí vì các file đánh giá chưa chứa điểm tiêu chí chi tiết.")

print("✨ Hoàn tất tạo tất cả biểu đồ trực quan hóa!")
