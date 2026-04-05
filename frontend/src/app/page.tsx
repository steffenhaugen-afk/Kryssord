import { hentDagligKryssord } from "@/lib/api";
import KryssordSpill from "@/components/KryssordSpill";
import Link from "next/link";

export const revalidate = 3600;

export default async function Forside() {
  let kryssord;
  try {
    kryssord = await hentDagligKryssord();
  } catch {
    return (
      <main className="max-w-4xl mx-auto px-4 py-16 text-center">
        <h1 className="text-3xl font-bold mb-4">Kryssord Norge</h1>
        <p className="text-gray-500">
          Ingen kryssord tilgjengelig akkurat nå.{" "}
          <Link href="/arkiv" className="underline text-blue-600">
            Se arkivet
          </Link>
          .
        </p>
      </main>
    );
  }

  return (
    <main>
      <nav className="border-b border-gray-200 mb-2">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link href="/" className="font-bold text-lg tracking-tight">
            Kryssord Norge
          </Link>
          <Link href="/arkiv" className="text-sm text-gray-600 hover:text-gray-900">
            Arkiv
          </Link>
        </div>
      </nav>
      <p className="text-center text-xs text-gray-400 mb-2">Dagens kryssord</p>
      <KryssordSpill kryssord={kryssord} />
    </main>
  );
}
