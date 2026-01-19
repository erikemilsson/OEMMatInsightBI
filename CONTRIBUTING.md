# Contributing to OEMMatInsightBI

Welcome! This guide will help you set up your development environment and contribute to the OEMMatInsightBI project.

## 📋 Prerequisites

### Required Software
- **Python 3.10+** (3.11 or 3.12 recommended)
- **Java 11+** (required for PySpark)
- **Git 2.x+**
- **Microsoft Fabric** workspace access (for integration testing)
- **Power BI Desktop** (optional, for report development)

### Recommended Tools
- **VS Code** with Python and Jupyter extensions
- **Azure Data Studio** (for SQL development)
- **Claude Code CLI** (for task management)

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/erikemilsson/OEMMatInsightBI.git
cd OEMMatInsightBI
```

### 2. Set Up Python Environment
```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements-test.txt
```

### 3. Verify Java Installation
```bash
java -version
# Should show: openjdk version "11.0.x" or higher
```

If Java is not installed:
- **macOS**: `brew install openjdk@11`
- **Ubuntu**: `sudo apt install openjdk-11-jdk`
- **Windows**: Download from [AdoptOpenJDK](https://adoptopenjdk.net/)

### 4. Run Tests
```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run specific test file
pytest tests/test_key_generation.py -v

# Run tests matching pattern
pytest tests/ -k "test_stable_key" -v
```

Expected output: **33 tests passing** in ~11 seconds

## 📁 Project Structure

```
OEMMatInsightBI/
├── .github/workflows/    # CI/CD pipelines
├── .claude/              # Claude Code task management
├── docs/                 # Project documentation
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
├── requirements-test.txt # Python dependencies
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
pytest tests/ -v

# Check code style (optional)
black src/ tests/ --check
flake8 src/ tests/
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
pytest -m unit
pytest -m integration
pytest -m slow

# Run with verbose output
pytest -v --tb=short

# Run until first failure
pytest -x
```

## 📊 Task Management

This project uses Claude Code task management:

### View Tasks
```bash
# View current status and action items
cat MISSION_CONTROL.md

# View specific task
cat .claude/tasks/task-014.json
```

### Work on a Task
```bash
# Use Claude Code CLI
/complete-task task-014

# Or manually update task status
# Edit .claude/tasks/task-014.json
```

### Task Priorities
- **P1**: Portfolio showcase features
- **P2**: Technical depth demonstrations
- **P3**: Infrastructure improvements

## 🐛 Debugging Tips

### Common Issues

#### PySpark Not Working
```bash
# Check Java version
java -version

# Set JAVA_HOME if needed
export JAVA_HOME=$(/usr/libexec/java_home -v 11)
```

#### Import Errors
```bash
# Ensure virtual environment is activated
which python
# Should show: /path/to/OEMMatInsightBI/.venv/bin/python

# Reinstall dependencies
pip install -r requirements-test.txt --force-reinstall
```

#### Test Failures
```bash
# Run single test with debugging
pytest tests/test_file.py::test_function -vv --tb=long

# Use pytest debugger
pytest --pdb tests/test_file.py
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
- [Project Definition](./project_definition.md) - Complete project specification
- [Architecture Diagrams](./docs/architecture/) - System design visuals
- [DAX Measure Guide](./docs/guides/MEASURE_GUIDE.md) - All measures explained

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