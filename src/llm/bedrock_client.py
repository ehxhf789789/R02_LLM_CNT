"""AWS Bedrock LLM 클라이언트.

Claude 모델을 사용하여 건설신기술 평가 에이전트의 응답을 생성한다.
Converse API를 사용하여 모델 독립적 인터페이스를 제공한다.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import boto3
from botocore.config import Config as BotoConfig

from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """LLM 응답 결과."""
    content: str = ""
    model_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""
    latency_ms: float = 0.0


class BedrockClient:
    """AWS Bedrock LLM 클라이언트."""

    def __init__(
        self,
        model_id: str | None = None,
        region: str | None = None,
        max_retries: int = 3,
        timeout: int = 300,
    ):
        self.model_id = model_id or settings.bedrock_model_id
        self.region = region or settings.aws_default_region

        boto_config = BotoConfig(
            region_name=self.region,
            retries={"max_attempts": max_retries, "mode": "adaptive"},
            read_timeout=timeout,
            connect_timeout=30,
        )

        self.client = boto3.client(
            "bedrock-runtime",
            config=boto_config,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )

    def invoke(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        top_p: float = 0.9,
    ) -> LLMResponse:
        """단일 메시지로 LLM 호출.

        Args:
            system_prompt: 시스템 프롬프트 (역할 + 기조)
            user_message: 유저 프롬프트 (평가 기준 + 선행기술 + 제안기술)
            max_tokens: 최대 응답 토큰 수
            temperature: 응답 다양성 (0=결정적, 1=다양)
            top_p: 핵 샘플링 확률

        Returns:
            LLMResponse with content and usage info
        """
        messages = [{"role": "user", "content": [{"text": user_message}]}]
        system = [{"text": system_prompt}]

        inference_config = {
            "maxTokens": max_tokens,
            "temperature": temperature,
        }

        start_time = time.time()

        try:
            response = self.client.converse(
                modelId=self.model_id,
                messages=messages,
                system=system,
                inferenceConfig=inference_config,
            )

            latency_ms = (time.time() - start_time) * 1000

            content = ""
            output = response.get("output", {})
            message = output.get("message", {})
            for block in message.get("content", []):
                if "text" in block:
                    content += block["text"]

            usage = response.get("usage", {})

            result = LLMResponse(
                content=content,
                model_id=self.model_id,
                input_tokens=usage.get("inputTokens", 0),
                output_tokens=usage.get("outputTokens", 0),
                stop_reason=response.get("stopReason", ""),
                latency_ms=latency_ms,
            )

            logger.info(
                "Bedrock 호출 완료: model=%s, in=%d, out=%d, %.0fms",
                self.model_id,
                result.input_tokens,
                result.output_tokens,
                result.latency_ms,
            )
            return result

        except Exception as e:
            logger.error("Bedrock 호출 실패: %s", e)
            raise

    def invoke_batch(
        self,
        prompts: list[dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.3,
        max_concurrent: int = 5,
    ) -> list[LLMResponse]:
        """여러 프롬프트를 순차 호출 (rate limit 고려).

        Args:
            prompts: list of {"system": ..., "user": ...}
            max_concurrent: 동시 호출 수 (현재 순차 구현)
        """
        results = []
        for i, prompt in enumerate(prompts):
            logger.info("배치 호출 %d/%d", i + 1, len(prompts))
            result = self.invoke(
                system_prompt=prompt["system"],
                user_message=prompt["user"],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            results.append(result)

            # Rate limit: Bedrock Claude는 분당 요청 제한 있음
            if i < len(prompts) - 1:
                time.sleep(1.0)

        return results


class BedrockEmbeddingClient:
    """AWS Bedrock 임베딩 클라이언트.

    Cohere embed-multilingual-v3 또는 Titan embed-text-v2 사용.
    """

    def __init__(
        self,
        model_id: str | None = None,
        region: str | None = None,
    ):
        self.model_id = model_id or settings.bedrock_embedding_model_id
        self.region = region or settings.aws_default_region

        self.client = boto3.client(
            "bedrock-runtime",
            region_name=self.region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )

        self._is_cohere = "cohere" in self.model_id.lower()
        self._is_titan = "titan" in self.model_id.lower()

    def embed_texts(
        self,
        texts: list[str],
        input_type: str = "search_document",
    ) -> list[list[float]]:
        """텍스트 리스트를 임베딩 벡터로 변환.

        Args:
            texts: 임베딩할 텍스트 리스트
            input_type: Cohere용 - "search_document" 또는 "search_query"

        Returns:
            임베딩 벡터 리스트
        """
        if self._is_cohere:
            return self._embed_cohere(texts, input_type)
        elif self._is_titan:
            return self._embed_titan(texts)
        else:
            raise ValueError(f"지원하지 않는 임베딩 모델: {self.model_id}")

    def embed_query(self, query: str) -> list[float]:
        """검색 쿼리를 임베딩 벡터로 변환."""
        results = self.embed_texts([query], input_type="search_query")
        return results[0]

    def _embed_cohere(
        self,
        texts: list[str],
        input_type: str,
    ) -> list[list[float]]:
        """Cohere embed-multilingual-v3 호출."""
        # Cohere는 한번에 최대 96개 텍스트
        all_embeddings = []
        batch_size = 96

        for i in range(0, len(texts), batch_size):
            batch = [t[:2048] for t in texts[i:i + batch_size]]

            body = json.dumps({
                "texts": batch,
                "input_type": input_type,
                "truncate": "END",
            })

            response = self.client.invoke_model(
                modelId=self.model_id,
                body=body,
                contentType="application/json",
                accept="application/json",
            )

            result = json.loads(response["body"].read())
            all_embeddings.extend(result["embeddings"])

            if i + batch_size < len(texts):
                time.sleep(0.5)

        return all_embeddings

    def _embed_titan(self, texts: list[str]) -> list[list[float]]:
        """Amazon Titan embed-text-v2 호출."""
        embeddings = []

        for text in texts:
            body = json.dumps({
                "inputText": text[:8192],  # Titan 최대 8192 tokens
            })

            response = self.client.invoke_model(
                modelId=self.model_id,
                body=body,
                contentType="application/json",
                accept="application/json",
            )

            result = json.loads(response["body"].read())
            embeddings.append(result["embedding"])

        return embeddings
