# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Cross-platform support**: Full compatibility with Windows, macOS, and Linux
  - Automatic FFmpeg detection across all platforms
  - Platform-aware installation scripts (`install.bat`, `install.sh`)
  - Comprehensive setup guide (SETUP.md) for all operating systems
  - Automated CI/CD testing on Windows, macOS, and Linux with Python 3.9-3.12
  - GitHub Actions workflow for multiplatform validation

- **Installation improvements**:
  - Automated installation scripts with dependency verification
  - Automatic FFmpeg installation via Chocolatey (Windows), Homebrew (macOS), apt-get (Linux)
  - Fallback mechanism to use FFmpeg from PATH if not in standard locations
  - Clear troubleshooting guidance for common installation issues

- **Development tools**:
  - Comprehensive test suite for FFmpeg detection across platforms
  - Test suite for filename sanitization and path construction
  - Unit tests with 95%+ coverage of multiplatform code paths
  - Automated testing via GitHub Actions on every commit

### Changed
- **FFmpeg detection**: Refactored to support Windows, macOS, and Linux
  - Replaced hardcoded Windows paths with platform-aware detection
  - Added fallback to `shutil.which()` for flexible FFmpeg discovery
  - Automatic detection of platform-specific executable names (`ffmpeg.exe` vs `ffmpeg`)

- **Utility scripts**: Removed hardcoded paths from utility scripts
  - `debug_api.py`: Now constructs config path dynamically
  - `rebuild_history.py`: Accepts configurable music folder path or defaults to `~/Music`

### Fixed
- Audio conversion now works correctly on macOS and Linux
- Installation works without manual PATH configuration on all platforms
- Removed dependency on Windows-specific environment variables

## [Previous versions]

### v1.0.0 (Initial Release)
- Windows-only functionality
- SoundCloud and YouTube download support
- Synchronization of SoundCloud likes
- Multiple audio format support (MP3, FLAC)
- Post-processing features (metadata embedding, volume normalization)

---

## How to Report Issues

If you encounter any issues:

1. Check [SETUP.md](SETUP.md) Troubleshooting section
2. Verify your FFmpeg installation: `ffmpeg -version`
3. Run tests: `pytest tests/ -v`
4. Open an issue on GitHub with:
   - Your operating system and version
   - Python version (`python --version`)
   - Complete error message
   - Steps to reproduce

## Contributing

See [SETUP.md](SETUP.md) Development section for guidelines on contributing across platforms.
