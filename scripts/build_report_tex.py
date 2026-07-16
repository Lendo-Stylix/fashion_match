#!/usr/bin/env python3
"""Builder: writes the LaTeX report .tex file with full Vietnamese diacritics,
XeTeX-compatible preamble (fontspec + Times New Roman), titlepage, and all 8 figure images.

USAGE:
  uv run scripts/build_report_tex.py          # generates .tex
  cd docs/reports && tectonic ...tex          # compiles PDF

This script replaces the fragile heredoc approach for .tex files with backslashes.
The CONTENT string is a raw triple-quoted Python string (r\"\"\") so all LaTeX
backslashes are preserved literally.
"""
import io, os

OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "reports", "stylist_model_report_dl.tex")
OUT = os.path.normpath(OUT)

CONTENT = r"""\documentclass[12pt,a4paper]{article}
% ===== XeTeX engine (Tectonic) -- native UTF-8, no [utf8]{vietnam}/[T5]{fontenc} =====
\usepackage{fontspec}
\setmainfont{Times New Roman}
\setsansfont{Arial}
\setmonofont{Consolas}
% ===== Layout & typography =====
\usepackage{geometry}
\geometry{left=2.5cm,right=2.5cm,top=2.8cm,bottom=2.8cm}
\usepackage{graphicx}
\graphicspath{{figures/}}
\usepackage{booktabs}
\usepackage{amsmath,amssymb}
\usepackage{listings}
\usepackage{xcolor}
\usepackage{hyperref}
\usepackage{float}
\usepackage{multirow}
\usepackage{caption}
\usepackage{titlesec}
\usepackage{enumitem}
\usepackage{fancyhdr}
\usepackage{tcolorbox}
\tcbuselibrary{skins,breakable}
% ===== Colors =====
\definecolor{codebg}{rgb}{0.97,0.97,0.97}
\definecolor{codekey}{rgb}{0.15,0.30,0.65}
\definecolor{linkblue}{HTML}{1A5276}
\definecolor{accent}{HTML}{1F618D}
\definecolor{lightgray}{HTML}{F2F3F4}
\definecolor{darkgray}{HTML}{2C3E50}
% ===== Hyperref =====
\hypersetup{colorlinks=true,linkcolor=linkblue,citecolor=linkblue,urlcolor=linkblue,
  pdftitle={Bao cao PBL -- Fine-tuning Stylist},
  pdfauthor={Nguyen Nhat Quang}}
% ===== Listings (Python code blocks) =====
\lstset{backgroundcolor=\color{codebg},basicstyle=\ttfamily\small,
 keywordstyle=\color{codekey}\bfseries,commentstyle=\color{gray}\itshape,
 stringstyle=\color{red!50!black},breaklines=true,frame=single,
 showstringspaces=false,tabsize=2,language=Python,
 columns=fullflexible,keepspaces=true}
% ===== Caption styling =====
\captionsetup{font=small,labelfont={bf,color=accent},labelsep=period,skip=4pt}
% ===== Section title styling =====
\titleformat{\section}{\Large\bfseries\color{darkgray}}{\thesection}{1em}{}
\titleformat{\subsection}{\large\bfseries\color{accent}}{\thesubsection}{1em}{}
\titlespacing{\section}{0pt}{1.2em}{0.5em}
\titlespacing{\subsection}{0pt}{1em}{0.3em}
% ===== Headers/footers =====
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small\color{gray} OutfitMatch -- Stylist Model}
\fancyhead[R]{\small\color{gray} \thepage}
\renewcommand{\headrulewidth}{0.4pt}
\renewcommand{\footrulewidth}{0pt}
% ===== Document =====
\begin{document}
% ===== Titlepage (avoids \\ inside \title/\author argument issues) =====
\begin{titlepage}
\centering
\vspace*{1.5cm}
{\Huge\bfseries\color{darkgray} Báo cáo Project-Based Learning\par}
\vspace{8pt}
{\Large\color{accent} Fine-tuning Mô hình Stylist Đa phương thức\\
cho Hệ thống Gợi ý Trang phục\par}
\vspace{14pt}
{\large\color{gray} Môn học: Deep Learning $\bullet$ Năm học 2025--2026\par}
\vfill
{\Large\bfseries Nguyễn Nhật Quang\par}
\vspace{6pt}
{\normalsize Sinh viên năm 3 --- Ngành Trí tuệ Nhân tạo\par
Trường CNTT\&TT --- Đại học FPT\par}
\vspace{6pt}
{\small\color{gray} Giảng viên hướng dẫn: \textit{[Tên GV]}\par}
\vspace{12pt}
{\small Tháng 07 năm 2026\par}
\vspace*{1.5cm}
\end{titlepage}
\thispagestyle{empty}
\begin{abstract}
\noindent Báo cáo này trình bày quá trình xây dựng và tinh chỉnh mô hình \emph{Stylist} --- thành phần
giao tiếp bằng ngôn ngữ tự nhiên trong hệ thống gợi ý trang phục OutfitMatch. Trọng tâm của
đồ án là áp dụng các kỹ thuật học sâu hiện đại: học chuyển giao qua mô hình ngôn ngữ lớn
(LLM) tiền huấn luyện, tinh chỉnh tham số thấp (LoRA/QLoRA), lượng tử hóa 4-bit, và học tăng
cường với phần thưởng có thể kiểm chứng (GRPO). Chúng tôi so sánh bốn ứng viên dựa trên
Qwen3-VL-8B, Qwen3.5-9B và Gemma-4-12B, huấn luyện trên \textbf{11.252 mẫu hội thoại tiếng Việt},
và chọn Qwen3-VL-8B-Thinking + LoRA (4-bit) làm mô hình sản xuất với Tool-F1 đạt
\textbf{0.8980}, tỷ lệ tuân thủ định dạng \textbf{1.0} và eval loss \textbf{0.5943}.
\end{abstract}
\vspace{0.5em}
\begin{tcolorbox}[colback=lightgray,colframe=accent,arc=3pt,boxrule=0.8pt]
\textbf{Từ khóa:} LoRA $\cdot$ QLoRA $\cdot$ GRPO $\cdot$ Tool-calling $\cdot$ Qwen3-VL $\cdot$ Lượng tử hóa 4-bit $\cdot$ Verifiable Reward
\end{tcolorbox}
\tableofcontents
\newpage
\section{Giới thiệu}
\label{sec:intro}
\subsection{Bối cảnh và động lực}
OutfitMatch là hệ thống gợi ý trang phục nhận thức dáng người và dịp mặc
(\emph{Body \& Occasion-Aware Fashion Recommender}), phát triển trong khuôn khổ môn học
Deep Learning. Hệ thống hoạt động theo kiến trúc 4 tầng (hình~\ref{fig:arch}):
(1) Knowledge Base (KB), (2) Stylist, (3) Retrieval, và (4) Personalization (Quiz).
Trong đó, tầng Stylist đóng vai trò \emph{giao diện hội thoại}: tiếp nhận yêu cầu tiếng
Việt (văn bản và/hoặc ảnh) từ người dùng, diễn giải ý định (\emph{intent parsing}), quyết
định gọi công cụ (\emph{tool-calling}) để truy vấn kho outfit, và cuối cùng giải thích kết
quả bằng tiếng Việt mà không bịa thông tin.
\begin{figure}[H]
  \centering
  \begin{tcolorbox}[colback=white,colframe=darkgray,arc=4pt,boxrule=0.8pt,width=0.92\textwidth]
    \centering\small
    \textbf{Người dùng} (văn bản / ảnh / quiz) \\[3pt]
    $\big\downarrow$ \\[3pt]
    \textbf{Tầng 2 --- Stylist (LLM + LoRA)}: parse intent $\rightarrow$ hỏi lại hoặc
    gọi \texttt{search\_outfits(occasion, style, body\_shape, \dots)} \\[3pt]
    $\big\downarrow$ \\[3pt]
    Tầng 3 --- Retrieval: seed-filter $\rightarrow$ graph traversal $\rightarrow$ post-filter outfit \\[3pt]
    $\big\downarrow$ \\[3pt]
    Tầng 2 --- Stylist: giải thích outfit bằng tiếng Việt
  \end{tcolorbox}
  \caption{Vị trí tầng Stylist trong kiến trúc OutfitMatch v3.1-lite (4 tầng).}
  \label{fig:arch}
\end{figure}
\subsection{Vấn đề nghiên cứu}
Việc dùng một LLM chung (off-the-shelf) làm stylist gặp ba thách thức đặc thù:
\begin{itemize}[leftmargin=1.2em,itemsep=4pt]
  \item \textbf{Ánh xạ ngôn ngữ tự nhiên sang từ vựng kiểm soát (\emph{controlled vocabulary}):}
  người dùng viết ``đi làm'', ``đi tiệc cưới'', ``tránh màu sáng'' nhưng hệ thống retrieval
  chỉ chấp nhận các giá trị enum tiếng Anh snake\_case (ví dụ \texttt{office}, \texttt{wedding}, \texttt{elegant}).
  \item \textbf{Chống ảo giác (\emph{anti-hallucination}):} mô hình không được tự bịa
  \texttt{outfit\_id} hay giá tiền không tồn tại trong KB.
  \item \textbf{Đa phương thức (\emph{multimodal}):} hỗ trợ người dùng gửi ảnh selfie/ảnh outfit để phân tích dáng người.
\end{itemize}
Báo cáo này tập trung vào việc giải quyết các vấn đề trên bằng phương pháp \emph{fine-tuning}
một LLM đa phương thức nền tảng, thay vì xây dựng mô hình từ đầu (vốn không khả thi về dữ liệu và compute).
\section{Cơ sở lý thuyết}
\label{sec:theory}
\subsection{Mô hình ngôn ngữ lớn và học chuyển giao}
Mô hình Stylist được xây dựng trên kiến trúc Transformer decoder-only tiền huấn luyện trên
quy mô lớn. Thay vì huấn luyện từ đầu, chúng tôi tận dụng \emph{transfer learning}: trọng số
tiền huấn luyện mang năng lực ngôn ngữ đa ngôn ngữ và suy luận chung, sau đó được tinh chỉnh
trên tập dữ liệu hội thoại thời trang tiếng Việt.
Với biến thể đa phương thức Qwen3-VL, mô hình bổ sung một bộ mã hóa thị giác (ViT ---
\emph{Vision Transformer}) nối vào backbone LLM qua cơ chế chiếu chéo (cross-attention
projection). Đầu vào có thể là văn bản, ảnh, hoặc cả hai trong cùng một prompt.
\subsection{LoRA và QLoRA --- Tinh chỉnh tham số thấp}
Huấn luyện toàn bộ ($>8$ tỷ tham số) đòi hỏi VRAM vượt quá giới hạn phần cứng (GPU 8--16\,GB).
Chúng tôi dùng \textbf{QLoRA} (Quantized LoRA) \cite{dettmers2023qlora}, kết hợp:
\begin{itemize}[leftmargin=1.2em,itemsep=4pt]
  \item \textbf{Lượng tử hóa 4-bit NF4 + double-quant} giảm bộ nhớ trọng số nền tảng từ
  $\sim 16$\,GB (bf16) xuống $\sim 4$--$5$\,GB.
  \item \textbf{LoRA} \cite{hu2021lora}: chỉ huấn luyện các ma trận hệ số thấp $\Delta W = BA$
  ($\text{rank } r=16$, $\alpha=32$) ghép vào các projection layers, đồng bằng trọng số gốc.
\end{itemize}
Số tham số huấn luyện chỉ chiếm một phần nhỏ của toàn bộ mô hình, giúp quá trình huấn luyện
chạy trên GPU T4 (Kaggle) và RTX 5060 Laptop 8\,GB (máy dev).
\subsection{Học tăng cường với phần thưởng có thể kiểm chứng (GRPO)}
Sau SFT (Supervised Fine-Tuning), chúng tôi thử nghiệm \textbf{GRPO} (Group Relative Policy
Optimization) \cite{shao2024deepseekmath} --- thuật toán RL on-policy không dùng Reward Model.
GRPO sinh $G$ hoàn chỉnh cho mỗi prompt, chuẩn hóa phần thưởng theo trung bình và độ lệch
chuẩn của nhóm, và tối ưu bằng PPO-style clipped objective kèm KL penalty ($\beta=0.04$):
\begin{equation}
  \hat{A}_i = \frac{r_i - \mathrm{mean}(r_1,\dots,r_G)}{\mathrm{std}(r_1,\dots,r_G)},
\end{equation}
\begin{equation}
  \mathcal{L}_{\text{GRPO}} = -\mathbb{E}\!\left[\min\!\left(
  \frac{\pi_\theta(y_i\mid x)}{\pi_{\text{old}}(y_i\mid x)}\hat{A}_i,\,
  \mathrm{clip}\!\left(\frac{\pi_\theta}{\pi_{\text{old}}},1-\epsilon,1+\epsilon\right)\hat{A}_i
  \right) - \beta\, \mathrm{KL}(\pi_\theta \| \pi_{\text{ref}})\right].
\end{equation}
Phần thưởng $r_i$ ở đây là các hàm quy tắc xác định (\emph{deterministic scorers}) trên tri
thức thời trang, không cần mô hình phân xét --- đảm bảo \emph{verifiable reward}.
\section{Phương pháp}
\label{sec:method}
\subsection{Lựa chọn mô hình nền tảng}
Chúng tôi khảo sát ba ứng viên (bảng~\ref{tab:models}). Tiêu chí then chốt: hỗ trợ tiếng
Việt, có công cụ gọi hàm (\emph{native tool-calling}), và VRAM 4-bit thấp.
\begin{table}[H]
  \centering
  \caption{Ba ứng viên mô hình nền tảng cho tầng Stylist.}
  \label{tab:models}
  \renewcommand{\arraystretch}{1.15}
  \begin{tabular}{lccc}
    \toprule
    \textbf{Thuộc tính} & Qwen3.5-9B & Qwen3-VL-8B & Gemma-4-12B \\
    \midrule
    Kiến trúc & Decoder-only & ViT + LLM (VL) & Decoder-only \\
    Tham số & 9B & 8B (LLM 7.5B + ViT 0.5B) & 12B \\
    Modal đầu vào & Chỉ văn bản & Văn bản + Ảnh & Chỉ văn bản \\
    Tool-calling & Có & Có & Không (prompt hack) \\
    VRAM (4-bit) & $\sim$5--6\,GB & $\sim$4--5\,GB & $\sim$7--8\,GB \\
    Tiếng Việt & Tốt & Khá & Yếu \\
    \bottomrule
  \end{tabular}
\end{table}
Quyết định thiết kế: chọn \textbf{Qwen3-VL-8B} làm mô hình chính vì khả năng đa phương thức
(chấp nhận ảnh người dùng --- tính năng cốt lõi v3.1) và tool-calling native; Qwen3.5-9B làm
phương án fallback text-only; Gemma-4-12B chỉ để so sánh ablation.
\subsection{Công cụ truy vấn (Tool-calling schema)}
Mô hình không truy xuất trực tiếp mà gọi công cụ \texttt{search\_outfits} với các tham số có
kiểu enum lấy từ \texttt{vocab.py} --- nguồn duy nhất của controlled vocabulary:
\begin{lstlisting}[caption={Định nghĩa công cụ search\_outfits (trích xuất từ tools.py).}]
SEARCH_OUTFITS_TOOL = {
  "name": "search_outfits",
  "parameters": {
    "occasion":   enum(list(OCCASION)),     # bat buoc
    "style":      enum(list(STYLE)),
    "body_shape": enum(list(BODY_SHAPE)),
    "skin_tone":  enum(list(SKIN_TONE)),
    "price_max":  integer,                  # VND
    "exclude_colors": array[string],
  },
  "required": ["occasion"],
}
\end{lstlisting}
Định dạng wire-format chuẩn hóa:
\texttt{<tool\_call>\{"name":"search\_outfits","arguments":\{...\}\}</tool\_call>}. Một lớp
\emph{validation} kiểm tra mọi \texttt{outfit\_id} sinh ra có tồn tại trong KB và mọi tham số
tool có hợp lệ theo schema --- cơ chế chống ảo giác cứng (\emph{hard guardrail}).
\subsection{Tập dữ liệu huấn luyện}
Tập dữ liệu cuối (\emph{final merged dataset}) gồm \textbf{11.252 mẫu huấn luyện / 348 mẫu eval},
trong đó 1.360 mẫu huấn luyện và 40 mẫu eval là các cặp tool-calling. Dữ liệu kết hợp ba
nhóm hành vi: \texttt{tool\_calling} / \texttt{tool\_calling\_grounded} (học gọi đúng
field/enum); \texttt{recommend\_explain} (giải thích outfit); \texttt{ask\_missing\_info}
(hỏi lại khi thiếu thông tin); \texttt{polite\_decline}, \texttt{anti\_hallucination} (từ
chối khi thiếu dự kiện); \texttt{body\_fit}, \texttt{multi\_turn}, \texttt{stylist\_knowledge}
(tư vấn dáng, hội thoại đa lượt, kiến thức phối đồ). Dữ liệu sinh tổng hợp (\emph{synthetic})
bằng Gemini Flash cộng metadata catalog Việt Nam, chuẩn hóa sang định dạng ChatML.

Các hình~\ref{fig:topic}--\ref{fig:len} minh họa phân bố và chất lượng tập dữ liệu sau cổng
chất lượng (\emph{quality gate}) chưng lọc (\emph{distillation}).
\begin{figure}[H]
  \centering
  \begin{minipage}[t]{0.46\textwidth}
    \centering
    \includegraphics[width=\textwidth]{topic_distribution_raw_vs_distilled.png}
    \caption{Phân bố chủ đề hội thoại: raw (trước quality gate) vs.\ distilled (sau lọc).}
    \label{fig:topic}
  \end{minipage}\hfill
  \begin{minipage}[t]{0.46\textwidth}
    \centering
    \includegraphics[width=\textwidth]{prompt_style_raw_vs_distilled.png}
    \caption{Phong cách prompt raw vs.\ distilled --- các mẫu phức tạp được loại.}
    \label{fig:style}
  \end{minipage}
\end{figure}
\begin{figure}[H]
  \centering
  \begin{minipage}[t]{0.46\textwidth}
    \centering
    \includegraphics[width=\textwidth]{quality_gate_drops.png}
    \caption{Số mẫu bị loại qua từng tầng quality gate.}
    \label{fig:gate}
  \end{minipage}\hfill
  \begin{minipage}[t]{0.46\textwidth}
    \centering
    \includegraphics[width=\textwidth]{answer_length_hist_raw_vs_distilled.png}
    \caption{Histogram độ dài câu trả lời: raw vs.\ distilled.}
    \label{fig:len}
  \end{minipage}
\end{figure}
\begin{figure}[H]
  \centering
  \begin{minipage}[t]{0.55\textwidth}
    \centering
    \includegraphics[width=\textwidth]{family_size_buckets_raw_vs_distilled.png}
    \caption{Phân nhóm kích thước gia đình outfit raw vs.\ distilled.}
    \label{fig:fam}
  \end{minipage}
\end{figure}
\subsection{Cấu hình huấn luyện (SFT --- QLoRA)}
Pipeline dùng \textbf{Unsloth} trên Kaggle T4$\times$2. Cấu hình chính (bảng~\ref{tab:hyper}):
\begin{table}[H]
  \centering
  \caption{Hyperparameters huấn luyện QLoRA (theo stylist\_finetune\_kaggle.yaml).}
  \label{tab:hyper}
  \renewcommand{\arraystretch}{1.15}
  \begin{tabular}{ll}
    \toprule
    \textbf{Tham số} & \textbf{Giá trị} \\
    \midrule
    Framework & Unsloth + QLoRA (SFT) \\
    Quantization & 4-bit NF4, double-quant \\
    LoRA rank $r$ / $\alpha$ & 16 / 32 \\
    LoRA dropout / bias & 0.05 / none \\
    Target modules & q,k,v,o\_proj; gate,up,down\_proj \\
    Max seq length & 2048 \\
    Batch (per device) & 1 (effective = 1$\times$GPU$\times$8 grad-accum) \\
    Learning rate & $2\times10^{-4}$ (cosine, warmup 3\%) \\
    Epochs & 1 (704 steps) \\
    Optimizer & AdamW 8-bit (paged) \\
    \bottomrule
  \end{tabular}
\end{table}
Lưu ý kỹ thuật: \texttt{device\_map=\{"":0\}} (không dùng \texttt{"auto"} gây lỗi
CPU-dispatch), và \texttt{torch\_dtype="auto"} (tránh lỗi dtype của lm\_head với checkpoint
bnb-4bit đồng bằng).

Hình~\ref{fig:llama} cho thấy giao diện theo dõi huấn luyện trên LLaMA-Factory, ghi nhận
qua 704 steps (1 epoch) trên dataset 11.252 mẫu.
\begin{figure}[H]
  \centering
  \includegraphics[width=0.72\textwidth]{llamafactory_screenshot.png}
  \caption{Giao diện LLaMA-Factory theo dõi fine-tune QLoRA trên Kaggle T4 (704 steps, 1 epoch).}
  \label{fig:llama}
\end{figure}
\section{Thực nghiệm và Kết quả}
\label{sec:exp}
\subsection{Thiết lập đánh giá}
Chúng tôi dùng 70 \emph{held-out prompts} phủ các loại tác vụ. Các metric: \texttt{mean\_tool\_call\_f1}
(F1 trên field/value tool-call --- quan trọng nhất vì ảnh hưởng trực tiếp đến retrieval E2E);
\texttt{mean\_text\_similarity}; \texttt{format\_compliance\_rate}; \texttt{error\_count}.
\subsection{Kết quả so sánh bốn adapter (SFT)}
Bốn adapter được huấn luyện trên cùng dataset, cùng benchmark (bảng~\ref{tab:bench}).
\begin{table}[H]
  \centering
  \caption{Kết quả benchmark 4 adapter QLoRA (nguồn: stylist\_final\_qlora\_benchmark).}
  \label{tab:bench}
  \renewcommand{\arraystretch}{1.2}
  \begin{tabular}{lcccc}
    \toprule
    \textbf{Model} & Eval loss & Tool F1 & Text sim & Format \\
    \midrule
    T3 Qwen3-VL-8B Thinking & \textbf{0.5943} & \textbf{0.8980} & \textbf{0.5519} & \textbf{1.0000} \\
    T2 Qwen3.5-9B BNB4 & 0.6880 & 0.8776 & 0.4877 & 1.0000 \\
    T1 Qwen3-VL-8B Instruct & 0.6027 & 0.8571 & 0.5437 & 1.0000 \\
    T4 Gemma-4-12B IT & 0.6255 & 0.6531 & 0.5354 & 0.9714 \\
    \bottomrule
  \end{tabular}
\end{table}
\paragraph{Phân tích.} T3 thắng tổng thể vì ổn định nhất: eval loss thấp nhất, Tool F1 cao
nhất, text similarity cao nhất và compliance 1.0. Đáng chú ý, \textbf{eval loss không quyết
định ranking} --- Gemma có loss 0.6255 nhưng Tool F1 chỉ 0.6531 vì không ``học'' trigger gọi
tool (đạt 0.0000 ở nhóm \texttt{tool\_calling} non-grounded). Với bài toán có \emph{contract
cứng}, chất lượng phải đo bằng hành vi tool-calling chứ không chỉ likelihood.
\subsection{Học tăng cường (GRPO) --- thử nghiệm và giới hạn}
Chúng tôi thiết kế 6 hàm phần thưởng xác định (bảng~\ref{tab:reward}) cầu nối từ
\texttt{fashion\_eval.py} sang \texttt{GRPOTrainer} của TRL.
\begin{table}[H]
  \centering
  \caption{6 reward functions cho GRPO (nguồn: grpo\_rewards.py).}
  \label{tab:reward}
  \renewcommand{\arraystretch}{1.15}
  \begin{tabular}{llp{6cm}}
    \toprule
    Mã & Scorer & Đo lường \\
    \midrule
    R1 & occasion\_formality & Precision/recall/F1 trên enum formality \\
    R2 & body\_shape\_advice & Recall positive $-$ 0.5$\times$negative keywords \\
    R3 & season\_advice & Recall positive $-$ 0.5$\times$negative keywords \\
    R4 & coherence & Binary accuracy (phù hợp/không) \\
    R5 & ask\_back & 1.0 nếu hỏi lại \& không ảo giác \\
    R6 & tool\_call\_derivation & Tool-call F1 $\times$ enum\_valid \\
    \bottomrule
  \end{tabular}
\end{table}
Chạy thực tế trên RTX 5060 Laptop 8\,GB cho thấy \emph{giới hạn phần cứng}: ở
\texttt{max\_completion\_length=96} (đủ RAM) câu trả lời bị cắt ngắn $\rightarrow$ reward = 0;
ở $\ge 160$ thì OOM. Tương tự trên Kaggle T4 16\,GB, cấu hình fit duy nhất là
\texttt{batch=1, G=2, max\_completion\_length=128}, và reward vẫn = 0 do truncation. Fix
thông qua \emph{tightening prompt} (câu $<$ 100 token, chỉ keyword/enum) đưa reward từ 0 lên
0.059 trên mô hình mock. Bài học then chốt: \textbf{GRPO cho 8B QLoRA không khả thi trên 8\,GB
VRAM} --- cần T4$\times$2 hoặc DeepSpeed. Đây là ranh giới thực tế giữa lý thuyết RL và ràng
buộc phần cứng.

Hình~\ref{fig:wb_reward} và \ref{fig:wb_table} ghi nhận dữ liệu W\&B thật từ run GRPO
(\texttt{6sk8ezbl}, project \texttt{vominhnhatquang-fpt-university/outfitmatch-stylist}):
\textbf{train/reward = 0 ở mọi step} (global\_step 10--60), run ghi nhận là \emph{crashed}.
Đây là bằng chứng thật của giới hạn, \textbf{không} phải kết quả thành công.
\begin{figure}[H]
  \centering
  \begin{minipage}[t]{0.46\textwidth}
    \centering
    \includegraphics[width=\textwidth]{wandb_grpo_reward_6sk8ezbl.png}
    \caption{W\&B: \texttt{train/reward} qua 6 steps của run GRPO \texttt{6sk8ezbl} --- reward = 0 ở mọi step do truncation (giới hạn 8\,GB VRAM).}
    \label{fig:wb_reward}
  \end{minipage}\hfill
  \begin{minipage}[t]{0.46\textwidth}
    \centering
    \includegraphics[width=\textwidth]{wandb_grpo_table_6sk8ezbl.png}
    \caption{W\&B: bảng metric thật của run \texttt{6sk8ezbl} --- reward/loss = 0, run \emph{crashed}. Bằng chứng giới hạn, không phải thành công.}
    \label{fig:wb_table}
  \end{minipage}
\end{figure}
\subsection{Kết quả baseline GRPO trên GPU thật}
Benchmark rule-based trên 28 items $\times$ 6 scorers (bảng~\ref{tab:gpu}):
\begin{table}[H]
  \centering
  \caption{Mean score các scorer trên GPU RTX 5060 8\,GB (rev 3, đã fix vocabulary bug).}
  \label{tab:gpu}
  \renewcommand{\arraystretch}{1.2}
  \begin{tabular}{lccc}
    \toprule
    Task & T1 (VL Instruct) & T2 (9B text) & T3 (VL Thinking) \\
    \midrule
    occasion\_formality & 0.607 & 0.585 & \textbf{0.740} \\
    body\_shape\_advice & 0.000 & 0.050 & 0.040 \\
    season\_advice & 0.258 & 0.333 & \textbf{0.383} \\
    coherence & 0.500 & \textbf{1.000} & 0.500 \\
    ask\_back & 0.667 & 0.667 & 0.667 \\
    tool\_call\_derivation & \textbf{0.812} & 0.788 & 0.763 \\
    \textbf{Overall mean} & 0.462 & \textbf{0.543} & 0.524 \\
    \bottomrule
  \end{tabular}
\end{table}
T3 dẫn đầu ở kiến thức dịp/mùa và có tool-calling SFT mạnh nhất, là mục tiêu RL dù mean thấp
hơn T2 một chút vì là mô hình đa phương thức duy nhất (có vision tower).
\section{Thảo luận}
\label{sec:discuss}
\subsection{Bài học về đo lường chất lượng mô hình}
Với hệ thống có \emph{tool contract cứng}, eval loss là metric gây hiểu lầm: một mô hình có
loss thấp vẫn có thể sai enum, bỏ quên \texttt{<tool\_call>}, hay trả lời prose thay vì JSON.
Benchmark hành vi (Tool F1, format compliance) phải là tiêu chí chọn mô hình chính.
\subsection{Trade-off đa phương thức vs.\ nguồn ngữ}
Qwen3-VL-8B (Thinking) thắng dự Qwen3.5-9B text-only vì tính năng ảnh người dùng là yêu cầu
cốt lõi, và vision tower không thể thêm sau vào mô hình text-only. Đây là ví dụ ưu tiên
\emph{fit với bài toán sản phẩm} hơn tối ưu benchmark hẹp.
\subsection{Hạn chế}
Benchmark 70 mẫu chưa đủ sâu cho regression; GRPO chưa chạy thành công trên compute hiện có
do giới hạn độ dài sinh; dữ liệu tool-calling hard-case còn mỏng.
\section{Kết luận}
\label{sec:conclude}
Đồ án hiện thực hóa thành công tầng Stylist của OutfitMatch bằng fine-tuning LLM đa phương
thức --- minh họa chu trình: transfer learning $\rightarrow$ QLoRA $\rightarrow$ tool-calling
schema $\rightarrow$ verifiable-reward RL $\rightarrow$ benchmark hành vi. Kết quả: (1) fine-tune
thành công 4 adapter QLoRA trên Kaggle, publish lên Hugging Face; (2) chọn \textbf{Qwen3-VL-8B-Thinking
+ LoRA (4-bit)}: Tool F1 = 0.8980, Format = 1.0, Eval loss = 0.5943; (3) thiết kế 6 deterministic
reward functions cho GRPO và phát hiện giới hạn phần cứng thực tế của RL 8B trên GPU 8\,GB.
Hướng phát triển: tăng dữ liệu hard-case, mở rộng benchmark lên 200--500 mẫu, thêm constrained
decoding / parser repair, và chạy GRPO trên T4$\times$2.
\section*{Lời cảm ơn}
Đồ án sử dụng tài nguyên Kaggle T4 và RTX 5060 8\,GB. Cảm ơn nhóm OutfitMatch (3 thành viên) và giảng viên.
\begin{thebibliography}{99}
\bibitem{dettmers2023qlora} T. Dettmers, A. Pagnoni, A. Holtzman, L. Zettlemoyer. \emph{QLoRA: Efficient Finetuning of Quantized LLMs}. arXiv:2305.14314, 2023.
\bibitem{hu2021lora} E. J. Hu, Y. Shen, P. Wallis, et al. \emph{LoRA: Low-Rank Adaptation of Large Language Models}. arXiv:2106.09685, 2021.
\bibitem{shao2024deepseekmath} Z. Shao, P. Wang, Q. Zhu, et al. \emph{DeepSeekMath}. arXiv:2402.03300, 2024.
\bibitem{liu2025drgrpo} Z. Liu, et al. \emph{Dr. GRPO}. arXiv:2503.20783, 2025.
\bibitem{vasileva2018polyvore} M. Vasileva, et al. \emph{Learning Type-Aware Embeddings for Fashion Compatibility}. ECCV 2018.
\bibitem{qwen3vl} Qwen Team. \emph{Qwen3-VL Technical Report}. \url{https://github.com/QwenLM/Qwen3-VL}, 2025.
\end{thebibliography}
\end{document}
"""

def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(CONTENT)
    print(f"OK: wrote {OUT}")
    print(f"   lines: {CONTENT.count(chr(10))+1}")
    print(f"   includegraphics: {CONTENT.count('includegraphics')}")
    diac = sum(CONTENT.count(c) for c in "áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ")
    print(f"   Vietnamese diacritic chars: {diac}")

if __name__ == "__main__":
    main()
