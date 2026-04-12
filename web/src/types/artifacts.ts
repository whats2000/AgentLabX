export interface LitReviewResult {
  papers: Array<{
    title: string;
    authors?: string;
    year?: number;
    summary?: string;
    url?: string;
    [k: string]: unknown;
  }>;
  summary: string;
}

export interface ResearchPlan {
  goals: string[];
  methodology: string;
  hypotheses: string[];
  full_text: string;
}

export interface EDAResult {
  findings: string[];
  data_quality_issues: string[];
  recommendations: string[];
}

export interface ExperimentResult {
  tag: string; // "baseline" | "main" | "ablation"
  metrics: Record<string, number>;
  description: string;
  code_path?: string | null;
  hypothesis_id?: string | null;
  reproducibility?: {
    random_seed?: number;
    environment_hash?: string;
    run_command?: string;
    container_image?: string | null;
    git_ref?: string | null;
    dependencies_snapshot?: Record<string, string>;
    timestamp?: string;
  };
}

export interface ReportResult {
  latex_source: string;
  sections: Record<string, string>;
  compiled_pdf_path?: string | null;
}

export interface ReviewResult {
  decision: "accept" | "revise" | "reject";
  scores: Record<string, number>;
  feedback: string;
  reviewer_id: string;
}

export interface Hypothesis {
  id: string;
  statement: string;
  status: "active" | "supported" | "refuted" | "abandoned";
  evidence_for?: Array<{
    experiment_result_index: number;
    metric: string;
    value: number;
    interpretation: string;
  }>;
  evidence_against?: Array<{
    experiment_result_index: number;
    metric: string;
    value: number;
    interpretation: string;
  }>;
  parent_hypothesis?: string | null;
  created_at_stage: string;
  resolved_at_stage?: string | null;
}

export interface ArtifactsPayload {
  literature_review: LitReviewResult[];
  plan: ResearchPlan[];
  data_exploration: EDAResult[];
  dataset_code: string[];
  experiment_results: ExperimentResult[];
  interpretation: string[];
  report: ReportResult[];
  review: ReviewResult[];
}
