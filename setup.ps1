# setup.ps1
# =========
# Run this once from the repo root to create all files and folders.
# Usage: .\setup.ps1

$base = $PSScriptRoot

# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------
$folders = @(
    "db",
    "images",
    "example",
    "example\components",
    "example\grids",
    "tests",
    ".github\workflows"
)
foreach ($f in $folders) {
    New-Item -ItemType Directory -Force -Path "$base\$f" | Out-Null
}

# ---------------------------------------------------------------------------
# .gitkeep placeholders
# ---------------------------------------------------------------------------
New-Item -ItemType File -Force -Path "$base\db\.gitkeep"    | Out-Null
New-Item -ItemType File -Force -Path "$base\images\.gitkeep" | Out-Null

# ---------------------------------------------------------------------------
# .gitignore
# ---------------------------------------------------------------------------
@"
# Database
db/*.db
db/*.sqlite

# Python
__pycache__/
*.py[cod]
*.pyo
.venv/
.env
*.egg-info/
dist/
build/

# uv
.python-version

# IDE
.vscode/
.idea/
"@ | Set-Content "$base\.gitignore" -Encoding UTF8

# ---------------------------------------------------------------------------
# requirements.txt
# ---------------------------------------------------------------------------
@"
nicegui>=2.0.0
sqlmodel>=0.0.16
"@ | Set-Content "$base\requirements.txt" -Encoding UTF8

# ---------------------------------------------------------------------------
# __init__.py files
# ---------------------------------------------------------------------------
"# nicegui-aggrid-crud demo package"  | Set-Content "$base\example\__init__.py"          -Encoding UTF8
""                                     | Set-Content "$base\example\components\__init__.py" -Encoding UTF8
""                                     | Set-Content "$base\example\grids\__init__.py"      -Encoding UTF8
""                                     | Set-Content "$base\tests\__init__.py"              -Encoding UTF8

Write-Host ""
Write-Host "Done. Now copy your Python files into the correct folders:"
Write-Host "  example\          <- main.py, models.py, database.py, services.py"
Write-Host "  example\components <- crud_grid.py, columns.py, formatters.py"
Write-Host "  example\grids      <- product_grid.py, cart_grid.py, order_line_grid.py"
Write-Host ""
Write-Host "Then run:  uv run python -m example.main"