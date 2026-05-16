import type {
  NeedsConfirmationResponse,
  NoEvidenceResponse,
  ValidationErrorResponse,
} from "@/types/chat";

function SuggestionChip({
  chembl_id,
  pref_name,
  similarity_score,
  onSelect,
}: {
  chembl_id: string;
  pref_name?: string | null;
  similarity_score: number;
  onSelect?: (name: string) => void;
}) {
  const label = pref_name ?? chembl_id;
  const pct = Math.round(similarity_score * 100);

  return (
    <button
      type="button"
      onClick={() => onSelect?.(pref_name ?? chembl_id)}
      className="inline-flex items-center gap-2 rounded-DEFAULT border border-secondary/40 bg-secondary-fixed/20 px-3 py-1.5 text-left hover:bg-secondary-fixed/40 transition-colors"
    >
      <span className="font-body-md text-body-md text-on-surface font-medium">{label}</span>
      <span className="font-data-mono text-[10px] text-on-surface-variant">{chembl_id}</span>
      <span className="ml-auto font-data-mono text-[10px] text-secondary">{pct}% match</span>
    </button>
  );
}

export function ValidationWarning({
  response,
  onSuggest,
}: {
  response: ValidationErrorResponse | NoEvidenceResponse | NeedsConfirmationResponse;
  onSuggest?: (query: string) => void;
}) {
  if (response.response_type === "needs_confirmation") {
    return (
      <div className="rounded-lg border border-secondary/40 bg-secondary-fixed/10 p-4 max-w-2xl w-full space-y-3">
        <div className="flex items-start gap-3">
          <span className="material-symbols-outlined text-[20px] text-secondary shrink-0 mt-0.5">
            help
          </span>
          <div className="space-y-1">
            <p className="font-label-caps text-label-caps text-secondary uppercase tracking-widest text-[10px]">
              Needs confirmation
            </p>
            <p className="font-body-md text-body-md text-on-surface">{response.message}</p>
          </div>
        </div>
        {response.suggestions && response.suggestions.length > 0 ? (
          <div className="space-y-2 pl-8 flex flex-col gap-2">
            {response.suggestions.map((s, i) => (
              <SuggestionChip
                key={`${s.chembl_id || s.pref_name || "suggestion"}-${i}`}
                chembl_id={s.chembl_id}
                pref_name={s.pref_name}
                similarity_score={s.similarity_score}
                onSelect={onSuggest}
              />
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  if (response.response_type === "no_evidence") {
    return (
      <div className="rounded-lg border border-outline-variant bg-surface-container-low p-4 max-w-2xl w-full">
        <div className="flex items-start gap-3">
          <span className="material-symbols-outlined text-[20px] text-on-surface-variant shrink-0 mt-0.5">
            info
          </span>
          <div className="space-y-1">
            <p className="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-widest text-[10px]">
              No evidence found
            </p>
            <p className="font-body-md text-body-md text-on-surface">{response.message}</p>
            {response.chembl_id ? (
              <p className="font-data-mono text-[11px] text-on-surface-variant">
                ChEMBL ID: {response.chembl_id}
              </p>
            ) : null}
          </div>
        </div>
      </div>
    );
  }

  const { error_code, error_message, suggestions } = response;

  const icon = error_code === "invalid_smiles" ? "biotech" : "warning";
  const heading =
    error_code === "invalid_smiles"
      ? "Invalid SMILES"
      : "Molecule not recognised";

  return (
    <div className="rounded-lg border border-error/30 bg-error-container/20 p-4 max-w-2xl w-full space-y-3">
      <div className="flex items-start gap-3">
        <span className="material-symbols-outlined text-[20px] text-error shrink-0 mt-0.5">
          {icon}
        </span>
        <div className="space-y-1">
          <p className="font-label-caps text-label-caps text-error uppercase tracking-widest text-[10px]">
            {heading}
          </p>
          <p className="font-body-md text-body-md text-on-surface">{error_message}</p>
        </div>
      </div>

      {suggestions && suggestions.length > 0 ? (
        <div className="space-y-2 pl-8">
          <p className="font-label-caps text-[10px] text-on-surface-variant uppercase tracking-widest">
            Did you mean…
          </p>
          <div className="flex flex-col gap-2">
            {suggestions.map((s, i) => (
              <SuggestionChip
                key={`${s.chembl_id || s.pref_name || "suggestion"}-${i}`}
                chembl_id={s.chembl_id}
                pref_name={s.pref_name}
                similarity_score={s.similarity_score}
                onSelect={onSuggest}
              />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
