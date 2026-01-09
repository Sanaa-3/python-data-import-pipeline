import pandas as pd

# Path to the input spreadsheet
INPUT_PATH = "data/input.xlsx"

def main():
    # Read the 3 input sheets I need
    constituents_df = pd.read_excel(
        INPUT_PATH,
        sheet_name="Input Constituents"
    )

    emails_df = pd.read_excel(
        INPUT_PATH,
        sheet_name="Input Emails"
    )

    donations_df = pd.read_excel(
        INPUT_PATH,
        sheet_name="Input Donation History"
    )

    #"When in doubt, print things out" - John John 
    print("=== Input Constituents ===")
    print(f"Rows: {len(constituents_df)}")
    print(constituents_df.head(), "\n")

    print("=== Input Emails ===")
    print(f"Rows: {len(emails_df)}")
    print(emails_df.head(), "\n")

    print("=== Input Donation History ===")
    print(f"Rows: {len(donations_df)}")
    print(donations_df.head(), "\n")

    #confirm expected columns exist
    print("Constituents columns:")
    print(list(constituents_df.columns), "\n")

    print("Emails columns:")
    print(list(emails_df.columns), "\n")

    print("Donations columns:")
    print(list(donations_df.columns))


if __name__ == "__main__":
    main()