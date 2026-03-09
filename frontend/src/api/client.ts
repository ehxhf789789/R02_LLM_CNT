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

export const fetchResults = () => api.get('/api/results');
export const fetchResult = (runId: string) => api.get(`/api/results/${runId}`);
export const fetchProposals = () => api.get('/api/proposals');
export const fetchProposal = (techNumber: string) => api.get(`/api/proposals/${techNumber}`);
export const fetchAccuracyAnalysis = () => api.get('/api/analysis/accuracy');
export const fetchConsistencyAnalysis = () => api.get('/api/analysis/consistency');
export const fetchScorePatternAnalysis = () => api.get('/api/analysis/score-patterns');
export const fetchExperienceCorrelation = () => api.get('/api/analysis/experience-correlation');
export const fetchKBStatus = () => api.get('/api/kb/status');
export const fetchKBDetail = () => api.get('/api/kb/detail');
export const fetchKBMetadata = () => api.get('/api/kb/metadata');
export const fetchPipelineWorkflow = () => api.get('/api/pipeline/workflow');
export const fetchEvalStatus = (runId: string) => api.get(`/api/evaluate/status/${runId}`);
export const fetchAllEvalStatus = () => api.get('/api/evaluate/status');

export const startEvaluation = (techNumber: string, seed?: number, skipChairman?: boolean) =>
  api.post('/api/evaluate', { tech_number: techNumber, seed, skip_chairman: skipChairman });

export const startBatchEvaluation = (techNumbers: string[], repetitions: number, seed?: number) =>
  api.post('/api/evaluate/batch', { tech_numbers: techNumbers, repetitions, seed });

export default api;
