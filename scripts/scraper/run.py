"""
run.py — CLI Entry Point cho scraper.

Cách dùng:
    # Cào toàn bộ Coolmate (tất cả category):
    python run.py --site coolmate

    # Cào Gumac, giới hạn 50 sản phẩm:
    python run.py --site gumac --limit 50

    # Cào Coolmate, lưu vào thư mục riêng:
    python run.py --site coolmate --output D:/my_data

Trước khi chạy:
    1. Chạy chrome_launcher.bat để khởi động Chrome
    2. Đảm bảo đã cài: pip install -r requirements.txt
    3. Nếu là lần đầu: pip install playwright && playwright install chromium
"""

import asyncio
import argparse
import sys
import os
import io

# Fix UnicodeEncodeError trên Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Thêm thư mục scraper vào Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper import scrape_site


def parse_args():
    parser = argparse.ArgumentParser(
        description="🛍️ Fashion Web Scraper — Thu thập dữ liệu sản phẩm thời trang",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ:
  python run.py --site coolmate
  python run.py --site gumac --limit 100
  python run.py --site coolmate --output D:/my_output
        """
    )
    parser.add_argument(
        "--site",
        required=True,
        choices=["coolmate", "gumac"],
        help="Website cần cào dữ liệu"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Giới hạn số sản phẩm (mặc định: không giới hạn)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Thư mục lưu kết quả (mặc định: ../../data/scraped/<site>)"
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    print(f"""
╔══════════════════════════════════════════════════════════╗
║         🛍️  FASHION WEB SCRAPER                         ║
║         Site   : {args.site:<38}║
║         Limit  : {str(args.limit or 'Không giới hạn'):<38}║
╚══════════════════════════════════════════════════════════╝

💡 Khởi chạy chế độ Headless Parallel tự động.
    """)

    try:
        stats = await scrape_site(
            site_name=args.site,
            limit=args.limit,
            output_dir=args.output,
        )
        success_rate = (stats["success"] / max(stats["total"], 1)) * 100
        print(f"\n✅ Hoàn thành! Tỷ lệ thành công: {success_rate:.1f}%")
    except ConnectionRefusedError:
        print("\n❌ LỖI: Không kết nối được Chrome!")
        print("   → Hãy chạy chrome_launcher.bat trước.\n")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️  Đã dừng bởi người dùng.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ LỖI KHÔNG MONG ĐỢI: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
