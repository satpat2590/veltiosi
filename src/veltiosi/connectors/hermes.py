"""Hermes integration connector."""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..settings import settings

logger = logging.getLogger(__name__)


class HermesConnector:
    """Connector for Hermes agent integration."""

    def __init__(self, hermes_home: Optional[Path] = None):
        """Initialize Hermes connector."""
        self.hermes_home = hermes_home or settings.hermes_home or Path.home() / ".hermes"
        self.skills_dir = self.hermes_home / "skills"
        self.profiles_dir = self.hermes_home / "profiles"

        logger.info(f"Hermes connector initialized with home: {self.hermes_home}")

    def get_available_skills(self) -> List[str]:
        """Get list of available Hermes skills."""
        skills = []

        if not self.skills_dir.exists():
            logger.warning(f"Hermes skills directory not found: {self.skills_dir}")
            return skills

        try:
            for skill_file in self.skills_dir.glob("*.py"):
                skills.append(skill_file.stem)

            logger.info(f"Found {len(skills)} Hermes skills")
            return sorted(skills)

        except Exception as e:
            logger.error(f"Failed to list Hermes skills: {e}")
            return []

    def get_skill_config(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific skill."""
        skill_file = self.skills_dir / f"{skill_name}.py"

        if not skill_file.exists():
            logger.warning(f"Skill file not found: {skill_file}")
            return None

        try:
            # Simple parsing of skill file for configuration
            with open(skill_file, "r") as f:
                content = f.read()

            config = {
                "name": skill_name,
                "file_path": str(skill_file),
                "size": os.path.getsize(skill_file),
                "has_obsidian_integration": "obsidian" in content.lower()
                or "note" in content.lower(),
                "has_atma_integration": "atma" in content.lower() or "task" in content.lower(),
            }

            return config

        except Exception as e:
            logger.error(f"Failed to parse skill {skill_name}: {e}")
            return None

    def execute_skill(
        self, skill_name: str, args: List[str] = None, capture_output: bool = True
    ) -> Dict[str, Any]:
        """Execute a Hermes skill."""
        if args is None:
            args = []

        skill_file = self.skills_dir / f"{skill_name}.py"

        if not skill_file.exists():
            return {"success": False, "error": f"Skill not found: {skill_name}", "output": ""}

        try:
            # Build command
            cmd = [sys.executable, str(skill_file)] + args

            # Execute
            if capture_output:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=self.hermes_home,
                    timeout=300,  # 5 minute timeout
                )

                return {
                    "success": result.returncode == 0,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "output": result.stdout + result.stderr,
                }
            else:
                # Run in background
                subprocess.Popen(
                    cmd, cwd=self.hermes_home, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )

                return {"success": True, "message": f"Skill {skill_name} started in background"}

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Skill {skill_name} timed out after 5 minutes",
                "output": "",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to execute skill {skill_name}: {e}",
                "output": "",
            }

    def get_active_profile(self) -> Optional[str]:
        """Get currently active Hermes profile."""
        profile_file = self.hermes_home / "active_profile.txt"

        if profile_file.exists():
            try:
                with open(profile_file, "r") as f:
                    return f.read().strip()
            except Exception as e:
                logger.warning(f"Failed to read active profile: {e}")

        return None

    def get_profile_config(self, profile_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific profile."""
        profile_dir = self.profiles_dir / profile_name

        if not profile_dir.exists():
            logger.warning(f"Profile directory not found: {profile_dir}")
            return None

        try:
            config_file = profile_dir / "config.json"
            if config_file.exists():
                with open(config_file, "r") as f:
                    return json.load(f)

            # Fallback: check for Python config
            config_py = profile_dir / "config.py"
            if config_py.exists():
                with open(config_py, "r") as f:
                    content = f.read()

                # Simple extraction of key configurations
                config = {
                    "name": profile_name,
                    "has_python_config": True,
                    "mentions_obsidian": "obsidian" in content.lower(),
                    "mentions_atma": "atma" in content.lower(),
                    "mentions_veltiosi": "veltiosi" in content.lower(),
                }

                return config

            return None

        except Exception as e:
            logger.error(f"Failed to parse profile {profile_name}: {e}")
            return None

    def register_veltiosi_skill(self) -> bool:
        """Register Veltiosi as a Hermes skill (circular-import safe)."""
        skill_template = '''#!/usr/bin/env python3
"""Veltiosi - Obsidian automation layer for Hermes."""

import argparse
import sys

# Lazy import to avoid circular imports
def get_app():
    """Lazy import of Veltiosi CLI app."""
    from veltiosi.cli import app
    return app

def main():
    """Main entry point for Veltiosi Hermes skill."""
    parser = argparse.ArgumentParser(
        description="Veltiosi - Obsidian automation layer"
    )
    parser.add_argument("command", nargs="?", help="Veltiosi command to run")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Command arguments")
    
    args = parser.parse_args()
    
    if args.command:
        # Run specific command
        sys.argv = ["veltiosi", args.command] + args.args
    else:
        # Show help
        sys.argv = ["veltiosi", "--help"]
    
    # Get app via lazy import
    app = get_app()
    app()

if __name__ == "__main__":
    main()'''

        try:
            skill_file = self.skills_dir / "veltiosi_hermes.py"  # CHANGED NAME

            # Create skills directory if it doesn't exist
            self.skills_dir.mkdir(parents=True, exist_ok=True)

            # Write skill file
            with open(skill_file, "w") as f:
                f.write(skill_template)

            # Make executable
            skill_file.chmod(0o755)

            logger.info(f"Registered Veltiosi as Hermes skill: {skill_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to register Veltiosi skill: {e}")
            return False

    def create_veltiosi_profile(self, profile_name: str = "satya") -> bool:
        """Create a Hermes profile with Veltiosi integration."""
        profile_dir = self.profiles_dir / profile_name
        profile_dir.mkdir(parents=True, exist_ok=True)

        # Create profile configuration
        profile_config = {
            "name": profile_name,
            "description": "Profile with Veltiosi Obsidian automation integration",
            "skills": ["veltiosi_hermes"],
            "environment": {
                "VELTIOSI_OBSIDIAN_VAULT": str(settings.obsidian_vault),
                "VELTIOSI_AUDIT_DIR": str(settings.audit_dir) if settings.audit_dir else "",
                "GOOGLE_API_KEY": settings.google_api_key or "",
                "ATMA_BASE_URL": settings.atma_base_url or "",
                "ATMA_API_KEY": settings.atma_api_key or "",
            },
            "cron_jobs": [
                {
                    "name": "veltiosi_daily_sync",
                    "schedule": "0 9 * * *",  # 9 AM daily
                    "command": "python -m veltiosi.cli sync --mode auto",
                    "description": "Daily sync of tasks and knowledge updates",
                },
                {
                    "name": "veltiosi_weekly_index",
                    "schedule": "0 10 * * 0",  # 10 AM every Sunday
                    "command": "python -m veltiosi.cli index --rebuild",
                    "description": "Weekly index rebuild and optimization",
                },
            ],
        }

        try:
            # Write config file
            config_file = profile_dir / "config.json"
            with open(config_file, "w") as f:
                json.dump(profile_config, f, indent=2)

            # Create profile activation script
            activation_script = profile_dir / "activate.py"
            activation_content = '''"""Activation script for Veltiosi profile."""

import os
import sys
from pathlib import Path

# Set environment variables
env_vars = {
    "VELTIOSI_OBSIDIAN_VAULT": "{obsidian_vault}",
    "VELTIOSI_AUDIT_DIR": "{audit_dir}",
    "GOOGLE_API_KEY": "{google_api_key}",
    "ATMA_BASE_URL": "{atma_base_url}",
    "ATMA_API_KEY": "{atma_api_key}",
}

for key, value in env_vars.items():
    if value:
        os.environ[key] = value

print("Activated Veltiosi profile: {profile_name}")
print("Environment variables set:")
for key in env_vars.keys():
    if os.environ.get(key):
        print(f"  {key}: [set]")
    else:
        print(f"  {key}: [not set]")
'''.format(
                obsidian_vault=str(settings.obsidian_vault),
                profile_name=profile_name,
                audit_dir=str(settings.audit_dir) if settings.audit_dir else "",
                google_api_key=settings.google_api_key or "",
                atma_base_url=settings.atma_base_url or "",
                atma_api_key=settings.atma_api_key or "",
            )

            with open(activation_script, "w") as f:
                f.write(activation_content)

            logger.info(f"Created Veltiosi profile: {profile_dir}")
            return True

        except Exception as e:
            logger.error(f"Failed to create Veltiosi profile: {e}")
            return False

    def setup_cron_jobs(self, profile_name: str = "satya") -> bool:
        """Set up cron jobs for the Veltiosi profile."""
        profile_dir = self.profiles_dir / profile_name

        if not profile_dir.exists():
            logger.error(f"Profile directory not found: {profile_dir}")
            return False

        try:
            config_file = profile_dir / "config.json"
            if not config_file.exists():
                logger.error(f"Profile config not found: {config_file}")
                return False

            with open(config_file, "r") as f:
                config = json.load(f)

            cron_jobs = config.get("cron_jobs", [])

            if not cron_jobs:
                logger.info(f"No cron jobs defined for profile {profile_name}")
                return True

            # Create cron setup script
            cron_script = profile_dir / "setup_cron.py"
            cron_content = '''"""Setup cron jobs for Veltiosi."""

import os
import subprocess
import sys

cron_jobs = {cron_jobs}

def setup_cron():
    """Setup cron jobs."""
    current_crontab = subprocess.run(
        ["crontab", "-l"],
        capture_output=True,
        text=True
    ).stdout
    
    new_crontab = current_crontab
    
    for job in cron_jobs:
        cron_line = f"{job['schedule']} {job['command']} # {job['name']}: {job['description']}"
        
        if cron_line not in new_crontab:
            new_crontab += f"\\n{cron_line}"
    
    # Write new crontab
    result = subprocess.run(
        ["crontab", "-"],
        input=new_crontab,
        text=True,
        capture_output=True
    )
    
    if result.returncode == 0:
        print("Cron jobs setup successfully")
        return True
    else:
        print(f"Failed to setup cron jobs: {result.stderr}")
        return False

if __name__ == "__main__":
    setup_cron()
'''.format(cron_jobs=json.dumps(cron_jobs))

            with open(cron_script, "w") as f:
                f.write(cron_content)

            logger.info(f"Created cron setup script: {cron_script}")
            return True

        except Exception as e:
            logger.error(f"Failed to setup cron jobs: {e}")
            return False

    def test_integration(self) -> Dict[str, Any]:
        """Test Hermes integration."""
        results = {
            "hermes_home_exists": self.hermes_home.exists(),
            "skills_dir_exists": self.skills_dir.exists(),
            "profiles_dir_exists": self.profiles_dir.exists(),
            "available_skills": [],
            "active_profile": None,
            "veltiosi_skill_registered": False,
        }

        if self.hermes_home.exists():
            results["available_skills"] = self.get_available_skills()
            results["active_profile"] = self.get_active_profile()
            results["veltiosi_skill_registered"] = (self.skills_dir / "veltiosi.py").exists()

        return results
