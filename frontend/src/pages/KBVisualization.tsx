import React, { useEffect, useState } from 'react';
import { fetchKBDetail } from '../api/client';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  PieChart, Pie, Cell, ResponsiveContainer,
} from 'recharts';

const COLORS = ['#1a237e', '#4CAF50', '#FF9800', '#9C27B0', '#00BCD4', '#F44336', '#3F51B5', '#E91E63'];

const KBVisualization: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [expandedSource, setExpandedSource] = useState<string | null>(null);

  useEffect(() => {
    fetchKBDetail()
      .then(res => setData(res.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading">KB 데이터 로딩 중...</div>;
  if (!data) return <div className="loading">KB 데이터 없음</div>;

  const sources = data.sources || {};
  const sourceList = Object.entries(sources).map(([key, val]: [string, any]) => ({
    key,
    label: val.label,
    total: val.total,
    by_category: val.by_category || {},
    sample: val.sample,
  }));

  const totalDocs = sourceList.reduce((sum: number, s: any) => sum + s.total, 0);

  // 소스별 파이 차트 데이터
  const pieData = sourceList.map((s, i) => ({
    name: s.label,
    value: s.total,
    fill: COLORS[i % COLORS.length],
  }));

  return (
    <div className="kb-viz">
      <h1>지식베이스 구축 현황</h1>

      {/* 1. 전체 요약 */}
      <div className="stats-grid">
        <div className="stat-card bg-blue">
          <div className="stat-value">{totalDocs.toLocaleString()}</div>
          <div className="stat-label">총 원본 문서</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{data.vector_db?.total_docs?.toLocaleString() || 0}</div>
          <div className="stat-label">벡터 인덱싱</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{data.embedding?.dimensions || 1024}</div>
          <div className="stat-label">임베딩 차원</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{data.vector_db?.exists ? '활성' : '미구축'}</div>
          <div className="stat-label">벡터 DB 상태</div>
        </div>
      </div>

      {/* 2. 데이터 소스 구성 */}
      <div className="section-row">
        <div className="chart-section" style={{ flex: 1 }}>
          <h2>데이터 소스 구성</h2>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie data={pieData} cx="50%" cy="50%" innerRadius={60} outerRadius={120}
                   dataKey="value" label={({ name, value }: any) => `${name}: ${value}`}>
                {pieData.map((entry, i) => (
                  <Cell key={i} fill={entry.fill} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="chart-section" style={{ flex: 1 }}>
          <h2>소스별 문서 수</h2>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={sourceList.map(s => ({ name: s.label.split(' ')[0], count: s.total }))}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="count" name="문서 수" fill="#1a237e" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 3. 전처리 및 임베딩 파이프라인 */}
      <div className="chart-section">
        <h2>전처리 및 임베딩 파이프라인</h2>
        <div className="pipeline-steps">
          {(data.preprocessing?.steps || []).map((step: string, i: number) => (
            <React.Fragment key={i}>
              <div className="pipeline-step">
                <div className="step-number">{i + 1}</div>
                <div className="step-text">{step}</div>
              </div>
              {i < (data.preprocessing?.steps?.length || 0) - 1 && (
                <div className="step-arrow">→</div>
              )}
            </React.Fragment>
          ))}
        </div>
        <div className="info-box" style={{ marginTop: 16 }}>
          <strong>임베딩 모델:</strong> {data.embedding?.model} ({data.embedding?.provider})
          <br />
          <strong>차원:</strong> {data.embedding?.dimensions}차원 벡터
          <br />
          <strong>벡터 DB:</strong> LanceDB ({data.vector_db?.total_docs?.toLocaleString()}건 인덱싱)
        </div>
      </div>

      {/* 4. 에이전트별 KB 구조 */}
      <div className="chart-section">
        <h2>에이전트별 KB 구성 (PIKE-RAG 계층 구조)</h2>
        <div className="kb-hierarchy">
          <div className="kb-level kb-level-1">
            <div className="kb-level-header">
              <span className="kb-badge">Level 1</span> 공통 지식 (Shared)
            </div>
            <div className="kb-level-body">
              {data.agent_kb_structure?.level_1_shared}
            </div>
          </div>
          <div className="kb-level kb-level-2">
            <div className="kb-level-header">
              <span className="kb-badge">Level 2</span> 분야별 지식 (Field-Specific)
            </div>
            <div className="kb-level-body">
              {data.agent_kb_structure?.level_2_field}
            </div>
          </div>
          <div className="kb-level kb-level-3">
            <div className="kb-level-header">
              <span className="kb-badge">Level 3</span> 경력별 행동 특성 (Experience-Based)
            </div>
            <div className="kb-level-body">
              {data.agent_kb_structure?.level_3_experience}
            </div>
          </div>
        </div>
        <div className="info-box" style={{ marginTop: 16 }}>
          <strong>독립성:</strong> {data.agent_kb_structure?.independence}
        </div>
      </div>

      {/* 5. 소스별 상세 */}
      <h2>데이터 소스 상세</h2>
      {sourceList.map(s => (
        <div key={s.key} className="chart-section" style={{ cursor: 'pointer' }}
             onClick={() => setExpandedSource(expandedSource === s.key ? null : s.key)}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0 }}>{s.label}</h3>
            <span className="stat-value" style={{ fontSize: 18 }}>{s.total.toLocaleString()}건</span>
          </div>
          {expandedSource === s.key && (
            <div style={{ marginTop: 16 }}>
              {Object.keys(s.by_category).length > 0 && (
                <>
                  <h4>분류별 분포</h4>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={Object.entries(s.by_category).map(([k, v]) => ({ name: k, count: v as number }))}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="count" fill="#4CAF50" />
                    </BarChart>
                  </ResponsiveContainer>
                </>
              )}
              {s.sample && (
                <>
                  <h4>샘플 문서 구조</h4>
                  <pre className="code-block">
                    {JSON.stringify(s.sample, null, 2)}
                  </pre>
                </>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

export default KBVisualization;
