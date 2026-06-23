Dựa trên bundle hiện tại, mình nghĩ vấn đề lớn nhất không còn là “thiếu distill”, mà là distill đúng thứ
 cần học.
 Nếu mục tiêu là tăng hiệu quả fine-tune rõ rệt, mình đề xuất ưu tiên các chiến lược sau:

 1. Chuyển từ “knowledge-heavy” sang “behavior-grounded”

 Hiện dataset vẫn khá thiên về kiến thức fashion chung. Nhưng model stylist production cần học:

 - hỏi lại khi thiếu info
 - gọi tool đúng lúc
 - không bịa
 - giải thích ngắn, đúng ngữ cảnh user
 - giữ state qua multi-turn

 ### Nên làm

 Tăng mạnh các mẫu:
 - ask_missing_info
 - tool_calling
 - recommend_explain
 - polite_decline
 - multi_turn

 ### Cụ thể

 Không chỉ synthetic chung chung, mà phải gắn với flow thật:
 - user intent → tool params
 - tool result giả lập thật → answer
 - thiếu field → hỏi field nào trước
 - field optional vs required
 - không có kết quả → fallback thế nào

 ### Tác động

 Model sẽ “giống assistant thật” hơn, thay vì chỉ “biết thời trang”.

 ────────────────────────────────────────────────────────────────────────────────

 2. Ground dataset vào retrieval/runtime thật

 Đây là chiến lược có tác động lớn nhất.

 Hiện nhiều row knowledge là fashion advice chung. Nhưng downstream thật của bạn là:
 - parse intent
 - gọi search_outfits
 - nhận outfit candidates
 - giải thích theo item thật / budget thật / occasion thật

 ### Nên làm

 Sinh thêm data từ pipeline thật:

 Input
 - prompt user thật hoặc synthetic sát thực tế VN

 Target
 - tool call đúng schema
 - hoặc final answer dựa trên OutfitRecord thật

 ### Ví dụ loại row nên có

 - “Đi cafe tối, ngân sách 800k, không thích màu cam”
   → tool call đúng params
 - tool trả 3 outfit
   → answer chọn 1-2 outfit và giải thích ngắn
 - tool trả 0 outfit
   → xin thêm info / nới điều kiện
 - user đòi outfit_id giả
   → decline đúng

 ### Tác động

 Model học đúng distribution inference-time.
 Đây thường là khác biệt lớn nhất giữa “finetune có vẻ ổn” và “finetune dùng được”.

 ────────────────────────────────────────────────────────────────────────────────

 3. Bổ sung hard negatives và counterfactuals

 Fine-tune tốt không chỉ cần positive examples.

 ### Nên thêm các case:

 - prompt thiếu occasion
 - prompt mâu thuẫn: “đi đám cưới nhưng siêu casual”
 - budget quá thấp cho yêu cầu sang trọng
 - body-shape/occasion/style conflict
 - user yêu cầu model bịa sản phẩm / size / outfit_id
 - user nhập quá mơ hồ
 - tool params gần đúng nhưng sai 1 field
 - answer dài nhưng kém hữu ích vs answer ngắn đúng trọng tâm

 ### Tác động

 Model học boundary rõ hơn:
 - khi nào hỏi lại
 - khi nào từ chối
 - khi nào không được tự tin trả lời

 ────────────────────────────────────────────────────────────────────────────────

 4. Tăng dữ liệu cho các topic hiếm theo targeted augmentation

 Hiện các nhóm yếu vẫn quá ít:
 - occasion_styling
 - care_maintenance
 - layering_season
 - shoes_accessories

 ### Nên làm

 Không tăng đều toàn bộ dataset.
 Chỉ tăng có chủ đích các vùng hiếm nhưng quan trọng với UX.

 ### Cách làm tốt hơn random synth

 Mỗi topic hiếm nên có:
 - definition
 - how-to
 - first-person
 - request
 - short answer
 - medium answer
 - follow-up case
 - tool/no-tool case

 ### Tác động

 Giảm tình trạng model kéo mọi prompt về color_analysis hoặc wardrobe_capsule.

 ────────────────────────────────────────────────────────────────────────────────

 5. Thay heuristic dedupe bằng semantic dedupe

 Hiện family key theo token đầu khá ổn, nhưng vẫn còn hạn chế.

 ### Nên làm tiếp

 Dùng embedding để gom cluster semantic:
 - paraphrase gần nghĩa
 - chỉ đổi vài cụm nhưng cùng intent
 - cùng answer pattern

 ### Rule gợi ý

 - cluster theo cosine similarity
 - mỗi cluster chỉ giữ top-k row tốt nhất
 - ưu tiên row:
     - rõ intent
     - answer ngắn-gọn-đủ
     - không generic
     - có actionability cao

 ### Tác động

 Giảm lặp gradient tốt hơn token-key heuristic.

 ────────────────────────────────────────────────────────────────────────────────

 6. Distill theo teacher ranking, không chỉ filter rule-based

 Thay vì chỉ loại row xấu, hãy chấm điểm row tốt/xấu.

 ### Nên có quality score cho mỗi sample

 Ví dụ score gồm:
 - clarity của prompt
 - groundedness của answer
 - conciseness
 - actionability
 - natural Vietnamese
 - tool usefulness
 - hallucination risk
 - redundancy penalty

 ### Cách làm

 Dùng LLM judge hoặc rubric tự động để rank:
 - giữ top sample trong mỗi cluster
 - bỏ sample generic / essay / dịch máy / sáo rỗng

 ### Tác động

 Dataset nhỏ hơn nhưng “sắc” hơn.

 ────────────────────────────────────────────────────────────────────────────────

 7. Bổ sung preference/pairwise data cho answer quality

 SFT một mình chưa chắc sửa được vấn đề “answer dài nhưng tệ”.

 ### Nên tạo cặp A/B

 Cùng một prompt:
 - A = answer verbose, generic
 - B = answer ngắn hơn, đúng hơn, grounded hơn

 Dùng cho:
 - DPO / ORPO / pairwise ranking
 - hoặc ít nhất dùng làm teacher filter

 ### Tác động

 Model học được phong cách trả lời mong muốn, không chỉ nội dung đúng/sai.

 ────────────────────────────────────────────────────────────────────────────────

 8. Tách dataset thành 3 tầng thay vì trộn hết

 Hiện bundle đang trộn knowledge + behavioral.
 Nên tách rõ:

 ### Tầng A — Core behavior

 - ask missing info
 - tool calling
 - decline
 - multi-turn
 - response formatting

 ### Tầng B — Grounded recommendation

 - retrieval-grounded answers
 - explanation theo item/outfit thật
 - budget/style/occasion constraints thật

 ### Tầng C — Background fashion knowledge

 - color, fabric, capsule, body fit...

 ### Cách train

 - hoặc weighted mixing
 - hoặc curriculum:
     1. behavior
     2. grounded recommendation
     3. nhẹ background knowledge

 ### Tác động

 Tránh việc knowledge chung lấn át assistant behavior.

 ────────────────────────────────────────────────────────────────────────────────

 9. Dùng failure-driven data generation

 Đây là cách hiệu quả nhất sau vòng fine-tune đầu tiên.

 ### Quy trình

 1. Fine-tune model hiện tại
 2. Chạy benchmark probe
 3. Gom failure thật:
     - hỏi thiếu info nhưng không hỏi lại
     - gọi tool sai params
     - answer quá dài
     - generic explanation
     - fail topic hiếm
 4. Tạo thêm data đúng vào failure đó
 5. Distill lại

 ### Tác động

 Data mới đi đúng vào chỗ model đang yếu, thay vì tăng data mù.

 ────────────────────────────────────────────────────────────────────────────────

 10. Xây held-out benchmark trước khi làm thêm data

 Nếu không có benchmark tốt, rất dễ “cải thiện dataset” nhưng không biết model tốt hơn thật hay không.

 ### Nên có 1 probe set cố định, chia theo task:

 - intent parsing
 - missing-info detection
 - tool-call correctness
 - anti-hallucination
 - concise explanation
 - rare-topic handling
 - multi-turn consistency

 ### Metrics gợi ý

 - tool-call accuracy
 - invalid tool param rate
 - follow-up precision
 - hallucination rate
 - response length median
 - rare-topic pass rate
 - judge score cho usefulness / groundedness / conciseness

 ### Tác động

 Biết chính xác chiến lược nào có ích.

 ────────────────────────────────────────────────────────────────────────────────

 Ưu tiên thực thi

 Nếu phải chọn theo impact cao nhất:

 Ưu tiên 1 — nên làm ngay

 1. Retrieval-grounded SFT data
 2. Failure-driven augmentation
 3. Hard negatives / counterfactuals
 4. Held-out benchmark cố định

 Ưu tiên 2

 5. Semantic dedupe
 6. Teacher quality ranking
 7. Rare-topic targeted augmentation

 Ưu tiên 3

 8. Pairwise preference data
 9. Curriculum / weighted-stage training

 ────────────────────────────────────────────────────────────────────────────────

 Kế hoạch ngắn gọn mình khuyên

 Option thực dụng nhất

 ### Sprint tiếp theo:

 - Giữ bundle 8.8k hiện tại làm baseline
 - Tạo thêm 2k–4k retrieval-grounded behavioral rows
 - Tạo 500–1k hard negatives
 - Lập 200–400 probe examples để benchmark cố định

 ### Mục tiêu

 Dataset mới không cần lớn hơn nhiều, nhưng phải:
 - grounded hơn
 - khó hơn
 - gần runtime hơn
 - đo được tốt hơn