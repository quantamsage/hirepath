"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken } from "@/lib/api";

export default function TopBar({ email }: { email: string }) {
  const router = useRouter();
  const path = usePathname();

  function logOut() {
    clearToken();
    router.replace("/login");
  }

  return (
    <header className="topbar">
      <div className="auth-brand">
        <span className="brand-mark" aria-hidden="true" />
        HirePath
      </div>
      <nav className="topbar-nav" aria-label="Main">
        <Link href="/board" aria-current={path === "/board" ? "page" : undefined}>Board</Link>
        <Link href="/stats" aria-current={path === "/stats" ? "page" : undefined}>Stats</Link>
      </nav>
      <div className="topbar-user">
        {email && <span className="topbar-email">{email}</span>}
        <button type="button" className="btn btn-quiet" onClick={logOut}>Log out</button>
      </div>
    </header>
  );
}
