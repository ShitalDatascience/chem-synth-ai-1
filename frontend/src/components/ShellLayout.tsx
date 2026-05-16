import Link from "next/link";
import { ShellNav } from "@/components/ShellNav";

export function ShellLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-background text-on-background font-body-md h-screen flex overflow-hidden">

      {/* ── SideNavBar ────────────────────────────────────────────────────────── */}
      <nav className="bg-slate-50 text-slate-900 font-inter text-xs font-semibold tracking-widest fixed left-0 top-14 bottom-0 flex flex-col p-4 w-64 z-40 border-r border-slate-200 transition-all duration-150 ease-in-out hidden md:flex">

        <div className="mb-8">
          <h2 className="text-slate-900 font-black font-label-caps uppercase">Discovery Lab</h2>
          <p className="text-on-surface-variant text-[10px] uppercase tracking-wider mt-1">Instance Alpha-7</p>
        </div>

        <Link
          href="/chat"
          className="w-full bg-primary text-on-primary font-label-caps uppercase py-3 px-4 rounded-DEFAULT hover:bg-slate-800 transition-colors mb-6 flex items-center justify-center gap-2"
        >
          <span className="material-symbols-outlined text-[16px]" data-icon="add">add</span>
          New Analysis
        </Link>

        <div className="flex-1 overflow-y-auto">
          <ShellNav />

          <div className="mt-8">
            <h3 className="font-label-caps text-on-surface-variant uppercase mb-2 px-3">Recent Analyses</h3>
            <ul className="space-y-1">
              {["Imatinib Binding Affinity", "Aspirin Synthesis Route", "Compound X Toxicity"].map((label) => (
                <li key={label}>
                  <a className="text-slate-600 hover:text-slate-900 px-3 py-1.5 block text-xs truncate" href="#">
                    {label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="mt-auto pt-4 border-t border-slate-200">
          <ul className="space-y-1">
            {[
              { icon: "contact_support", label: "Support" },
              { icon: "menu_book",       label: "Documentation" },
            ].map(({ icon, label }) => (
              <li key={label}>
                <a className="text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-sm flex items-center gap-3 px-3 py-2 transition-colors" href="#">
                  <span className="material-symbols-outlined text-[18px]" data-icon={icon}>{icon}</span>
                  <span className="font-label-caps uppercase">{label}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      </nav>

      {/* ── Main column ───────────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col md:ml-64 relative">

        {/* TopAppBar */}
        <header className="bg-white/80 backdrop-blur-md text-slate-900 font-inter text-sm font-medium tracking-tight border-b border-slate-200 fixed top-0 w-full z-50 flex justify-between items-center h-14 px-4">

          <div className="flex items-center gap-4">
            <button className="md:hidden text-slate-500 hover:bg-slate-50 p-1 rounded transition-colors cursor-pointer active:opacity-80">
              <span className="material-symbols-outlined" data-icon="menu">menu</span>
            </button>
            <Link href="/" className="text-lg font-bold tracking-tighter text-slate-900 font-headline-md">
              ChemSynth AI
            </Link>
          </div>

          <div className="flex items-center gap-4">
            <div className="relative hidden sm:block">
              <input
                className="bg-surface-container-low border border-outline-variant text-on-surface text-sm rounded-DEFAULT focus:ring-primary focus:border-primary block w-64 pl-10 p-2 font-body-md outline-none"
                placeholder="Search..."
                type="text"
              />
              <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
                <span className="material-symbols-outlined text-outline text-[18px]" data-icon="search">search</span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button className="text-slate-500 hover:bg-slate-50 transition-colors p-2 rounded-full cursor-pointer active:opacity-80">
                <span className="material-symbols-outlined" data-icon="notifications">notifications</span>
              </button>
              <button className="text-slate-500 hover:bg-slate-50 transition-colors p-2 rounded-full cursor-pointer active:opacity-80">
                <span className="material-symbols-outlined" data-icon="help_outline">help_outline</span>
              </button>
              <button className="text-slate-500 hover:bg-slate-50 transition-colors p-2 rounded-full cursor-pointer active:opacity-80 hidden sm:block">
                <span className="material-symbols-outlined" data-icon="settings">settings</span>
              </button>
              <img
                alt="Researcher Profile"
                className="w-8 h-8 rounded-full border border-outline-variant ml-2"
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuD_VI7va0xPVvjAhQwfguM01XL09ywfCdluDKcuwzbJP5r95CEkTKrtttzXvHvTYdpFsBEthAj8_RHP1qbhPKRgovxZMfxn50C9R6jSLzXHwZDItqPMNRvtnwB9laqQMUIe3B0JlNXsuPvZupD5c593R6rXvK_RGHjGitpdcBInIL69ex5uIcyicPdPtlX2elggr9mzD0sIAMzV3X7OoZh9ckmTCMp-mmfTdj4uQhOam6LIaStLShLcc-ZAAZWkAUnRKxv7WaEn6B4"
              />
            </div>
          </div>
        </header>

        <main className="flex-1 mt-14 overflow-hidden flex flex-col">
          {children}
        </main>
      </div>
    </div>
  );
}
