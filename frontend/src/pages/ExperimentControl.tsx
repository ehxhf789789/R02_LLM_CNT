import React, { useEffect, useState } from 'react';
import {
  fetchProposals, fetchResults, startEvaluation, startBatchEvaluation,
} from '../api/client';

interface Props {
  runningJobs: any[];
  setRunningJobs: React.Dispatch<React.SetStateAction<any[]>>;
}

const ExperimentControl: React.FC<Props> = ({ runningJobs, setRunningJobs }) => {
  const [proposals, setProposals] = useState<any[]>([]);
  const [results, setResults] = useState<any[]>([]);
  const [selectedTechs, setSelectedTechs] = useState<string[]>([]);
  const [repetitions, setRepetitions] = useState(5);
  const [seed, setSeed] = useState(42);
  const [skipChairman, setSkipChairman] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([fetchProposals(), fetchResults()])
      .then(([pRes, rRes]) => {
        setProposals(pRes.data.proposals || []);
        setResults(rRes.data.results || []);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  // 실행이 모두 끝나면 결과 갱신
  useEffect(() => {
    if (runningJobs.length === 0 && !loading) {
      fetchResults()
        .then(r => setResults(r.data.results || []))
        .catch(console.error);
    }
  }, [runningJobs.length]);

  const toggleTech = (techNum: string) => {
    setSelectedTechs(prev =>
      prev.includes(techNum) ? prev.filter(t => t !== techNum) : [...prev, techNum]
    );
  };

  const selectAll = () => {
    if (selectedTechs.length === proposals.length) {
      setSelectedTechs([]);
    } else {
      setSelectedTechs(proposals.map(p => p.tech_number));
    }
  };

  const runExperiment = async () => {
    if (selectedTechs.length === 0) return;
    try {
      const res = await startBatchEvaluation(selectedTechs, repetitions, seed);
      setRunningJobs(res.data.run_ids.map((id: string) => ({ run_id: id, status: 'running', progress: 0 })));
    } catch (e: any) {
      alert('실험 실행 실패: ' + e.message);
    }
  };

  const runSingle = async (techNum: string) => {
    try {
      const res = await startEvaluation(techNum, seed, skipChairman);
      setRunningJobs(prev => [...prev, { run_id: res.data.run_id, status: 'running', progress: 0 }]);
    } catch (e: any) {
      alert('실행 실패: ' + e.message);
    }
  };

  const resultsByTech: Record<string, any[]> = {};
  results.forEach(r => {
    const tn = r.tech_number;
    if (!resultsByTech[tn]) resultsByTech[tn] = [];
    resultsByTech[tn].push(r);
  });

  if (loading) return <div className="loading">로딩 중...</div>;

  return (
    <div className="experiment-page">
      <h1>실험 실행 관리</h1>

      {/* 진행 상황 (항상 상단에 표시) */}
      {runningJobs.length > 0 && (
        <div className="chart-section" style={{ borderLeft: '4px solid #FF9800' }}>
          <h2>진행 중 ({runningJobs.length}건)</h2>
          {runningJobs.map((job: any) => (
            <div key={job.run_id} className="case-box">
              <strong>{job.run_id}</strong>: {job.step || job.status}
              {job.progress !== undefined && (
                <div className="progress-bar">
                  <div className="progress-fill" style={{ width: `${job.progress}%` }} />
                </div>
              )}
            </div>
          ))}
          <div className="info-box" style={{ marginTop: 8 }}>
            다른 탭으로 이동해도 시뮬레이션은 백그라운드에서 계속 진행됩니다.
          </div>
        </div>
      )}

      {/* 실험 설정 */}
      <div className="chart-section">
        <h2>실험 설정</h2>
        <div className="experiment-config">
          <div className="config-row">
            <label>반복 횟수:</label>
            <input type="number" value={repetitions} onChange={e => setRepetitions(parseInt(e.target.value) || 1)}
                   min={1} max={30} style={{ width: 80 }} />
            <span className="hint">일관성 분석을 위해 최소 5회 권장</span>
          </div>
          <div className="config-row">
            <label>랜덤 시드:</label>
            <input type="number" value={seed} onChange={e => setSeed(parseInt(e.target.value) || 0)}
                   style={{ width: 100 }} />
            <span className="hint">재현성을 위한 시드 값</span>
          </div>
          <div className="config-row">
            <label>
              <input type="checkbox" checked={skipChairman} onChange={e => setSkipChairman(e.target.checked)} />
              {' '}의장 검토 생략
            </label>
          </div>
        </div>
      </div>

      {/* 제안기술 선택 */}
      <div className="chart-section">
        <h2>평가 대상 선택</h2>
        <button className="btn btn-secondary" onClick={selectAll}>
          {selectedTechs.length === proposals.length ? '전체 해제' : '전체 선택'}
        </button>
        <table className="result-table" style={{ marginTop: 8 }}>
          <thead>
            <tr>
              <th style={{ width: 40 }}>선택</th>
              <th>기술번호</th>
              <th>기술명</th>
              <th>분야</th>
              <th>기존 결과</th>
              <th>실행</th>
            </tr>
          </thead>
          <tbody>
            {proposals.map(p => {
              const existingResults = resultsByTech[p.tech_number] || [];
              return (
                <tr key={p.tech_number}>
                  <td>
                    <input type="checkbox" checked={selectedTechs.includes(p.tech_number)}
                           onChange={() => toggleTech(p.tech_number)} />
                  </td>
                  <td>{p.tech_number}</td>
                  <td>{p.tech_name?.substring(0, 40)}</td>
                  <td>{p.tech_field?.substring(0, 20)}</td>
                  <td>
                    {existingResults.length > 0 ? (
                      <span>
                        {existingResults.length}건
                        ({existingResults.filter((r: any) => r.final_verdict === 'approved').length}승인)
                      </span>
                    ) : '-'}
                  </td>
                  <td>
                    <button className="btn btn-sm" onClick={() => runSingle(p.tech_number)}
                            disabled={runningJobs.length > 0}>
                      단일 실행
                    </button>
                  </td>
                </tr>
              );
            })}
            {proposals.length === 0 && (
              <tr><td colSpan={6} style={{ textAlign: 'center' }}>제안기술이 없습니다. prepare 단계를 먼저 실행하세요.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 배치 실행 */}
      {selectedTechs.length > 0 && (
        <div className="chart-section">
          <h2>배치 실행</h2>
          <div className="info-box">
            <strong>선택됨:</strong> {selectedTechs.length}건 x
            {repetitions}회 반복 = 총 {selectedTechs.length * repetitions}건 평가 실행
          </div>
          <button className="btn btn-primary" onClick={runExperiment}
                  disabled={runningJobs.length > 0}>
            {runningJobs.length > 0 ? '실행 중...' : '배치 실험 시작'}
          </button>
        </div>
      )}

      {/* 기존 결과 요약 */}
      {results.length > 0 && (
        <div className="chart-section">
          <h2>기존 평가 결과 ({results.length}건)</h2>
          <table className="result-table">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>기술번호</th>
                <th>기술명</th>
                <th>의결</th>
                <th>찬성률</th>
                <th>평균총점</th>
                <th>상세</th>
              </tr>
            </thead>
            <tbody>
              {results.map(r => (
                <tr key={r.run_id}>
                  <td>{r.run_id}</td>
                  <td>{r.tech_number}</td>
                  <td>{r.tech_name?.substring(0, 30)}</td>
                  <td className={r.final_verdict === 'approved' ? 'verdict-approved' : 'verdict-rejected'}>
                    {r.final_verdict === 'approved' ? '승인' : '거절'}
                  </td>
                  <td>{(r.approval_ratio * 100).toFixed(0)}%</td>
                  <td>{r.avg_total?.toFixed(1)}</td>
                  <td>
                    <a href={`#/result/${r.run_id}`} className="btn btn-sm">보기</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default ExperimentControl;
