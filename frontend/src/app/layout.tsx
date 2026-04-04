import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Kryssord Norge",
  description: "Norske kryssord",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="no">
      <body>{children}</body>
    </html>
  );
}
