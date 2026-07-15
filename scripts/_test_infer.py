import sys
sys.stdout.reconfigure(encoding="utf-8")
from outfitmatch.stylist.service import StylistService

svc = StylistService(model=None, processor=None, graph=None)
tests = [
    "Đám cưới bạn thân cuối tuần này mình mặc gì cho đẹp?",
    "Gợi ý outfit đi làm văn phòng nam, style tối giản, ngân sách dưới 1.5 triệu",
    "Mình cao 1m75 nặng 90kg, đi hẹn hò xem phim mặc sao cho thoải mái?",
    "Phong cách streetwear cho nam mùa hè có gợi ý gì?",
    "Đi sinh nhật bạn gái, màu đỏ chủ đạo, tránh đồ đen, ngân sách 2 triệu",
    "Chào bạn, hôm nay thời tiết thế nào?",
]
for t in tests:
    print(repr(t[:40]), "->", svc._infer_request(t, ""))
