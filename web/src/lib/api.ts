// ────────────────────────────────────────────────────────────
// OutfitMatch API client
// Targets the FastAPI backend at API_URL (default http://localhost:8000).
// Falls back to mock data so the redesigned UI is fully explorable
// even when the backend is unavailable (sandbox / demo / offline).
// ────────────────────────────────────────────────────────────

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ────────────────────────────────────────────────────────────
// Types — mirror FastAPI schemas (server/schemas.py)
// ────────────────────────────────────────────────────────────

export type QuizOption = {
  id: string;
  label_vi: string;
  description_vi?: string;
};

export type QuizQuestion = {
  key: string;
  label_vi: string;
  hint_vi?: string;
  type: "single_select" | "multi_select";
  options: QuizOption[];
};

export type QuizResponse = {
  questions: QuizQuestion[];
};

export type RecommendItem = {
  item_id: string;
  category: string;
  title_vi: string;
  price_vnd: number;
  store_name: string;
  product_url: string;
  image_path: string;
  // UI-friendly extras (mock only)
  color?: string;
  fabric?: string;
};

export type Outfit = {
  outfit_id: string;
  explanation_vi: string;
  price_total_vnd: number;
  score?: number;
  tags?: string[];
  items: RecommendItem[];
};

export type RecommendResponse = {
  outfits: Outfit[];
  meta?: {
    occasion?: string;
    total?: number;
    latency_ms?: number;
  };
};

export type ChatTurn = {
  role: "user" | "bot";
  text: string;
  outfits?: Outfit[];
  ts?: number;
};

// ────────────────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────────────────

const fmtVND = (n: number) =>
  new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 }).format(n);

export const vnd = (n: number) => `${fmtVND(n)} ₫`;

export const compactVND = (n: number) => {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}tr ₫`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k ₫`;
  return `${n} ₫`;
};

// ────────────────────────────────────────────────────────────
// Mock data — used when backend is unreachable
// ────────────────────────────────────────────────────────────

const MOCK_QUIZ: QuizResponse = {
  questions: [
    {
      key: "gender",
      label_vi: "Bạn muốn phong cách cho ai?",
      hint_vi: "Chọn giới tính để gợi ý form dáng phù hợp",
      type: "single_select",
      options: [
        { id: "female", label_vi: "Nữ", description_vi: "Form dáng nữ" },
        { id: "male", label_vi: "Nam", description_vi: "Form dáng nam" },
        { id: "unisex", label_vi: "Unisex", description_vi: "Phi giới tính" },
      ],
    },
    {
      key: "body_shape",
      label_vi: "Dáng người của bạn",
      hint_vi: "Giúp chọn quần áo tôn dáng",
      type: "single_select",
      options: [
        { id: "pear", label_vi: "Lê", description_vi: "Hông > vai" },
        { id: "apple", label_vi: "Táo", description_vi: "Vai > hông" },
        { id: "hourglass", label_vi: "Đồng hồ cát", description_vi: "Vai = hông" },
        { id: "rectangle", label_vi: "Chữ nhật", description_vi: "Thon đều" },
        { id: "inverted_triangle", label_vi: "Tam giác ngược", description_vi: "Vai rộng" },
      ],
    },
    {
      key: "height_cm",
      label_vi: "Chiều cao",
      hint_vi: "Sử dụng để chọn size gợi ý",
      type: "single_select",
      options: [
        { id: "under_160", label_vi: "< 160cm" },
        { id: "160_170", label_vi: "160 - 170cm" },
        { id: "170_180", label_vi: "170 - 180cm" },
        { id: "over_180", label_vi: "> 180cm" },
      ],
    },
    {
      key: "occasions",
      label_vi: "Dịp đi (chọn nhiều)",
      hint_vi: "Chọn các dịp bạn thường tham gia",
      type: "multi_select",
      options: [
        { id: "office", label_vi: "Công sở" },
        { id: "date", label_vi: "Hẹn hò" },
        { id: "daily", label_vi: "Đi chơi" },
        { id: "party", label_vi: "Tiệc tùng" },
        { id: "travel", label_vi: "Du lịch" },
        { id: "workout", label_vi: "Tập luyện" },
      ],
    },
    {
      key: "style_vibes",
      label_vi: "Phong cách yêu thích (chọn nhiều)",
      hint_vi: "Định hình cá tính thời trang của bạn",
      type: "multi_select",
      options: [
        { id: "minimal", label_vi: "Tối giản" },
        { id: "streetwear", label_vi: "Streetwear" },
        { id: "vintage", label_vi: "Vintage" },
        { id: "elegant", label_vi: "Thanh lịch" },
        { id: "casual", label_vi: "Casual" },
        { id: "y2k", label_vi: "Y2K" },
        { id: "old_money", label_vi: "Old Money" },
      ],
    },
  ],
};

const STORES = [
  "YODY",
  "Coolmate",
  "Routine",
  "Oven",
  "Levents",
  "Maris.",
  "IVY Moda",
  "Canifa",
  "Elise",
  "NEM",
];

const CATEGORIES = [
  { cat: "top", vi: "Áo thun", priceRange: [149000, 399000] },
  { cat: "shirt", vi: "Sơ mi", priceRange: [299000, 699000] },
  { cat: "pants", vi: "Quần dài", priceRange: [349000, 899000] },
  { cat: "skirt", vi: "Chân váy", priceRange: [299000, 799000] },
  { cat: "dress", vi: "Đầm", priceRange: [499000, 1290000] },
  { cat: "outerwear", vi: "Áo khoác", priceRange: [599000, 1990000] },
  { cat: "shoes", vi: "Giày", priceRange: [499000, 1890000] },
  { cat: "accessory", vi: "Phụ kiện", priceRange: [99000, 599000] },
];

const COLORS = [
  { name: "Beige", hex: "#D4C5A0" },
  { name: "Cream", hex: "#F4ECD8" },
  { name: "Black", hex: "#1A1A1A" },
  { name: "White", hex: "#FAFAFA" },
  { name: "Terracotta", hex: "#A0522D" },
  { name: "Sage", hex: "#9CAF88" },
  { name: "Navy", hex: "#1B2845" },
  { name: "Burgundy", hex: "#5C1A1B" },
  { name: "Camel", hex: "#C19A6B" },
  { name: "Charcoal", hex: "#36454F" },
];

const FABRICS = ["Cotton", "Linen", "Wool", "Silk", "Denim", "Polyester"];

const OUTFIT_TEMPLATES: Array<{
  name: string;
  explanation: string;
  tags: string[];
  categories: string[];
}> = [
  {
    name: "Office Minimal",
    explanation:
      "Set công sở tối giản với sơ mi linen và quần ống suông, tôn dáng và thanh lịch cho ngày làm việc dài.",
    tags: ["Office", "Minimal", "Thanh lịch"],
    categories: ["shirt", "pants", "shoes"],
  },
  {
    name: "Weekend Casual",
    explanation:
      "Đồ đi chơi cuối tuần nhẹ nhàng với áo thun cotton, quần jeans và sneakers thoải mái cả ngày.",
    tags: ["Casual", "Weekend", "Năng động"],
    categories: ["top", "pants", "shoes"],
  },
  {
    name: "Date Night Elegant",
    explanation:
      "Set hẹn hò gợi cảm với dress linen nhẹ nhàng, tôn vồng da và phụ kiện tinh tế.",
    tags: ["Date", "Elegant", "Quyến rũ"],
    categories: ["dress", "shoes", "accessory"],
  },
  {
    name: "Street Cool",
    explanation:
      "Streetwear hiện đại với áo thun oversized, quần cargo và giày thể thao cá tính.",
    tags: ["Street", "Cool", "Cá tính"],
    categories: ["top", "pants", "outerwear", "shoes"],
  },
  {
    name: "Old Money",
    explanation:
      "Phong cách old-money với sơ mi linen, quần chino và áo khoác mỏng — sang trọng không phô trương.",
    tags: ["Old Money", "Sang trọng", "Tinh tế"],
    categories: ["shirt", "pants", "outerwear", "shoes"],
  },
  {
    name: "Vintage Charm",
    explanation:
      "Vibe vintage với chân váy midi, áo blouse họa tiết và giày búp bê nữ tính.",
    tags: ["Vintage", "Nữ tính", "Mềm mại"],
    categories: ["shirt", "skirt", "shoes"],
  },
];

function rand<T>(arr: T[], seed: number): T {
  return arr[seed % arr.length];
}

function generateItem(idx: number, catKey: string) {
  const catDef = CATEGORIES.find((c) => c.cat === catKey) ?? CATEGORIES[0];
  const color = rand(COLORS, idx * 7 + 3);
  const fabric = rand(FABRICS, idx * 3 + 1);
  const store = rand(STORES, idx * 5 + 2);
  const price =
    catDef.priceRange[0] +
    ((idx * 137) % (catDef.priceRange[1] - catDef.priceRange[0]));
  return {
    item_id: `item_${idx.toString().padStart(4, "0")}`,
    category: catDef.cat,
    title_vi: `${catDef.vi} ${color.name} ${fabric}`,
    price_vnd: price,
    store_name: store,
    product_url: "#",
    image_path: "",
    color: color.name,
    fabric,
  };
}

function generateOutfits(answers: Record<string, any>): Outfit[] {
  const occasion = answers.occasions?.[0] || "daily";
  const seedBase = occasion.length + Object.keys(answers).length * 11;
  return OUTFIT_TEMPLATES.map((tpl, i) => {
    const items = tpl.categories.map((cat, j) =>
      generateItem(i * 10 + j + seedBase, cat)
    );
    const total = items.reduce((s, it) => s + it.price_vnd, 0);
    return {
      outfit_id: `OUTFIT-${(i + 1).toString().padStart(3, "0")}`,
      explanation_vi: tpl.explanation,
      price_total_vnd: total,
      score: 0.72 + ((i * 13) % 25) / 100,
      tags: tpl.tags,
      items,
    };
  });
}

// ────────────────────────────────────────────────────────────
// Public API
// ────────────────────────────────────────────────────────────

async function tryBackend<T>(
  url: string,
  init?: RequestInit
): Promise<T | null> {
  try {
    const ctrl = new AbortController();
    const timeout = setTimeout(() => ctrl.abort(), 2500);
    const res = await fetch(url, { ...init, signal: ctrl.signal });
    clearTimeout(timeout);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export async function fetchQuiz(): Promise<{
  data: QuizResponse;
  source: "backend" | "mock";
}> {
  const data = await tryBackend<QuizResponse>(`${API_URL}/api/quiz`);
  if (data?.questions?.length) return { data, source: "backend" };
  return { data: MOCK_QUIZ, source: "mock" };
}

export async function fetchRecommendations(
  answers: Record<string, any>,
  occasion?: string
): Promise<{
  data: RecommendResponse;
  source: "backend" | "mock";
}> {
  const data = await tryBackend<RecommendResponse>(`${API_URL}/api/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      occasion: occasion || answers.occasions?.[0] || "daily",
      quiz_answers: answers,
    }),
  });
  if (data?.outfits?.length) return { data, source: "backend" };
  // Fallback to mock
  await new Promise((r) => setTimeout(r, 900)); // simulate latency
  return {
    data: { outfits: generateOutfits(answers), meta: { occasion } },
    source: "mock",
  };
}

// ────────────────────────────────────────────────────────────
// Chat SSE — try backend, else simulate streaming
// ────────────────────────────────────────────────────────────

export type ChatSSEHandlers = {
  onToken: (t: string) => void;
  onOutfitCards?: (outfits: Outfit[]) => void;
  onError?: (msg: string) => void;
  onDone?: () => void;
};

export async function streamChat(
  message: string,
  handlers: ChatSSEHandlers
): Promise<void> {
  // Try real backend first
  try {
    const ctrl = new AbortController();
    const timeout = setTimeout(() => ctrl.abort(), 3000);
    const res = await fetch(`${API_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
      signal: ctrl.signal,
    });
    clearTimeout(timeout);
    if (res.ok && res.body) {
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split(/\r?\n\r?\n/);
        buffer = parts.pop() || "";
        for (const part of parts) {
          const lines = part.split("\n");
          let eventType = "";
          let data = "";
          for (const line of lines) {
            if (line.startsWith("event:")) eventType = line.slice(6).trim();
            else if (line.startsWith("data:")) data = line.slice(5).trim();
          }
          if (eventType === "token") handlers.onToken(data);
          else if (eventType === "outfit_cards") {
            try {
              const parsed = JSON.parse(data);
              const outfits = Array.isArray(parsed)
                ? parsed
                : parsed.outfits || [];
              handlers.onOutfitCards?.(outfits);
            } catch {
              /* ignore */
            }
          } else if (eventType === "error") handlers.onError?.(data);
          else if (eventType === "done") handlers.onDone?.();
        }
      }
      handlers.onDone?.();
      return;
    }
  } catch {
    /* fall through to mock */
  }

  // Mock streaming
  await new Promise((r) => setTimeout(r, 250));
  const reply = generateMockReply(message);
  // Stream token-by-token
  const tokens = reply.text.split(/(\s+)/);
  for (const t of tokens) {
    handlers.onToken(t);
    await new Promise((r) => setTimeout(r, 18 + Math.random() * 35));
  }
  if (reply.outfits.length) {
    await new Promise((r) => setTimeout(r, 200));
    handlers.onOutfitCards?.(reply.outfits);
  }
  handlers.onDone?.();
}

function generateMockReply(message: string): {
  text: string;
  outfits: Outfit[];
} {
  const lower = message.toLowerCase();
  if (
    lower.includes("đi làm") ||
    lower.includes("công sở") ||
    lower.includes("office")
  ) {
    return {
      text:
        "Cho dịp công sở, mình gợi ý set thanh lịch: sơ mi linen beige, quần chino camel và giày loafers đen. Form dáng tôn vóc, màu trung tính dễ phối, phù hợp cả ngày dài họp hành và đi cafe sau giờ làm.",
      outfits: generateOutfits({ occasions: ["office"] }).slice(0, 2),
    };
  }
  if (lower.includes("hẹn") || lower.includes("date") || lower.includes("tiệc")) {
    return {
      text:
        "Dịp hẹn hò nên tôn vẻ nữ tính — set đầm midi linen + giày búp bê + túi clutch nhỏ. Tone-on-tone cream/blush rất hợp mùa hè. Mình đính kèm 2 outfit dưới đây cho bạn chọn nè.",
      outfits: generateOutfits({ occasions: ["date"] }).slice(1, 3),
    };
  }
  return {
    text:
      "Mình là OutfitMatch Stylist — AI được tinh chỉnh trên Qwen3-VL-8B để gợi ý trang phục theo dáng người, dịp đi và phong cách của bạn. Hãy thử hỏi: \"Mặc gì đi làm?\", \"Outfit đi date hôm nay?\" hoặc \"Phối đồ old money cho nam 175cm.\"",
    outfits: [],
  };
}
