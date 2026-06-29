# Parse File

Index a local debate .docx file into the card search index.

## Usage
/parse-file [file_path] [optional metadata: team, school, tournament, round, side, year, topic]

## Instructions

1. Call `parse_debate_docx` with the provided file path and any metadata the user gave.
2. Report back:
   - Whether the file uses Verbatim formatting or generic formatting
   - How many cards were indexed
   - The first 5 cards as a preview (tag + cite)
   - Any parse errors
3. If the parse succeeded, tell the user they can now search with `/search-evidence` or `search_cards`.
4. If no metadata was provided, ask the user if they want to add team/tournament/side info to the cards now — this makes search results more useful. If yes, call `parse_debate_docx` again with the metadata.

## Metadata fields
- `team` — team code (e.g. "Harvard KP")
- `school` — school name
- `tournament` — tournament name (e.g. "NDT 2024")
- `round` — round number
- `side` — "aff" or "neg"
- `year` — season year (e.g. "2024")
- `topic` — topic slug (e.g. "24-25NationalCircuit")
- `source_url` — download URL for this file
- `wiki_url` — wiki page where this file is listed
