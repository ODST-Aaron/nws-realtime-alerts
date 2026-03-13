# Contributing to NWS Real-Time Alert Monitor

Thank you for considering contributing to this project! Here are some guidelines to help you get started.

## How to Contribute

### Reporting Bugs

If you find a bug, please open an issue on GitHub with:
- A clear, descriptive title
- Steps to reproduce the issue
- Expected behavior vs actual behavior
- Your environment (OS, Python version, dependency versions)
- Relevant logs or error messages

### Suggesting Enhancements

Feature requests are welcome! Please open an issue with:
- A clear description of the enhancement
- Use case / motivation for the feature
- Example of how the feature would work

### Pull Requests

1. **Fork the repository** and create a new branch from `main`
2. **Make your changes** — keep them focused and atomic
3. **Test your changes** thoroughly
4. **Update documentation** if needed (README, docstrings, comments)
5. **Submit a pull request** with a clear description of changes

#### Code Style

- Follow PEP 8 style guidelines
- Use type hints where appropriate (Python 3.12+)
- Add docstrings for new functions/classes
- Keep changes minimal and surgical — avoid unnecessary refactoring of working code

#### Testing

Before submitting a PR:
- Test the monitor with your actual locations CSV
- Verify startup, alert detection, and shutdown behavior
- Test with both Discord and Slack webhooks (if applicable)
- Check map generation if you've modified `alert_mapper.py`

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/nws-realtime-alerts.git
cd nws-realtime-alerts

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create a test locations.csv with a few sites
# Configure webhook URLs in weather_alerts.py
# Run the monitor
python weather_alerts.py
```

## Commit Messages

Use clear, descriptive commit messages:
- Start with a verb in present tense (e.g., "Add", "Fix", "Update")
- Keep the first line under 50 characters
- Add detailed explanation in body if needed

Good examples:
```
Add support for custom alert tier colors
Fix polygon matching for MultiPolygon alerts
Update README with Oracle Cloud deployment instructions
```

## Questions?

If you have questions about contributing, feel free to open an issue with the `question` label.

## Code of Conduct

Be respectful and constructive. This is a small project maintained by a NOC engineer — contributions are appreciated, but please be patient with review times.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
