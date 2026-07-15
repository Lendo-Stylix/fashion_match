import type { Metadata } from "next";
import { Inter, Playfair_Display, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";
import { ThemeProvider } from "@/components/theme-provider";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin", "vietnamese"],
  display: "swap",
});

const playfair = Playfair_Display({
  variable: "--font-playfair",
  subsets: ["latin", "vietnamese"],
  display: "swap",
  weight: ["400", "500", "600", "700", "800", "900"],
  style: ["normal", "italic"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "OutfitMatch — AI Stylist cá nhân hóa phong cách",
  description:
    "OutfitMatch: gợi ý trang phục thông minh theo dáng người và dịp đi, tích hợp AI Stylist Qwen3-VL. Thời trang Việt Nam, cá nhân hóa cho từng người.",
  keywords: [
    "OutfitMatch",
    "AI Stylist",
    "thời trang",
    "gợi ý trang phục",
    "phong cách cá nhân",
    "Qwen3-VL",
    "Vietnam fashion",
  ],
  authors: [{ name: "OutfitMatch Team" }],
  openGraph: {
    title: "OutfitMatch — AI Stylist cá nhân hóa",
    description:
      "Gợi ý trang phục thông minh theo dáng người và dịp đi, tích hợp AI Stylist Qwen3-VL.",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "OutfitMatch — AI Stylist cá nhân hóa",
    description:
      "Gợi ý trang phục thông minh theo dáng người và dịp đi.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" suppressHydrationWarning>
      <body
        className={`${inter.variable} ${playfair.variable} ${jetbrainsMono.variable} antialiased bg-background text-foreground`}
      >
        <ThemeProvider>
          {children}
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
