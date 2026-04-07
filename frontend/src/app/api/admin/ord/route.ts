import { NextRequest, NextResponse } from "next/server";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const KEY = process.env.ADMIN_API_KEY ?? "";

function adminHeaders() {
  return { "X-Admin-Key": KEY, "Content-Type": "application/json" };
}

export async function GET(request: NextRequest) {
  const q = new URL(request.url).searchParams.get("q") ?? "";
  const res = await fetch(
    `${API}/api/admin/ord?q=${encodeURIComponent(q)}`,
    { headers: adminHeaders(), cache: "no-store" }
  );
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function POST(request: NextRequest) {
  const { tekst, ledetrad } = await request.json();
  const res = await fetch(
    `${API}/api/admin/ord/${encodeURIComponent(tekst)}/ledetrad`,
    {
      method: "POST",
      headers: adminHeaders(),
      body: JSON.stringify({ ledetrad }),
    }
  );
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
