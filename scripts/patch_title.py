#!/usr/bin/env python3
"""Replace the title/author block AND \\maketitle with a titlepage environment.
titlepage gives full control (\\\\, \\vspace, \\centering all work) and avoids the
'There's no line here to end' / 'Paragraph ended before \\author' errors caused
by \\\\ and \\par inside \\title/\\author arguments."""
import io, os
P = os.path.join(os.path.dirname(__file__), "..", "docs", "reports", "stylist_model_report_dl.tex")
P = os.path.normpath(P)

# New title block (as preamble defs are harmless; but we won't use \maketitle).
TITLEPAGE = r"""\begin{titlepage}
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
\thispagestyle{empty}"""

with io.open(P, "r", encoding="utf-8", newline="\n") as f:
    s = f.read()

# 1) Drop the old title-block (Title marker through \date{...} line).
lines = s.split("\n")
start = next(i for i, l in enumerate(lines) if "Title block" in l)
end = start
for i in range(start, len(lines)):
    if lines[i].lstrip().startswith(r"\date{"):
        end = i
        break
assert end > start, "could not find \\date line after Title marker"
lines = lines[:start] + lines[end+1:]
s = "\n".join(lines)

# 2) Replace \maketitle (and the following \thispagestyle{empty}) with TITLEPAGE.
s = s.replace(r"\maketitle" + "\n" + r"\thispagestyle{empty}", TITLEPAGE, 1)
assert r"\maketitle" not in s, "\\maketitle still present after patch"

with io.open(P, "w", encoding="utf-8", newline="\n") as f:
    f.write(s)
print("OK: title block replaced with titlepage environment; \\maketitle removed")
