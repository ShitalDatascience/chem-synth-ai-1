export type MoleculeIdentity = {
  chembl_id: string;
  pref_name?: string | null;
  canonical_smiles?: string | null;
  standard_inchi?: string | null;
  standard_inchi_key?: string | null;
  mw_freebase?: number | null;
  alogp?: number | null;
  psa?: number | null;
  hba?: number | null;
  hbd?: number | null;
  rtb?: number | null;
  full_molformula?: string | null;
};

function fmtNumber(n: number | null | undefined, digits = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

export function MoleculeCards({ molecule }: { molecule: MoleculeIdentity }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="col-span-1 border border-outline-variant bg-surface-container-lowest rounded-DEFAULT overflow-hidden">
        <div className="bg-surface-container-low px-3 py-2 border-b border-outline-variant">
          <h4 className="font-label-caps text-label-caps text-on-surface uppercase">
            Physicochemical Properties
          </h4>
        </div>
        <div className="p-4 space-y-3">
          <div className="flex justify-between border-b border-outline-variant/30 pb-1">
            <span className="font-body-md text-sm text-on-surface-variant">
              Molecular Weight
            </span>
            <span className="font-data-mono text-data-mono">
              {molecule.mw_freebase ? `${fmtNumber(molecule.mw_freebase)} g/mol` : "—"}
            </span>
          </div>
          <div className="flex justify-between border-b border-outline-variant/30 pb-1">
            <span className="font-body-md text-sm text-on-surface-variant">
              Formula
            </span>
            <span className="font-data-mono text-data-mono">
              {molecule.full_molformula ?? "—"}
            </span>
          </div>
          <div className="flex justify-between border-b border-outline-variant/30 pb-1">
            <span className="font-body-md text-sm text-on-surface-variant">
              LogP
            </span>
            <span className="font-data-mono text-data-mono">
              {molecule.alogp === null || molecule.alogp === undefined
                ? "—"
                : fmtNumber(molecule.alogp, 2)}
            </span>
          </div>
          <div className="flex justify-between border-b border-outline-variant/30 pb-1">
            <span className="font-body-md text-sm text-on-surface-variant">
              HBD / HBA
            </span>
            <span className="font-data-mono text-data-mono">
              {(molecule.hbd ?? "—").toString()} / {(molecule.hba ?? "—").toString()}
            </span>
          </div>
          <div className="flex justify-between pb-1">
            <span className="font-body-md text-sm text-on-surface-variant">
              PSA
            </span>
            <span className="font-data-mono text-data-mono">
              {molecule.psa === null || molecule.psa === undefined
                ? "—"
                : `${fmtNumber(molecule.psa)} Å²`}
            </span>
          </div>
        </div>
      </div>

      <div className="col-span-1 lg:col-span-2 grid grid-cols-2 gap-4">
        <div className="border border-outline-variant bg-surface-container-lowest rounded-DEFAULT overflow-hidden flex flex-col">
          <div className="bg-surface-container-low px-3 py-2 border-b border-outline-variant flex justify-between items-center">
            <h4 className="font-label-caps text-label-caps text-on-surface uppercase">
              2D Structure
            </h4>
            <span className="font-data-mono text-data-mono text-on-surface-variant">
              PNG later
            </span>
          </div>
          <div className="flex-1 bg-white flex items-center justify-center p-4 min-h-[200px]">
            <div className="w-full h-full border border-dashed border-outline-variant/50 flex items-center justify-center text-on-surface-variant font-label-caps uppercase">
              [2D Render Viewport]
            </div>
          </div>
        </div>
        <div className="border border-outline-variant bg-tertiary rounded-DEFAULT overflow-hidden flex flex-col">
          <div className="bg-slate-800 px-3 py-2 border-b border-slate-700 flex justify-between items-center text-white">
            <h4 className="font-label-caps text-label-caps uppercase">
              3D Conformation
            </h4>
            <span className="font-data-mono text-data-mono text-slate-200">
              WebGL later
            </span>
          </div>
          <div className="flex-1 bg-black flex items-center justify-center p-4 min-h-[200px] relative">
            <div className="w-full h-full border border-dashed border-slate-800 flex items-center justify-center text-slate-500 font-label-caps uppercase">
              [3D WebGL Viewport]
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

