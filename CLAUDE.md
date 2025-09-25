# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GramAddict is a free, open-source Instagram automation bot that operates through Android devices via ADB (Android Debug Bridge). It uses uiautomator2 to simulate human-like interactions on Instagram through actual UI automation rather than API calls, making it safer from detection.

## Architecture

### Core Components

- **GramAddict/core/**: Core functionality modules
  - `bot_flow.py`: Main bot execution flow and session management
  - `device_facade.py`: Android device interaction abstraction layer
  - `navigation.py`: Instagram UI navigation logic
  - `interaction.py`: User interaction simulation (likes, follows, comments)
  - `filter.py`: User filtering logic based on various criteria
  - `session_state.py`: Session persistence and state management
  - `storage.py`: Data storage and analytics
  - `config.py`: Configuration management

- **GramAddict/plugins/**: Action plugins for different bot behaviors
  - `interact_*.py`: Various interaction strategies (hashtags, followers, etc.)
  - `action_unfollow_followers.py`: Unfollowing functionality
  - `telegram.py`: Telegram reporting integration

### Entry Points

- `run.py`: Simple entry point that imports and runs GramAddict
- `GramAddict/__main__.py`: CLI interface with subcommands (init, run, dump)

## Development Commands

### Installation and Setup
```bash
# Install the package
pip3 install GramAddict

# Initialize bot for an account
gramaddict init <instagram_username>

# Install from source (for development)
git clone https://github.com/GramAddict/bot.git gramaddict
cd gramaddict
pip3 install -r requirements.txt
```

### Running the Bot
```bash
# Run with pip installation
gramaddict run --config accounts/username/config.yml

# Run from source
python3 run.py --config accounts/username/config.yml
```

### Development Tools
```bash
# Install dev dependencies (includes linting tools)
pip3 install -e ".[dev]"

# Lint with flake8
flake8 GramAddict/

# Format with black
black GramAddict/

# Sort imports with isort
isort GramAddict/

# Lint with ruff
ruff check GramAddict/

# Dump current screen for debugging
gramaddict dump [--device DEVICE_ID]
```

## Configuration Structure

Bot configurations are stored in `accounts/username/` directories:
- `config.yml`: Main bot configuration
- `filters.yml`: User filtering criteria
- `telegram.yml`: Telegram reporting settings
- `whitelist.txt`: Users to never unfollow
- `blacklist.txt`: Users to avoid
- `comments_list.txt`: Comments for automation
- `pm_list.txt`: Private message templates

## Key Dependencies

- **uiautomator2**: Android UI automation
- **colorama**: Terminal color output
- **PyYAML**: Configuration file parsing
- **ConfigArgParse**: Command-line argument parsing
- **emoji**: Emoji handling for comments
- **langdetect**: Language detection for filtering

## Testing and Debugging

The bot includes a `dump` command to capture screen state for debugging:
```bash
gramaddict dump --device DEVICE_ID
```

This creates a zip file with screenshot and UI hierarchy for troubleshooting.

## Important Notes

- Instagram must be set to English language
- Requires Android 4.4+ device or emulator
- Uses ADB for device communication
- No root access required
- Plugin-based architecture allows easy extension of functionality