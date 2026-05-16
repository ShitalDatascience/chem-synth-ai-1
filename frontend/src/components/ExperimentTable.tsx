export function ExperimentTable() {
  return (
    <div className="bg-white border border-slate-200 rounded overflow-hidden">
      <div className="bg-slate-50 border-b border-slate-200 px-4 py-3 flex justify-between items-center">
        <h3 className="font-label-caps text-label-caps text-slate-700 uppercase tracking-widest">
          Experiments & Evidence
        </h3>
        <span className="font-data-mono text-data-mono text-slate-500 text-[11px] self-center">
          Phase 2 retrieval
        </span>
      </div>
      <div className="w-full overflow-x-auto">
        <table className="w-full text-left border-collapse min-w-[700px]">
          <thead className="bg-slate-50 sticky top-0 border-b border-slate-200">
            <tr>
              <th className="p-3 font-label-caps text-label-caps text-slate-500 uppercase">
                Assay
              </th>
              <th className="p-3 font-label-caps text-label-caps text-slate-500 uppercase">
                Target
              </th>
              <th className="p-3 font-label-caps text-label-caps text-slate-500 uppercase text-right">
                Type
              </th>
              <th className="p-3 font-label-caps text-label-caps text-slate-500 uppercase text-right">
                Value
              </th>
              <th className="p-3 font-label-caps text-label-caps text-slate-500 uppercase text-right">
                Units
              </th>
            </tr>
          </thead>
          <tbody className="font-data-mono text-data-mono text-slate-700 divide-y divide-slate-200">
            {[
              { assay: "CHEMBL Assay 1", target: "COX-1", type: "IC50", value: "4.2", units: "nM" },
              { assay: "CHEMBL Assay 2", target: "COX-2", type: "Ki", value: "18.0", units: "nM" },
              { assay: "CHEMBL Assay 3", target: "PTGS1", type: "EC50", value: "—", units: "—" },
            ].map((r, i) => (
              <tr
                key={`${r.assay}-${i}`}
                className={i % 2 === 1 ? "bg-slate-50 hover:bg-slate-100 transition-colors" : "hover:bg-slate-50 transition-colors"}
              >
                <td className="p-3">{r.assay}</td>
                <td className="p-3">{r.target}</td>
                <td className="p-3 text-right">{r.type}</td>
                <td className="p-3 text-right">{r.value}</td>
                <td className="p-3 text-right">{r.units}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

