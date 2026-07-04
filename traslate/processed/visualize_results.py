import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Thiết lập phong cách hiển thị biểu đồ
sns.set_theme(style="whitegrid")
plt.rcParams['font.family'] = 'DejaVu Sans'  # Font an toàn có hỗ trợ Unicode cơ bản
plt.rcParams['figure.figsize'] = (12, 6)

# Đường dẫn thư mục hiện tại
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Định nghĩa các mô hình và file đánh giá tương ứng
eval_files = {
    "Qwen3-VL-8B (Thinking)": os.path.join(BASE_DIR, "t1_qwen3_vl_8b_thinking_outputs_part1_eval.json"),
    "Qwen3.5-9B": os.path.join(BASE_DIR, "t2_qwen35_9b_outputs_part1_eval.json"),
    "Qwen3-VL-8B (Instruct)": os.path.join(BASE_DIR, "t3_qwen3_vl_8b_instruct_outputs_part1_eval.json"),
    "Gemma": os.path.join(BASE_DIR, "t4_gemma_outputs_part1_eval.json")
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
        if 'judge_score' in item:
            records.append({
                "Model": model_name,
                "Prompt": item.get('prompt', ''),
                "Score": item['judge_score']
            })

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

plt.title("So Sánh Điểm Số Đánh Giá Trung Bình Của Các Mô Hình (Thang 1-5)", fontsize=14, fontweight='bold', pad=15)
plt.xlabel("Điểm đánh giá trung bình", fontsize=12)
plt.ylabel("Mô hình", fontsize=12)
plt.xlim(0, 5.5)
plt.tight_layout()

output_avg = os.path.join(BASE_DIR, "benchmark_average_scores.png")
plt.savefig(output_avg, dpi=300)
plt.close()
print(f"Đã lưu biểu đồ điểm trung bình tại: {output_avg}")

# ----------------------------------------------------
# BIỂU ĐỒ 2: PHÂN PHỐI ĐIỂM SỐ (Score Distribution Grouped Bar Chart)
# ----------------------------------------------------
plt.figure(figsize=(12, 6))

# Đếm tần suất điểm 1-5 cho mỗi model
dist_df = df.groupby(["Model", "Score"]).size().reset_index(name="Count")
# Tính tỷ lệ phần trăm
total_per_model = df.groupby("Model").size().reset_index(name="Total")
dist_df = dist_df.merge(total_per_model, on="Model")
dist_df["Percentage"] = (dist_df["Count"] / dist_df["Total"]) * 100

ax2 = sns.barplot(
    x="Score", 
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

plt.title("Phần Trăm Phân Phối Điểm Số (1 đến 5) Của Từng Mô Hình", fontsize=14, fontweight='bold', pad=15)
plt.xlabel("Điểm số (Judge Score)", fontsize=12)
plt.ylabel("Tỷ lệ (%)", fontsize=12)
plt.ylim(0, 100)
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
axes[0].set_ylim(0.5, 5.5)
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
axes[1].set_ylim(0.5, 5.5)
axes[1].tick_params(axis='x', rotation=15)

plt.suptitle("Phân Tích Chi Tiết Biểu Đồ Hộp & Biểu Đồ Violin", fontsize=15, fontweight='bold', y=0.98)
plt.tight_layout()

output_combined = os.path.join(BASE_DIR, "benchmark_box_violin_plots.png")
plt.savefig(output_combined, dpi=300)
plt.close()
print(f"Đã lưu biểu đồ phân bố chi tiết tại: {output_combined}")

print("✨ Hoàn tất tạo tất cả biểu đồ trực quan hóa!")
