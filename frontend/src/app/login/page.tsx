import Link from "next/link";

/* ─── Provider icons ────────────────────────────────────────────────────────── */
function GoogleIcon() {
  return (
    <svg aria-hidden="true" className="h-[18px] w-[18px] shrink-0" viewBox="0 0 48 48" fill="none">
      <path d="M44.5 24.5c0-1.5-.1-2.6-.3-3.8H24v7.2h11.8c-.2 1.8-1.5 4.6-4.4 6.4l-.1.5 6.4 5 .4.1c3.9-3.6 6-8.9 6-15.4Z" fill="#4285F4" />
      <path d="M24 45c5.8 0 10.7-1.9 14.3-5.1l-6.8-5.3c-1.8 1.2-4.2 2.1-7.5 2.1-5.7 0-10.6-3.7-12.4-8.9l-.5.1-6.9 5.4-.2.5C7.6 40.7 15.3 45 24 45Z" fill="#34A853" />
      <path d="M11.6 27.8A12.7 12.7 0 0 1 11 24c0-1.3.2-2.6.6-3.8l-.1-.5-7 5.5-.2.5A21 21 0 0 0 3 24c0 3.4.8 6.6 2.2 9.5l6.4-5.7Z" fill="#FBBC05" />
      <path d="M24 11.4c4 0 6.6 1.7 8.1 3.2l5.9-5.7C34.7 5.8 29.8 3 24 3 15.3 3 7.6 7.3 4 14.3l7.6 5.9C13.4 15.1 18.3 11.4 24 11.4Z" fill="#EA4335" />
    </svg>
  );
}

function LinkedInIcon() {
  return (
    <svg aria-hidden="true" className="h-[18px] w-[18px] shrink-0" viewBox="0 0 24 24">
      <rect width="24" height="24" rx="3" fill="#0A66C2" />
      <path d="M7.2 9.8H4.4v8.7h2.8V9.8ZM5.8 8.5a1.6 1.6 0 1 0 0-3.2 1.6 1.6 0 0 0 0 3.2ZM19.6 13c0-2.3-1.2-3.6-3-3.6-1.3 0-2 .7-2.3 1.2V9.8h-2.7v8.7h2.7v-4.7c0-1.1.5-1.8 1.5-1.8.9 0 1.3.6 1.3 1.8v4.7h2.8V13Z" fill="#fff" />
    </svg>
  );
}

function MicrosoftIcon() {
  return (
    <svg aria-hidden="true" className="h-[18px] w-[18px] shrink-0" viewBox="0 0 24 24">
      <path d="M2 2h9v9H2V2Z" fill="#F25022" />
      <path d="M13 2h9v9h-9V2Z" fill="#7FBA00" />
      <path d="M2 13h9v9H2v-9Z" fill="#00A4EF" />
      <path d="M13 13h9v9h-9v-9Z" fill="#FFB900" />
    </svg>
  );
}

function SsoButton({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <button
      type="button"
      className="w-full bg-white rounded-[4px] py-[10px] px-4 grid grid-cols-[22px_1fr_22px] items-center hover:bg-[#f7f9ff] active:bg-[#eef1f8] transition-colors"
      style={{ border: "1px solid #d0d2d9" }}
    >
      <span className="flex items-center">{icon}</span>
      <span className="text-[13px] font-normal text-[#0b1c30] text-center">
        {label}
      </span>
      <span aria-hidden="true" />
    </button>
  );
}

/* ─── Page ──────────────────────────────────────────────────────────────────── */
export default function LoginPage() {
  return (
    <div className="min-h-screen flex flex-col relative antialiased" style={{ backgroundColor: "#eef1f8" }}>
      <div className="absolute inset-0 grid-pattern pointer-events-none z-0" />

      <main className="flex-1 flex items-center justify-center relative z-10 px-4 py-8">
        <div
          className="w-full flex flex-col"
          style={{
            maxWidth: "360px",
            background: "#ffffff",
            border: "1px solid #d8dce8",
            borderRadius: "8px",
            padding: "40px 36px 36px",
            boxShadow: "0 8px 32px rgba(11,28,48,0.10)",
          }}
        >
          {/* Logo + heading */}
          <div className="flex flex-col items-center mb-8">
            <span
              className="material-symbols-outlined select-none mb-3"
              style={{
                fontSize: "38px",
                lineHeight: 1,
                color: "#0f1117",
                fontVariationSettings: "'FILL' 1, 'wght' 500, 'GRAD' 0, 'opsz' 40",
              }}
            >
              science
            </span>
            <h1
              className="text-center font-bold tracking-[-0.02em]"
              style={{ fontSize: "28px", lineHeight: "36px", color: "#0f1117" }}
            >
              ChemSynth AI
            </h1>
            <p className="text-center mt-1" style={{ fontSize: "13px", color: "#5f6168" }}>
              Enterprise Discovery Platform
            </p>
          </div>

          {/* Form */}
          <form className="flex flex-col" style={{ gap: "18px" }}>
            {/* Email */}
            <div className="flex flex-col" style={{ gap: "5px" }}>
              <label
                htmlFor="email"
                className="uppercase font-semibold"
                style={{ fontSize: "10.5px", letterSpacing: "0.08em", color: "#5f6168" }}
              >
                Institutional Email
              </label>
              <input
                id="email"
                type="email"
                placeholder="user@institution.edu"
                className="w-full rounded-[4px] px-3 py-[7px] text-[13px] outline-none"
                style={{ background: "#fff", border: "1px solid #d0d2d9", color: "#0b1c30" }}
              />
            </div>

            {/* Password */}
            <div className="flex flex-col" style={{ gap: "5px" }}>
              <div className="flex justify-between items-center">
                <label
                  htmlFor="password"
                  className="uppercase font-semibold"
                  style={{ fontSize: "10.5px", letterSpacing: "0.08em", color: "#5f6168" }}
                >
                  Password
                </label>
                <a href="#" className="hover:underline" style={{ fontSize: "13px", color: "#1565c0" }}>
                  Forgot Password?
                </a>
              </div>
              <input
                id="password"
                type="password"
                placeholder="••••••••"
                className="w-full rounded-[4px] px-3 py-[7px] text-[13px] outline-none"
                style={{ background: "#fff", border: "1px solid #d0d2d9", color: "#0b1c30" }}
              />
            </div>

            {/* CTA button */}
            <Link
              href="/chat"
              className="w-full mt-1 rounded-[4px] flex items-center justify-center gap-2 uppercase font-semibold tracking-[0.1em] transition-opacity hover:opacity-90 active:opacity-80"
              style={{
                backgroundColor: "#1a2038",
                color: "#ffffff",
                fontSize: "11px",
                padding: "13px 16px",
              }}
            >
              Sign In to Workspace
              <span className="material-symbols-outlined" style={{ fontSize: "16px", lineHeight: 1 }}>
                arrow_forward
              </span>
            </Link>
          </form>

          {/* Corporate SSO divider */}
          <div className="flex items-center gap-3 my-6">
            <hr className="flex-1" style={{ borderColor: "#d0d2d9" }} />
            <span
              className="uppercase font-semibold shrink-0"
              style={{ fontSize: "10.5px", letterSpacing: "0.08em", color: "#5f6168" }}
            >
              Corporate SSO
            </span>
            <hr className="flex-1" style={{ borderColor: "#d0d2d9" }} />
          </div>

          {/* SSO buttons */}
          <div className="flex flex-col" style={{ gap: "10px" }}>
            <SsoButton icon={<GoogleIcon />} label="Continue with Google" />
            <SsoButton icon={<LinkedInIcon />} label="Continue with LinkedIn" />
            <SsoButton icon={<MicrosoftIcon />} label="Continue with Microsoft" />
          </div>

          {/* Request access */}
          <p className="mt-7 text-center" style={{ fontSize: "13px", color: "#5f6168" }}>
            Need an enterprise account?{" "}
            <a href="#" className="font-semibold hover:underline" style={{ color: "#1565c0" }}>
              Request Access
            </a>
          </p>
        </div>
      </main>

      {/* Footer */}
      <footer
        className="relative z-20 w-full flex flex-col md:flex-row justify-between items-center px-8 py-5 gap-3"
        style={{ fontSize: "9.5px", letterSpacing: "0.12em", color: "#6b7280" }}
      >
        <span className="uppercase">
          © 2024 BioDiscovery Systems. All rights reserved. Clinical Grade Precision.
        </span>
        <div className="flex gap-5 uppercase">
          <a href="#" className="underline hover:text-[#0b1c30] transition-colors">Privacy Policy</a>
          <a href="#" className="underline hover:text-[#0b1c30] transition-colors">Terms of Service</a>
          <a href="#" className="underline hover:text-[#0b1c30] transition-colors">Security Disclosure</a>
        </div>
      </footer>
    </div>
  );
}
