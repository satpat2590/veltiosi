# Veltiosi Quick Start Guide

## 5-Minute Setup

### 1. Clone and Install
```bash
cd ~
git clone <repository-url> veltiosi
cd veltiosi
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Basic Configuration
```bash
# Copy environment template
cp .env.example .env

# Edit .env to point to your Obsidian vault
# VELTIOSI_OBSIDIAN_VAULT=/path/to/your/obsidian/vault
```

### 3. First Run
```bash
# Check system status
python -m veltiosi.cli status

# Run a consistency check
python -m veltiosi.cli wiki-index --check

# Generate indexes (dry run first)
python -m veltiosi.cli wiki-index --dry-run
python -m veltiosi.cli wiki-index
```

## Common Tasks

### Check Vault Health
```bash
# Quick scan
python -m veltiosi.cli status

# Detailed consistency check
python -m veltiosi.cli wiki-index --check

# View configuration
python -m veltiosi.cli config-show
```

### Generate Indexes
```bash
# Full index generation
python -m veltiosi.cli wiki-index

# Check-only mode (no writes)
python -m veltiosi.cli wiki-index --check

# Dry run (see what would be written)
python -m veltiosi.cli wiki-index --dry-run

# Force full reclassification
python -m veltiosi.cli wiki-index --full
```

### View Generated Content
After running `wiki-index`, check:
```bash
# Central MOCs
ls ~/Obsidian/14-Maps-of-Content/

# Example: Physical MOC
cat ~/Obsidian/14-Maps-of-Content/Physical\ MOC.md

# Domain indexes (if you have domain folders)
ls ~/Obsidian/15-Daily-Notes/*Index.md 2>/dev/null || echo "No domain indexes yet"
```

## Configuration Examples

### Customizing Categories
Edit `config/categories.yaml`:
```yaml
roots:
  physical:
    display_name: "Physical Health"
    moc_path: "14-Maps-of-Content/Physical Health MOC.md"
    color: "#4CAF50"
    description: "Physical wellness, fitness, and health systems"
```

### Adding Subcategories
Edit `config/subcategories.yaml`:
```yaml
subcategories:
  meditation:
    display_name: "Meditation"
    primary_root: mental
    moc_path: "14-Maps-of-Content/Meditation MOC.md"
    local_index_path: "15-Daily-Notes/Meditation Index.md"
    domain_folders:
      - "15-Daily-Notes"
      - "03-Mindfulness"
    description: "Meditation and mindfulness practice"
```

### Mapping Domain Folders
Edit `config/domain_map.yaml`:
```yaml
domain_folders:
  "03-Mindfulness":
    default_roots:
      - mental
    description: "Mindfulness and meditation practice"
```

## Troubleshooting

### Common Issues

1. **"Vault not found" error**
   ```bash
   # Check your .env file
   cat .env
   # Ensure VELTIOSI_OBSIDIAN_VAULT points to correct path
   ```

2. **Permission errors**
   ```bash
   # Check vault directory permissions
   ls -la ~/Obsidian/
   ```

3. **Empty or missing indexes**
   ```bash
   # Run with more verbosity
   python -m veltiosi.cli wiki-index --check
   # Check for notes in your vault
   find ~/Obsidian -name "*.md" | wc -l
   ```

### Debug Mode
```bash
# Set debug environment variable
export VELTIOSI_DEBUG=1

# Run command with debug output
python -m veltiosi.cli wiki-index --check
```

## Next Steps

### 1. Review Generated Indexes
- Check `~/Obsidian/14-Maps-of-Content/` for MOCs
- Verify note categorization looks correct
- Review any consistency issues reported

### 2. Customize Configuration
- Edit YAML files in `config/` to match your taxonomy
- Add task rules in `config/task_rules.yaml` for Atma integration
- Configure LLM settings in `config/llm.yaml` if using Gemini

### 3. Set Up Scheduled Runs
```bash
# Example cron job (runs daily at 9 AM)
0 9 * * * cd ~/veltiosi && .venv/bin/python -m veltiosi.cli wiki-index

# Weekly synthesis (Sunday at 10 AM)
0 10 * * 0 cd ~/veltiosi && .venv/bin/python -m veltiosi.cli weekly-synthesis
```

### 4. Integrate with Hermes
```bash
# Register Veltiosi as Hermes skill
python -c "from veltiosi.connectors.hermes import HermesConnector; h = HermesConnector(); h.register_veltiosi_skill()"

# Create Hermes profile with Veltiosi integration
python -c "from veltiosi.connectors.hermes import HermesConnector; h = HermesConnector(); h.create_veltiosi_profile()"
```

## Getting Help

### Check Documentation
- `README.md` - Overview and installation
- `ARCHITECTURE.md` - System architecture
- `implementation/progression.md` - Development status

### CLI Help
```bash
# General help
python -m veltiosi.cli --help

# Command-specific help
python -m veltiosi.cli wiki-index --help
python -m veltiosi.cli status --help
```

### Audit Logs
```bash
# View audit logs
ls ~/.veltiosi/audit/events/

# Check latest run
ls -lt ~/.veltiosi/audit/events/ | head -5
```

## Example Workflows

### Daily Maintenance
```bash
# Morning: Quick status check
python -m veltiosi.cli status

# Afternoon: Process new notes
python -m veltiosi.cli wiki-index

# Evening: Check for issues
python -m veltiosi.cli wiki-index --check
```

### Weekly Review
```bash
# Generate weekly synthesis
python -m veltiosi.cli weekly-synthesis

# Full consistency check
python -m veltiosi.cli wiki-index --check --full

# Review audit reports
python -c "from veltiosi.audit import AuditLogger; a = AuditLogger(); print(a.generate_report())"
```

### Onboarding New Domain
```bash
# 1. Add domain folder mapping
# Edit config/domain_map.yaml

# 2. Add subcategory if needed
# Edit config/subcategories.yaml

# 3. Generate indexes
python -m veltiosi.cli wiki-index

# 4. Verify new MOCs
ls ~/Obsidian/14-Maps-of-Content/*.md
```