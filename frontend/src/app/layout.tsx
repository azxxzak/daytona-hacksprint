import type { Metadata, Viewport } from "next";
import { Noto_Sans_JP } from "next/font/google";
import { cookies } from "next/headers";
import { I18nProvider } from "@/components/i18n-provider";
import { LANG_COOKIE, isLang } from "@/lib/i18n";
import "./globals.css";

const noto = Noto_Sans_JP({
  variable: "--font-noto",
  weight: ["400", "500", "700"],
  display: "swap",
  preload: false,
});

export const metadata: Metadata = {
  title: { default: "AdLens", template: "%s · AdLens" },
  description: "See your ad through the eyes of an AI viewer panel.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const c = (await cookies()).get(LANG_COOKIE)?.value;
  const lang = isLang(c) ? c : "en";
  return (
    <html lang={lang} className={noto.variable}>
      <body>
        <I18nProvider initial={lang}>{children}</I18nProvider>
      </body>
    </html>
  );
}
