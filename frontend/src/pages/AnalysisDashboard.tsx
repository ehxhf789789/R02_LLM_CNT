import React, { useEffect, useState } from 'react';
import {
  fetchAccuracyAnalysis,
  fetchConsistencyAnalysis,
  fetchScorePatternAnalysis,
  fetchExperienceCorrelation,
  fetchSensitivityAnalysis,
} from '../api/client';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  ScatterChart, Scatter, Cell,
  ResponsiveContainer,
} from 'recharts';
// @ts-ignore - ReferenceLine exists in recharts v3 but types may lag
import { ReferenceLine } from 'recharts';

type TabKey = 'accuracy' | 'consistency' | 'patterns' | 'sensitivity' | 'correlation';

const AnalysisDashboard: React.FC = () => {
  const [tab, setTab] = useState<TabKey>('accuracy');
  const [accuracy, setAccuracy] = useState<any>(null);
  const [consistency, setConsistency] = useState<any>(null);
  const [patterns, setPatterns] = useState<any>(null);
  const [correlation, setCorrelation] = useState<any>(null);
  const [sensitivity, setSensitivity] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchAccuracyAnalysis().catch(() => ({ data: {} })),
      fetchConsistencyAnalysis().catch(() => ({ data: {} })),
      fetchScorePatternAnalysis().catch(() => ({ data: {} })),
      fetchExperienceCorrelation().catch(() => ({ data: {} })),
      fetchSensitivityAnalysis().catch(() => ({ data: {} })),
    ])
      .then(([a, c, p, e, s]) => {
        setAccuracy(a.data);
        setConsistency(c.data);
        setPatterns(p.data);
        setCorrelation(e.data);
        setSensitivity(s.data);
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
        <button className={tab === 'sensitivity' ? 'active' : ''} onClick={() => setTab('sensitivity')}>
          검증4: 민감도
        </button>
        <button className={tab === 'correlation' ? 'active' : ''} onClick={() => setTab('correlation')}>
          경력 상관관계
        </button>
      </div>

      {tab === 'accuracy' && accuracy && <AccuracyTab data={accuracy} />}
      {tab === 'consistency' && consistency && <ConsistencyTab data={consistency} />}
      {tab === 'patterns' && patterns && <PatternsTab data={patterns} />}
      {tab === 'sensitivity' && <SensitivityTab data={sensitivity} />}
      {tab === 'correlation' && correlation && <CorrelationTab data={correlation} />}
    </div>
  );
};

/* ─── 검증1: 정확도 (2018+ 기술) ─── */
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
        <strong>검증1 (정확도 8-1):</strong> 2018년 이후 지정 기술 대상. 이미 통과된 기술이므로 '승인' 판정이 정확합니다.
        {data.filter && <span style={{ marginLeft: 8, color: '#666' }}>필터: {data.filter}</span>}
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
        <div className="stat-card">
          <div className="stat-value">
            {data.case_results.filter((c: any) => c.is_correct).length}
          </div>
          <div className="stat-label">정확 판정</div>
        </div>
      </div>

      <h3>건별 찬성률</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={caseData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" />
          <YAxis domain={[0, 100]} />
          <Tooltip />
          <ReferenceLine y={66.7} stroke="#ff5722" strokeDasharray="5 5" label="2/3 정족수" />
          <Bar dataKey="approval_ratio" name="찬성률(%)">
            {caseData.map((entry: any, i: number) => (
              <Cell key={i} fill={entry.approval_ratio >= 66.7 ? '#4CAF50' : '#F44336'} />
            ))}
          </Bar>
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

/* ─── 검증2: 일관성 ─── */
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
        <strong>검증2 (일관성 8-2):</strong> 전체 263건 대상. 동일 입력에 대해 반복 실행 시 평가 결과의 안정성을 측정합니다.
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

/* ─── 검증3: 패턴분석 ─── */
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
        <strong>검증3 (패턴분석 8-3):</strong> 전체 투표 대상. 에이전트들의 채점 패턴을 분석합니다.
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
              <ReferenceLine y={0} stroke="#999" />
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

/* ─── 검증4: 커트오프 민감도 ─── */
const SensitivityTab: React.FC<{ data: any }> = ({ data }) => {
  if (!data || data.error) {
    return (
      <div>
        <div className="info-box">
          <strong>검증4 (민감도 8-4):</strong> 2013-2017년 지정 기술에 대해 시간적 커트오프 적용/미적용 결과를 비교합니다.
        </div>
        <div className="chart-section" style={{ textAlign: 'center', padding: 40 }}>
          <p style={{ fontSize: 16, color: '#666' }}>
            민감도 분석 데이터가 없습니다.
          </p>
          <p style={{ color: '#999' }}>
            실험 스크립트에서 <code>--phase sensitivity</code>를 실행하여 커트오프 미적용 평가를 추가 실행하세요.
          </p>
        </div>
      </div>
    );
  }

  const vc = data.verdict_comparison || {};
  const sc = data.score_comparison || {};
  const pfs = data.per_field_sensitivity || {};
  const kbc = data.kb_coverage_correlation || {};
  const summary = data.summary || {};

  const perTechData = (sc.per_tech_diffs || []).map((d: any) => ({
    name: d.tech_number,
    cutoff: d.cutoff_total,
    nocutoff: d.nocutoff_total,
    diff: d.diff,
  }));

  const FIELD_LABELS = ['차별성', '독창성', '품질향상', '개발정도', '안전성', '친환경성'];
  const fieldData = FIELD_LABELS
    .filter(label => pfs[label] && typeof pfs[label].mean_diff === 'number')
    .map(label => ({
      name: label,
      mean_diff: pfs[label].mean_diff,
      sensitive: pfs[label].sensitive,
      p_value: pfs[label].p_value,
    }));

  const corrData = (kbc.data_points || []).map((d: any) => ({
    x: d.year,
    y: d.score_diff,
  }));

  return (
    <div>
      <div className="info-box">
        <strong>검증4 (민감도 8-4):</strong> 2013-2017년 지정 기술({data.n_pairs}건)에 대해
        시간적 커트오프 적용 vs 미적용 결과를 비교하여 KB 풍부도가 평가에 미치는 영향을 측정합니다.
      </div>

      {/* 핵심 지표 */}
      <div className="stats-grid">
        <div className="stat-card" style={{ borderLeft: `4px solid ${vc.verdict_match_rate >= 0.9 ? '#4CAF50' : vc.verdict_match_rate >= 0.7 ? '#FF9800' : '#F44336'}` }}>
          <div className="stat-value">{((vc.verdict_match_rate || 0) * 100).toFixed(1)}%</div>
          <div className="stat-label">의결 일치율</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{(sc.mean_score_diff || 0) >= 0 ? '+' : ''}{(sc.mean_score_diff || 0).toFixed(1)}</div>
          <div className="stat-label">평균 점수 차이</div>
        </div>
        <div className="stat-card" style={{ borderLeft: `4px solid ${sc.significant_at_005 ? '#F44336' : '#4CAF50'}` }}>
          <div className="stat-value">p={(sc.paired_p_value || 1).toFixed(3)}</div>
          <div className="stat-label">통계적 유의성</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{data.n_pairs}</div>
          <div className="stat-label">비교 쌍 수</div>
        </div>
      </div>

      {/* 의결 변동 */}
      <div className="chart-section">
        <h3>의결 변동 분석</h3>
        <div className="info-box" style={{
          background: vc.verdict_match_rate >= 0.9 ? '#e8f5e9' : vc.verdict_match_rate >= 0.7 ? '#fff3e0' : '#ffebee'
        }}>
          {vc.interpretation}
        </div>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 12 }}>
          <div className="case-box" style={{ flex: 1 }}>
            <strong>일치</strong>: {vc.verdict_match}건 ({((vc.verdict_match_rate || 0) * 100).toFixed(0)}%)
          </div>
          <div className="case-box" style={{ flex: 1 }}>
            <strong>커트오프시 거절 → 전체KB시 승인</strong>: {vc.cutoff_rejected_to_nocutoff_approved}건
            {vc.cutoff_rejected_to_nocutoff_approved > 0 && (
              <span style={{ color: '#FF9800', marginLeft: 8 }}>KB 부족 영향</span>
            )}
          </div>
          <div className="case-box" style={{ flex: 1 }}>
            <strong>커트오프시 승인 → 전체KB시 거절</strong>: {vc.cutoff_approved_to_nocutoff_rejected}건
          </div>
        </div>
      </div>

      {/* 기술별 점수 비교 */}
      {perTechData.length > 0 && (
        <div className="chart-section">
          <h3>기술별 점수 비교 (커트오프 적용 vs 미적용)</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={perTechData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis domain={[0, 100]} />
              <Tooltip /><Legend />
              <Bar dataKey="cutoff" name="커트오프 적용" fill="#2196F3" />
              <Bar dataKey="nocutoff" name="커트오프 미적용 (전체KB)" fill="#FF9800" />
            </BarChart>
          </ResponsiveContainer>

          <h3>기술별 점수 변동량</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={perTechData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <ReferenceLine y={0} stroke="#999" />
              <Bar dataKey="diff" name="점수차 (전체KB - 커트오프)">
                {perTechData.map((entry: any, i: number) => (
                  <Cell key={i} fill={entry.diff >= 0 ? '#4CAF50' : '#F44336'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* 세부항목별 민감도 */}
      {fieldData.length > 0 && (
        <div className="chart-section">
          <h3>세부 항목별 민감도</h3>
          <p style={{ color: '#666', fontSize: 13 }}>
            양수: 전체 KB 사용 시 점수 상승 | 음수: 하락 | 빨간색: 통계적으로 유의미 (p&lt;0.05)
          </p>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={fieldData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip formatter={(value: number) => [value.toFixed(2), '평균 차이']} />
              <ReferenceLine y={0} stroke="#999" />
              <Bar dataKey="mean_diff" name="평균 점수 차이">
                {fieldData.map((entry: any, i: number) => (
                  <Cell key={i} fill={entry.sensitive ? '#F44336' : '#90CAF9'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>

          {summary.sensitive_fields && summary.sensitive_fields.length > 0 && (
            <div className="info-box" style={{ background: '#ffebee' }}>
              <strong>KB 부족에 취약한 항목:</strong> {summary.sensitive_fields.join(', ')}
            </div>
          )}
        </div>
      )}

      {/* KB 커버리지 상관 */}
      {corrData.length >= 3 && (
        <div className="chart-section">
          <h3>지정연도 vs 점수 변동 (KB 풍부도 영향)</h3>
          <p style={{ color: '#666', fontSize: 13 }}>
            Pearson r = {kbc.pearson_r?.toFixed(3)} (p = {kbc.p_value?.toFixed(3)})
            {kbc.significant_at_005 ? ' — 유의미' : ' — 유의미하지 않음'}
          </p>
          <ResponsiveContainer width="100%" height={300}>
            <ScatterChart>
              <CartesianGrid />
              <XAxis dataKey="x" name="지정연도" type="number" domain={['dataMin - 1', 'dataMax + 1']} />
              <YAxis dataKey="y" name="점수차이" />
              <Tooltip />
              <ReferenceLine y={0} stroke="#999" strokeDasharray="5 5" />
              <Scatter data={corrData} fill="#2196F3" />
            </ScatterChart>
          </ResponsiveContainer>
          <div className="info-box">{kbc.interpretation}</div>
        </div>
      )}

      {/* 종합 권고 */}
      <div className="chart-section" style={{ borderLeft: '4px solid #1a237e' }}>
        <h3>종합 분석 및 권고</h3>
        <table className="vote-table">
          <tbody>
            <tr><td style={{ fontWeight: 'bold', width: 150 }}>의결 안정성</td><td>{((summary.verdict_stability || 0) * 100).toFixed(1)}%</td></tr>
            <tr><td style={{ fontWeight: 'bold' }}>평균 점수 영향</td><td>{(summary.mean_score_impact || 0) >= 0 ? '+' : ''}{(summary.mean_score_impact || 0).toFixed(1)}점</td></tr>
            <tr><td style={{ fontWeight: 'bold' }}>통계적 유의성</td><td>{summary.score_impact_significant ? '유의미 (p < 0.05)' : '유의미하지 않음'}</td></tr>
            <tr><td style={{ fontWeight: 'bold' }}>KB 풍부도 효과</td><td>{summary.kb_coverage_effect || '-'}</td></tr>
          </tbody>
        </table>
        <div className="info-box" style={{ marginTop: 12, background: '#e3f2fd' }}>
          <strong>권고:</strong> {summary.recommendation}
        </div>
      </div>
    </div>
  );
};

/* ─── 경력 상관관계 ─── */
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

      {rawScatter.length > 0 && (
        <>
          <h3>경력 연수 vs 총점 (산점도)</h3>
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
