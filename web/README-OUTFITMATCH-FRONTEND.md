# OutfitMatch — AI Stylist v3.1-lite (Frontend Redesign)

AI Stylist cá nhân hoá phong cách châu Á cho thị trường Việt Nam.  
Frontend được thiết kế lại với **2 themes**: Editorial Light + Luxury Dark.

## ✨ Tính năng frontend

### 2 themes
- **Editorial Light** (default) — warm-neutral ivory + burnt-sienna accent, kiểu tạp chí thời trang cao cấp
- **Luxury Dark** — deep obsidian black + champagne gold, premium feel cho fashion luxury

Toggle theme bằng icon Sun/Sparkles ở góc trên phải Navbar.

### 4 luồng chính (single-page app)
1. **Home** — Hero magazine-style + Feature strip (kiến trúc 4 tầng) + How-it-works 3 bước
2. **Quiz** — Multi-step 5 câu hỏi, progress bar, single/multi-select, animated transitions
3. **Results** — Grid outfit cards sortable (match score / giá), mỗi item có color dot, fabric, store, price VND
4. **Chat** — Streaming SSE realtime với Qwen3-VL Stylist, suggestion chips, caret blink, inline outfit cards

### Stack kỹ thuật
- **Framework**: Next.js 16 + App Router + Turbopack
- **Language**: TypeScript 5 (strict)
- **Styling**: Tailwind CSS 4 + shadcn/ui (New York) + Lucide icons
- **Animation**: Framer Motion
- **Theming**: next-themes (class-based, custom Luxury variant)
- **Fonts**: Playfair Display (display) + Inter (body) + JetBrains Mono (numbers)

## 🚀 Cài đặt

```bash
# Yêu cầu Node.js ≥ 20.9 (test trên Node 26.5.0)
cd outfitmatch-frontend
npm install        # hoặc: bun install / pnpm install

# Dev server (port 3000)
npm run dev

# Production build
npm run build
npm run start
```

## 🔌 Backend integration

Frontend gọi FastAPI backend tại `http://localhost:8000` (mặc định).  
Override bằng env:

```bash
NEXT_PUBLIC_API_URL=http://your-backend:8000 npm run dev
```

Khi backend không khả dụng, UI tự fallback sang **mock data** để demo vẫn chạy được.  
Badge "Backend Live" / "Demo Mode" hiển thị ở Quiz & Results.

### Endpoints API
- `GET /api/quiz` — trả về câu hỏi onboarding
- `POST /api/recommend` — trả về outfits cá nhân hoá
- `POST /api/chat` — SSE streaming với Qwen3-VL stylist (event: token, outfit_cards, error, done)

## 📁 Cấu trúc source

```text
src/
├── app/
│   ├── globals.css          # Design system + 2 themes (light + luxury)
│   ├── layout.tsx           # Fonts, metadata, ThemeProvider
│   └── page.tsx             # Single-page view orchestrator (4 views)
├── components/
│   ├── theme-provider.tsx   # next-themes wrapper
│   ├── outfitmatch/
│   │   ├── Navbar.tsx       # Sticky nav + ThemeToggle
│   │   ├── Hero.tsx         # Editorial hero + collage
│   │   ├── FeatureStrip.tsx # 4-tier architecture cards
│   │   ├── QuizSection.tsx  # Multi-step quiz
│   │   ├── ResultsSection.tsx # Sortable outfit grid
│   │   ├── ChatSection.tsx  # SSE streaming chat
│   │   ├── OutfitCard.tsx   # Rich outfit card with item tiles
│   │   ├── Footer.tsx       # Sticky footer
│   │   └── ThemeToggle.tsx  # Light ⇄ Luxury toggle
│   └── ui/                  # shadcn/ui primitives
└── lib/
    ├── api.ts               # API client + mock fallback
    ├── db.ts                # Prisma client (optional)
    └── utils.ts             # cn() helper
```

## 🎨 Design tokens

### Editorial Light (default)
| Token | Value | Mô tả |
|---|---|---|
| `--background` | `oklch(0.975 0.012 75)` | Warm ivory |
| `--foreground` | `oklch(0.22 0.018 55)` | Deep cocoa |
| `--brand` | `oklch(0.55 0.165 38)` | Burnt sienna |
| `--brand-deep` | `oklch(0.38 0.12 32)` | Roasted terracotta |

### Luxury Dark (toggle)
| Token | Value | Mô tả |
|---|---|---|
| `--background` | `oklch(0.12 0.008 60)` | Obsidian black |
| `--foreground` | `oklch(0.95 0.014 80)` | Champagne white |
| `--brand` | `oklch(0.78 0.13 80)` | Champagne gold |
| `--brand-deep` | `oklch(0.62 0.10 65)` | Antique bronze |

## 📚 Tài liệu thêm

- Repo gốc: https://github.com/Lendo-Stylix/fashion_match
- Architecture v3.1: `Kien_truc_v3.1.md`
- Backend API docs: http://localhost:8000/docs (khi backend chạy)

## 👥 Team OutfitMatch

| Vai trò | Owner |
|---|---|
| Dev A — Data/KB (Tầng 1) | Nhật Quang |
| Dev B — Model/Stylist (Tầng 2) | Đình Lộc |
| Dev C — Retrieval/Quiz/UI/API (Tầng 3-4) | Hữu Hoàng |

© 2026 OutfitMatch · Built with Next.js 16 + Qwen3-VL
