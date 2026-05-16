import { ShellLayout } from "@/components/ShellLayout";
import { SimilarCompoundsTable } from "@/components/SimilarCompoundsTable";
import { ExperimentTable } from "@/components/ExperimentTable";

export default async function MoleculePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <ShellLayout>
      <main className="flex-1 ml-0 mt-0 p-gutter overflow-y-auto bg-slate-50">
        <div className="mb-6 flex justify-between items-end">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="font-label-caps text-label-caps text-tertiary bg-tertiary-fixed px-2 py-0.5 rounded-sm uppercase tracking-widest">
                Validated
              </span>
              <span className="font-data-mono text-data-mono text-slate-500">{id}</span>
            </div>
            <h1 className="font-display-lg text-display-lg text-slate-900">
              Aspirin (Acetylsalicylic acid)
            </h1>
          </div>
          <div className="flex gap-2">
            <button className="px-4 py-2 border border-slate-200 bg-white text-slate-700 font-data-mono text-data-mono rounded hover:bg-slate-50 transition-colors flex items-center gap-2">
              <span className="material-symbols-outlined text-[18px]">download</span>
              Export SDF
            </button>
            <button className="px-4 py-2 bg-primary text-on-primary font-data-mono text-data-mono rounded hover:bg-slate-800 transition-colors flex items-center gap-2">
              <span className="material-symbols-outlined text-[18px]">play_arrow</span>
              Run Simulation
            </button>
          </div>
        </div>

        <div className="grid grid-cols-12 gap-gutter">
          <div className="col-span-8 bg-black rounded border border-slate-800 flex flex-col overflow-hidden min-h-[400px]">
            <div className="px-4 py-2 bg-slate-900 border-b border-slate-800 flex justify-between items-center">
              <span className="font-label-caps text-label-caps text-slate-400 uppercase tracking-widest">
                Molecular Viewport - 3D
              </span>
              <div className="flex gap-2">
                <button className="w-6 h-6 flex items-center justify-center bg-slate-800 text-slate-400 rounded-sm hover:text-white">
                  <span className="material-symbols-outlined text-[16px]">zoom_in</span>
                </button>
                <button className="w-6 h-6 flex items-center justify-center bg-slate-800 text-slate-400 rounded-sm hover:text-white">
                  <span className="material-symbols-outlined text-[16px]">zoom_out</span>
                </button>
              </div>
            </div>
            <div className="flex-1 relative flex items-center justify-center bg-[#0a0a0a] bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-slate-800/20 via-black to-black">
              <img
                alt="3D Molecule"
                className="opacity-60 object-contain h-64 w-64 mix-blend-screen"
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuDf3Xdadb9uI70G4yUUWC-HEJKEAZg3D5WCws8Qp7DbOMPddUEKI_kdk0RaA22scttd9XeTa9nCZEfb4ItgmNHE7T5ey_aE1_5q0jMvPxJtRJwlFi-808JGOwZiL0IVGj-GtmEJpxVESnLgj_CanzCfZ_GMm2fYAOJd4kr2PlQmURNkyzom97TB3IxEiVMX4xJZPykdSSySqBdW2K8FqmwQoBZ_GDypr6Ehe-_GEogwQLjMe9tnVgklX9TYDIwxuG09MXhyKgm8ky0"
              />
              <div className="absolute bottom-4 left-4 font-data-mono text-data-mono text-slate-500 text-[11px]">
                SMILES: CC(=O)Oc1ccccc1C(=O)O
              </div>
            </div>
          </div>

          <div className="col-span-4 flex flex-col gap-gutter">
            <div className="bg-white border border-slate-200 rounded p-4 flex-1">
              <h3 className="font-label-caps text-label-caps text-slate-500 uppercase tracking-widest mb-4 border-b border-slate-100 pb-2">
                Physicochemical Properties
              </h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="font-label-caps text-label-caps text-slate-400 mb-1">
                    Molecular Weight
                  </p>
                  <p className="font-data-mono text-data-mono text-slate-900 text-lg">
                    180.16 g/mol
                  </p>
                </div>
                <div>
                  <p className="font-label-caps text-label-caps text-slate-400 mb-1">LogP</p>
                  <p className="font-data-mono text-data-mono text-slate-900 text-lg">
                    1.19
                  </p>
                </div>
                <div>
                  <p className="font-label-caps text-label-caps text-slate-400 mb-1">
                    H-Bond Donors
                  </p>
                  <p className="font-data-mono text-data-mono text-slate-900 text-lg">
                    1
                  </p>
                </div>
                <div>
                  <p className="font-label-caps text-label-caps text-slate-400 mb-1">
                    H-Bond Acceptors
                  </p>
                  <p className="font-data-mono text-data-mono text-slate-900 text-lg">
                    4
                  </p>
                </div>
                <div>
                  <p className="font-label-caps text-label-caps text-slate-400 mb-1">TPSA</p>
                  <p className="font-data-mono text-data-mono text-slate-900 text-lg">
                    65.12 Å²
                  </p>
                </div>
                <div>
                  <p className="font-label-caps text-label-caps text-slate-400 mb-1">
                    Rotatable Bonds
                  </p>
                  <p className="font-data-mono text-data-mono text-slate-900 text-lg">
                    3
                  </p>
                </div>
              </div>
            </div>
            <div className="bg-white border border-slate-200 rounded p-4 flex-1">
              <h3 className="font-label-caps text-label-caps text-slate-500 uppercase tracking-widest mb-4 border-b border-slate-100 pb-2">
                Lipinski&apos;s Rule of 5
              </h3>
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="font-data-mono text-data-mono text-slate-600">MW &lt; 500</span>
                  <span className="material-symbols-outlined text-[18px] text-tertiary-fixed-dim">
                    check_circle
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="font-data-mono text-data-mono text-slate-600">LogP &lt; 5</span>
                  <span className="material-symbols-outlined text-[18px] text-tertiary-fixed-dim">
                    check_circle
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="font-data-mono text-data-mono text-slate-600">HBD &lt; 5</span>
                  <span className="material-symbols-outlined text-[18px] text-tertiary-fixed-dim">
                    check_circle
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="font-data-mono text-data-mono text-slate-600">HBA &lt; 10</span>
                  <span className="material-symbols-outlined text-[18px] text-tertiary-fixed-dim">
                    check_circle
                  </span>
                </div>
              </div>
            </div>
          </div>

          <SimilarCompoundsTable />
        </div>

        <div className="mt-4">
          <ExperimentTable />
        </div>
      </main>
    </ShellLayout>
  );
}

