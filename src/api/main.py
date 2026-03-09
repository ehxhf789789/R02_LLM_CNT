"""FastAPI 백엔드.

건설신기술 평가 시스템의 REST API를 제공한다.

엔드포인트:
  - POST /api/evaluate: 단일 기술 평가 실행
  - POST /api/evaluate/batch: 배치 평가 실행
  - GET  /api/results: 평가 결과 목록
  - GET  /api/results/{run_id}: 개별 결과 상세
  - GET  /api/analysis/accuracy: 정확도 분석
  - GET  /api/analysis/consistency: 일관성 분석
  - GET  /api/analysis/score-patterns: 점수 패턴 분석
  - GET  /api/proposals: 제안기술 목록
  - GET  /api/kb/status: KB 상태
"""

from __future__ import annotations

import json
import logging
import statistics
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config.settings import settings

logger = logging.getLogger(__name__)

app = FastAPI(
    title="건설신기술 LLM 평가 시스템",
    description="LLM 기반 건설신기술 1차 평가 프레임워크",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request/Response Models ---

class EvaluateRequest(BaseModel):
    tech_number: str
    seed: int | None = None
    skip_chairman: bool = False


class BatchEvaluateRequest(BaseModel):
    tech_numbers: list[str]
    repetitions: int = 1
    seed: int | None = None


# --- Endpoints ---

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/evaluate")
async def evaluate_single(req: EvaluateRequest, bg: BackgroundTasks):
    """단일 기술 평가 실행 (백그라운드)."""
    from src.pipeline.orchestrator import Orchestrator

    # proposal 로드
    proposal_path = settings.proposals_dir / f"proposal_{req.tech_number}.json"
    if not proposal_path.exists():
        raise HTTPException(404, f"제안기술 없음: {req.tech_number}")

    with open(proposal_path, encoding="utf-8") as f:
        proposal = json.load(f)

    run_id = f"run_{req.tech_number}_{hash(str(req.seed)) % 10000:04d}"

    bg.add_task(_run_evaluation, proposal, run_id, req.seed, req.skip_chairman)

    return {"run_id": run_id, "status": "started", "tech_number": req.tech_number}


@app.post("/api/evaluate/batch")
async def evaluate_batch(req: BatchEvaluateRequest, bg: BackgroundTasks):
    """배치 평가 실행 (백그라운드)."""
    run_ids = []

    for tech_num in req.tech_numbers:
        for rep in range(req.repetitions):
            seed = (req.seed or 0) + rep if req.seed is not None else None
            run_id = f"run_{tech_num}_{rep:03d}"
            run_ids.append(run_id)

            proposal_path = settings.proposals_dir / f"proposal_{tech_num}.json"
            if not proposal_path.exists():
                continue

            with open(proposal_path, encoding="utf-8") as f:
                proposal = json.load(f)

            bg.add_task(_run_evaluation, proposal, run_id, seed, False)

    return {"run_ids": run_ids, "status": "started", "count": len(run_ids)}


@app.get("/api/results")
def list_results():
    """평가 결과 목록."""
    results_dir = settings.results_dir
    if not results_dir.exists():
        return {"results": []}

    results = []
    for f in sorted(results_dir.glob("run_*.json"), reverse=True):
        with open(f, encoding="utf-8") as fp:
            data = json.load(fp)
        results.append({
            "run_id": data.get("run_id", f.stem),
            "tech_number": data.get("tech_number", ""),
            "tech_name": data.get("tech_name", ""),
            "final_verdict": data.get("ensemble_result", {}).get("final_verdict", ""),
            "approval_ratio": data.get("ensemble_result", {}).get("approval_ratio", 0),
            "avg_total": data.get("ensemble_result", {}).get("avg_total", 0),
            "panel_size": data.get("panel_size", 0),
            "elapsed_seconds": data.get("elapsed_seconds", 0),
        })

    return {"results": results, "count": len(results)}


@app.get("/api/results/{run_id}")
def get_result(run_id: str):
    """개별 결과 상세."""
    result_path = settings.results_dir / f"{run_id}.json"
    if not result_path.exists():
        raise HTTPException(404, f"결과 없음: {run_id}")

    with open(result_path, encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/analysis/accuracy")
def analyze_accuracy():
    """정확도 분석."""
    from src.analysis.accuracy_analyzer import AccuracyAnalyzer
    analyzer = AccuracyAnalyzer()
    return analyzer.analyze(settings.results_dir)


@app.get("/api/analysis/consistency")
def analyze_consistency():
    """일관성 분석."""
    from src.analysis.consistency_analyzer import ConsistencyAnalyzer
    analyzer = ConsistencyAnalyzer()
    return analyzer.analyze(settings.results_dir)


@app.get("/api/analysis/score-patterns")
def analyze_score_patterns():
    """점수 패턴 분석."""
    from src.analysis.score_pattern_analyzer import ScorePatternAnalyzer
    analyzer = ScorePatternAnalyzer()
    return analyzer.analyze(settings.results_dir)


@app.get("/api/proposals")
def list_proposals():
    """제안기술 목록."""
    proposals_dir = settings.proposals_dir
    if not proposals_dir.exists():
        return {"proposals": []}

    proposals = []
    for f in sorted(proposals_dir.glob("proposal_*.json")):
        with open(f, encoding="utf-8") as fp:
            data = json.load(fp)
        proposals.append({
            "tech_number": data.get("tech_number", ""),
            "tech_name": data.get("tech_name", ""),
            "tech_field": data.get("tech_field", ""),
        })

    return {"proposals": proposals, "count": len(proposals)}


@app.get("/api/kb/status")
def kb_status():
    """KB 상태 확인."""
    status = {"vector_db_exists": False, "data_sources": {}}

    # 벡터 DB 확인
    vdb_path = settings.vector_db_dir
    if vdb_path.exists():
        status["vector_db_exists"] = True

    # 데이터 소스 확인 (레코드 수 집계)
    dynamic_dir = settings.dynamic_kb_dir
    for source in ["patents", "patents_recent", "scholar_papers", "kci_papers",
                    "codil", "cnt_designated", "openalex_papers", "crossref_papers",
                    "korean_papers", "kcsc_standards"]:
        source_dir = dynamic_dir / source
        if source_dir.exists():
            files = list(source_dir.rglob("*.json"))
            n_records = 0
            for f in files:
                try:
                    with open(f, encoding="utf-8") as fp:
                        data = json.load(fp)
                    n_records += len(data) if isinstance(data, list) else 1
                except Exception:
                    continue
            status["data_sources"][source] = {"files": len(files), "records": n_records}
        else:
            status["data_sources"][source] = {"files": 0, "records": 0}

    return status


# 진행 상황 추적용 인메모리 상태
_eval_status: dict[str, dict] = {}


@app.get("/api/evaluate/status/{run_id}")
def get_eval_status(run_id: str):
    """평가 진행 상황 조회."""
    if run_id in _eval_status:
        return _eval_status[run_id]

    # 완료된 결과 파일 확인
    result_path = settings.results_dir / f"{run_id}.json"
    if result_path.exists():
        return {"run_id": run_id, "status": "completed", "progress": 100}

    return {"run_id": run_id, "status": "not_found"}


@app.get("/api/evaluate/status")
def get_all_eval_status():
    """모든 진행 중인 평가 상태."""
    return {"evaluations": list(_eval_status.values())}


def _run_evaluation(proposal: dict, run_id: str, seed: int | None, skip_chairman: bool):
    """백그라운드 평가 실행 (진행 상황 추적)."""
    from src.pipeline.orchestrator import Orchestrator

    _eval_status[run_id] = {
        "run_id": run_id,
        "tech_name": proposal.get("tech_name", ""),
        "status": "running",
        "progress": 0,
        "step": "패널 생성 중",
    }

    try:
        orchestrator = Orchestrator()
        _eval_status[run_id]["step"] = "LLM 호출 중"
        _eval_status[run_id]["progress"] = 30

        orchestrator.evaluate(
            proposal=proposal,
            run_id=run_id,
            seed=seed,
            skip_chairman=skip_chairman,
        )

        _eval_status[run_id]["status"] = "completed"
        _eval_status[run_id]["progress"] = 100
        _eval_status[run_id]["step"] = "완료"

    except Exception as e:
        _eval_status[run_id]["status"] = "failed"
        _eval_status[run_id]["error"] = str(e)
        logger.error("평가 실행 실패 (%s): %s", run_id, e)


# --- KB Detail Endpoints ---

@app.get("/api/kb/detail")
def kb_detail():
    """KB 구축 상세 정보: 데이터 소스, 전처리, 임베딩, 에이전트별 KB 구성."""
    dynamic_dir = settings.dynamic_kb_dir

    sources = {}
    source_configs = {
        "patents": {"label": "특허 (KIPRIS 기존)", "category_field": "category_major"},
        "patents_recent": {"label": "특허 (KIPRIS 최근추가)", "category_field": "category_major"},
        "scholar_papers": {"label": "논문 (Semantic Scholar)", "category_field": "category_major"},
        "kci_papers": {"label": "논문 (KCI)", "category_field": "category_major"},
        "openalex_papers": {"label": "논문 (OpenAlex)", "category_field": "category_major"},
        "crossref_papers": {"label": "논문 (CrossRef/MDPI)", "category_field": "category_major"},
        "korean_papers": {"label": "논문 (한국 학술지)", "category_field": "category_major"},
        "codil": {"label": "건설기준 (CODIL)", "category_field": "category_major"},
        "kcsc_standards": {"label": "건설기준 (KCSC)", "category_field": "category_major"},
        "cnt_designated": {"label": "지정 건설신기술 (KAIA)", "category_field": None},
    }

    for source_key, cfg in source_configs.items():
        source_dir = dynamic_dir / source_key
        if not source_dir.exists():
            sources[source_key] = {"label": cfg["label"], "total": 0, "by_category": {}, "sample": None}
            continue

        files = list(source_dir.rglob("*.json"))
        total_records = 0
        by_cat: dict[str, int] = {}
        sample = None

        for f in files:
            try:
                with open(f, encoding="utf-8") as fp:
                    data = json.load(fp)
                if isinstance(data, list):
                    total_records += len(data)
                    for item in data:
                        cat = item.get(cfg["category_field"] or "tech_field", "unknown")
                        by_cat[cat] = by_cat.get(cat, 0) + 1
                    if not sample and data:
                        sample = {k: str(v)[:200] for k, v in data[0].items()} if data[0] else None
                else:
                    total_records += 1
                    cat = data.get(cfg["category_field"] or "tech_field", "unknown")
                    by_cat[cat] = by_cat.get(cat, 0) + 1
                    if not sample:
                        sample = {k: str(v)[:200] for k, v in data.items()}
            except Exception:
                continue

        sources[source_key] = {
            "label": cfg["label"],
            "total": total_records,
            "files": len(files),
            "by_category": by_cat,
            "sample": sample,
        }

    # 벡터 DB 정보
    vector_info = {"exists": False, "total_docs": 0}
    vdb_path = settings.vector_db_dir
    if vdb_path.exists():
        vector_info["exists"] = True
        try:
            import lancedb
            db = lancedb.connect(str(vdb_path))
            tbl = db.open_table("cnt_knowledge_base")
            vector_info["total_docs"] = tbl.count_rows()
        except Exception:
            pass

    # 정적 KB
    static_info = {}
    static_dir = settings.static_kb_dir
    if static_dir.exists():
        for f in static_dir.glob("*.json"):
            static_info[f.stem] = {"size_kb": f.stat().st_size // 1024}

    return {
        "sources": sources,
        "vector_db": vector_info,
        "static_kb": static_info,
        "embedding": {
            "model": settings.bedrock_embedding_model_id,
            "dimensions": 1024,
            "provider": "AWS Bedrock (Cohere)",
        },
        "preprocessing": {
            "steps": [
                "JSON 원본 수집 (API/크롤링)",
                "텍스트 청킹 (title + abstract/claims)",
                "Cohere embed-multilingual-v3 임베딩 (1024차원)",
                "LanceDB 벡터 인덱싱",
            ],
        },
        "agent_kb_structure": {
            "level_1_shared": "평가 매뉴얼 + 평가기준표 (모든 에이전트 공유)",
            "level_2_field": "분야별 특허/논문/지정기술/CODIL (전문분야 기반 필터링 → 같은 전문분야 에이전트는 동일 L2 KB 공유)",
            "level_3_experience": "경력별 판단 기조 + 채점 편향 (고/중/저 경력별 차별화 → 같은 경력 수준은 동일 L3 공유)",
            "independence": "같은 전문분야+경력 수준의 에이전트는 동일한 KB를 공유. 전문분야 또는 경력이 다르면 서로 다른 KB 조합.",
        },
    }


@app.get("/api/kb/metadata")
def kb_metadata():
    """KB 메타데이터 파일 로드."""
    meta_path = settings.static_kb_dir / "kb_metadata.json"
    if not meta_path.exists():
        raise HTTPException(404, "KB 메타데이터 파일 없음")
    with open(meta_path, encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/pipeline/workflow")
def pipeline_workflow():
    """파이프라인 워크플로우 구조 반환 (GUI 노드 연결용)."""
    return {
        "nodes": [
            {"id": "input", "label": "입력 데이터 (제안기술)", "type": "input",
             "detail": "tech_number, tech_name, tech_field, tech_description, tech_core_content, differentiation_claim, test_results, field_application"},
            {"id": "classify", "label": "분야 분류", "type": "process",
             "detail": "제안기술의 tech_field에서 대분류(건축/토목/기계설비) → 중분류 → 소분류 추출"},
            {"id": "panel_gen", "label": "패널 생성 (10~15명)", "type": "process",
             "detail": "70% 정합 + 30% 부분정합, 경력: 고(30%) 중(40%) 저(30%), 근속연수: 경력범위 내 랜덤"},
            {"id": "prior_art", "label": "선행기술 검색 (RAG-Novelty)", "type": "process",
             "detail": "KIPRIS 특허 + OpenAlex/Scholar/CrossRef 논문 + KAIA 지정기술 + 자기참조 제외"},
            {"id": "kb_assembly", "label": "계층적 KB 조립 (PIKE-RAG)", "type": "process",
             "detail": "L1(공통 평가기준) + L2(분야별 벡터검색: 특허3500+논문4600+CODIL3000+KCSC) + L3(경력별 판단기조)"},
            {"id": "prompt_build", "label": "프롬프트 구성", "type": "process",
             "detail": "시스템(역할+판단기조) + 유저(평가기준+선행기술+제안기술+출력형식)"},
            {"id": "llm_call", "label": "LLM 병렬 호출", "type": "llm",
             "detail": "AWS Bedrock Claude Sonnet 4.6, ThreadPool 동시 호출, temperature=0.3"},
            {"id": "parse", "label": "응답 파싱", "type": "process",
             "detail": "JSON 파싱 → AgentVote(신규성/진보성 점수, 의결, 근거, 확신도)"},
            {"id": "ensemble", "label": "앙상블 집계 (PoLL)", "type": "process",
             "detail": "확신도 가중 투표, 2/3 정족수, 소수의견 추출, 합의 근거 종합"},
            {"id": "chairman", "label": "의장 검토", "type": "llm",
             "detail": "일관성 점검, 환각 탐지, 논리 오류 검사, 최종 의결 확인/번복"},
            {"id": "output", "label": "최종 결과", "type": "output",
             "detail": "의결(승인/거절), 찬성률, 평균 점수, 개별 투표 상세, 의장 검토 포함 JSON"},
        ],
        "edges": [
            {"from": "input", "to": "classify"},
            {"from": "classify", "to": "panel_gen"},
            {"from": "input", "to": "prior_art"},
            {"from": "panel_gen", "to": "kb_assembly"},
            {"from": "prior_art", "to": "kb_assembly"},
            {"from": "kb_assembly", "to": "prompt_build"},
            {"from": "input", "to": "prompt_build"},
            {"from": "prompt_build", "to": "llm_call"},
            {"from": "llm_call", "to": "parse"},
            {"from": "parse", "to": "ensemble"},
            {"from": "ensemble", "to": "chairman"},
            {"from": "chairman", "to": "output"},
        ],
        "prompt_structure": {
            "system": {
                "description": "시스템 프롬프트 (역할 + 판단 기조)",
                "template": (
                    "당신은 건설신기술 1차 평가위원회의 전문위원입니다.\n"
                    "전문분야: {specialty}\n"
                    "매칭수준: {match_level_desc}\n\n"
                    "{judgment_tendency}\n\n"
                    "당신의 임무는 제출된 건설신기술 신청서를 검토하고,\n"
                    "아래의 평가 기준에 따라 신규성과 진보성을 채점하는 것입니다."
                ),
            },
            "user_sections": [
                {"name": "평가 기준 (Level 1)", "description": "신규성(차별성25+독창성25) + 진보성(품질향상15+개발정도15+안전성10+친환경성10)"},
                {"name": "선행기술 컨텍스트 (RAG-Novelty)", "description": "검색된 관련 특허/논문/지정기술 목록"},
                {"name": "제안기술 명세", "description": "기술명, 분야, 개요, 핵심내용, 차별점, 시험결과, 현장적용실적"},
                {"name": "출력 형식", "description": "JSON 구조: novelty/progressiveness 점수, evidence[], verdict, confidence"},
            ],
            "output_format": {
                "novelty": {"differentiation": "0~25", "originality": "0~25"},
                "progressiveness": {"quality_improvement": "0~15", "development_degree": "0~15", "safety": "0~10", "eco_friendliness": "0~10"},
                "verdict": "approved | rejected (신규성≥35 AND 진보성≥35)",
                "evidence": "[{claim, source_type, source_ref, relevance}]",
                "confidence": "0.0~1.0",
            },
        },
        "panel_config": {
            "size_range": [settings.min_panel_size, settings.max_panel_size],
            "exact_match_ratio": settings.exact_match_ratio,
            "experience_distribution": {"high": 0.3, "medium": 0.4, "low": 0.3},
            "experience_years": {"high": "15~25", "medium": "7~14", "low": "3~6"},
            "quorum_threshold": settings.quorum_threshold,
        },
    }


@app.get("/api/proposals/{tech_number}")
def get_proposal(tech_number: str):
    """개별 제안기술 상세."""
    proposal_path = settings.proposals_dir / f"proposal_{tech_number}.json"
    if not proposal_path.exists():
        raise HTTPException(404, f"제안기술 없음: {tech_number}")
    with open(proposal_path, encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/analysis/experience-correlation")
def analyze_experience_correlation():
    """경력(근속연수)과 채점 패턴의 상관관계 분석."""
    results_dir = settings.results_dir
    if not results_dir.exists():
        return {"error": "결과 없음"}

    agent_data: list[dict] = []

    for f in results_dir.glob("run_*.json"):
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception:
            continue

        panel_map = {p["agent_id"]: p for p in data.get("panel_profiles", [])}
        for vote in data.get("votes", []):
            profile = panel_map.get(vote["agent_id"], {})
            years = profile.get("experience_years", 0)
            exp = profile.get("experience", "")
            match = profile.get("match_level", "")
            total = vote.get("total", 0)
            novelty_total = vote.get("novelty", {}).get("total", 0)
            prog_total = vote.get("progressiveness", {}).get("total", 0)
            verdict = 1 if vote.get("vote") == "approved" else 0
            confidence = vote.get("confidence", 0)

            agent_data.append({
                "experience_years": years,
                "experience_level": exp,
                "match_level": match,
                "total_score": total,
                "novelty_total": novelty_total,
                "progressiveness_total": prog_total,
                "verdict": verdict,
                "confidence": confidence,
                "tech_number": data.get("tech_number", ""),
                "agent_id": vote["agent_id"],
            })

    if not agent_data:
        return {"error": "데이터 없음"}

    # 경력 연수별 통계
    by_years: dict[int, list[dict]] = {}
    for d in agent_data:
        y = d["experience_years"]
        by_years.setdefault(y, []).append(d)

    years_stats = []
    for y in sorted(by_years.keys()):
        entries = by_years[y]
        scores = [e["total_score"] for e in entries]
        approvals = [e["verdict"] for e in entries]
        confs = [e["confidence"] for e in entries]
        years_stats.append({
            "years": y,
            "count": len(entries),
            "avg_score": statistics.mean(scores) if scores else 0,
            "score_std": statistics.stdev(scores) if len(scores) > 1 else 0,
            "approval_rate": statistics.mean(approvals) if approvals else 0,
            "avg_confidence": statistics.mean(confs) if confs else 0,
        })

    # 경력 수준별 통계
    by_level: dict[str, list[dict]] = {}
    for d in agent_data:
        by_level.setdefault(d["experience_level"], []).append(d)

    level_stats = {}
    for level, entries in by_level.items():
        scores = [e["total_score"] for e in entries]
        novelties = [e["novelty_total"] for e in entries]
        progs = [e["progressiveness_total"] for e in entries]
        approvals = [e["verdict"] for e in entries]
        confs = [e["confidence"] for e in entries]
        level_stats[level] = {
            "count": len(entries),
            "avg_score": statistics.mean(scores) if scores else 0,
            "score_std": statistics.stdev(scores) if len(scores) > 1 else 0,
            "avg_novelty": statistics.mean(novelties) if novelties else 0,
            "avg_progressiveness": statistics.mean(progs) if progs else 0,
            "approval_rate": statistics.mean(approvals) if approvals else 0,
            "avg_confidence": statistics.mean(confs) if confs else 0,
        }

    # 매칭 수준별 통계
    by_match: dict[str, list[dict]] = {}
    for d in agent_data:
        by_match.setdefault(d["match_level"], []).append(d)

    match_stats = {}
    for level, entries in by_match.items():
        scores = [e["total_score"] for e in entries]
        approvals = [e["verdict"] for e in entries]
        match_stats[level] = {
            "count": len(entries),
            "avg_score": statistics.mean(scores) if scores else 0,
            "approval_rate": statistics.mean(approvals) if approvals else 0,
        }

    return {
        "total_observations": len(agent_data),
        "by_years": years_stats,
        "by_level": level_stats,
        "by_match": match_stats,
        "raw_scatter": [
            {"x": d["experience_years"], "y": d["total_score"],
             "verdict": d["verdict"], "level": d["experience_level"],
             "match": d["match_level"]}
            for d in agent_data
        ],
    }


# --- Static File Serving (React 빌드) ---

_frontend_build = Path(__file__).resolve().parent.parent.parent / "frontend" / "build"

if _frontend_build.exists():
    app.mount("/static", StaticFiles(directory=str(_frontend_build / "static")), name="static-files")

    @app.get("/{full_path:path}")
    async def serve_react(full_path: str):
        """API가 아닌 모든 경로를 React index.html로 라우팅"""
        file_path = _frontend_build / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_frontend_build / "index.html"))
