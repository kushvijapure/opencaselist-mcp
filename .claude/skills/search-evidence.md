# Search Evidence

Search the local card index for debate evidence matching a query.

## Usage
/search-evidence [query] [optional: --field tag|cite|card_text] [optional: --exact] [optional: --side aff|neg] [optional: --year YYYY]

## Instructions

Call `search_cards` with the user's query. If the user passed flags, map them:
- `--field` → `search_field`
- `--exact` → `exact: true`
- `--side` → `filters.side`
- `--year` → `filters.year`
- `--team` → `filters.team`
- `--school` → `filters.school`

Default: `limit: 20`, `search_field: "all"`, `exact: false`.

After getting results, present them in a readable table:

| # | Tag (truncated) | Cite | Team | Tournament | Side | Source file |
|---|-----------------|------|------|------------|------|-------------|

For each result include the `card_id` so the user can reference it in `build_card_packet`.

If `total_indexed_cards` is 0, tell the user they need to index files first using `parse_debate_docx` or `/parse-file`.

If results are empty, suggest broadening the query or searching a different field.
