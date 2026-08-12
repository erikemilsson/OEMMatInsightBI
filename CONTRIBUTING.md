# Contributing to OEMMatInsightBI

Welcome! This guide will help you set up your development environment and contribute to the OEMMatInsightBI project.

## 📋 Prerequisites

### Required Software
- **[`uv`](https://docs.astral.sh/uv/)** — manages Python for this repo; you do not need a system Python
- **Java 17** (required for PySpark 4.x; what CI uses)
- **Git 2.x+**
- **Microsoft Fabric** workspace access (for integration testing)
- **Power BI Desktop** (optional, for report development)

### Recommended Tools
- **VS Code** with Python and Jupyter extensions
- **Azure Data Studio** (for SQL development)

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/erikemilsson/OEMMatInsightBI.git
cd OEMMatInsightBI
```

### 2. Set Up Python Environment

Python and its dependencies are managed by [`uv`](https://docs.astral.sh/uv/). Install uv, then there is no further setup step:

```bash
uv run pytest tests/ -v
```

On first run uv reads `.python-version` (3.13) and `pyproject.toml`, downloads the interpreter if needed, creates `.venv`, installs the pinned dev dependencies, and runs. You do not create or activate a venv yourself, and you do not need a system Python.

Useful variants:

```bash
uv run pytest tests/ -q                 # quiet
uv run pytest tests/test_watermark.py   # one file
uv run --python 3.10 pytest tests/      # check the CI floor locally
uv sync                                 # materialise .venv without running anything
```

> **Do not `pip install` into this project.** `pyproject.toml` is the single source of truth for the test runtime. `pyspark` is pinned to exactly `4.0.1` because the repo's cast/ANSI semantics notes are written against that version — a floating range let `4.2.0` resolve, which changes behaviour with no diff to explain it.

### 3. Verify Java Installation
```bash
java -version
# Should show: openjdk version "17.0.x" (what CI uses and what PySpark 4.x expects)
```

If Java is not installed:
- **macOS**: `brew install openjdk@17`
- **Ubuntu**: `sudo apt install openjdk-17-jdk`
- **Windows**: Download from [AdoptOpenJDK](https://adoptopenjdk.net/)

### 4. Run Tests
```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_key_generation.py -v

# Run tests matching pattern
uv run pytest tests/ -k "test_stable_key" -v
```

Expected output: **300 tests passing** in about 30 seconds.

> Coverage is deliberately not wired up: `pytest-cov` is not a dependency and no CI step consumes it. `--cov` will error. Add it to `pyproject.toml` first if you want it.

## 📁 Project Structure

```
OEMMatInsightBI/
├── .github/workflows/    # CI/CD pipelines
├── .claude/              # Spec, decisions, and agent environment (mostly gitignored)
├── docs/                 # Project documentation (canonical)
│   ├── architecture/     # System diagrams
│   ├── guides/          # User guides
│   ├── portfolio/       # Portfolio assets
│   └── setup/           # Setup documentation
├── fabric/              # Microsoft Fabric artifacts
│   ├── *.DataPipeline/  # Orchestration pipelines
│   ├── *.Notebook/      # PySpark notebooks
│   ├── *.Dataflow/      # Data ingestion flows
│   └── *.SemanticModel/ # Power BI models
├── src/                 # Source code
│   └── transformations/ # Reusable functions
├── tests/               # Unit tests
├── pyproject.toml       # Python dependencies + requires-python (uv-managed)
├── .python-version      # Pinned local interpreter (3.13)
├── uv.lock              # Resolved dependency lock — commit it
└── pytest.ini           # Pytest configuration
```

## 🔧 Development Workflow

### 1. Create a Feature Branch
```bash
git checkout -b feature/your-feature-name
```

### 2. Make Changes

#### For Python Code (src/)
- Follow PEP 8 style guidelines
- Add docstrings to all functions
- Write unit tests for new functions

#### For Notebooks (fabric/)
- Test locally with sample data first
- Export to `.py` format for version control
- Document cell purposes with markdown

#### For Semantic Model (TMDL)
- Use display folders for organization
- Add descriptions to measures
- Follow naming conventions

### 3. Test Your Changes
```bash
# Run tests
uv run pytest tests/ -v

# Check code style (optional) — lint tools live in their own group
uv run --group lint black src/ tests/ --check
uv run --group lint flake8 src/ tests/
```

### 4. Commit Your Changes
```bash
git add .
git commit -m "feat: Add your feature description"
```

Follow [Conventional Commits](https://www.conventionalcommits.org/):
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Adding tests
- `refactor:` Code refactoring
- `chore:` Maintenance tasks

### 5. Push and Create PR
```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub.

## 🧪 Testing Guidelines

### Unit Tests
Located in `tests/` directory. We use pytest with the following patterns:

```python
# tests/test_example.py
import pytest
from src.transformations.module import function

def test_function_normal_case(spark):
    """Test normal behavior"""
    result = function(spark, input_data)
    assert result == expected

def test_function_edge_case():
    """Test edge cases"""
    with pytest.raises(ValueError):
        function(None, invalid_data)
```

### Test Fixtures
Common fixtures in `tests/conftest.py`:
- `spark`: PySpark session
- `sample_country_data`: Sample country DataFrame
- `sample_material_data`: Sample material DataFrame

### Running Specific Tests
```bash
# Run tests by marker
uv run pytest -m unit

# Run with verbose output
uv run pytest -v --tb=short

# Run until first failure
uv run pytest -x
```

## 🐛 Debugging Tips

### Common Issues

#### PySpark Not Working
```bash
# Check Java version
java -version

# Set JAVA_HOME if needed
export JAVA_HOME=$(/usr/libexec/java_home -v 17)
```

#### Import Errors
```bash
# Check which interpreter uv is actually using
uv run python -V          # expect 3.13.x
uv run python -c "import pyspark; print(pyspark.__version__)"   # expect 4.0.1

# Rebuild the environment from scratch
rm -rf .venv && uv sync
```

> If a bare `python3 -V` disagrees with `uv run python -V`, that is expected and not a problem — `uv run` is the entry point. Only a bare `python3` matters for tools that shell out to one.

#### Test Failures
```bash
# Run single test with debugging
uv run pytest tests/test_file.py::test_function -vv --tb=long

# Use pytest debugger
uv run pytest --pdb tests/test_file.py
```

## 📝 Code Style

### Python
- Use `black` for formatting
- Follow PEP 8
- Maximum line length: 127 characters
- Use type hints where appropriate

### SQL
- Use UPPERCASE for keywords
- Indent with 4 spaces
- Comment complex logic
- Use CTEs over subqueries

### DAX
- One measure per line in TMDL
- Use variables for clarity
- Include format strings
- Document complex calculations

## 🔍 Code Review Checklist

Before submitting a PR, ensure:

- [ ] All tests pass locally
- [ ] New code has unit tests
- [ ] Documentation is updated
- [ ] No hardcoded values
- [ ] No sensitive data in code
- [ ] Commit messages follow convention
- [ ] PR description explains changes

## 📚 Additional Resources

### Documentation
- [README](./README.md) - Project overview and what it demonstrates
- [Architecture](./docs/architecture/) - System design docs
- [DAX Measure Guide](./docs/guides/dax_measure_guide.md) - Measures explained
- [DAX Measure Library](./docs/dax_measure_library.md) - As-built measure catalogue (45 measures)

### External Resources
- [Microsoft Fabric Documentation](https://learn.microsoft.com/fabric/)
- [PySpark API Reference](https://spark.apache.org/docs/latest/api/python/)
- [DAX Reference](https://dax.guide/)

## 🤝 Getting Help

### Project-Specific
- Check [FAQ](./docs/guides/FAQ.md)
- Review [Troubleshooting Guide](./docs/setup/TROUBLESHOOTING.md)
- Search existing [Issues](https://github.com/erikemilsson/OEMMatInsightBI/issues)

### Contact
- **Project Lead**: Erik Emilsson
- **LinkedIn**: [erikemilsson](https://www.linkedin.com/in/erikemilsson/)
- **GitHub**: [@erikemilsson](https://github.com/erikemilsson)

## 📄 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file.

---

*Thank you for contributing to OEMMatInsightBI! Your improvements help showcase best practices in data engineering and BI development.*