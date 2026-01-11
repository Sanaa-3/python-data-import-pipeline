import pandas as pd
import numpy as np
import re
import os
import requests

INPUT_PATH = "data/input.xlsx"
OUTPUT_DIR = "data/output"

# Regular expression for validating email addresses
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

#
TAG_MAPPING_API = "https://6719768f7fc4c5ff8f4d84f1.mockapi.io/api/v1/tags"

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

#Splits a comma-separated tag string into a list of unique, trimmed tags
def split_tags(tag_str):
    if pd.isna(tag_str):
        return []
    parts = [t.strip() for t in str(tag_str).split(",")]
    parts = [t for t in parts if t]

    # dedupe while preserving order
    seen = set()
    out = []
    for t in parts:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out



def fetch_tag_mapping():
    """
    Returns dict: original_tag -> mapped_tag
    If API is unavailable, return {} (identity mapping).
    """
    try:
        r = requests.get(TAG_MAPPING_API, timeout=10)
        if r.status_code != 200:
            print(f"WARNING: Tag mapping API returned {r.status_code}; using identity mapping.")
            return {}
        data = r.json()
        mapping = {}
        for item in data:
            name = as_clean_str(item.get("name"))
            mapped = as_clean_str(item.get("mapped_name"))
            if name and mapped:
                mapping[name] = mapped
        return mapping
    except Exception as e:
        print(f"WARNING: Tag mapping API failed ({e}); using identity mapping.")
        return {}

def map_tags(tag_list, mapping):
    """
    Applies mapping to each tag, then dedupes again (important if two tags map to same final tag).
    """
    mapped = [mapping.get(t, t) for t in tag_list]
    seen = set()
    out = []
    for t in mapped:
        t = as_clean_str(t)
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


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

    constituents["Clean Tags"] = constituents["Tags"].apply(split_tags)

    #print(constituents[["Patron ID", "Tags", "Clean Tags"]].head(10))

    #output.to_csv(f"{OUTPUT_DIR}/constituents_step2.csv", index=False)
    #print("Checkpoint 2 complete: constituents_step2.csv written")



    # mapped tags + tag count output 
    tag_mapping = fetch_tag_mapping()

    constituents["Mapped Tags"] = constituents["Clean Tags"].apply(lambda tags: map_tags(tags, tag_mapping))

    # Create (Patron ID, Tag) rows
    exploded = constituents[["Patron ID", "Mapped Tags"]].explode("Mapped Tags")
    exploded = exploded.rename(columns={"Mapped Tags": "CB Tag Name"})
    exploded["CB Tag Name"] = exploded["CB Tag Name"].apply(as_clean_str)
    exploded = exploded[exploded["CB Tag Name"] != ""]

    # Count unique patrons per tag
    tag_counts = (
        exploded.groupby("CB Tag Name")["Patron ID"]
        .nunique()
        .reset_index(name="CB Tag Count")
        .sort_values("CB Tag Name")
    )
    donations = pd.read_excel(INPUT_PATH, sheet_name="Input Donation History")
    print("Donation History columns:", list(donations.columns))
    print(donations.head(3))
    print(donations["Status"].value_counts(dropna=False))


    #tag_counts.to_csv(f"{OUTPUT_DIR}/tags_step3.csv", index=False)
   #print("Wrote data/output/tags_step3.csv")

   

if __name__ == "__main__":
    main()
