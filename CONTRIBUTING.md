# 🤝 Contributing to LocAi

Thank you for your interest in contributing to **LocAi**! We welcome contributions from developers of all skill levels.

---

## 📋 Table of Contents
- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Code Style & Standards](#code-style--standards)
- [Testing Guidelines](#testing-guidelines)
- [Commit Message Conventions](#commit-message-conventions)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Community & Support](#community--support)

---

## Code of Conduct
We are committed to providing a welcoming, inclusive, and harassment-free environment for everyone. Please be respectful, considerate, and collaborative.

---

## Getting Started

### Prerequisites
- **Python 3.11+**
- **Git**
- **Ollama** (for local agent testing)

### Setup Development Environment
1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/ilhanakd-max/Local_Ajan.git
   cd Local_Ajan
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate       # On Linux/macOS
   # .venv\Scripts\activate       # On Windows PowerShell
   ```

3. **Install dependencies in editable/dev mode:**
   ```bash
   pip install -e ".[dev]"
   ```

4. **Verify tests:**
   ```bash
   pytest
   ```

---

## Development Workflow

1. **Create a topic branch from `main`:**
   ```bash
   git checkout -b feat/my-new-feature
   # or
   git checkout -b fix/issue-description
   ```
2. **Implement changes with clean, modular code.**
3. **Add or update tests in `tests/`** to cover your changes.
4. **Ensure all tests pass:**
   ```bash
   pytest -v
   ```

---

## Code Style & Standards

- Follow **[PEP 8](https://peps.python.org/pep-0008/)** standards.
- Use explicit type annotations wherever possible.
- Keep tool interfaces concise and safe: tool definitions sent to local LLMs should remain compact to fit inside limited context windows.
- Provide descriptive docstrings for public classes and functions:
  ```python
  def read_file(path: str, max_chars: int = 50000) -> str:
      """
      Read file contents safely within the workspace.

      Args:
          path: Relative or absolute path to the file.
          max_chars: Character limit to avoid context flooding.

      Returns:
          File content string.
      """
  ```

---

## Testing Guidelines

Run the test suite before submitting PRs:
```bash
# Run all unit tests
pytest

# Run with verbose output
pytest -v

# Run a specific test module
pytest tests/test_agent.py
```

When adding new tools or model profiles, ensure edge cases (e.g. malformed JSON tool calls, missing files, shell timeouts) are covered with unit tests.

---

## Commit Message Conventions

We follow Conventional Commits formatting:
```text
<type>(<scope>): <short description>

[optional body]
[optional footer]
```

### Types:
- `feat`: A new feature or tool
- `fix`: A bug fix
- `docs`: Documentation updates
- `style`: Formatting, missing semicolons, etc. (no code logic change)
- `refactor`: Code restructuring without changing behavior
- `perf`: Code change that improves performance
- `test`: Adding or correcting tests
- `chore`: Build process or tooling changes

**Example:**
```bash
git commit -m "feat(profile): optimize system prompt for qwen3 0.6b"
```

---

## Submitting a Pull Request

1. Push your branch to your GitHub fork:
   ```bash
   git push origin feat/my-new-feature
   ```
2. Open a Pull Request against `main` on [ilhanakd-max/Local_Ajan](https://github.com/ilhanakd-max/Local_Ajan).
3. Fill out the PR template with a clear description, related issue numbers, and testing confirmation.
4. Respond to feedback and collaborate on reviews.

---

## Community & Support

- 💬 **Discussions:** [GitHub Discussions](https://github.com/ilhanakd-max/Local_Ajan/discussions)
- 🐛 **Issues:** [GitHub Issues](https://github.com/ilhanakd-max/Local_Ajan/issues)
- 🌐 **Website:** [locai-cli.netlify.app](https://locai-cli.netlify.app/)

Thank you for helping make LocAi better! 🚀
