import { ShellLayout } from "@/components/ShellLayout";

export default function SettingsPage() {
  return (
    <ShellLayout>
      <div className="flex-1 flex flex-col items-center justify-center bg-[#f8f9ff]">
        <span
          className="material-symbols-outlined mb-4 select-none"
          style={{ fontSize: 48, color: "#c6c6cd" }}
        >
          settings
        </span>
        <p
          className="font-semibold uppercase tracking-[0.08em]"
          style={{ fontSize: 12, color: "#76777d" }}
        >
          Settings
        </p>
        <p style={{ fontSize: 13, color: "#9ea0a8", marginTop: 6 }}>
          Coming soon
        </p>
      </div>
    </ShellLayout>
  );
}
