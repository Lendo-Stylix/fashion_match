import json

# Danh sách các file cần gộp
file_names = [
    'D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\4men_products_full.json', 
    'D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\5sfashion_products_full.json', 
    'D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\aristino_products_full.json',
    "D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\badrabbit_products_full.json",
    "D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\canifa_products_full.json",
    "D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\citycycle_products_full.json",
    "D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\coolmate_products_full.json",
    "D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\degrey_products_full.json",
    "D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\dirtycoins_products_full.json",
    "D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\elise_products_full.json",
    "D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\gumac_products_full.json",
    "D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\hm_products_full.json",
    "D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\juno_products_full.json",
    "D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\levents_products_full.json",
    "D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\owen_products_full.json",
    "D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\teelab_products_full.json",
    "D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\underarmour_products_full.json",
    "D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\uniqlo_products_full.json",
    "D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\yame_products_full.json",
    "D:\\Learning\\ky_5\\DPL302m\\Project\\fashion_match\\loc_scraper\\harvest\\result\\yody_products_full.json",
]

combined_data = []

# Đọc và gộp dữ liệu từ từng file
for file_name in file_names:
    try:
        with open(file_name, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Các file này đều chứa một list (mảng) các sản phẩm
            if isinstance(data, list):
                combined_data.extend(data)
            else:
                combined_data.append(data)
        print(f"Đã đọc thành công file: {file_name}")
    except Exception as e:
        print(f"Lỗi khi đọc file {file_name}: {e}")

# Lưu toàn bộ dữ liệu đã gộp vào một file duy nhất
output_file = 'combined_products_full.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(combined_data, f, ensure_ascii=False, indent=4)

print(f"\nĐã gộp thành công! Tổng số sản phẩm thu được: {len(combined_data)}")
print(f"File mới được lưu tại: {output_file}")