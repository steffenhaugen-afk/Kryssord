import { NextRequest, NextResponse } from "next/server";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const KEY = process.env.ADMIN_API_KEY ?? "";

function adminHeaders() {
  return { "X-Admin-Key": KEY, "Content-Type": "application/json" };
}

export async function GET() {
  const res = await fetch(`${API}/api/admin/kryssord`, {
    headers: adminHeaders(),
    cache: "no-store",
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const res = await fetch(`${API}/api/admin/kryssord/generer`, {
    method: "POST",
    headers: adminHeaders(),
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
