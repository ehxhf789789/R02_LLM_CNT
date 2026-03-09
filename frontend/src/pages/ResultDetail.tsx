import React, { useEffect, useState } from 'react';
import { fetchResult, EvaluationResult, EvidenceDetail } from '../api/client';
import {
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ScatterChart, Scatter, ZAxis,
} from 'recharts';

interface Props {
  runId: string;
}

const SCORE_LABELS = ['차별성', '독창성', '품질향상', '개발정도', '안전성', '친환경성'];
const SCORE_MAX = [25, 25, 15, 15, 10, 10];
const SOURCE_COLORS: Record<string, string> = {
  patent: '#2196F3',
  paper: '#4CAF50',
  designated_tech: '#FF9800',
  codil: '#9C27B0',
  evaluation_criteria: '#F44336',
  proposal: '#00BCD4',
};
const SOURCE_LABELS: Record<string, string> = {
  patent: '특허',
  paper: '논문',
  designated_tech: '지정기술',
  codil: 'CODIL',
  evaluation_criteria: '평가기준',
  proposal: '제안기술',
};

const ResultDetail: React.FC<Props> = ({ runId }) => {
  const [result, setResult] = useState<EvaluationResult | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [showAllEvidence, setShowAllEvidence] = useState(false);

  useEffect(() => {
    fetchResult(runId)
      .then(res => setResult(res.data))
      .catch(console.error);
  }, [runId]);

  if (!result) return <div className="loading">로딩 중...</div>;

  const { ensemble_result: ensemble, votes, panel_profiles: panel } = result;

  // 레이더 차트 데이터
  const radarData = SCORE_LABELS.map((label, i) => {
    const entry: any = { subject: label, fullMark: SCORE_MAX[i] };
    const avgScores = votes.map(v => {
      const scores = [
        v.novelty.differentiation, v.novelty.originality,
        v.progressiveness.quality_improvement, v.progressiveness.development_degree,
        v.progressiveness.safety, v.progressiveness.eco_friendliness,
      ];
      return scores[i];
    });
    entry['평균'] = avgScores.reduce((a, b) => a + b, 0) / (avgScores.length || 1);
    if (selectedAgent) {
      const sv = votes.find(v => v.agent_id === selectedAgent);
      if (sv) {
        const scores = [
          sv.novelty.differentiation, sv.novelty.originality,
          sv.progressiveness.quality_improvement, sv.progressiveness.development_degree,
          sv.progressiveness.safety, sv.progressiveness.eco_friendliness,
        ];
        entry[selectedAgent] = scores[i];
      }
    }
    return entry;
  });

  // 바 차트 데이터
  const barData = votes.map(v => {
    const profile = panel.find(p => p.agent_id === v.agent_id);
    return {
      name: v.agent_id.replace('agent_', ''),
      novelty: v.novelty.total,
      progressiveness: v.progressiveness.total,
      verdict: v.vote,
      years: profile?.experience_years || 0,
      match: profile?.match_level || '',
    };
  });

  // 경력-점수 산점도
  const scatterApproved = votes.filter(v => v.vote === 'approved').map(v => {
    const profile = panel.find(p => p.agent_id === v.agent_id);
    return { years: profile?.experience_years || 0, score: v.total, confidence: v.confidence, agent: v.agent_id };
  });
  const scatterRejected = votes.filter(v => v.vote !== 'approved').map(v => {
    const profile = panel.find(p => p.agent_id === v.agent_id);
    return { years: profile?.experience_years || 0, score: v.total, confidence: v.confidence, agent: v.agent_id };
  });

  // 근거 소스 분석
  const allEvidenceDetails: EvidenceDetail[] = votes.flatMap(v => v.evidence_details || []);
  const sourceTypeCounts: Record<string, number> = {};
  allEvidenceDetails.forEach(e => {
    sourceTypeCounts[e.source_type] = (sourceTypeCounts[e.source_type] || 0) + 1;
  });

  const selectedVote = selectedAgent ? votes.find(v => v.agent_id === selectedAgent) : null;
  const selectedProfile = selectedAgent ? panel.find(p => p.agent_id === selectedAgent) : null;

  return (
    <div className="result-detail">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>{result.tech_name}</h1>
        <a href="#/" className="btn btn-secondary">목록</a>
      </div>
      <div className="meta-info">
        <span>기술번호: {result.tech_number}</span>
        <span>분야: {result.tech_field}</span>
        <span>패널: {result.panel_size}명</span>
        <span>소요시간: {result.elapsed_seconds.toFixed(1)}초</span>
      </div>

      {/* 앙상블 결과 */}
      <div className="ensemble-summary">
        <h2>평가 결과</h2>
        <div className="stats-grid">
          <div className={`stat-card ${ensemble.final_verdict === 'approved' ? 'bg-green' : 'bg-red'}`}>
            <div className="stat-value">{ensemble.final_verdict === 'approved' ? '승인' : '거절'}</div>
            <div className="stat-label">최종 의결</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{(ensemble.approval_ratio * 100).toFixed(1)}%</div>
            <div className="stat-label">찬성률</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{ensemble.avg_novelty_total.toFixed(1)}/50</div>
            <div className="stat-label">신규성</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{ensemble.avg_progressiveness_total.toFixed(1)}/50</div>
            <div className="stat-label">진보성</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{ensemble.avg_total.toFixed(1)}/100</div>
            <div className="stat-label">총점</div>
          </div>
        </div>
      </div>

      {/* 에이전트별 총점 바 차트 */}
      <div className="chart-section">
        <h2>에이전트별 점수</h2>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={barData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis domain={[0, 100]} />
            <Tooltip content={({ payload }: any) => {
              if (!payload || payload.length === 0) return null;
              const d = payload[0]?.payload;
              return (
                <div style={{ background: 'white', padding: 8, border: '1px solid #ddd', borderRadius: 4, fontSize: 12 }}>
                  <p><strong>{d?.name}</strong> (경력 {d?.years}년, {d?.match === 'exact' ? '정합' : '부분정합'})</p>
                  <p>신규성: {d?.novelty}/50 | 진보성: {d?.progressiveness}/50</p>
                  <p>의결: {d?.verdict === 'approved' ? '승인' : '거절'}</p>
                </div>
              );
            }} />
            <Legend />
            <Bar dataKey="novelty" name="신규성" stackId="a" fill="#4CAF50" />
            <Bar dataKey="progressiveness" name="진보성" stackId="a" fill="#2196F3" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* 평균 레이더 차트 */}
      <div className="chart-section">
        <h2>세부 항목 점수</h2>
        <ResponsiveContainer width="100%" height={350}>
          <RadarChart data={radarData}>
            <PolarGrid />
            <PolarAngleAxis dataKey="subject" />
            <PolarRadiusAxis />
            <Radar name="평균" dataKey="평균" stroke="#1a237e" fill="#1a237e" fillOpacity={0.3} />
            {selectedAgent && (
              <Radar name={selectedAgent} dataKey={selectedAgent} stroke="#FF5722" fill="#FF5722" fillOpacity={0.2} />
            )}
            <Legend />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* 경력-점수 산점도 */}
      <div className="chart-section">
        <h2>경력 연수 vs 총점 (상관관계)</h2>
        <ResponsiveContainer width="100%" height={300}>
          <ScatterChart>
            <CartesianGrid />
            <XAxis dataKey="years" name="경력(년)" type="number" />
            <YAxis dataKey="score" name="총점" domain={[0, 100]} />
            <ZAxis dataKey="confidence" name="확신도" range={[60, 200]} />
            <Tooltip content={({ payload }: any) => {
              if (!payload || payload.length === 0) return null;
              const d = payload[0]?.payload;
              return (
                <div style={{ background: 'white', padding: 8, border: '1px solid #ddd', borderRadius: 4, fontSize: 12 }}>
                  <p><strong>{d?.agent}</strong></p>
                  <p>경력: {d?.years}년 | 총점: {d?.score} | 확신도: {d?.confidence?.toFixed(2)}</p>
                </div>
              );
            }} />
            <Scatter data={scatterApproved} fill="#4CAF50" name="승인" />
            <Scatter data={scatterRejected} fill="#F44336" name="거절" />
            <Legend />
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      {/* 근거 소스 분석 */}
      {allEvidenceDetails.length > 0 && (
        <div className="chart-section">
          <h2>근거 소스 분석 (검증3)</h2>
          <div className="stats-grid">
            {Object.entries(sourceTypeCounts).map(([type, count]) => (
              <div key={type} className="stat-card" style={{ borderLeft: `4px solid ${SOURCE_COLORS[type] || '#999'}` }}>
                <div className="stat-value">{count}</div>
                <div className="stat-label">{SOURCE_LABELS[type] || type}</div>
              </div>
            ))}
          </div>
          <button className="btn btn-secondary" style={{ marginTop: 8 }}
                  onClick={() => setShowAllEvidence(!showAllEvidence)}>
            {showAllEvidence ? '근거 숨기기' : `전체 근거 보기 (${allEvidenceDetails.length}건)`}
          </button>
          {showAllEvidence && (
            <div style={{ marginTop: 12 }}>
              {allEvidenceDetails.map((e, i) => (
                <div key={i} className="evidence-card" style={{ borderLeft: `4px solid ${SOURCE_COLORS[e.source_type] || '#999'}` }}>
                  <div className="evidence-type">{SOURCE_LABELS[e.source_type] || e.source_type}</div>
                  <div className="evidence-claim">{e.claim}</div>
                  <div className="evidence-ref">출처: {e.source_ref}</div>
                  <div className="evidence-relevance">활용: {e.relevance}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 개별 에이전트 투표 목록 */}
      <div className="votes-section">
        <h2>개별 위원 평가</h2>
        <table className="vote-table">
          <thead>
            <tr>
              <th>에이전트</th>
              <th>매칭</th>
              <th>경력</th>
              <th>연수</th>
              <th>의결</th>
              <th>신규성</th>
              <th>진보성</th>
              <th>총점</th>
              <th>확신도</th>
              <th>근거</th>
            </tr>
          </thead>
          <tbody>
            {votes.map(v => {
              const profile = panel.find(p => p.agent_id === v.agent_id);
              const evidenceCount = (v.evidence_details || v.evidence || []).length;
              return (
                <tr key={v.agent_id}
                    className={selectedAgent === v.agent_id ? 'selected' : ''}
                    onClick={() => setSelectedAgent(v.agent_id === selectedAgent ? null : v.agent_id)}>
                  <td>{v.agent_id}</td>
                  <td>{profile?.match_level === 'exact' ? '정합' : '부분정합'}</td>
                  <td>{profile?.experience === 'high' ? '고' : profile?.experience === 'medium' ? '중' : '저'}</td>
                  <td>{profile?.experience_years}년</td>
                  <td className={v.vote === 'approved' ? 'verdict-approved' : 'verdict-rejected'}>
                    {v.vote === 'approved' ? '승인' : '거절'}
                  </td>
                  <td>{v.novelty.total.toFixed(0)}/50</td>
                  <td>{v.progressiveness.total.toFixed(0)}/50</td>
                  <td>{v.total.toFixed(0)}/100</td>
                  <td>{v.confidence.toFixed(2)}</td>
                  <td>{evidenceCount}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* 선택된 에이전트 상세 */}
      {selectedVote && (
        <div className="agent-detail">
          <h3>{selectedAgent} 상세 평가</h3>
          {selectedProfile && (
            <div className="info-box">
              <strong>전문분야:</strong> {selectedProfile.specialty} |
              <strong> 경력:</strong> {selectedProfile.experience_years}년 ({selectedProfile.experience}) |
              <strong> 매칭:</strong> {selectedProfile.match_level === 'exact' ? '정합' : '부분정합'}
            </div>
          )}

          <h4>세부 점수</h4>
          <div className="stats-grid">
            <div className="stat-card"><div className="stat-value">{selectedVote.novelty.differentiation}</div><div className="stat-label">차별성 /25</div></div>
            <div className="stat-card"><div className="stat-value">{selectedVote.novelty.originality}</div><div className="stat-label">독창성 /25</div></div>
            <div className="stat-card"><div className="stat-value">{selectedVote.progressiveness.quality_improvement}</div><div className="stat-label">품질향상 /15</div></div>
            <div className="stat-card"><div className="stat-value">{selectedVote.progressiveness.development_degree}</div><div className="stat-label">개발정도 /15</div></div>
            <div className="stat-card"><div className="stat-value">{selectedVote.progressiveness.safety}</div><div className="stat-label">안전성 /10</div></div>
            <div className="stat-card"><div className="stat-value">{selectedVote.progressiveness.eco_friendliness}</div><div className="stat-label">친환경성 /10</div></div>
          </div>

          <h4>판단 근거 (KB 소스 추적)</h4>
          {selectedVote.evidence_details && selectedVote.evidence_details.length > 0 ? (
            <div className="evidence-list">
              {selectedVote.evidence_details.map((e: EvidenceDetail, i: number) => (
                <div key={i} className="evidence-card" style={{ borderLeft: `4px solid ${SOURCE_COLORS[e.source_type] || '#999'}` }}>
                  <div className="evidence-type">{SOURCE_LABELS[e.source_type] || e.source_type}</div>
                  <div className="evidence-claim">{e.claim}</div>
                  <div className="evidence-ref">출처: {e.source_ref}</div>
                  <div className="evidence-relevance">활용: {e.relevance}</div>
                </div>
              ))}
            </div>
          ) : (
            <ul>
              {selectedVote.evidence.map((e, i) => (
                <li key={i}>{typeof e === 'object' ? Object.entries(e).map(([k, v]) => `${k}: ${v}`).join(' | ') : String(e)}</li>
              ))}
            </ul>
          )}

          {selectedVote.prior_art_comparison && (
            <>
              <h4>선행기술 비교</h4>
              <p>{selectedVote.prior_art_comparison}</p>
            </>
          )}

          {selectedVote.reasoning && (
            <>
              <h4>종합 판단</h4>
              {typeof selectedVote.reasoning === 'string' ? (
                <p>{selectedVote.reasoning}</p>
              ) : (
                <div className="reasoning-details">
                  {Object.entries(selectedVote.reasoning).map(([key, value]) => (
                    <div key={key} style={{ marginBottom: 8 }}>
                      <strong>{key.replace(/_/g, ' ').replace('reasoning', '').trim()}:</strong>
                      <p style={{ margin: '4px 0 0 12px' }}>{String(value)}</p>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* 소수 의견 */}
      {ensemble.dissenting_opinions && ensemble.dissenting_opinions.length > 0 && (
        <div className="dissenting">
          <h3>소수 의견</h3>
          <ul>{ensemble.dissenting_opinions.map((d, i) => <li key={i}>{d}</li>)}</ul>
        </div>
      )}

      {/* 의장 검토 */}
      {result.chairman_review && result.chairman_review.review_verdict && (
        <div className="chairman-review">
          <h2>의장 검토</h2>
          <p><strong>검토 결과:</strong> {result.chairman_review.review_verdict}</p>
          <p><strong>일관성 점수:</strong> {result.chairman_review.consistency_score}/10</p>
          <p><strong>확신도:</strong> {result.chairman_review.confidence}</p>
          {result.chairman_review.hallucination_flags?.length > 0 && (
            <>
              <h4>환각/오류 탐지</h4>
              <ul>{result.chairman_review.hallucination_flags.map((f: string, i: number) => <li key={i}>{f}</li>)}</ul>
            </>
          )}
          <p><strong>종합 의견:</strong> {result.chairman_review.final_opinion}</p>
        </div>
      )}
    </div>
  );
};

export default ResultDetail;
