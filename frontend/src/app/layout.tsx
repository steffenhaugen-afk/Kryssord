import type { Metadata } from "next";
import "./globals.css";

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
    <html lang="no">
      <body className="bg-gray-50 text-gray-900 antialiased min-h-screen">
        {children}
      </body>
    </html>
  );
}
