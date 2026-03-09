import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 60000,
});

export interface EvaluationResult {
  run_id: string;
  tech_number: string;
  tech_name: string;
  tech_field: string;
  panel_size: number;
  panel_profiles: AgentProfile[];
  votes: AgentVote[];
  ensemble_result: EnsembleResult;
  chairman_review: any;
  elapsed_seconds: number;
}

export interface AgentProfile {
  agent_id: string;
  match_level: string;
  experience: string;
  experience_years: number;
  specialty: string;
}

export interface AgentVote {
  agent_id: string;
  vote: string;
  confidence: number;
  novelty: { differentiation: number; originality: number; total: number };
  progressiveness: {
    quality_improvement: number;
    development_degree: number;
    safety: number;
    eco_friendliness: number;
    total: number;
  };
  total: number;
  evidence: string[];
  evidence_details?: EvidenceDetail[];
  reasoning?: string;
  prior_art_comparison: string;
}

export interface EvidenceDetail {
  claim: string;
  source_type: string;
  source_ref: string;
  relevance: string;
}

export interface EnsembleResult {
  final_verdict: string;
  approval_ratio: number;
  weighted_approval_ratio: number;
  avg_novelty_total: number;
  avg_progressiveness_total: number;
  avg_total: number;
  dissenting_opinions: string[];
  consensus_evidence: string[];
}

export interface ProposalSummary {
  tech_number: string;
  tech_name: string;
  tech_field: string;
  category_code: string;
  designation_year: number | null;
  status: string;
}

export interface ExperimentConfig {
  groups: {
    accuracy: string[];
    consistency: string[];
    sensitivity: string[];
  };
  accuracy_cutoff_year: number;
  sensitivity_year_range: number[];
  total_proposals: number;
}

export interface SensitivityResult {
  n_pairs: number;
  tech_numbers: string[];
  verdict_comparison: {
    total_pairs: number;
    verdict_match: number;
    verdict_match_rate: number;
    cutoff_rejected_to_nocutoff_approved: number;
    cutoff_approved_to_nocutoff_rejected: number;
    interpretation: string;
  };
  score_comparison: {
    cutoff_mean_total: number;
    nocutoff_mean_total: number;
    mean_score_diff: number;
    std_score_diff: number;
    paired_t_stat: number;
    paired_p_value: number;
    significant_at_005: boolean;
    cutoff_mean_approval: number;
    nocutoff_mean_approval: number;
    per_tech_diffs: { tech_number: string; cutoff_total: number; nocutoff_total: number; diff: number }[];
  };
  per_field_sensitivity: Record<string, {
    mean_diff: number; std_diff: number; t_stat: number; p_value: number; sensitive: boolean;
  }>;
  kb_coverage_correlation: {
    n_data_points: number;
    pearson_r?: number;
    p_value?: number;
    significant_at_005?: boolean;
    interpretation: string;
  };
  summary: {
    verdict_stability: number;
    mean_score_impact: number;
    score_impact_significant: boolean;
    sensitive_fields: string[];
    kb_coverage_effect: string;
    recommendation: string;
  };
  error?: string;
}

// Results
export const fetchResults = () => api.get('/api/results');
export const fetchResult = (runId: string) => api.get(`/api/results/${runId}`);

// Proposals
export const fetchProposals = () => api.get('/api/proposals');
export const fetchProposal = (techNumber: string) => api.get(`/api/proposals/${techNumber}`);

// Analysis
export const fetchAccuracyAnalysis = () => api.get('/api/analysis/accuracy');
export const fetchConsistencyAnalysis = () => api.get('/api/analysis/consistency');
export const fetchScorePatternAnalysis = () => api.get('/api/analysis/score-patterns');
export const fetchExperienceCorrelation = () => api.get('/api/analysis/experience-correlation');
export const fetchSensitivityAnalysis = () => api.get('/api/analysis/sensitivity');

// Experiment
export const fetchExperimentConfig = () => api.get('/api/experiment/config');
export const startSensitivityRun = (techNumbers: string[], repetitions: number, seed?: number) =>
  api.post('/api/evaluate/sensitivity', { tech_numbers: techNumbers, repetitions, seed });

// Knowledge Base
export const fetchKBStatus = () => api.get('/api/kb/status');
export const fetchKBDetail = () => api.get('/api/kb/detail');
export const fetchKBMetadata = () => api.get('/api/kb/metadata');

// Pipeline
export const fetchPipelineWorkflow = () => api.get('/api/pipeline/workflow');

// Evaluation Status
export const fetchEvalStatus = (runId: string) => api.get(`/api/evaluate/status/${runId}`);
export const fetchAllEvalStatus = () => api.get('/api/evaluate/status');

// Evaluation Actions
export const startEvaluation = (techNumber: string, seed?: number, skipChairman?: boolean) =>
  api.post('/api/evaluate', { tech_number: techNumber, seed, skip_chairman: skipChairman });

export const startBatchEvaluation = (techNumbers: string[], repetitions: number, seed?: number) =>
  api.post('/api/evaluate/batch', { tech_numbers: techNumbers, repetitions, seed });

// Settings
export const fetchSettings = () => api.get('/api/settings');
export const updateSettings = (settings: Record<string, any>) =>
  api.put('/api/settings', settings);
export const testBedrockConnection = () => api.post('/api/settings/test-bedrock');

export default api;
