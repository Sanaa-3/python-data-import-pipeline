import pandas as pd
import numpy as np
import re
import os
import requests

INPUT_PATH = "data/input.xlsx"
OUTPUT_DIR = "data/output"

# Regular expression for validating email addresses
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Given API endpoint for tag mapping
TAG_MAPPING_API = "https://6719768f7fc4c5ff8f4d84f1.mockapi.io/api/v1/tags"

#Function to clean and standardize string values
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

#Converts a date/datetime to ISO 8601 format string; returns empty string if invalid
def to_iso_datetime(x):
    dt = pd.to_datetime(x, errors="coerce")
    if pd.isna(dt):
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M:%S")

#Deduplicates constituents based on Patron ID, keeping the “best” row per ID
#“Best” is defined as the row with the highest completeness score (most non-missing
#fields). Ties are broken by most recent Date Entered.
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

#Fetches tag mapping from external API
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

#Applies tag mapping to a list of tags, then dedupes the result
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

#Formats a number as currency string (e.g., 1234.5 -> "$1234.50")
def to_currency(x):
    return f"${float(x):.2f}" if pd.notna(x) else ""

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    out_tags = os.path.join(OUTPUT_DIR, "cuebox_tags.csv")
    out_cons = os.path.join(OUTPUT_DIR, "cuebox_constituents.csv")

    # 1) Load inputs
    constituents = pd.read_excel(INPUT_PATH, sheet_name="Input Constituents")
    emails = pd.read_excel(INPUT_PATH, sheet_name="Input Emails")

    # # 2) Clean/dedupe constituents
    constituents = dedupe_constituents(constituents)

    constituents["Patron ID"] = constituents["Patron ID"].astype(str).str.strip()
    constituents = constituents.set_index("Patron ID")


    # 3) Build email lookup
    emails["Patron ID"] = emails["Patron ID"].astype(str).str.strip()
    emails["Email"] = emails["Email"].apply(as_clean_str).str.lower()
    emails = emails[emails["Email"].apply(is_valid_email)]

    email_map = emails.groupby("Patron ID")["Email"].apply(list).to_dict()

    def resolve_emails(row):
        patron_id = str(row.name)  # Patron ID because it's the index now

        primary = as_clean_str(row.get("Primary Email")).lower()
        others = email_map.get(patron_id, [])

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

    constituents[["CB Email 1 (Standardized)", "CB Email 2 (Standardized)"]] = constituents.apply(resolve_emails, axis=1)
    constituents["Clean Tags"] = constituents["Tags"].apply(split_tags)
    constituents["CB Created At"] = constituents["Date Entered"].apply(to_iso_datetime)

    # 4) mapped tags + tag count output 
    tag_mapping = fetch_tag_mapping()

    constituents["Mapped Tags"] = constituents["Clean Tags"].apply(lambda tags: map_tags(tags, tag_mapping))
    constituents["CB Tags"] = constituents["Mapped Tags"].apply(lambda tags: ", ".join(sorted(tags)) if tags else "")

    # Create (Patron ID, Tag) rows
    tmp = constituents.reset_index()  # brings Patron ID back as a column
    exploded = tmp[["Patron ID", "Mapped Tags"]].explode("Mapped Tags")
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
    tag_counts.to_csv(out_tags, index=False)
    print(f"Wrote {out_tags}")

    # 5) Donations
    donations = pd.read_excel(INPUT_PATH, sheet_name="Input Donation History")
    
    # Donation rollups (Paid only) 
    donations["Patron ID"] = donations["Patron ID"].astype(str).str.strip()
    donations = donations[donations["Status"] == "Paid"].copy()

    donations["Donation Date"] = pd.to_datetime(donations["Donation Date"], errors="coerce")
    donations["Donation Amount"] = pd.to_numeric(donations["Donation Amount"], errors="coerce")

    # 6) Remaining CB fields
    # Lifetime sum
    lifetime = donations.groupby("Patron ID")["Donation Amount"].sum()

    # Most recent donation per patron (max date)
    recent = (
        donations.dropna(subset=["Donation Date"])
        .sort_values(["Patron ID", "Donation Date"], ascending=[True, False])
        .drop_duplicates("Patron ID", keep="first")
        .set_index("Patron ID")
    )

    # Join onto constituents (constituents index is Patron ID)
    # Lifetime donation total
    constituents["CB Lifetime Donation Amount"] = pd.Series(
        constituents.index.map(lifetime),
        index=constituents.index
    ).map(to_currency)

    # Most recent donation date
    constituents["CB Most Recent Donation Date"] = pd.Series(
        constituents.index.map(recent["Donation Date"]),
        index=constituents.index
    ).map(lambda d: d.strftime("%Y-%m-%dT%H:%M:%S") if pd.notna(d) else "")

    # Most recent donation amount
    constituents["CB Most Recent Donation Amount"] = pd.Series(
        constituents.index.map(recent["Donation Amount"]),
        index=constituents.index
    ).map(to_currency)


    # CB Constituent Type 
    company = constituents["Company"].fillna("").astype(str).str.strip()
    bad_company_values = ["none", "nan", "n/a", "...", "null"]
    is_company = (company != "") & (~company.str.lower().isin(bad_company_values))

    constituents["CB Constituent Type"] = np.where(is_company, "Company", "Person")


    #  Name fields 
    constituents["CB First Name"] = constituents["First Name"].fillna("").str.strip()
    constituents["CB Last Name"] = constituents["Last Name"].fillna("").str.strip()
    constituents["CB Company Name"] = constituents["Company"].fillna("").str.strip()

    # If Company, blank out person fields
    constituents.loc[
        constituents["CB Constituent Type"] == "Company",
        ["CB First Name", "CB Last Name"]
    ] = ""

    # If Person, blank out company field
    constituents.loc[
        constituents["CB Constituent Type"] == "Person",
        "CB Company Name"
    ] = ""

    #  CB Title 
    allowed_titles = {"Mr.": "Mr.", "Mr": "Mr.",
                    "Mrs.": "Mrs.", "Mrs": "Mrs.",
                    "Ms.": "Ms.", "Ms": "Ms.",
                    "Dr.": "Dr.", "Dr": "Dr."}

    def normalize_cb_title(x):
        s = as_clean_str(x)
        return allowed_titles.get(s, "")

    # Prefer Salutation; go back to Title if Salutation doesn't map
    constituents["CB Title"] = constituents["Salutation"].apply(normalize_cb_title)
    fallback = constituents["CB Title"] == ""
    constituents.loc[fallback, "CB Title"] = constituents.loc[fallback, "Title"].apply(normalize_cb_title)

    # CB Background Information 
    def build_background_info(row):
        job = as_clean_str(row.get("Title"))
        marital = as_clean_str(row.get("Gender"))  # the given data uses the Gender column for Married/Single/Unknown

        parts = []
        if job:
            parts.append(f"Job Title: {job}")
        if marital and marital.lower() != "unknown":
            parts.append(f"Marital Status: {marital}")

        return "; ".join(parts)


    constituents["CB Background Information"] = constituents.apply(build_background_info, axis=1)

    # 7) Final CSV output
    final_constituents = pd.DataFrame({
        "CB Constituent ID": constituents.index,
        "CB Constituent Type": constituents["CB Constituent Type"],
        "CB First Name": constituents["CB First Name"],
        "CB Last Name": constituents["CB Last Name"],
        "CB Company Name": constituents["CB Company Name"],
        "CB Created At": constituents["CB Created At"],
        "CB Email 1 (Standardized)": constituents["CB Email 1 (Standardized)"],
        "CB Email 2 (Standardized)": constituents["CB Email 2 (Standardized)"],
        "CB Title": constituents["CB Title"],
        "CB Tags": constituents["CB Tags"],
        "CB Background Information": constituents["CB Background Information"],
        "CB Lifetime Donation Amount": constituents["CB Lifetime Donation Amount"],
        "CB Most Recent Donation Date": constituents["CB Most Recent Donation Date"],
        "CB Most Recent Donation Amount": constituents["CB Most Recent Donation Amount"],
    })

    final_constituents.to_csv(out_cons, index=False)
    print(f"Wrote {out_cons}")



if __name__ == "__main__":
    main()
