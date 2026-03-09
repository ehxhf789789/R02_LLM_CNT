from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # KIPRIS Plus API
    kipris_api_key: str = ""
    kipris_base_url: str = "http://plus.kipris.or.kr/kipo-api/kipi/patUtiModInfoSearchSevice"

    # ScienceON API (비활성화 - 토큰 발급 이슈)
    scienceon_auth_key: str = ""
    scienceon_client_id: str = ""
    scienceon_mac_address: str = ""
    scienceon_base_url: str = "https://apigateway.kisti.re.kr/openapicall.do"
    scienceon_token_url: str = "https://apigateway.kisti.re.kr/tokenrequest.do"

    # Semantic Scholar API (키 없이도 동작)
    semantic_scholar_api_key: str = ""

    # KCI (한국학술지인용색인) API
    kci_api_key: str = ""

    # KAIA
    kaia_cnt_list_url: str = "https://www.kaia.re.kr/portal/newtec/comparelist.do"
    kaia_ntech_base_url: str = "https://ntech.kaia.re.kr"

    # AWS Bedrock
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = "us-east-1"
    bedrock_model_id: str = "us.anthropic.claude-sonnet-4-6-20250514-v1:0"
    bedrock_embedding_model_id: str = "cohere.embed-multilingual-v3"

    # Evaluation settings
    min_panel_size: int = 10
    max_panel_size: int = 15
    exact_match_ratio: float = 0.7
    quorum_threshold: float = 2 / 3

    # Paths
    data_dir: Path = Path("./data")

    @property
    def static_kb_dir(self) -> Path:
        return self.data_dir / "static"

    @property
    def dynamic_kb_dir(self) -> Path:
        return self.data_dir / "dynamic"

    @property
    def classifications_dir(self) -> Path:
        return self.data_dir / "classifications"

    @property
    def proposals_dir(self) -> Path:
        return self.data_dir / "proposals"

    @property
    def results_dir(self) -> Path:
        return self.data_dir / "evaluation_results"

    @property
    def vector_db_dir(self) -> Path:
        return self.data_dir / "vector_db"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
