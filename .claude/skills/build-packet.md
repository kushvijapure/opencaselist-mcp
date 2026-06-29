# Build Packet

Compile selected cards into a downloadable .docx evidence packet.

## Usage
/build-packet [search query or list of card IDs] [optional: --title "Packet Title"] [optional: --group-by pocket|block|source_file|none]

## Instructions

1. If the user gave a search query (not card IDs), call `search_cards` first and show results. Ask them to confirm which cards to include — they can say "all", give numbers, or give card IDs.

2. Collect the `card_id` values for all selected cards.

3. Call `build_card_packet` with:
   - `card_ids` — the selected IDs
   - `title` — from user input, or generate one from the query
   - `group_by` — from user input (default: "pocket")
   - `include_source_metadata: true` unless user says otherwise

4. Report:
   - Path to the generated .docx
   - Number of cards included
   - Number of groups

5. Tell the user the file is at the returned path and ready to open in Word or Verbatim.

## Notes
- Cards must be indexed first (via `parse_debate_docx`) for their IDs to be valid.
- The packet preserves Verbatim-compatible paragraph styles where possible.
