/** Mirrors the backend ChatResponse discriminated union. */

export type FinalReport = {
  query: string;
  molecule: Record<string, unknown>;
  similar_compounds: Record<string, unknown>[];
  evidence_summary: Record<string, unknown>;
  experiment_list: Record<string, unknown>[];
  predictions: Record<string, unknown>[];
  report_sections: Record<string, string>;
  metadata?: { model_version?: string; pipeline?: string };
};

export type ValidationSuggestion = {
  chembl_id: string;
  pref_name?: string | null;
  canonical_smiles?: string | null;
  similarity_score: number;
};

export type ValidationErrorResponse = {
  response_type: "validation_error";
  query: string;
  error_code: string;
  error_message: string;
  suggestions: ValidationSuggestion[];
};

export type NoEvidenceResponse = {
  response_type: "no_evidence";
  query: string;
  chembl_id?: string | null;
  message: string;
};

export type NeedsConfirmationResponse = {
  response_type: "needs_confirmation";
  query: string;
  message: string;
  suggestions: ValidationSuggestion[];
};

export type ReportResponse = {
  response_type: "report";
  report: FinalReport;
};

export type TargetCompound = {
  chembl_id: string;
  molecule_name?: string | null;
  target_chembl_id?: string | null;
  target_pref_name?: string | null;
  organism?: string | null;
  standard_type?: string | null;
  standard_value?: number | null;
  standard_units?: string | null;
  pchembl_value?: number | null;
  assay_type?: string | null;
  confidence_score?: number | null;
};

export type ScaffoldCluster = {
  scaffold: string;
  size: number;
  examples: string[];
  median_pchembl?: number | null;
  median_alogp?: number | null;
};

export type PhyschemTrend = {
  descriptor: string;
  label: string;
  unit: string;
  n: number;
  mean: number;
  median: number;
  min: number;
  max: number;
};

export type TargetReportResponse = {
  response_type: "target_report";
  query: string;
  target_name: string;
  intent: string;
  filters: Record<string, unknown>;
  total: number;
  compounds: TargetCompound[];
  scaffold_clusters: ScaffoldCluster[];
  physchem_trends: PhyschemTrend[];
};

export type ToxicityExperimentalEvidence = {
  compound: string;
  chembl_id: string;
  IC50: string;
  source: string;
};

export type ToxicityPredictedEvidence = {
  compound: string;
  risk_score: string;
  model: string;
};

export type ToxicityRiskResponse = {
  response_type: "toxicity_risk_analysis";
  intent: "toxicity_risk_analysis";
  query: string;
  target: string;
  experimental_evidence: ToxicityExperimentalEvidence[];
  predicted_evidence: ToxicityPredictedEvidence[];
  risk_summary: "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN";
  note: string;
  filters: Record<string, unknown>;
};

export type ChatResponse =
  | ValidationErrorResponse
  | NoEvidenceResponse
  | NeedsConfirmationResponse
  | ReportResponse
  | TargetReportResponse
  | ToxicityRiskResponse;
