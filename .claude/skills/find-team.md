# Find Team

Find a team's disclosed files on OpenCaselist.

## Usage
/find-team [team name or wiki URL] [optional: --side aff|neg] [optional: --year YYYY]

## Instructions

1. If the user gave a team name (not a URL), first call `search_opencaselist` with the team name and any year filter. Present the top results and ask the user to confirm which team page to use.

2. Once you have the team page URL or title, call `get_team_files` with any side/keyword filters.

3. Present the results:
   - Team name, school, topic, year
   - Table of disclosed files: name, side (inferred from filename if possible), download URL
   - List of round subpages if available

4. Ask the user: "Would you like me to download and index any of these files?"
   - If yes, call `download_docx` for the chosen file, then immediately call `parse_debate_docx` on the downloaded path.
   - If no, show the wiki URL and file URLs so they can access manually.

## Notes
- Never download more than the files the user explicitly selects.
- If the wiki is unreachable or login is required, return the wiki URL and tell the user to access it manually.
