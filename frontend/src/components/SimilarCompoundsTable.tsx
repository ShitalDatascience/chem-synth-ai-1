export function SimilarCompoundsTable() {
  return (
    <div className="col-span-12 bg-white border border-slate-200 rounded overflow-hidden mt-4">
      <div className="bg-slate-50 border-b border-slate-200 px-4 py-3 flex justify-between items-center">
        <h3 className="font-label-caps text-label-caps text-slate-700 uppercase tracking-widest">
          Similar Compounds (ChEMBL)
        </h3>
        <span className="font-data-mono text-data-mono text-slate-500 text-[11px] self-center">
          Showing top 3 matches
        </span>
      </div>
      <div className="w-full overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-white border-b border-slate-200 font-label-caps text-label-caps text-slate-500 uppercase">
              <th className="p-3 w-16 text-center">Structure</th>
              <th className="p-3">Compound ID</th>
              <th className="p-3">Similarity</th>
              <th className="p-3">MW</th>
              <th className="p-3">LogP</th>
              <th className="p-3">Bioactivity</th>
              <th className="p-3 w-12"></th>
            </tr>
          </thead>
          <tbody className="font-data-mono text-data-mono text-slate-700">
            <tr className="border-b border-slate-100 hover:bg-slate-50 transition-colors">
              <td className="p-3 w-16">
                <div className="w-12 h-12 bg-slate-50 border border-slate-200 rounded flex items-center justify-center">
                  <span className="material-symbols-outlined text-slate-400">category</span>
                </div>
              </td>
              <td className="p-3 font-medium text-slate-900">CHEMBL134</td>
              <td className="p-3">
                <div className="flex items-center gap-2">
                  <div className="w-16 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                    <div className="h-full bg-slate-800 w-[95%]" />
                  </div>
                  <span>0.95</span>
                </div>
              </td>
              <td className="p-3">138.12</td>
              <td className="p-3">1.02</td>
              <td className="p-3">
                <span className="bg-surface-container-high text-on-surface px-2 py-0.5 rounded-sm text-[11px]">
                  Active (COX-1)
                </span>
              </td>
              <td className="p-3 text-right">
                <button className="text-slate-400 hover:text-slate-900">
                  <span className="material-symbols-outlined text-[18px]">chevron_right</span>
                </button>
              </td>
            </tr>
            <tr className="bg-slate-50 border-b border-slate-100 hover:bg-slate-100 transition-colors">
              <td className="p-3 w-16">
                <div className="w-12 h-12 bg-white border border-slate-200 rounded flex items-center justify-center">
                  <span className="material-symbols-outlined text-slate-400">category</span>
                </div>
              </td>
              <td className="p-3 font-medium text-slate-900">CHEMBL423</td>
              <td className="p-3">
                <div className="flex items-center gap-2">
                  <div className="w-16 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                    <div className="h-full bg-slate-600 w-[82%]" />
                  </div>
                  <span>0.82</span>
                </div>
              </td>
              <td className="p-3">152.15</td>
              <td className="p-3">1.34</td>
              <td className="p-3">
                <span className="bg-surface-container-high text-on-surface px-2 py-0.5 rounded-sm text-[11px]">
                  Moderate
                </span>
              </td>
              <td className="p-3 text-right">
                <button className="text-slate-400 hover:text-slate-900">
                  <span className="material-symbols-outlined text-[18px]">chevron_right</span>
                </button>
              </td>
            </tr>
            <tr className="border-b border-slate-100 hover:bg-slate-50 transition-colors">
              <td className="p-3 w-16">
                <div className="w-12 h-12 bg-slate-50 border border-slate-200 rounded flex items-center justify-center">
                  <span className="material-symbols-outlined text-slate-400">category</span>
                </div>
              </td>
              <td className="p-3 font-medium text-slate-900">CHEMBL981</td>
              <td className="p-3">
                <div className="flex items-center gap-2">
                  <div className="w-16 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                    <div className="h-full bg-slate-400 w-[76%]" />
                  </div>
                  <span>0.76</span>
                </div>
              </td>
              <td className="p-3">194.19</td>
              <td className="p-3">1.88</td>
              <td className="p-3">
                <span className="bg-slate-100 text-slate-500 px-2 py-0.5 rounded-sm text-[11px]">
                  Inactive
                </span>
              </td>
              <td className="p-3 text-right">
                <button className="text-slate-400 hover:text-slate-900">
                  <span className="material-symbols-outlined text-[18px]">chevron_right</span>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

