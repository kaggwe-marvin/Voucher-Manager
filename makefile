ISCC := "C:\Program Files\Inno Setup 7\ISCC.exe"

.PHONY: help setup run clean icon build-exe installer clean-build

# Default target when you just type 'make'
help:
	@echo "Available commands:"
	@echo "  make setup       - Install project dependencies using Poetry"
	@echo "  make run         - Run the main script via Poetry"
	@echo "  make icon        - Regenerate assets/icon.ico and icon.png"
	@echo "  make build-exe   - Build dist/VoucherManager.exe from VoucherManager.spec"
	@echo "  make installer   - Build the exe, then the Inno Setup installer"
	@echo "  make clean       - Remove Python cache files"
	@echo "  make clean-build - Remove build/, dist/ and Output/"

# Initialize dependencies
setup:
	poetry install

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
