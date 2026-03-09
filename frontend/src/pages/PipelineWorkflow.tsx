import React, { useEffect, useState } from 'react';
import { fetchPipelineWorkflow, fetchResults } from '../api/client';

interface WorkflowNode {
  id: string;
  label: string;
  type: string;
  detail: string;
}

interface WorkflowEdge {
  from: string;
  to: string;
}

const NODE_COLORS: Record<string, string> = {
  input: '#4CAF50',
  output: '#F44336',
  process: '#2196F3',
  llm: '#FF9800',
};

const NODE_TYPE_LABELS: Record<string, string> = {
  input: '입력',
  output: '출력',
  process: '처리',
  llm: 'LLM',
};

// 노드 위치 (고정 레이아웃 — 위에서 아래, 좌우 분기)
const NODE_POSITIONS: Record<string, { x: number; y: number }> = {
  input:        { x: 320, y: 20 },
  classify:     { x: 120, y: 110 },
  prior_art:    { x: 520, y: 110 },
  panel_gen:    { x: 120, y: 200 },
  kb_assembly:  { x: 320, y: 290 },
  prompt_build: { x: 320, y: 380 },
  llm_call:     { x: 320, y: 470 },
  parse:        { x: 320, y: 560 },
  ensemble:     { x: 200, y: 650 },
  chairman:     { x: 440, y: 650 },
  output:       { x: 320, y: 740 },
};

const NODE_W = 180;
const NODE_H = 44;

// 직교 경로(꺾인 연결선) 생성
function makeOrthogonalPath(fromId: string, toId: string): string {
  const from = NODE_POSITIONS[fromId];
  const to = NODE_POSITIONS[toId];
  if (!from || !to) return '';

  const fCx = from.x + NODE_W / 2;
  const tCx = to.x + NODE_W / 2;
  const sy = from.y + NODE_H;
  const ey = to.y;

  // 수직 직선 (같은 열)
  if (Math.abs(fCx - tCx) < 10) {
    return `M${fCx},${sy} L${tCx},${ey}`;
  }

  // 꺾인 연결선: 아래로 내려간 후 수평 이동, 다시 아래로
  const midY = sy + (ey - sy) / 2;
  return `M${fCx},${sy} L${fCx},${midY} L${tCx},${midY} L${tCx},${ey}`;
}

const PipelineWorkflow: React.FC = () => {
  const [workflow, setWorkflow] = useState<any>(null);
  const [results, setResults] = useState<any[]>([]);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [showPrompt, setShowPrompt] = useState(false);
  const [selectedResult, setSelectedResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([fetchPipelineWorkflow(), fetchResults()])
      .then(([wf, res]) => {
        setWorkflow(wf.data);
        setResults(res.data.results || []);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading">파이프라인 로딩 중...</div>;
  if (!workflow) return <div className="loading">파이프라인 데이터 없음</div>;

  const nodes: WorkflowNode[] = workflow.nodes || [];
  const edges: WorkflowEdge[] = workflow.edges || [];
  const promptStructure = workflow.prompt_structure;
  const panelConfig = workflow.panel_config;

  const selectedNodeData = selectedNode ? nodes.find(n => n.id === selectedNode) : null;
  const selectedRun = selectedResult
    ? results.find((r: any) => r.run_id === selectedResult)
    : null;

  return (
    <div className="pipeline-page">
      <h1>평가 파이프라인 워크플로우</h1>

      {/* 실행 결과 선택 */}
      {results.length > 0 && (
        <div className="info-box">
          <strong>실행 결과 선택:</strong>{' '}
          <select value={selectedResult || ''} onChange={e => setSelectedResult(e.target.value || null)}
                  style={{ padding: '4px 8px', marginLeft: 8 }}>
            <option value="">-- 선택 --</option>
            {results.map((r: any) => (
              <option key={r.run_id} value={r.run_id}>
                {r.tech_number} - {r.tech_name?.substring(0, 30)} ({r.final_verdict === 'approved' ? '승인' : '거절'})
              </option>
            ))}
          </select>
          {selectedRun && (
            <span style={{ marginLeft: 16 }}>
              찬성률: {(selectedRun.approval_ratio * 100).toFixed(0)}% |
              평균: {selectedRun.avg_total?.toFixed(1)}/100 |
              패널: {selectedRun.panel_size}명 |
              {selectedRun.elapsed_seconds?.toFixed(1)}초
            </span>
          )}
        </div>
      )}

      {/* 워크플로우 시각화 */}
      <div className="chart-section">
        <h2>처리 흐름</h2>
        <div className="workflow-container" style={{ textAlign: 'center' }}>
          <svg viewBox="0 0 740 810" className="workflow-svg"
               style={{ maxWidth: 740, margin: '0 auto', display: 'block' }}>
            <defs>
              <marker id="arrow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                <polygon points="0 0, 8 3, 0 6" fill="#78909C" />
              </marker>
            </defs>

            {/* 직교 꺾인 연결선 */}
            {edges.map((edge, i) => {
              const path = makeOrthogonalPath(edge.from, edge.to);
              if (!path) return null;
              return (
                <path key={i} d={path}
                      fill="none" stroke="#B0BEC5" strokeWidth={2}
                      markerEnd="url(#arrow)" />
              );
            })}

            {/* 노드 */}
            {nodes.map(node => {
              const pos = NODE_POSITIONS[node.id];
              if (!pos) return null;
              const color = NODE_COLORS[node.type] || '#666';
              const isSelected = selectedNode === node.id;
              return (
                <g key={node.id} onClick={() => setSelectedNode(isSelected ? null : node.id)}
                   style={{ cursor: 'pointer' }}>
                  <rect x={pos.x} y={pos.y} width={NODE_W} height={NODE_H} rx={8}
                        fill={isSelected ? color : 'white'}
                        stroke={color} strokeWidth={isSelected ? 3 : 2} />
                  <text x={pos.x + NODE_W / 2} y={pos.y + NODE_H / 2 + 1}
                        textAnchor="middle" dominantBaseline="middle"
                        fill={isSelected ? 'white' : '#333'} fontSize={12} fontWeight={600}>
                    {node.label.length > 20 ? node.label.substring(0, 20) + '...' : node.label}
                  </text>
                  {/* 타입 뱃지 */}
                  <rect x={pos.x + NODE_W - 32} y={pos.y - 8} width={32} height={16} rx={8}
                        fill={color} />
                  <text x={pos.x + NODE_W - 16} y={pos.y + 1}
                        textAnchor="middle" dominantBaseline="middle"
                        fill="white" fontSize={8} fontWeight={700}>
                    {NODE_TYPE_LABELS[node.type] || node.type}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      </div>

      {/* 선택된 노드 상세 */}
      {selectedNodeData && (
        <div className="chart-section">
          <h2>{selectedNodeData.label}</h2>
          <div className="node-detail-grid">
            <div className="info-box">
              <strong>유형:</strong> {NODE_TYPE_LABELS[selectedNodeData.type] || selectedNodeData.type}
            </div>
            <div className="info-box">
              <strong>설명:</strong> {selectedNodeData.detail}
            </div>
          </div>

          {selectedNodeData.id === 'panel_gen' && panelConfig && (
            <div className="panel-config-grid">
              <div className="stat-card">
                <div className="stat-value">{panelConfig.size_range[0]}~{panelConfig.size_range[1]}명</div>
                <div className="stat-label">패널 규모</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{(panelConfig.exact_match_ratio * 100).toFixed(0)}%</div>
                <div className="stat-label">정합 비율</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{(panelConfig.quorum_threshold * 100).toFixed(0)}%</div>
                <div className="stat-label">정족수 기준</div>
              </div>
            </div>
          )}

          {selectedNodeData.id === 'classify' && (
            <div className="info-box">
              <strong>분류 체계:</strong> 대분류(건축/토목/기계설비) → 중분류 → 소분류
              <br/>
              <strong>에이전트 전문분야:</strong> 입력 제안기술의 tech_field 값에서 자동 매핑
              <br/>
              <strong>근속연수:</strong> 경력 범위(고: 15~25, 중: 7~14, 저: 3~6) 내 랜덤 생성
            </div>
          )}
        </div>
      )}

      {/* 프롬프트 구조 */}
      <div className="chart-section">
        <h2 onClick={() => setShowPrompt(!showPrompt)} style={{ cursor: 'pointer' }}>
          프롬프트 구조 {showPrompt ? '▼' : '▶'}
        </h2>
        {showPrompt && promptStructure && (
          <div className="prompt-structure">
            <div className="prompt-section">
              <h3>시스템 프롬프트</h3>
              <p>{promptStructure.system.description}</p>
              <pre className="code-block">{promptStructure.system.template}</pre>
            </div>
            <div className="prompt-section">
              <h3>유저 프롬프트 구성</h3>
              {promptStructure.user_sections.map((sec: any, i: number) => (
                <div key={i} className="info-box" style={{ marginBottom: 8 }}>
                  <strong>{i + 1}. {sec.name}:</strong> {sec.description}
                </div>
              ))}
            </div>
            <div className="prompt-section">
              <h3>출력 형식</h3>
              <pre className="code-block">
                {JSON.stringify(promptStructure.output_format, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </div>

      {/* 패널 구성 규칙 */}
      {panelConfig && (
        <div className="chart-section">
          <h2>패널 구성 규칙</h2>
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-value">{panelConfig.size_range[0]}~{panelConfig.size_range[1]}</div>
              <div className="stat-label">패널 규모 (명)</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{(panelConfig.exact_match_ratio * 100).toFixed(0)}%/{((1 - panelConfig.exact_match_ratio) * 100).toFixed(0)}%</div>
              <div className="stat-label">정합/부분정합 비율</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{(panelConfig.quorum_threshold * 100).toFixed(0)}%</div>
              <div className="stat-label">정족수 기준</div>
            </div>
          </div>
          <div className="exp-dist">
            <h3>경력 분포</h3>
            <div className="stats-grid">
              {Object.entries(panelConfig.experience_distribution).map(([level, ratio]) => (
                <div key={level} className="stat-card">
                  <div className="stat-value">{((ratio as number) * 100).toFixed(0)}%</div>
                  <div className="stat-label">
                    {level === 'high' ? '고경력' : level === 'medium' ? '중경력' : '저경력'}
                    ({(panelConfig.experience_years as any)[level]})
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PipelineWorkflow;
