import type { Metadata } from "next";
import { Playfair_Display } from "next/font/google";
import "./globals.css";

const playfair = Playfair_Display({
  subsets: ["latin"],
  variable: "--font-playfair",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Kryssord Norge",
  description: "Løs norske kryssord – nytt kryssord hver dag",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="no" className={playfair.variable}>
      <body className="bg-[#F5F0E8] text-gray-900 antialiased min-h-screen">
        {children}
      </body>
    </html>
  );
}
