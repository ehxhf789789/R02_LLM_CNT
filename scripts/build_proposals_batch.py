"""유효+enriched 지정기술에서 프로포절을 일괄 생성.

기존 enriched JSON + designated_list.json 데이터만으로 구축.
KAIA 상세 페이지 재크롤링 불필요.

사용법:
  py scripts/build_proposals_batch.py              # 전체 생성 (기존 건 스킵)
  py scripts/build_proposals_batch.py --force      # 기존 건 포함 재생성
  py scripts/build_proposals_batch.py --status     # 현황 확인
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False))],
)
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data"
DESIGNATED_LIST = DATA_DIR / "dynamic" / "cnt_designated" / "designated_list.json"
ENRICHED_DIR = DATA_DIR / "dynamic" / "cnt_designated" / "enriched"
PROPOSALS_DIR = DATA_DIR / "proposals"


def load_designated_map() -> dict[str, dict]:
    """designated_list.json에서 tech_number → 기술정보 매핑."""
    if not DESIGNATED_LIST.exists():
        return {}
    techs = json.load(open(DESIGNATED_LIST, encoding="utf-8"))
    return {str(t.get("tech_number", "")): t for t in techs if t.get("tech_number")}


def load_enriched(tech_number: str) -> dict | None:
    """enriched JSON 로드."""
    path = ENRICHED_DIR / f"designated_{tech_number}.json"
    if not path.exists():
        return None
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, list):
        data = data[0]
    return data


def build_proposal(tech_info: dict, enriched: dict) -> dict:
    """designated_list 기본정보 + enriched PDF 텍스트로 프로포절 구축."""
    tech_number = str(tech_info.get("tech_number", ""))
    texts = enriched.get("extracted_texts", {})

    # PDF에서 추출한 주요 필드
    prior_art = texts.get("prior_art_survey", "")
    tech_detail = texts.get("tech_detail", "")
    intro = texts.get("intro", "")
    summary = texts.get("summary", "")
    procedure = texts.get("procedure", "")
    ip_info = texts.get("ip_info", "")
    cost = texts.get("cost", "")

    # 기술 설명: summary > intro > tech_detail 순으로 채움
    tech_description = summary or intro or tech_detail
    if len(tech_description) > 500:
        tech_description = tech_description[:500]

    # 핵심 기술 내용: tech_detail + summary 통합
    core_content = tech_detail
    if summary and summary != tech_detail:
        core_content = (core_content + "\n" + summary) if core_content else summary

    # 차별성 주장: prior_art_survey에서 추출 (선행기술 대비 차별점)
    differentiation = prior_art if prior_art else ""

    # 전체 PDF 텍스트 통합
    all_text_parts = [v for v in texts.values() if v and len(v) > 10]
    all_text = "\n\n".join(all_text_parts)

    # 특허 정보
    patents = enriched.get("patents", [])

    # 분야에서 카테고리 코드 추출
    tech_field = tech_info.get("tech_field", enriched.get("tech_field", ""))
    category_code = _extract_category_code(tech_field)

    proposal = {
        "tech_number": tech_number,
        "tech_name": tech_info.get("tech_name", enriched.get("tech_name", "")),
        "tech_field": tech_field,
        "category_code": category_code,
        "tech_description": tech_description,
        "tech_core_content": core_content,
        "differentiation_claim": differentiation,
        "test_results": "",
        "field_application": "",
        "search_keywords": _extract_keywords(tech_info, enriched),
        "patents": patents,
        "pdf_content": all_text,
        "protection_period": tech_info.get("protection_period", ""),
        "designation_year": _extract_designation_year(tech_info.get("protection_period", "")),
        "applicant": tech_info.get("applicant", ""),
        "status": tech_info.get("status", ""),
        "source": "kaia",
        # enriched 텍스트 필드 (개별 접근용)
        "prior_art_survey_text": prior_art,
        "tech_detail_text": tech_detail,
        "summary_text": summary,
        "intro_text": intro,
        "procedure_text": procedure,
        "ip_info_text": ip_info,
        "cost_text": cost,
        "all_extracted_text": all_text,
        "enrichment_source": "enriched",
        "enrichment_files": list(texts.keys()),
    }

    return proposal


def _extract_designation_year(protection_period: str) -> int | None:
    """보호기간 문자열에서 지정연도 추출. (e.g., '2020-09-30 ~ 2027-09-30' → 2020)"""
    import re
    if not protection_period:
        return None
    match = re.match(r"(\d{4})", str(protection_period))
    return int(match.group(1)) if match else None


def _extract_category_code(tech_field: str) -> str:
    """기술 분야에서 카테고리 코드 추출."""
    major = tech_field.split(">")[0].strip() if tech_field else ""
    mapping = {
        "토목": "CIV",
        "건축": "ARC",
        "기계설비": "MEC",
        "기계": "MEC",
        "설비": "MEC",
    }
    for k, v in mapping.items():
        if k in major:
            return v
    return "CIV"  # 기본값


def _extract_keywords(tech_info: dict, enriched: dict) -> list[str]:
    """검색 키워드 추출."""
    keywords = []

    # 기술명에서 핵심 단어
    name = tech_info.get("tech_name", "")
    if name:
        keywords.append(name)

    # 분야 키워드
    field = tech_info.get("tech_field", "")
    if field:
        parts = [p.strip() for p in field.split(">") if p.strip()]
        keywords.extend(parts[1:])  # 중분류, 소분류

    return keywords[:5]


def build_all_proposals(force: bool = False) -> dict:
    """유효+enriched 전체 프로포절 생성."""
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)

    designated_map = load_designated_map()
    if not designated_map:
        logger.error("designated_list.json 없음")
        return {}

    # enriched 파일 목록
    enriched_files = list(ENRICHED_DIR.glob("designated_*.json"))
    enriched_nums = {f.stem.replace("designated_", "") for f in enriched_files}

    logger.info("designated_list: %d건, enriched: %d건", len(designated_map), len(enriched_nums))

    # 유효 기술 중 enriched 보유 건 필터
    candidates = []
    for tech_num in enriched_nums:
        info = designated_map.get(tech_num)
        if not info:
            continue
        status = info.get("status", "")
        if "만료" in status:
            continue  # 만료 기술 제외
        candidates.append(tech_num)

    candidates.sort(key=lambda x: int(x) if x.isdigit() else 0)
    logger.info("유효+enriched 후보: %d건", len(candidates))

    stats = {"created": 0, "skipped": 0, "failed": 0}
    category_counts = {"CIV": 0, "ARC": 0, "MEC": 0}

    for tech_num in candidates:
        out_path = PROPOSALS_DIR / f"proposal_{tech_num}.json"

        # 기존 파일 스킵 (force가 아닌 경우)
        if out_path.exists() and not force:
            stats["skipped"] += 1
            continue

        try:
            info = designated_map[tech_num]
            enriched = load_enriched(tech_num)
            if not enriched:
                stats["failed"] += 1
                continue

            # enriched 텍스트가 충분한지 검증
            texts = enriched.get("extracted_texts", {})
            total_text_len = sum(len(v) for v in texts.values())
            if total_text_len < 200:
                logger.warning("텍스트 부족 (%d chars): %s", total_text_len, tech_num)
                stats["failed"] += 1
                continue

            proposal = build_proposal(info, enriched)

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(proposal, f, ensure_ascii=False, indent=2, default=str)

            cat = proposal.get("category_code", "CIV")
            category_counts[cat] = category_counts.get(cat, 0) + 1
            stats["created"] += 1

        except Exception as e:
            logger.error("프로포절 생성 실패 %s: %s", tech_num, e)
            stats["failed"] += 1

    logger.info("=== 프로포절 생성 완료 ===")
    logger.info("  생성: %d건, 스킵: %d건, 실패: %d건", stats["created"], stats["skipped"], stats["failed"])
    logger.info("  분류별: %s", category_counts)

    # 전체 현황
    all_proposals = list(PROPOSALS_DIR.glob("proposal_*.json"))
    logger.info("  전체 프로포절: %d건", len(all_proposals))

    return stats


def show_status():
    """프로포절 현황."""
    print("\n=== 프로포절 현황 ===\n")

    proposals = list(PROPOSALS_DIR.glob("proposal_*.json"))
    if not proposals:
        print("  프로포절 없음")
        return

    cats = {"CIV": [], "ARC": [], "MEC": [], "기타": []}
    total_text_lens = []
    with_prior_art = 0
    with_patents = 0

    for f in sorted(proposals):
        try:
            p = json.load(open(f, encoding="utf-8"))
            cat = p.get("category_code", "")
            if cat not in cats:
                cat = "기타"
            cats[cat].append(p.get("tech_number", ""))

            text_len = len(p.get("all_extracted_text", "") or p.get("pdf_content", ""))
            total_text_lens.append(text_len)

            if p.get("prior_art_survey_text") and len(p["prior_art_survey_text"]) > 100:
                with_prior_art += 1
            if p.get("patents") and len(p["patents"]) > 0:
                with_patents += 1
        except Exception:
            pass

    total = len(proposals)
    avg_text = sum(total_text_lens) / max(len(total_text_lens), 1)

    print(f"  전체: {total}건")
    print(f"  분류별:")
    for cat in ["CIV", "ARC", "MEC", "기타"]:
        if cats[cat]:
            nums = cats[cat]
            print(f"    {cat}: {len(nums)}건 ({nums[0]}~{nums[-1]})")
    print(f"  선행기술조사 보유: {with_prior_art}건 ({with_prior_art/max(total,1)*100:.0f}%)")
    print(f"  특허 정보 보유: {with_patents}건 ({with_patents/max(total,1)*100:.0f}%)")
    print(f"  평균 텍스트 길이: {avg_text:,.0f} chars")

    # enriched 후보 대비 커버리지
    designated_map = load_designated_map()
    enriched_files = list(ENRICHED_DIR.glob("designated_*.json"))
    enriched_nums = {f.stem.replace("designated_", "") for f in enriched_files}
    valid_enriched = sum(
        1 for n in enriched_nums
        if n in designated_map and "만료" not in designated_map[n].get("status", "")
    )
    print(f"\n  후보 (유효+enriched): {valid_enriched}건")
    print(f"  커버리지: {total}/{valid_enriched} ({total/max(valid_enriched,1)*100:.0f}%)")


def main():
    parser = argparse.ArgumentParser(description="프로포절 일괄 생성")
    parser.add_argument("--force", action="store_true", help="기존 파일 포함 재생성")
    parser.add_argument("--status", action="store_true", help="현황 확인")
    args = parser.parse_args()

    if args.status:
        show_status()
    else:
        build_all_proposals(force=args.force)


if __name__ == "__main__":
    main()
