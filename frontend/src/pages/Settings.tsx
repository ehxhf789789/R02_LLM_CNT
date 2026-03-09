import React, { useEffect, useState } from 'react';
import { fetchSettings, updateSettings, testBedrockConnection } from '../api/client';

const BEDROCK_MODELS = [
  { id: 'us.anthropic.claude-sonnet-4-6-20250514-v1:0', label: 'Claude Sonnet 4.6 (us cross-region)' },
  { id: 'us.anthropic.claude-haiku-4-5-20251001-v1:0', label: 'Claude Haiku 4.5 (us cross-region)' },
  { id: 'us.anthropic.claude-opus-4-6-20250612-v1:0', label: 'Claude Opus 4.6 (us cross-region)' },
  { id: 'anthropic.claude-sonnet-4-6-20250514-v1:0', label: 'Claude Sonnet 4.6' },
  { id: 'anthropic.claude-haiku-4-5-20251001-v1:0', label: 'Claude Haiku 4.5' },
  { id: 'us.meta.llama3-3-70b-instruct-v1:0', label: 'Llama 3.3 70B (us cross-region)' },
  { id: 'us.amazon.nova-pro-v1:0', label: 'Amazon Nova Pro (us cross-region)' },
];

const Settings: React.FC = () => {
  const [current, setCurrent] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  // Form fields
  const [accessKey, setAccessKey] = useState('');
  const [secretKey, setSecretKey] = useState('');
  const [region, setRegion] = useState('');
  const [modelId, setModelId] = useState('');
  const [minPanel, setMinPanel] = useState(10);
  const [maxPanel, setMaxPanel] = useState(15);
  const [quorum, setQuorum] = useState(0.667);

  useEffect(() => {
    fetchSettings()
      .then(res => {
        const s = res.data;
        setCurrent(s);
        setRegion(s.aws_default_region || '');
        setModelId(s.bedrock_model_id || '');
        setMinPanel(s.min_panel_size || 10);
        setMaxPanel(s.max_panel_size || 15);
        setQuorum(s.quorum_threshold || 0.667);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaveMsg('');
    try {
      const updates: any = {};
      if (accessKey) updates.aws_access_key_id = accessKey;
      if (secretKey) updates.aws_secret_access_key = secretKey;
      if (region !== current?.aws_default_region) updates.aws_default_region = region;
      if (modelId !== current?.bedrock_model_id) updates.bedrock_model_id = modelId;
      if (minPanel !== current?.min_panel_size) updates.min_panel_size = minPanel;
      if (maxPanel !== current?.max_panel_size) updates.max_panel_size = maxPanel;
      if (quorum !== current?.quorum_threshold) updates.quorum_threshold = quorum;

      if (Object.keys(updates).length === 0) {
        setSaveMsg('변경 사항 없음');
        return;
      }

      const res = await updateSettings(updates);
      setSaveMsg(`저장 완료: ${res.data.updated_fields.join(', ')}`);
      setAccessKey('');
      setSecretKey('');
      // Reload current settings
      const refreshed = await fetchSettings();
      setCurrent(refreshed.data);
    } catch (e: any) {
      setSaveMsg('저장 실패: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await testBedrockConnection();
      setTestResult(res.data);
    } catch (e: any) {
      setTestResult({ status: 'error', error: e.message });
    } finally {
      setTesting(false);
    }
  };

  if (loading) return <div className="loading">로딩 중...</div>;

  return (
    <div className="settings-page">
      <h1>시스템 설정</h1>

      {/* AWS Bedrock 자격증명 */}
      <div className="chart-section" style={{ borderLeft: '4px solid #1a237e' }}>
        <h2>AWS Bedrock 자격증명</h2>
        <div className="experiment-config">
          <div className="config-row">
            <label>Access Key ID:</label>
            <input
              type="text"
              value={accessKey}
              onChange={e => setAccessKey(e.target.value)}
              placeholder={current?.aws_access_key_id || '미설정'}
              style={{ width: 300 }}
            />
            <span className="hint">현재: {current?.aws_access_key_id}</span>
          </div>
          <div className="config-row">
            <label>Secret Access Key:</label>
            <input
              type="password"
              value={secretKey}
              onChange={e => setSecretKey(e.target.value)}
              placeholder={current?.aws_secret_access_key || '미설정'}
              style={{ width: 300 }}
            />
            <span className="hint">현재: {current?.aws_secret_access_key}</span>
          </div>
          <div className="config-row">
            <label>Region:</label>
            <select value={region} onChange={e => setRegion(e.target.value)} style={{ width: 200 }}>
              <option value="us-east-1">us-east-1</option>
              <option value="us-west-2">us-west-2</option>
              <option value="ap-northeast-1">ap-northeast-1</option>
              <option value="ap-northeast-2">ap-northeast-2</option>
              <option value="eu-west-1">eu-west-1</option>
            </select>
          </div>
          <div className="config-row">
            <label>LLM Model ID:</label>
            <select value={modelId} onChange={e => setModelId(e.target.value)} style={{ width: 420, padding: '6px 8px' }}>
              {BEDROCK_MODELS.map(m => (
                <option key={m.id} value={m.id}>{m.label}</option>
              ))}
              {!BEDROCK_MODELS.some(m => m.id === modelId) && modelId && (
                <option value={modelId}>{modelId} (사용자 지정)</option>
              )}
            </select>
            <span className="hint" style={{ fontSize: 11 }}>{modelId}</span>
          </div>
          <div style={{ marginTop: 12, display: 'flex', gap: 12 }}>
            <button className="btn btn-primary" onClick={handleTest} disabled={testing}>
              {testing ? '테스트 중...' : '연결 테스트'}
            </button>
          </div>
          {testResult && (
            <div className={`info-box ${testResult.status === 'success' ? '' : 'error-box'}`}
                 style={{ marginTop: 8, borderLeft: `4px solid ${testResult.status === 'success' ? '#4caf50' : '#f44336'}` }}>
              <strong>{testResult.status === 'success' ? '연결 성공' : '연결 실패'}</strong>
              {testResult.status === 'success' && <span> — 응답: "{testResult.response}"</span>}
              {testResult.error && <div style={{ color: '#f44336', fontSize: 13, marginTop: 4 }}>{testResult.error}</div>}
              <div style={{ fontSize: 12, color: '#666' }}>모델: {testResult.model}</div>
            </div>
          )}
        </div>
      </div>

      {/* 평가 설정 */}
      <div className="chart-section">
        <h2>평가 패널 설정</h2>
        <div className="experiment-config">
          <div className="config-row">
            <label>최소 패널 인원:</label>
            <input type="number" value={minPanel} onChange={e => setMinPanel(parseInt(e.target.value) || 10)}
                   min={5} max={20} style={{ width: 80 }} />
          </div>
          <div className="config-row">
            <label>최대 패널 인원:</label>
            <input type="number" value={maxPanel} onChange={e => setMaxPanel(parseInt(e.target.value) || 15)}
                   min={5} max={30} style={{ width: 80 }} />
          </div>
          <div className="config-row">
            <label>의결 정족수 비율:</label>
            <input type="number" value={quorum} onChange={e => setQuorum(parseFloat(e.target.value) || 0.667)}
                   min={0.5} max={1.0} step={0.01} style={{ width: 100 }} />
            <span className="hint">2/3 = 0.667</span>
          </div>
        </div>
      </div>

      {/* 현재 경로 정보 */}
      <div className="chart-section">
        <h2>데이터 경로</h2>
        <div className="info-box">
          <div><strong>데이터 디렉토리:</strong> {current?.data_dir}</div>
          <div><strong>임베딩 모델:</strong> {current?.bedrock_embedding_model_id}</div>
          <div><strong>정합 비율:</strong> {((current?.exact_match_ratio || 0) * 100).toFixed(0)}%</div>
        </div>
      </div>

      {/* 저장 */}
      <div style={{ marginTop: 16, display: 'flex', gap: 12, alignItems: 'center' }}>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? '저장 중...' : '설정 저장'}
        </button>
        {saveMsg && <span style={{ color: saveMsg.includes('실패') ? '#f44336' : '#4caf50' }}>{saveMsg}</span>}
      </div>
    </div>
  );
};

export default Settings;
