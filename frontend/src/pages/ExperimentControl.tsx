import React, { useEffect, useState } from 'react';
import {
  fetchProposals, fetchResults, startEvaluation, startBatchEvaluation,
  startSensitivityRun,
} from '../api/client';

interface Props {
  runningJobs: any[];
  setRunningJobs: React.Dispatch<React.SetStateAction<any[]>>;
}

const ACCURACY_CUTOFF = 2018;
const SENSITIVITY_RANGE: [number, number] = [2013, 2017];

type GroupFilter = 'all' | 'accuracy' | 'sensitivity' | 'pre2018';

const ExperimentControl: React.FC<Props> = ({ runningJobs, setRunningJobs }) => {
  const [proposals, setProposals] = useState<any[]>([]);
  const [results, setResults] = useState<any[]>([]);
  const [selectedTechs, setSelectedTechs] = useState<string[]>([]);
  const [repetitions, setRepetitions] = useState(5);
  const [seed, setSeed] = useState(42);
  const [skipChairman, setSkipChairman] = useState(false);
  const [loading, setLoading] = useState(true);
  const [groupFilter, setGroupFilter] = useState<GroupFilter>('all');

  useEffect(() => {
    Promise.all([fetchProposals(), fetchResults()])
      .then(([pRes, rRes]) => {
        setProposals(pRes.data.proposals || []);
        setResults(rRes.data.results || []);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (runningJobs.length === 0 && !loading) {
      fetchResults()
        .then(r => setResults(r.data.results || []))
        .catch(console.error);
    }
  }, [runningJobs.length]);

  const getDesignationYear = (p: any) => p.designation_year || null;

  const getGroup = (p: any): string => {
    const year = getDesignationYear(p);
    if (!year) return 'unknown';
    if (year >= ACCURACY_CUTOFF) return 'accuracy';
    if (year >= SENSITIVITY_RANGE[0] && year <= SENSITIVITY_RANGE[1]) return 'sensitivity';
    return 'pre2018';
  };

  const filteredProposals = proposals.filter(p => {
    if (groupFilter === 'all') return true;
    return getGroup(p) === groupFilter;
  });

  const groupCounts = {
    all: proposals.length,
    accuracy: proposals.filter(p => getGroup(p) === 'accuracy').length,
    sensitivity: proposals.filter(p => getGroup(p) === 'sensitivity').length,
    pre2018: proposals.filter(p => getGroup(p) === 'pre2018' || getGroup(p) === 'sensitivity').length,
  };

  const toggleTech = (techNum: string) => {
    setSelectedTechs(prev =>
      prev.includes(techNum) ? prev.filter(t => t !== techNum) : [...prev, techNum]
    );
  };

  const selectFiltered = () => {
    const filteredNums = filteredProposals.map(p => p.tech_number);
    const allSelected = filteredNums.every(n => selectedTechs.includes(n));
    if (allSelected) {
      setSelectedTechs(prev => prev.filter(t => !filteredNums.includes(t)));
    } else {
      setSelectedTechs(prev => Array.from(new Set([...prev, ...filteredNums])));
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

  const runSensitivity = async () => {
    const sensTechs = proposals
      .filter(p => getGroup(p) === 'sensitivity')
      .map(p => p.tech_number);
    if (sensTechs.length === 0) return;
    try {
      const res = await startSensitivityRun(sensTechs, repetitions, seed);
      setRunningJobs(prev => [
        ...prev,
        ...(res.data.run_ids || []).map((id: string) => ({ run_id: id, status: 'running', progress: 0 })),
      ]);
    } catch (e: any) {
      alert('민감도 실험 실행 실패: ' + e.message);
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

  // nocutoff 결과 수
  const nocutoffResults = results.filter(r => r.run_id?.startsWith('nocutoff_'));

  if (loading) return <div className="loading">로딩 중...</div>;

  return (
    <div className="experiment-page">
      <h1>실험 실행 관리</h1>

      {/* 진행 상황 */}
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
        </div>
      )}

      {/* 실험 설계 요약 */}
      <div className="chart-section" style={{ borderLeft: '4px solid #1a237e' }}>
        <h2>하이브리드 4검증 실험 설계</h2>
        <div className="stats-grid">
          <div className="stat-card bg-blue">
            <div className="stat-value">{groupCounts.accuracy}</div>
            <div className="stat-label">검증1: 정확도 (2018+)</div>
          </div>
          <div className="stat-card bg-green">
            <div className="stat-value">{groupCounts.all}</div>
            <div className="stat-label">검증2: 일관성 (전체)</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{groupCounts.all}</div>
            <div className="stat-label">검증3: 패턴 (전체)</div>
          </div>
          <div className="stat-card" style={{ borderLeft: '4px solid #FF9800' }}>
            <div className="stat-value">{groupCounts.sensitivity}</div>
            <div className="stat-label">검증4: 민감도 (2013-17)</div>
          </div>
        </div>
        <div className="info-box" style={{ marginTop: 8 }}>
          <strong>시간적 커트오프:</strong> 각 기술의 지정연도 이후 KB 자료를 자동 제외합니다.
          검증4에서는 동일 기술을 커트오프 적용/미적용 양쪽으로 평가하여 KB 풍부도 영향을 측정합니다.
        </div>
      </div>

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

        {/* 그룹 필터 */}
        <div className="tab-bar" style={{ marginBottom: 12 }}>
          <button className={groupFilter === 'all' ? 'active' : ''} onClick={() => setGroupFilter('all')}>
            전체 ({groupCounts.all})
          </button>
          <button className={groupFilter === 'accuracy' ? 'active' : ''} onClick={() => setGroupFilter('accuracy')}>
            정확도 그룹 2018+ ({groupCounts.accuracy})
          </button>
          <button className={groupFilter === 'sensitivity' ? 'active' : ''} onClick={() => setGroupFilter('sensitivity')}>
            민감도 그룹 2013-17 ({groupCounts.sensitivity})
          </button>
        </div>

        <button className="btn btn-secondary" onClick={selectFiltered}>
          {filteredProposals.every(p => selectedTechs.includes(p.tech_number)) ? '필터 해제' : '필터 전체 선택'}
        </button>

        <table className="result-table" style={{ marginTop: 8 }}>
          <thead>
            <tr>
              <th style={{ width: 40 }}>선택</th>
              <th>번호</th>
              <th>기술명</th>
              <th>분야</th>
              <th>지정연도</th>
              <th>그룹</th>
              <th>기존 결과</th>
              <th>실행</th>
            </tr>
          </thead>
          <tbody>
            {filteredProposals.map(p => {
              const existingResults = resultsByTech[p.tech_number] || [];
              const year = getDesignationYear(p);
              const group = getGroup(p);
              const groupLabel = group === 'accuracy' ? '정확도' : group === 'sensitivity' ? '민감도' : group;
              const groupColor = group === 'accuracy' ? '#2196F3' : group === 'sensitivity' ? '#FF9800' : '#999';

              return (
                <tr key={p.tech_number}>
                  <td>
                    <input type="checkbox" checked={selectedTechs.includes(p.tech_number)}
                           onChange={() => toggleTech(p.tech_number)} />
                  </td>
                  <td>{p.tech_number}</td>
                  <td>{p.tech_name?.substring(0, 35)}</td>
                  <td>{p.tech_field?.substring(0, 15)}</td>
                  <td>{year || '-'}</td>
                  <td><span style={{ color: groupColor, fontWeight: 'bold', fontSize: 12 }}>{groupLabel}</span></td>
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
                      실행
                    </button>
                  </td>
                </tr>
              );
            })}
            {filteredProposals.length === 0 && (
              <tr><td colSpan={8} style={{ textAlign: 'center' }}>해당 그룹에 제안기술이 없습니다.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 배치 실행 */}
      {selectedTechs.length > 0 && (
        <div className="chart-section">
          <h2>배치 실행</h2>
          <div className="info-box">
            <strong>선택됨:</strong> {selectedTechs.length}건 x {repetitions}회 반복 = 총 {selectedTechs.length * repetitions}건 평가
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <button className="btn btn-primary" onClick={runExperiment}
                    disabled={runningJobs.length > 0}>
              {runningJobs.length > 0 ? '실행 중...' : '배치 실험 시작 (커트오프 적용)'}
            </button>
          </div>
        </div>
      )}

      {/* 민감도 실험 (검증4) */}
      <div className="chart-section" style={{ borderLeft: '4px solid #FF9800' }}>
        <h2>검증4: 커트오프 민감도 실험</h2>
        <div className="info-box">
          2013-2017년 기술 {groupCounts.sensitivity}건에 대해 커트오프 미적용 버전을 추가 실행합니다.
          (커트오프 적용 버전은 일반 배치 실행에서 수행)
        </div>
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-value">{groupCounts.sensitivity}</div>
            <div className="stat-label">대상 기술</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{groupCounts.sensitivity * repetitions}</div>
            <div className="stat-label">추가 실행 건수</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{nocutoffResults.length}</div>
            <div className="stat-label">완료된 nocutoff 결과</div>
          </div>
        </div>
        <button className="btn btn-primary" onClick={runSensitivity}
                disabled={runningJobs.length > 0 || groupCounts.sensitivity === 0}
                style={{ background: '#FF9800' }}>
          {runningJobs.length > 0 ? '실행 중...' : '민감도 실험 시작 (커트오프 미적용)'}
        </button>
      </div>

      {/* 기존 결과 요약 */}
      {results.length > 0 && (
        <div className="chart-section">
          <h2>기존 평가 결과 ({results.length}건, nocutoff: {nocutoffResults.length}건)</h2>
          <table className="result-table">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>번호</th>
                <th>기술명</th>
                <th>의결</th>
                <th>찬성률</th>
                <th>평균총점</th>
                <th>상세</th>
              </tr>
            </thead>
            <tbody>
              {results.slice(0, 50).map(r => (
                <tr key={r.run_id} style={r.run_id?.startsWith('nocutoff_') ? { background: '#fff8e1' } : undefined}>
                  <td style={{ fontSize: 11 }}>{r.run_id}</td>
                  <td>{r.tech_number}</td>
                  <td>{r.tech_name?.substring(0, 25)}</td>
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
          {results.length > 50 && (
            <p style={{ color: '#999', textAlign: 'center' }}>
              ... 외 {results.length - 50}건 (최근 50건만 표시)
            </p>
          )}
        </div>
      )}
    </div>
  );
};

export default ExperimentControl;
