ISCC := "C:\Program Files\Inno Setup 7\ISCC.exe"

.PHONY: help setup run clean icon build-exe installer clean-build changelog bump

# Default target when you just type 'make'
help:
	@echo "Available commands:"
	@echo "  make setup       - Install dependencies and the commit-message hook"
	@echo "  make run         - Run the main script via Poetry"
	@echo "  make icon        - Regenerate assets/icon.ico and icon.png"
	@echo "  make build-exe   - Build dist/VoucherManager.exe from VoucherManager.spec"
	@echo "  make installer   - Build the exe, then the Inno Setup installer"
	@echo "  make changelog   - Regenerate CHANGELOG.md from commit history"
	@echo "  make bump        - Bump version from commits, update changelog, tag"
	@echo "  make clean       - Remove Python cache files"
	@echo "  make clean-build - Remove build/, dist/ and Output/"

# Initialize dependencies
setup:
	poetry install
	poetry run pre-commit install --hook-type commit-msg

changelog:
	poetry run cz changelog

# Picks the next version from commit types (fix -> patch, feat -> minor),
# updates pyproject.toml, app/__init__.py and CHANGELOG.md, commits and tags.
bump:
	poetry run cz bump

# Run the Tkinter script within the Poetry environment
run:
	poetry run python main.py

# Clean up Python cache and temporary files
clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

icon:
	poetry run python tools/make_icon.py

# The spec is the single source of build settings (version info, no UPX, etc.)
build-exe:
	poetry run pyinstaller --noconfirm VoucherManager.spec

installer: build-exe
	$(ISCC) installer.iss

clean-build:
	rm -rf build dist Output
