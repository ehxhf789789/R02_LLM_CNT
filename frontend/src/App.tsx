import React, { useState, useEffect } from 'react';
import Dashboard from './pages/Dashboard';
import ResultDetail from './pages/ResultDetail';
import AnalysisDashboard from './pages/AnalysisDashboard';
import KBVisualization from './pages/KBVisualization';
import PipelineWorkflow from './pages/PipelineWorkflow';
import ExperimentControl from './pages/ExperimentControl';
import Settings from './pages/Settings';
import { fetchAllEvalStatus } from './api/client';
import './App.css';

type Page = 'dashboard' | 'result' | 'analysis' | 'kb' | 'pipeline' | 'experiment' | 'settings';

const App: React.FC = () => {
  const [page, setPage] = useState<Page>('dashboard');
  const [selectedRunId, setSelectedRunId] = useState<string>('');

  // 실험 실행 상태를 App 레벨에서 관리 (탭 전환해도 유지)
  const [runningJobs, setRunningJobs] = useState<any[]>([]);

  useEffect(() => {
    const handleHash = () => {
      const hash = window.location.hash;
      if (hash.startsWith('#/result/')) {
        setSelectedRunId(hash.replace('#/result/', ''));
        setPage('result');
      } else if (hash === '#/analysis') {
        setPage('analysis');
      } else if (hash === '#/kb') {
        setPage('kb');
      } else if (hash === '#/pipeline') {
        setPage('pipeline');
      } else if (hash === '#/experiment') {
        setPage('experiment');
      } else if (hash === '#/settings') {
        setPage('settings');
      } else {
        setPage('dashboard');
      }
    };

    window.addEventListener('hashchange', handleHash);
    handleHash();
    return () => window.removeEventListener('hashchange', handleHash);
  }, []);

  // 백그라운드 폴링: 실행 중인 작업이 있으면 어떤 탭에서든 계속 추적
  useEffect(() => {
    if (runningJobs.length === 0) return;
    const interval = setInterval(() => {
      fetchAllEvalStatus()
        .then(res => {
          const evals = res.data.evaluations || [];
          const stillRunning = evals.filter((e: any) => e.status === 'running');
          setRunningJobs(stillRunning);
        })
        .catch(console.error);
    }, 3000);
    return () => clearInterval(interval);
  }, [runningJobs.length]);

  const hasRunning = runningJobs.length > 0;

  return (
    <div className="app">
      <nav className="nav-bar">
        <div className="nav-title" onClick={() => { window.location.hash = '#/'; }}>
          CNT 평가 시스템
        </div>
        <div className="nav-links">
          <a href="#/" className={page === 'dashboard' ? 'active' : ''}>대시보드</a>
          <a href="#/pipeline" className={page === 'pipeline' ? 'active' : ''}>파이프라인</a>
          <a href="#/kb" className={page === 'kb' ? 'active' : ''}>지식베이스</a>
          <a href="#/analysis" className={page === 'analysis' ? 'active' : ''}>검증분석</a>
          <a href="#/experiment" className={page === 'experiment' ? 'active' : ''}>
            실험실행{hasRunning && <span className="running-badge">{runningJobs.length}</span>}
          </a>
          <a href="#/settings" className={page === 'settings' ? 'active' : ''}>설정</a>
        </div>
      </nav>

      <main className="main-content">
        {page === 'dashboard' && <Dashboard />}
        {page === 'result' && selectedRunId && <ResultDetail runId={selectedRunId} />}
        {page === 'analysis' && <AnalysisDashboard />}
        {page === 'kb' && <KBVisualization />}
        {page === 'pipeline' && <PipelineWorkflow />}
        {page === 'experiment' && (
          <ExperimentControl
            runningJobs={runningJobs}
            setRunningJobs={setRunningJobs}
          />
        )}
        {page === 'settings' && <Settings />}
      </main>
    </div>
  );
};

export default App;
