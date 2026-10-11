# Film-Themed Decision Assessment Web Application

A Flask-based assessment web app spanning three themes and nine films (sci-fi, fantasy, anime), built around a five-dimension decision-style scoring framework (Rationality, Altruism, Aggressiveness, Efficiency, Caution).

## Project Overview
Parses a Markdown question bank into structured data, scores user choices across five decision dimensions, matches users to film characters via score rules and renders radar charts for visual feedback.

## Tech Stack
- Python, Flask
- Regex-based Markdown parser (question-bank validation)
- Matplotlib radar chart rendering (PNG byte streams, no local file writes)
- Robust input sanitisation (None/NaN/inf handling, 0–100 score clamping)

## Key Features
- Parser extracts stage-one warm-up questions, sandbox allocation/game/selection stages across 9 films and validates structural completeness (3 themes × 9 films)
- Score-draw renders five-dimension radar charts with theme-matched colour presets (cyber / magic / anime)
- Role-matching engine: character analysis text + optional cosine-similarity vector matching
- Character library externalised to `roles.json` with LRU caching; graceful fallback to built-in library

## Files
- `parser.py`: Markdown question-bank parser + validation
- `score_draw.py`: radar chart generator + character analysis module
- `roles.json`: character role library
- `question_bank.md`: structured question bank (three themes, nine films)
- `app.py`: Flask web entry point (if applicable)
- `requirements.txt`: dependency list

## Sample Output
<img width="1464" height="779" alt="216499b91875e340e8a7da07f460031e" src="https://github.com/user-attachments/assets/1df13544-a392-41cf-bb8a-4f7687d8119e" />


