ISCC := "C:\Program Files\Inno Setup 7\ISCC.exe"

.PHONY: setup run clean help

# Default target when you just type 'make'
help:
	@echo "Available commands:"
	@echo "  make setup  - Install project dependencies using Poetry"
	@echo "  make run    - Run the main script via Poetry"
	@echo "  make clean  - Remove Python cache files"

# Initialize dependencies
setup:
	poetry install

# Run the Tkinter script within the Poetry environment
run:
	poetry run python main.py

# Clean up Python cache and temporary files
clean:
	rm -rf __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build-exe:
	poetry run pyinstaller --onefile --windowed --name VoucherManager main.py
 
installer: build-exe
	$(ISCC) installer.iss
 
clean-build:
	rmdir /s /q build dist Output 2>nul || true
	del /q VoucherManager.spec 2>nul || true
