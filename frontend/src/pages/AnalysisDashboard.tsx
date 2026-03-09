import React, { useEffect, useState } from 'react';
import {
  fetchAccuracyAnalysis,
  fetchConsistencyAnalysis,
  fetchScorePatternAnalysis,
  fetchExperienceCorrelation,
} from '../api/client';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  ScatterChart, Scatter, ZAxis,
  ResponsiveContainer,
} from 'recharts';

const AnalysisDashboard: React.FC = () => {
  const [tab, setTab] = useState<'accuracy' | 'consistency' | 'patterns' | 'correlation'>('accuracy');
  const [accuracy, setAccuracy] = useState<any>(null);
  const [consistency, setConsistency] = useState<any>(null);
  const [patterns, setPatterns] = useState<any>(null);
  const [correlation, setCorrelation] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchAccuracyAnalysis().catch(() => ({ data: {} })),
      fetchConsistencyAnalysis().catch(() => ({ data: {} })),
      fetchScorePatternAnalysis().catch(() => ({ data: {} })),
      fetchExperienceCorrelation().catch(() => ({ data: {} })),
    ])
      .then(([a, c, p, e]) => {
        setAccuracy(a.data);
        setConsistency(c.data);
        setPatterns(p.data);
        setCorrelation(e.data);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading">분석 데이터 로딩 중...</div>;

  return (
    <div className="analysis-dashboard">
      <h1>검증 분석 대시보드</h1>

      <div className="tab-bar">
        <button className={tab === 'accuracy' ? 'active' : ''} onClick={() => setTab('accuracy')}>
          검증1: 정확도
        </button>
        <button className={tab === 'consistency' ? 'active' : ''} onClick={() => setTab('consistency')}>
          검증2: 일관성
        </button>
        <button className={tab === 'patterns' ? 'active' : ''} onClick={() => setTab('patterns')}>
          검증3: 패턴분석
        </button>
        <button className={tab === 'correlation' ? 'active' : ''} onClick={() => setTab('correlation')}>
          경력 상관관계
        </button>
      </div>

      {tab === 'accuracy' && accuracy && <AccuracyTab data={accuracy} />}
      {tab === 'consistency' && consistency && <ConsistencyTab data={consistency} />}
      {tab === 'patterns' && patterns && <PatternsTab data={patterns} />}
      {tab === 'correlation' && correlation && <CorrelationTab data={correlation} />}
    </div>
  );
};

const AccuracyTab: React.FC<{ data: any }> = ({ data }) => {
  if (!data.case_results) return <p>데이터 없음</p>;

  const caseData = data.case_results.map((c: any) => ({
    name: c.tech_number,
    approval_ratio: (c.approval_ratio * 100),
    avg_total: c.avg_total,
    correct: c.is_correct ? 1 : 0,
  }));

  const matchData = Object.entries(data.by_match_level || {}).map(([key, val]: [string, any]) => ({
    name: key === 'exact' ? '정합' : '부분정합',
    accuracy: (val.accuracy * 100),
    avg_score: val.avg_score,
    count: val.count,
  }));

  const expData = Object.entries(data.by_experience || {}).map(([key, val]: [string, any]) => ({
    name: key === 'high' ? '고경력' : key === 'medium' ? '중경력' : '저경력',
    accuracy: (val.accuracy * 100),
    avg_score: val.avg_score,
    count: val.count,
  }));

  return (
    <div>
      <div className="info-box">
        <strong>검증1 (정확도):</strong> 입력 데이터는 이미 통과된 기술이므로, 에이전트 평가도 '승인'으로 판정해야 정확합니다.
      </div>
      <div className="stats-grid">
        <div className="stat-card bg-blue">
          <div className="stat-value">{(data.overall_accuracy * 100).toFixed(1)}%</div>
          <div className="stat-label">전체 정확도</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{data.total_cases}</div>
          <div className="stat-label">총 케이스</div>
        </div>
      </div>

      <h3>건별 찬성률</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={caseData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" />
          <YAxis domain={[0, 100]} />
          <Tooltip />
          <Bar dataKey="approval_ratio" name="찬성률(%)" fill="#4CAF50" />
        </BarChart>
      </ResponsiveContainer>

      {matchData.length > 0 && (
        <>
          <h3>매칭 수준별 정확도</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={matchData}>
              <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis domain={[0, 100]} />
              <Tooltip /><Legend />
              <Bar dataKey="accuracy" name="정확도(%)" fill="#2196F3" />
              <Bar dataKey="avg_score" name="평균 점수" fill="#FF9800" />
            </BarChart>
          </ResponsiveContainer>
        </>
      )}

      {expData.length > 0 && (
        <>
          <h3>경력별 정확도</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={expData}>
              <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis domain={[0, 100]} />
              <Tooltip /><Legend />
              <Bar dataKey="accuracy" name="정확도(%)" fill="#9C27B0" />
              <Bar dataKey="avg_score" name="평균 점수" fill="#00BCD4" />
            </BarChart>
          </ResponsiveContainer>
        </>
      )}
    </div>
  );
};

const ConsistencyTab: React.FC<{ data: any }> = ({ data }) => {
  if (!data.case_consistency) return <p>데이터 없음 (반복 실행 필요 - 실험실행 탭에서 5회 이상 반복)</p>;

  const kappa = data.fleiss_kappa;
  const stabilityData = data.case_consistency.map((c: any) => ({
    name: c.tech_number,
    stability: (c.verdict_stability * 100),
    cv: c.score_cv_percent,
  }));

  return (
    <div>
      <div className="info-box">
        <strong>검증2 (일관성):</strong> 동일 입력에 대해 반복 실행 시 평가 결과의 안정성을 측정합니다.
      </div>
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{(data.overall_verdict_stability * 100).toFixed(1)}%</div>
          <div className="stat-label">의결 안정성</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{data.overall_score_cv?.toFixed(1) || 0}%</div>
          <div className="stat-label">점수 변동계수</div>
        </div>
        {kappa && (
          <div className="stat-card">
            <div className="stat-value">{kappa.kappa?.toFixed(3) || 'N/A'}</div>
            <div className="stat-label">Fleiss' kappa</div>
          </div>
        )}
        <div className="stat-card">
          <div className="stat-value">{data.cases_with_repetitions}</div>
          <div className="stat-label">반복 분석 케이스</div>
        </div>
      </div>

      {kappa && (
        <div className="info-box">
          <strong>Fleiss' kappa 해석:</strong> {kappa.interpretation}
        </div>
      )}

      <h3>건별 의결 안정성</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={stabilityData}>
          <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis domain={[0, 100]} />
          <Tooltip /><Legend />
          <Bar dataKey="stability" name="의결 안정성(%)" fill="#4CAF50" />
          <Bar dataKey="cv" name="점수 CV(%)" fill="#F44336" />
        </BarChart>
      </ResponsiveContainer>

      {data.case_consistency.length > 0 && (
        <>
          <h3>케이스별 점수 분포</h3>
          {data.case_consistency.map((c: any) => (
            <div key={c.tech_number} className="case-box">
              <strong>{c.tech_number}</strong>:
              평균 {c.score_mean.toFixed(1)} &plusmn; {c.score_std.toFixed(1)} |
              95% CI [{c.score_ci_95[0].toFixed(1)}, {c.score_ci_95[1].toFixed(1)}] |
              의결: {c.majority_verdict} ({(c.verdict_stability * 100).toFixed(0)}% 안정)
            </div>
          ))}
        </>
      )}
    </div>
  );
};

const PatternsTab: React.FC<{ data: any }> = ({ data }) => {
  if (!data.overall_stats) return <p>데이터 없음</p>;

  const LABELS = data.score_fields || ['차별성', '독창성', '품질향상', '개발정도', '안전성', '친환경성'];
  const MAX = data.score_max || [25, 25, 15, 15, 10, 10];

  const groupRadarData = LABELS.map((label: string, i: number) => {
    const entry: any = { subject: label, fullMark: 100 };
    const byMatch = data.by_match_level || {};
    for (const [key, val] of Object.entries(byMatch) as [string, any][]) {
      if (val.mean) entry[key === 'exact' ? '정합' : '부분정합'] = (val.mean[i] / MAX[i] * 100);
    }
    const byExp = data.by_experience || {};
    for (const [key, val] of Object.entries(byExp) as [string, any][]) {
      if (val.mean) {
        const expLabel = key === 'high' ? '고경력' : key === 'medium' ? '중경력' : '저경력';
        entry[expLabel] = (val.mean[i] / MAX[i] * 100);
      }
    }
    return entry;
  });

  const corr = data.correlation || {};

  return (
    <div>
      <div className="info-box">
        <strong>검증3 (패턴분석):</strong> 에이전트들의 통과/탈락 근거를 종합하여 채점 패턴을 분석합니다.
      </div>
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{data.total_votes}</div>
          <div className="stat-label">총 투표 수</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{corr.total_vs_verdict?.toFixed(3) || 'N/A'}</div>
          <div className="stat-label">총점-의결 상관</div>
        </div>
      </div>

      <h3>매칭 수준별 점수 패턴</h3>
      <ResponsiveContainer width="100%" height={350}>
        <RadarChart data={groupRadarData}>
          <PolarGrid /><PolarAngleAxis dataKey="subject" /><PolarRadiusAxis domain={[0, 100]} />
          <Radar name="정합" dataKey="정합" stroke="#4CAF50" fill="#4CAF50" fillOpacity={0.2} />
          <Radar name="부분정합" dataKey="부분정합" stroke="#F44336" fill="#F44336" fillOpacity={0.2} />
          <Legend />
        </RadarChart>
      </ResponsiveContainer>

      <h3>경력별 점수 패턴</h3>
      <ResponsiveContainer width="100%" height={350}>
        <RadarChart data={groupRadarData}>
          <PolarGrid /><PolarAngleAxis dataKey="subject" /><PolarRadiusAxis domain={[0, 100]} />
          <Radar name="고경력" dataKey="고경력" stroke="#2196F3" fill="#2196F3" fillOpacity={0.2} />
          <Radar name="중경력" dataKey="중경력" stroke="#FF9800" fill="#FF9800" fillOpacity={0.2} />
          <Radar name="저경력" dataKey="저경력" stroke="#9C27B0" fill="#9C27B0" fillOpacity={0.2} />
          <Legend />
        </RadarChart>
      </ResponsiveContainer>

      {corr.per_field_vs_verdict && (
        <>
          <h3>세부 항목별 의결 상관계수</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={Object.entries(corr.per_field_vs_verdict).map(([k, v]) => ({
              name: k, correlation: v as number,
            }))}>
              <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis domain={[-1, 1]} />
              <Tooltip />
              <Bar dataKey="correlation" name="상관계수" fill="#2196F3" />
            </BarChart>
          </ResponsiveContainer>
        </>
      )}

      {data.agent_profiles && data.agent_profiles.length > 0 && (
        <>
          <h3>에이전트 프로파일</h3>
          <table className="vote-table">
            <thead>
              <tr><th>에이전트</th><th>매칭</th><th>경력</th><th>평가수</th><th>평균총점</th><th>승인율</th><th>확신도</th></tr>
            </thead>
            <tbody>
              {data.agent_profiles.map((p: any) => (
                <tr key={p.agent_id}>
                  <td>{p.agent_id}</td>
                  <td>{p.match_level === 'exact' ? '정합' : '부분정합'}</td>
                  <td>{p.experience === 'high' ? '고' : p.experience === 'medium' ? '중' : '저'}</td>
                  <td>{p.n_evaluations}</td>
                  <td>{p.mean_total.toFixed(1)}</td>
                  <td>{(p.approval_rate * 100).toFixed(0)}%</td>
                  <td>{p.avg_confidence.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
};

const CorrelationTab: React.FC<{ data: any }> = ({ data }) => {
  if (data.error) return <p>{data.error}</p>;

  const byYears = data.by_years || [];
  const byLevel = data.by_level || {};
  const rawScatter = data.raw_scatter || [];

  const levelData = Object.entries(byLevel).map(([level, stats]: [string, any]) => ({
    name: level === 'high' ? '고경력 (15~25년)' : level === 'medium' ? '중경력 (7~14년)' : '저경력 (3~6년)',
    avg_score: stats.avg_score,
    score_std: stats.score_std,
    approval_rate: stats.approval_rate * 100,
    avg_confidence: stats.avg_confidence,
    count: stats.count,
    avg_novelty: stats.avg_novelty,
    avg_progressiveness: stats.avg_progressiveness,
  }));

  return (
    <div>
      <div className="info-box">
        <strong>경력 상관관계:</strong> 근속연수가 채점에 미치는 영향을 분석합니다.
        고경력은 본질적 차별성에, 저경력은 형식적 완결성에 더 집중하는 경향을 확인합니다.
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{data.total_observations}</div>
          <div className="stat-label">총 관측 수</div>
        </div>
      </div>

      <h3>경력 수준별 평균 점수</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={levelData}>
          <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis domain={[0, 100]} />
          <Tooltip /><Legend />
          <Bar dataKey="avg_score" name="평균 총점" fill="#1a237e" />
          <Bar dataKey="avg_novelty" name="평균 신규성" fill="#4CAF50" />
          <Bar dataKey="avg_progressiveness" name="평균 진보성" fill="#2196F3" />
        </BarChart>
      </ResponsiveContainer>

      <h3>경력 수준별 승인율</h3>
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={levelData}>
          <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis />
          <Tooltip /><Legend />
          <Bar dataKey="approval_rate" name="승인율(%)" fill="#4CAF50" />
        </BarChart>
      </ResponsiveContainer>

      {byYears.length > 0 && (
        <>
          <h3>경력 연수별 평균 점수</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={byYears}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="years" label={{ value: '경력(년)', position: 'bottom' }} />
              <YAxis domain={[0, 100]} />
              <Tooltip /><Legend />
              <Bar dataKey="avg_score" name="평균 총점" fill="#1a237e" />
            </BarChart>
          </ResponsiveContainer>
        </>
      )}

      {rawScatter.length > 0 && (
        <>
          <h3>경력 연수 vs 총점 (전체 산점도)</h3>
          <ResponsiveContainer width="100%" height={350}>
            <ScatterChart>
              <CartesianGrid />
              <XAxis dataKey="x" name="경력(년)" type="number" />
              <YAxis dataKey="y" name="총점" domain={[0, 100]} />
              <Tooltip content={({ payload }: any) => {
                if (!payload || payload.length === 0) return null;
                const d = payload[0]?.payload;
                return (
                  <div style={{ background: 'white', padding: 8, border: '1px solid #ddd', borderRadius: 4, fontSize: 12 }}>
                    <p>경력: {d?.x}년 | 총점: {d?.y}</p>
                    <p>{d?.level === 'high' ? '고' : d?.level === 'medium' ? '중' : '저'}경력 | {d?.match === 'exact' ? '정합' : '부분정합'}</p>
                  </div>
                );
              }} />
              <Scatter data={rawScatter.filter((d: any) => d.verdict === 1)} fill="#4CAF50" name="승인" />
              <Scatter data={rawScatter.filter((d: any) => d.verdict === 0)} fill="#F44336" name="거절" />
              <Legend />
            </ScatterChart>
          </ResponsiveContainer>
        </>
      )}

      <h3>경력 수준별 상세 통계</h3>
      <table className="vote-table">
        <thead>
          <tr><th>경력 수준</th><th>관측 수</th><th>평균 총점</th><th>표준편차</th><th>신규성</th><th>진보성</th><th>승인율</th><th>확신도</th></tr>
        </thead>
        <tbody>
          {levelData.map(d => (
            <tr key={d.name}>
              <td>{d.name}</td>
              <td>{d.count}</td>
              <td>{d.avg_score.toFixed(1)}</td>
              <td>{d.score_std.toFixed(1)}</td>
              <td>{d.avg_novelty?.toFixed(1)}</td>
              <td>{d.avg_progressiveness?.toFixed(1)}</td>
              <td>{d.approval_rate.toFixed(0)}%</td>
              <td>{d.avg_confidence.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default AnalysisDashboard;
