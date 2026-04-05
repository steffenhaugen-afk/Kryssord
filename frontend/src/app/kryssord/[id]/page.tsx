import { hentKryssord } from "@/lib/api";
import KryssordSpill from "@/components/KryssordSpill";
import Link from "next/link";
import { notFound } from "next/navigation";

interface PageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: PageProps) {
  const { id } = await params;
  try {
    const k = await hentKryssord(id);
    return { title: `${k.tittel} – Kryssord Norge` };
  } catch {
    return { title: "Kryssord – Kryssord Norge" };
  }
}

export default async function KryssordSide({ params }: PageProps) {
  const { id } = await params;

  let kryssord;
  try {
    kryssord = await hentKryssord(id);
  } catch {
    notFound();
  }

  return (
    <main>
      <nav className="border-b border-gray-200 mb-2">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-2 text-sm text-gray-500">
          <Link href="/" className="hover:text-gray-800">
            Kryssord Norge
          </Link>
          <span>/</span>
          <Link href="/arkiv" className="hover:text-gray-800">
            Arkiv
          </Link>
          <span>/</span>
          <span className="text-gray-800 font-medium">{kryssord.tittel}</span>
        </div>
      </nav>
      <KryssordSpill kryssord={kryssord} />
    </main>
  );
}
