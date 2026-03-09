import React, { useEffect, useState } from 'react';
import { fetchResults, fetchKBStatus, fetchProposals } from '../api/client';

interface ResultSummary {
  run_id: string;
  tech_number: string;
  tech_name: string;
  final_verdict: string;
  approval_ratio: number;
  avg_total: number;
  panel_size: number;
  elapsed_seconds: number;
}

const ACCURACY_CUTOFF = 2018;
const SENSITIVITY_RANGE: [number, number] = [2013, 2017];

const Dashboard: React.FC = () => {
  const [results, setResults] = useState<ResultSummary[]>([]);
  const [kbStatus, setKbStatus] = useState<any>(null);
  const [proposals, setProposals] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([fetchResults(), fetchKBStatus(), fetchProposals()])
      .then(([resResults, resKB, resProposals]) => {
        setResults(resResults.data.results || []);
        setKbStatus(resKB.data);
        setProposals(resProposals.data.proposals || []);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading">로딩 중...</div>;

  const approvedCount = results.filter(r => r.final_verdict === 'approved').length;
  const nocutoffCount = results.filter(r => r.run_id?.startsWith('nocutoff_')).length;

  const accuracyProposals = proposals.filter(p => (p.designation_year || 0) >= ACCURACY_CUTOFF);
  const sensitivityProposals = proposals.filter(p => {
    const y = p.designation_year || 0;
    return y >= SENSITIVITY_RANGE[0] && y <= SENSITIVITY_RANGE[1];
  });

  return (
    <div className="dashboard">
      <h1>건설신기술 LLM 평가 시스템</h1>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{results.length}</div>
          <div className="stat-label">총 평가 건수</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{approvedCount}</div>
          <div className="stat-label">승인 건수</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">
            {results.length > 0 ? (approvedCount / results.length * 100).toFixed(1) : 0}%
          </div>
          <div className="stat-label">승인율</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">
            {kbStatus?.vector_db_exists ? '구축됨' : '미구축'}
          </div>
          <div className="stat-label">벡터 KB 상태</div>
        </div>
      </div>

      {/* 하이브리드 4검증 실험 설계 요약 */}
      <div className="chart-section" style={{ borderLeft: '4px solid #1a237e' }}>
        <h2>하이브리드 4검증 실험 설계</h2>
        <div className="stats-grid">
          <div className="stat-card bg-blue">
            <div className="stat-value">{accuracyProposals.length}</div>
            <div className="stat-label">검증1: 정확도 (2018+)</div>
          </div>
          <div className="stat-card bg-green">
            <div className="stat-value">{proposals.length}</div>
            <div className="stat-label">검증2: 일관성 (전체)</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{proposals.length}</div>
            <div className="stat-label">검증3: 점수패턴 (전체)</div>
          </div>
          <div className="stat-card" style={{ borderLeft: '4px solid #FF9800' }}>
            <div className="stat-value">{sensitivityProposals.length}</div>
            <div className="stat-label">검증4: 민감도 (2013-17)</div>
          </div>
        </div>
        {nocutoffCount > 0 && (
          <div className="info-box" style={{ marginTop: 8 }}>
            커트오프 미적용(nocutoff) 결과: {nocutoffCount}건 완료
          </div>
        )}
      </div>

      <h2>평가 결과 목록</h2>
      <table className="result-table">
        <thead>
          <tr>
            <th>기술번호</th>
            <th>기술명</th>
            <th>의결</th>
            <th>찬성률</th>
            <th>평균 총점</th>
            <th>패널</th>
            <th>소요시간</th>
          </tr>
        </thead>
        <tbody>
          {results.map(r => (
            <tr key={r.run_id} onClick={() => window.location.hash = `#/result/${r.run_id}`}>
              <td>{r.tech_number}</td>
              <td>{r.tech_name}</td>
              <td className={r.final_verdict === 'approved' ? 'verdict-approved' : 'verdict-rejected'}>
                {r.final_verdict === 'approved' ? '승인' : '거절'}
              </td>
              <td>{(r.approval_ratio * 100).toFixed(1)}%</td>
              <td>{r.avg_total.toFixed(1)}</td>
              <td>{r.panel_size}명</td>
              <td>{r.elapsed_seconds.toFixed(1)}초</td>
            </tr>
          ))}
          {results.length === 0 && (
            <tr><td colSpan={7} style={{textAlign: 'center'}}>평가 결과가 없습니다</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
};

export default Dashboard;
