"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavItem = {
  href: string;
  icon: string;
  label: string;
  activePrefix: string;
};

const NAV: NavItem[] = [
  { href: "/chat",        icon: "smart_toy",  label: "Intelligence",     activePrefix: "/chat" },
  { href: "/dashboard",   icon: "analytics",  label: "Dashboard",        activePrefix: "/dashboard" },
  { href: "/experiments", icon: "science",    label: "Experiments",      activePrefix: "/experiments" },
  { href: "/molecule/CHEMBL25", icon: "science", label: "Molecular Library", activePrefix: "/molecule" },
  { href: "/settings",    icon: "settings",   label: "Settings",         activePrefix: "/settings" },
];

export function ShellNav() {
  const pathname = usePathname();

  return (
    <ul className="space-y-1">
      {NAV.map((item) => {
        const isActive = pathname === item.href || pathname.startsWith(item.activePrefix + "/");

        return (
          <li key={item.href}>
            <Link
              href={item.href}
              className={[
                "rounded-sm flex items-center gap-3 px-3 py-2 transition-colors",
                isActive
                  ? "bg-slate-200 text-slate-900"
                  : "text-slate-600 hover:text-slate-900 hover:bg-slate-100",
              ].join(" ")}
            >
              <span className="material-symbols-outlined text-[18px]" data-icon={item.icon}>
                {item.icon}
              </span>
              <span style={{ fontSize: 11, letterSpacing: "0.05em", fontWeight: 700 }} className="uppercase">
                {item.label}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
