# brave-ai-grounding-cli

CLI tool for Brave AI Grounding API - get synthesized, cited answers from web sources.

## Installation

From the repository root:

```bash
pip install -e tools/brave-ai-grounding-cli/
```

## Configuration

### Option 1: Package `.env` file (Recommended for standalone use)

```bash
cd tools/brave-ai-grounding-cli
cp .env.example .env
# Edit .env and add your API key
```

### Option 2: Environment variable

```bash
export BRAVE_AI_GROUNDING_API_KEY=your_api_key_here
```

### Option 3: Repository `hass-credentials.env` (Automatic in hass-addons repo)

The tool automatically searches upward from the current directory for `hass-credentials.env`.

Get your API key from: <https://brave.com/search/api/>

## Usage

### Basic query

```bash
brave-ai-grounding-cli "What is quantum computing?"
```

### Research mode (deep research with multiple searches)

```bash
brave-ai-grounding-cli "Explain the latest developments in quantum computing" --research
```

### Without citations

```bash
brave-ai-grounding-cli "What is machine learning?" --no-citations
```

## Output

- **Main content**: Synthesized answer streams in real-time
- **Sources**: Numbered list of citation URLs with snippets
- **Usage metrics**: Token counts and cost tracking

## Options

- `--research`: Enable deep research mode (slower, more comprehensive)
- `--no-citations`: Disable citations (faster responses)
