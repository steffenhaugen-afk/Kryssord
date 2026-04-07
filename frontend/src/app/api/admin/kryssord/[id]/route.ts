import { NextRequest, NextResponse } from "next/server";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const KEY = process.env.ADMIN_API_KEY ?? "";

function adminHeaders() {
  return { "X-Admin-Key": KEY, "Content-Type": "application/json" };
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const res = await fetch(`${API}/api/admin/kryssord/${id}`, {
    headers: adminHeaders(),
    cache: "no-store",
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const url = new URL(request.url);
  // Velg endepunkt basert på query-param ?action=status|ledetrad
  const action = url.searchParams.get("action") ?? "status";
  const body = await request.json();

  const res = await fetch(`${API}/api/admin/kryssord/${id}/${action}`, {
    method: "PATCH",
    headers: adminHeaders(),
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const res = await fetch(`${API}/api/admin/kryssord/${id}`, {
    method: "DELETE",
    headers: adminHeaders(),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
