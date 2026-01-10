import pandas as pd
import numpy as np
import re
import os

INPUT_PATH = "data/input.xlsx"
OUTPUT_DIR = "data/output"

# Regular expression for validating email addresses
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

#Functtion to clean and standardize string values
#converts NaN/None to empty string
#strips whitespace
def as_clean_str(x):
    if pd.isna(x):
        return ""
    return str(x).strip()

#Funtion to measure how “filled out” each row is
def completeness_score(df):
    cleaned = df.copy()
    for col in cleaned.columns:
        cleaned[col] = cleaned[col].apply(as_clean_str)
        cleaned[col] = cleaned[col].replace({"": np.nan})
    #counts how many non-missing cells exist per row
    return cleaned.notna().sum(axis=1)


def dedupe_constituents(df):
    df = df.copy()
    df["Patron ID"] = df["Patron ID"].astype(str)

    df["_score"] = completeness_score(df)
    df["_date"] = pd.to_datetime(df["Date Entered"], errors="coerce")

    #Sorts so the “best” row per Patron ID comes first
    df = df.sort_values(
        by=["Patron ID", "_score", "_date"],
        ascending=[True, False, False]
    )
    #Drops duplicate Patron IDs (keeps the 1 one)        #Removes helper columns 
    return df.drop_duplicates("Patron ID", keep="first").drop(columns=["_score", "_date"])

#filters out things that obviously aren’t emails. (which is all of them in this case according to the regex)
def is_valid_email(email):
    return bool(EMAIL_REGEX.match(email))

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    constituents = pd.read_excel(INPUT_PATH, sheet_name="Input Constituents")
    emails = pd.read_excel(INPUT_PATH, sheet_name="Input Emails")

    # Deduplicate constituents
    constituents = dedupe_constituents(constituents)

    # Build email lookup
    emails["Patron ID"] = emails["Patron ID"].astype(str)
    emails["Email"] = emails["Email"].apply(as_clean_str).str.lower()
    emails = emails[emails["Email"].apply(is_valid_email)]

    email_map = emails.groupby("Patron ID")["Email"].apply(list).to_dict()

    def resolve_emails(row):
        primary = as_clean_str(row.get("Primary Email")).lower()
        others = email_map.get(row["Patron ID"], [])

        candidates = []
        if primary:
            candidates.append(primary)
        candidates.extend(others)

        seen = []
        for e in candidates:
            if e not in seen:
                seen.append(e)

        email1 = seen[0] if len(seen) > 0 else ""
        email2 = seen[1] if len(seen) > 1 else ""

        if not email1:
            email2 = ""

        return pd.Series([email1, email2])

    constituents[["Email 1", "Email 2"]] = constituents.apply(resolve_emails, axis=1)

    # Minimal output (partial, on purpose)
    output = pd.DataFrame({
        "CB Constituent ID": constituents["Patron ID"],
        "CB Email 1 (Standardized)": constituents["Email 1"],
        "CB Email 2 (Standardized)": constituents["Email 2"],
    })

    output.to_csv(f"{OUTPUT_DIR}/constituents_step2.csv", index=False)

    print("Checkpoint 2 complete: constituents_step2.csv written")

if __name__ == "__main__":
    main()
