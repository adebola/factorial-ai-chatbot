# Python Environment Setup Guide

## Overview

All FastAPI microservices in this project use **Python 3.11** to match the Docker production environment. This ensures consistency between development, IDE execution, and production deployments.

## Why Python 3.11?

- **Docker Compatibility**: All Dockerfiles use `python:3.11-slim` base image
- **Dependency Compatibility**: Ensures uvicorn, websockets, and other packages work identically across environments
- **IDE Consistency**: Prevents ModuleNotFoundError when running services from IDE vs command line
- **Production Parity**: Development environment matches production exactly

## Initial Setup

### 1. Install Python 3.11

```bash
# macOS (Homebrew)
brew install python@3.11

# Verify installation
python3.11 --version  # Should show Python 3.11.x
```

### 2. Create Virtual Environment for Each Service

Run this for **each** service (chat-service, onboarding-service, communications-service, workflow-service):

```bash
cd <service-directory>

# Create venv with Python 3.11
python3.11 -m venv venv

# Activate venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

## Running Services

### From Command Line

```bash
cd <service-directory>

# Use venv Python directly (recommended)
./venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port <PORT> --reload
```

### From IDE (PyCharm, VS Code, etc.)

Configure your IDE to use the venv Python interpreter:

**Path**: `<service-directory>/venv/bin/python3`

Example for workflow-service:
```
/Users/<username>/path/to/backend/workflow-service/venv/bin/python3
```

The IDE should automatically detect and use this interpreter for running configurations.

## Verification

After setup, verify each service venv:

```bash
cd <service-directory>

# Check Python version
./venv/bin/python3 --version
# Output: Python 3.11.x

# Check critical packages
./venv/bin/pip list | grep -E "(uvicorn|websockets)"
# Output should show:
# uvicorn           0.37.0
# websockets        14.2
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'websockets.legacy'"

**Cause**: Using Anaconda Python or wrong venv with incompatible websockets version

**Solution**:
1. Ensure you're using the service's venv Python 3.11
2. Check uvicorn and websockets versions match requirements.txt
3. Recreate venv if needed

### IDE Not Finding Modules

**Cause**: IDE is using system Python instead of venv

**Solution**:
1. In IDE settings, set Python interpreter to `<service>/venv/bin/python3`
2. Restart IDE
3. Verify interpreter in IDE status bar shows correct venv path

### Different Behavior: Command Line vs IDE

**Cause**: Command line using Anaconda, IDE using venv (or vice versa)

**Solution**:
- **Always use venv**: `./venv/bin/python3 -m uvicorn ...`
- Configure IDE to use venv interpreter
- Avoid using `uvicorn` command directly (uses whatever's in PATH)

## Docker Build Verification

Since Docker uses Python 3.11, your local venv should produce identical behavior:

```bash
cd <service-directory>

# Test locally with venv
./venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port <PORT>

# Build Docker image
docker build -t <service-name>:test .

# Run Docker container
docker run -p <PORT>:<PORT> <service-name>:test

# Both should behave identically
```

## Environment Consistency Matrix

| Environment | Python Version | Source |
|------------|----------------|--------|
| **Development (venv)** | 3.11.13 | Homebrew |
| **Docker (production)** | 3.11-slim | python:3.11-slim image |
| **IDE (PyCharm/VS Code)** | 3.11.13 | Service venv |

## Adding New Services

When creating a new FastAPI service:

1. **Dockerfile**: Use `FROM python:3.11-slim`
2. **Local venv**: Create with `python3.11 -m venv venv`
3. **requirements.txt**: Include at minimum:
   ```
   fastapi>=0.115.0
   uvicorn[standard]>=0.32.0
   websockets>=14.0,<15.0
   ```
4. **Test**: Verify service runs identically in venv and Docker

## Best Practices

1. **Never use Anaconda Python for services**: Anaconda may have different package versions
2. **Always activate venv**: `source venv/bin/activate` before installing packages
3. **Use explicit Python path**: Prefer `./venv/bin/python3` over `python` or `python3`
4. **Keep requirements.txt updated**: Always add new dependencies with exact versions
5. **Verify Docker parity**: Test Docker builds regularly to catch environment drift

## Cleanup

If you encounter issues, recreate the venv:

```bash
cd <service-directory>

# Backup old venv
mv venv venv.backup.old

# Create fresh venv
python3.11 -m venv venv

# Install dependencies
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# Verify
./venv/bin/python3 --version
./venv/bin/pip list
```

## Notes

- Old venvs are backed up as `venv.backup.old` - safe to delete after verifying new setup works
- All services now use consistent Python 3.11 environment
- This matches production Docker containers exactly
- IDE configurations will need to be updated to point to new venv paths
