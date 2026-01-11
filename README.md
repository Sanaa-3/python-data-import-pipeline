## Overview
This project simulates a client onboarding data import.  
I was given data exported from a client’s existing system and asked to transform it into two CSV files that match CueBox’s import format.

The goal of the project is to correctly clean, normalize, and validate the data while clearly documenting assumptions and edge cases.

The script produces:
- `cuebox_constituents.csv`
- `cuebox_tags.csv`

## How to Run

1. (Optional) Create and activate a virtual environment
2. Install dependencies: 
`pip install -r requirements.txt`
3. Place the provided spreadsheet at:
`data/input.xlsx`
4. Run the script: 
`python main.py`
5. The output CSVs will be written to:
- `data/output/cuebox_constituents.csv`
- `data/output/cuebox_tags.csv`

## Assumptions & Decisions

- **Primary key:** Patron ID is treated as the authoritative identifier for a constituent.
- **Duplicate Patron IDs:**  
If multiple rows share the same Patron ID, I keep the row with the most non-empty fields (tie-breaker: most recent Date Entered).
- **Emails:**  
- Prefer Primary Email when present.  
- If missing, fall back to the Emails table.  
- Keep up to two unique, valid-format emails.  
- Email 2 is never populated unless Email 1 exists.  
- Email validation is format-based only; domains are not corrected or guessed.
- **Names:**
- Normalized name casing for consistency; no name values were inferred or restructured.
- **Tags:**  
- Tags are split, trimmed, and deduplicated per constituent.  
- Tag names are mapped using the provided API. If the API is unavailable, tags are left unchanged.  
- If multiple original tags map to the same cleaned tag, they are deduplicated before counting.
- **Donations:**  
- Only donations with `Status = "Paid"` are included in rollups.  
- Refunded donations are excluded.  
- Donation fields are left blank for constituents with no paid donations.
- **Timestamps:**  
- When the source data only includes a date, timestamps default to `00:00:00` using ISO format.
- **Missing data:**  
- Missing names, emails, or other attributes are left blank rather than inferred or fabricated.

## QA Checks

- Verified that all Paid donations have non-null amounts before aggregation.
- Confirmed there is exactly one output row per CB Constituent ID.
- Checked that Email 2 never exists without Email 1.
- Ensured tag counts reflect unique constituents, not raw rows.
- Validated final CSV columns match the import specification exactly.

## AI Usage Statement

I used ChatGPT for guidance on approach, clarification of requirements, and help understanding data engineering patterns.  
All code, decisions, and validation were done by me, and no output was used without manual review and understanding.
I used ChatGPT for debugging as well.