# Contributing to Helix Hub Shared

We welcome contributions to the Helix Hub Shared infrastructure! This guide explains how to get started.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/helix-hub-shared.git`
3. Create a branch: `git checkout -b feature/your-feature`
4. Make changes and commit: `git commit -am 'Add feature'`
5. Push to branch: `git push origin feature/your-feature`
6. Submit a pull request

## Development Setup

```bash
git clone https://github.com/Deathcharge/helix-hub-shared.git
cd helix-hub-shared
pip install -e ".[dev]"
pip install -r requirements-test.txt
```

## Running Tests

```bash
pytest tests/ -v
pytest tests/ --cov
pytest tests/ -m engine  # Run specific marker
pytest tests/ -m integration  # Run integration tests
```

## Coding Standards

- Follow PEP 8
- Use type hints
- Write comprehensive docstrings
- Keep lines under 100 characters
- Use meaningful variable names
- Add tests for new features (minimum 80% coverage)

## Documentation

Update documentation for new features:

- Update README.md for major changes
- Update GETTING_STARTED.md for new patterns
- Add examples for new features
- Update API documentation
- Add inline code comments for complex logic

## Pull Request Process

1. Ensure all tests pass: `pytest tests/`
2. Add tests for new functionality
3. Update documentation as needed
4. Provide a clear description of changes
5. Reference any related issues
6. Wait for review and feedback

## Code Review Guidelines

- Be respectful and constructive
- Focus on the code, not the person
- Suggest improvements, don't demand
- Acknowledge good work
- Help reviewees improve

## Testing Requirements

- Minimum 80% code coverage
- All tests must pass
- Add tests for edge cases
- Test error conditions
- Include integration tests

## Commit Message Format

```
<type>: <subject>

<body>

<footer>
```

Types: feat, fix, docs, style, refactor, test, chore

Example:
```
feat: Add agent communication logging

- Implement message logging for all agent communications
- Add history retrieval functionality
- Add tests for logging functionality

Fixes #123
```

## Questions?

- Open an issue for questions
- Check existing documentation
- Review past pull requests
- Contact maintainers

## Code of Conduct

Please follow our [Code of Conduct](CODE_OF_CONDUCT.md).
