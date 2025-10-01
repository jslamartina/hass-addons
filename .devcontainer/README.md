# Devcontainer Setup Scripts

This directory contains setup scripts for the CyncLAN development environment.

## File Organization

### Setup Scripts (in execution order)

#### Addon Development (Node.js/Prettier)
- **`00-addon-setup-nodejs.sh`** - Sets up Node.js and Prettier for addon development
- **`addon-format-code.sh`** - Formats code with Prettier (utility script)

#### Python Package Development (cync-lan)
- **`01-python-setup-env.sh`** - Sets up Python development environment
- **`02-python-clone-repo.sh`** - Clones the cync-lan repository
- **`03-python-setup-workspace.sh`** - Sets up development workspace
- **`04-python-configure-vscode.sh`** - Configures VS Code for Python development

#### Master Scripts
- **`99-python-setup-all.sh`** - Runs all Python development scripts in order (01-04)

### Workspace Files
- **`hass-cync-dev.code-workspace`** - Multi-root workspace configuration (in repo root)

## Devcontainer Configuration

The main `.devcontainer.json` file (in the root directory) is configured to:
1. Use the Home Assistant devcontainer base image
2. Install Python 3.12 with development tools
3. Mount your local `cync-lan` repository for live editing
4. Automatically run setup scripts on container creation:
   - `00-addon-setup-nodejs.sh` (Node.js/Prettier)
   - `99-python-setup-all.sh` (Python environment & cync-lan repo)

## Usage

### Automatic (via devcontainer)
The scripts run automatically when the devcontainer is created.

### Manual
```bash
# Run all Python development setup
bash .devcontainer/99-python-setup-all.sh

# Run individual scripts in order
bash .devcontainer/00-addon-setup-nodejs.sh    # Addon setup first
bash .devcontainer/01-python-setup-env.sh      # Then Python env
bash .devcontainer/02-python-clone-repo.sh     # Clone repo
bash .devcontainer/03-python-setup-workspace.sh # Setup workspace
bash .devcontainer/04-python-configure-vscode.sh # Configure IDE

# Format code (utility)
bash .devcontainer/addon-format-code.sh
```

## Directory Structure After Setup

```
/mnt/supervisor/addons/local/
├── hass-addons/           # Home Assistant addon repository
│   ├── cync-lan-source/   # Symlink to cync-lan repo
│   ├── hass-cync-dev.code-workspace  # Multi-repo workspace file
│   └── test-cync-lan.sh   # Test script
├── cync-lan/              # Python package repository
└── .vscode/               # Global VS Code settings
```

## Development Workflow

### Multi-Repository Setup

**To automatically load both repositories:**
1. From your **local machine**, open the file: `hass-cync-dev.code-workspace`
2. VS Code/Cursor will prompt to "Reopen in Container"
3. Both repositories will load automatically in the multi-root workspace

**If you opened the folder first (single repo view):**
1. Inside the container, click File → Open Workspace from File
2. Select: `hass-cync-dev.code-workspace`
3. This will reload with both hass-addons and cync-lan repositories

### Daily Development
1. Make changes to either repository
2. Test with: `./test-cync-lan.sh`
3. Format code: `npm run format`

