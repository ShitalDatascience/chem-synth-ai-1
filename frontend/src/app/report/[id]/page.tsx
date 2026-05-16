import { ShellLayout } from "@/components/ShellLayout";
import { ReportViewer } from "@/components/ReportViewer";

export default async function ReportPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <ShellLayout>
      <ReportViewer reportId={id} />
    </ShellLayout>
  );
}

