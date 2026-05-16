export function ReportViewer({ reportId }: { reportId: string }) {
  return (
    <main className="md:ml-0 pt-0 min-h-[calc(100vh-56px)] flex flex-col">
      <div className="flex-1 max-w-[1440px] w-full mx-auto p-margin md:p-8">
        <header className="mb-8 border-b border-outline-variant pb-6">
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-2 text-on-surface-variant font-label-caps text-label-caps uppercase">
                <span className="material-symbols-outlined text-[14px]">folder_open</span>
                <span>Project XR-892</span>
                <span className="mx-1 text-outline">/</span>
                <span>Synthesis Phase 4</span>
              </div>
              <h1 className="font-display-lg text-display-lg text-on-surface mb-2">
                Efficacy &amp; Yield Report: Nav1.7 Inhibitors
              </h1>
              <p className="font-body-md text-body-md text-on-surface-variant max-w-3xl">
                Comprehensive analysis of 12 parallel synthesis runs targeting high-affinity binding
                pockets in the Nav1.7 voltage-gated sodium channel. Focus on optimization of the
                macrocyclic core.
              </p>
            </div>
            <div className="flex flex-col items-start md:items-end gap-1 font-data-mono text-data-mono text-on-surface-variant">
              <div>
                <span className="text-outline mr-2">Generated:</span> 2023-10-27 14:32 UTC
              </div>
              <div>
                <span className="text-outline mr-2">Lead Investigator:</span> Dr. Aris Thorne
              </div>
              <div>
                <span className="text-outline mr-2">Status:</span>{" "}
                <span className="text-on-tertiary-container bg-tertiary-fixed px-1.5 py-0.5 rounded-sm">
                  Final Review
                </span>
              </div>
              <div>
                <span className="text-outline mr-2">Report:</span> {reportId}
              </div>
            </div>
          </div>
        </header>

        <section className="grid grid-cols-1 md:grid-cols-4 gap-gutter mb-margin">
          <div className="bg-surface-container-lowest border border-outline-variant rounded-lg p-gutter flex flex-col relative overflow-hidden">
            <div className="font-label-caps text-label-caps text-on-surface-variant uppercase mb-2">
              Total Yield Average
            </div>
            <div className="font-display-lg text-display-lg text-on-surface mt-auto">78.4%</div>
            <div className="font-data-mono text-data-mono text-on-tertiary-container flex items-center gap-1 mt-1">
              <span className="material-symbols-outlined text-[14px]">trending_up</span>
              +4.2% vs Phase 3
            </div>
          </div>

          <div className="bg-surface-container-lowest border border-outline-variant rounded-lg p-gutter flex flex-col">
            <div className="font-label-caps text-label-caps text-on-surface-variant uppercase mb-2">
              Purity Median
            </div>
            <div className="font-display-lg text-display-lg text-on-surface mt-auto">99.1%</div>
            <div className="font-data-mono text-data-mono text-outline flex items-center gap-1 mt-1">
              <span className="material-symbols-outlined text-[14px]">check_circle</span>
              HPLC-UV/Vis
            </div>
          </div>

          <div className="bg-surface-container-lowest border border-outline-variant rounded-lg p-gutter flex flex-col">
            <div className="font-label-caps text-label-caps text-on-surface-variant uppercase mb-2">
              Failed Runs
            </div>
            <div className="font-display-lg text-display-lg text-on-surface mt-auto">
              2{" "}
              <span className="text-on-surface-variant text-body-md font-body-md font-normal">
                / 12
              </span>
            </div>
            <div className="font-data-mono text-data-mono text-error flex items-center gap-1 mt-1">
              <span className="material-symbols-outlined text-[14px]">warning</span>
              See EXP-892-04, 09
            </div>
          </div>

          <div className="bg-surface-container-lowest border border-outline-variant rounded-lg p-gutter flex flex-col bg-surface-container-low">
            <div className="font-label-caps text-label-caps text-on-surface-variant uppercase mb-2">
              Target Affinity (IC50)
            </div>
            <div className="font-display-lg text-display-lg text-on-surface mt-auto">
              4.2{" "}
              <span className="text-on-surface-variant text-body-md font-body-md font-normal">
                nM
              </span>
            </div>
            <div className="font-data-mono text-data-mono text-on-tertiary-container flex items-center gap-1 mt-1">
              Best in class: XR-892-11
            </div>
          </div>
        </section>

        <section className="flex flex-col gap-margin">
          <h2 className="font-headline-md text-headline-md text-on-surface border-b border-outline-variant pb-2">
            Experiment Protocols &amp; Results
          </h2>

          <article className="bg-surface-container-lowest border border-outline-variant rounded-lg overflow-hidden flex flex-col">
            <div className="bg-surface-container px-gutter py-3 border-b border-outline-variant flex justify-between items-center">
              <div className="flex items-center gap-3">
                <h3 className="font-headline-md text-headline-md text-on-surface text-[16px]">
                  EXP-892-11
                </h3>
                <span className="bg-tertiary-container text-on-tertiary-container font-label-caps text-label-caps uppercase px-2 py-1 rounded-sm flex items-center gap-1">
                  <span
                    className="material-symbols-outlined text-[12px]"
                    data-weight="fill"
                  >
                    check_circle
                  </span>
                  Validated
                </span>
              </div>
              <div className="font-data-mono text-data-mono text-on-surface-variant">
                Duration: 14h 30m
              </div>
            </div>

            <div className="p-gutter flex flex-col md:flex-row gap-gutter">
              <div className="md:w-1/3 flex flex-col gap-4">
                <div>
                  <h4 className="font-label-caps text-label-caps text-on-surface-variant uppercase mb-1">
                    Primary Findings
                  </h4>
                  <p className="font-body-md text-body-md text-on-surface leading-relaxed">
                    Substitution of the fluorine atom at the C4 position with a trifluoromethyl
                    group significantly improved metabolic stability without compromising target
                    binding affinity.
                  </p>
                </div>
                <div className="bg-surface-dim p-3 rounded border border-outline-variant">
                  <h4 className="font-label-caps text-label-caps text-on-surface-variant uppercase mb-1">
                    AI Recommendation
                  </h4>
                  <p className="font-data-mono text-data-mono text-on-surface text-[12px] leading-tight">
                    Consider escalating scaling factor for next batch. Kinetic modeling suggests a
                    15% reduction in reaction time is possible at 45°C.
                  </p>
                </div>
              </div>

              <div className="md:w-2/3 overflow-x-auto border border-outline-variant rounded">
                <table className="w-full text-left border-collapse min-w-[500px]">
                  <thead className="bg-surface sticky top-0 border-b border-outline-variant">
                    <tr>
                      <th className="p-3 font-label-caps text-label-caps text-on-surface-variant uppercase">
                        Reagent / Condition
                      </th>
                      <th className="p-3 font-label-caps text-label-caps text-on-surface-variant uppercase text-right">
                        Volume/Mass
                      </th>
                      <th className="p-3 font-label-caps text-label-caps text-on-surface-variant uppercase text-right">
                        Yield (%)
                      </th>
                      <th className="p-3 font-label-caps text-label-caps text-on-surface-variant uppercase text-right">
                        Purity
                      </th>
                    </tr>
                  </thead>
                  <tbody className="font-data-mono text-data-mono text-on-surface divide-y divide-outline-variant">
                    <tr className="hover:bg-surface-container-low transition-colors">
                      <td className="p-3 flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-secondary" />
                        Compound A (Core)
                      </td>
                      <td className="p-3 text-right">150 mg</td>
                      <td className="p-3 text-right text-on-surface-variant">-</td>
                      <td className="p-3 text-right text-on-surface-variant">-</td>
                    </tr>
                    <tr className="bg-surface-container-lowest hover:bg-surface-container-low transition-colors">
                      <td className="p-3 flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-outline" />
                        Trifluoromethylator
                      </td>
                      <td className="p-3 text-right">2.5 eq</td>
                      <td className="p-3 text-right text-on-surface-variant">-</td>
                      <td className="p-3 text-right text-on-surface-variant">-</td>
                    </tr>
                    <tr className="bg-surface-bright hover:bg-surface-container-low transition-colors">
                      <td className="p-3 font-semibold">Final Product (XR-892-11)</td>
                      <td className="p-3 text-right text-on-surface-variant">185 mg</td>
                      <td className="p-3 text-right font-semibold text-on-tertiary-container">
                        84.2%
                      </td>
                      <td className="p-3 text-right font-semibold">99.8%</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </article>

          <article className="bg-surface-container-lowest border border-outline-variant rounded-lg overflow-hidden flex flex-col opacity-90">
            <div className="bg-surface-container px-gutter py-3 border-b border-outline-variant flex justify-between items-center">
              <div className="flex items-center gap-3">
                <h3 className="font-headline-md text-headline-md text-on-surface text-[16px]">
                  EXP-892-09
                </h3>
                <span className="bg-error-container text-on-error-container font-label-caps text-label-caps uppercase px-2 py-1 rounded-sm flex items-center gap-1">
                  <span
                    className="material-symbols-outlined text-[12px]"
                    data-weight="fill"
                  >
                    cancel
                  </span>
                  Failed
                </span>
              </div>
              <div className="font-data-mono text-data-mono text-on-surface-variant">
                Aborted at 4h 15m
              </div>
            </div>

            <div className="p-gutter flex flex-col md:flex-row gap-gutter">
              <div className="md:w-1/3 flex flex-col gap-4">
                <div>
                  <h4 className="font-label-caps text-label-caps text-on-surface-variant uppercase mb-1">
                    Failure Analysis
                  </h4>
                  <p className="font-body-md text-body-md text-on-surface leading-relaxed">
                    Unexpected exotherm observed during the addition phase. Temperature spiked
                    beyond safety thresholds (T &gt; 85°C), leading to auto-abort by the synthesis rig.
                  </p>
                </div>
                <div>
                  <h4 className="font-label-caps text-label-caps text-on-surface-variant uppercase mb-1">
                    Root Cause
                  </h4>
                  <p className="font-body-md text-body-md text-on-surface-variant italic">
                    Suspected solvent incompatibility with the catalyst under high-pressure conditions.
                  </p>
                </div>
              </div>

              <div className="md:w-2/3 overflow-x-auto border border-outline-variant rounded">
                <table className="w-full text-left border-collapse min-w-[500px]">
                  <thead className="bg-surface sticky top-0 border-b border-outline-variant">
                    <tr>
                      <th className="p-3 font-label-caps text-label-caps text-on-surface-variant uppercase">
                        Parameter
                      </th>
                      <th className="p-3 font-label-caps text-label-caps text-on-surface-variant uppercase text-right">
                        Target
                      </th>
                      <th className="p-3 font-label-caps text-label-caps text-on-surface-variant uppercase text-right">
                        Actual (Peak)
                      </th>
                      <th className="p-3 font-label-caps text-label-caps text-on-surface-variant uppercase text-right">
                        Deviation
                      </th>
                    </tr>
                  </thead>
                  <tbody className="font-data-mono text-data-mono text-on-surface divide-y divide-outline-variant">
                    <tr className="hover:bg-surface-container-low transition-colors">
                      <td className="p-3">Internal Temp</td>
                      <td className="p-3 text-right">45°C</td>
                      <td className="p-3 text-right text-error font-semibold">88.3°C</td>
                      <td className="p-3 text-right text-error">+43.3°C</td>
                    </tr>
                    <tr className="bg-surface-container-lowest hover:bg-surface-container-low transition-colors">
                      <td className="p-3">Reactor Pressure</td>
                      <td className="p-3 text-right">1.2 atm</td>
                      <td className="p-3 text-right text-error font-semibold">3.8 atm</td>
                      <td className="p-3 text-right text-error">+2.6 atm</td>
                    </tr>
                    <tr className="bg-surface-bright hover:bg-surface-container-low transition-colors">
                      <td className="p-3">Stir Rate</td>
                      <td className="p-3 text-right">400 rpm</td>
                      <td className="p-3 text-right">400 rpm</td>
                      <td className="p-3 text-right text-on-surface-variant">0 rpm</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </article>
        </section>
      </div>
    </main>
  );
}

