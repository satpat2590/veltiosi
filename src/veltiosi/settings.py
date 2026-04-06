"""Settings and configuration loader."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RootCategoryConfig(BaseModel):
    """Root category configuration."""

    display_name: str
    moc_path: str
    color: Optional[str] = None
    description: Optional[str] = None


class SubcategoryConfig(BaseModel):
    """Subcategory configuration."""

    display_name: str
    primary_root: str
    moc_path: str
    local_index_path: str
    domain_folders: list[str]
    description: Optional[str] = None


class DomainFolderConfig(BaseModel):
    """Domain folder configuration."""

    default_roots: list[str]
    description: Optional[str] = None


class TaskRuleConfig(BaseModel):
    """Task mapping rule configuration."""

    id: str
    match_any: list[str]
    category: Optional[str] = None
    subcategories: list[str] = []
    tags: list[str] = []
    target_page: Optional[str] = None
    confidence: float = 0.5


class GenerationRulesConfig(BaseModel):
    """Generation and safety rules."""

    generated_sections: Dict[str, Any]
    review_queue: Dict[str, Any]
    logging: Dict[str, Any]
    ignored_paths: list[str]
    lint: Dict[str, Any]
    indexing: Dict[str, Any]
    synthesis: Dict[str, Any]


class LLMConfig(BaseModel):
    """LLM configuration."""

    provider: str
    model_policy: Dict[str, Any]
    timeouts: Dict[str, Any]
    generation: Dict[str, Any]
    prompts: Dict[str, Any]


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="VELTIOSI_",
        case_sensitive=False,
    )

    # Environment variables
    obsidian_vault: Path = Field(default=Path.home() / "Obsidian")
    audit_dir: Optional[Path] = None
    google_api_key: Optional[str] = None
    atma_base_url: Optional[str] = None
    atma_api_key: Optional[str] = None
    hermes_home: Optional[Path] = None

    # Loaded from config files
    root_categories: Dict[str, RootCategoryConfig] = {}
    subcategories: Dict[str, SubcategoryConfig] = {}
    domain_folders: Dict[str, DomainFolderConfig] = {}
    task_rules: list[TaskRuleConfig] = []
    generation_rules: GenerationRulesConfig
    llm_config: LLMConfig

    @field_validator("obsidian_vault", mode="before")
    @classmethod
    def validate_obsidian_vault(cls, v: Any) -> Path:
        """Validate and convert obsidian_vault to Path."""
        if isinstance(v, str):
            return Path(v).expanduser()
        return v

    @field_validator("audit_dir", "hermes_home", mode="before")
    @classmethod
    def validate_optional_paths(cls, v: Any) -> Optional[Path]:
        """Validate and convert optional paths."""
        if v is None:
            return None
        if isinstance(v, str):
            return Path(v).expanduser()
        return v

    @classmethod
    def load_from_configs(cls, config_dir: Path) -> "Settings":
        """Load settings from config directory."""
        config_dir = config_dir.expanduser()

        # Load YAML configs
        with open(config_dir / "categories.yaml") as f:
            categories_data = yaml.safe_load(f)

        with open(config_dir / "subcategories.yaml") as f:
            subcategories_data = yaml.safe_load(f)

        with open(config_dir / "domain_map.yaml") as f:
            domain_map_data = yaml.safe_load(f)

        with open(config_dir / "task_rules.yaml") as f:
            task_rules_data = yaml.safe_load(f)

        with open(config_dir / "generation_rules.yaml") as f:
            generation_rules_data = yaml.safe_load(f)

        with open(config_dir / "llm.yaml") as f:
            llm_data = yaml.safe_load(f)

        # Build settings
        root_categories = {
            name: RootCategoryConfig(**config)
            for name, config in categories_data.get("roots", {}).items()
        }

        subcategories = {
            name: SubcategoryConfig(**config)
            for name, config in subcategories_data.get("subcategories", {}).items()
        }

        domain_folders = {
            name: DomainFolderConfig(**config)
            for name, config in domain_map_data.get("domain_folders", {}).items()
        }

        task_rules = [TaskRuleConfig(**rule) for rule in task_rules_data.get("rules", [])]

        generation_rules = GenerationRulesConfig(**generation_rules_data)
        llm_config = LLMConfig(**llm_data)

        # Create settings instance
        return cls(
            root_categories=root_categories,
            subcategories=subcategories,
            domain_folders=domain_folders,
            task_rules=task_rules,
            generation_rules=generation_rules,
            llm_config=llm_config,
        )


def get_settings() -> Settings:
    """Get application settings."""
    config_dir = Path(__file__).parent.parent.parent / "config"
    return Settings.load_from_configs(config_dir)


# Global settings instance
settings = get_settings()
