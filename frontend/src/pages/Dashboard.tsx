import React, { useEffect, useState } from 'react';
import { fetchResults, fetchKBStatus } from '../api/client';

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

const Dashboard: React.FC = () => {
  const [results, setResults] = useState<ResultSummary[]>([]);
  const [kbStatus, setKbStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([fetchResults(), fetchKBStatus()])
      .then(([resResults, resKB]) => {
        setResults(resResults.data.results || []);
        setKbStatus(resKB.data);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading">로딩 중...</div>;

  const approvedCount = results.filter(r => r.final_verdict === 'approved').length;

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
