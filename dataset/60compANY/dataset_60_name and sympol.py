
import pandas as pd

input_file = r"C:\Users\HONOR\OneDrive - IMAM ABDULRAHMAN BIN FAISAL UNIVERSITY\Desktop\GRAD_PROJECT\DATA SETS\Copy of Data.xlsx"
output_file = "60_Companies_List.xlsx"

df = pd.read_excel(input_file, sheet_name="all_events")

required_columns = ["CompanyName", "Symbol"]

missing = [col for col in required_columns if col not in df.columns]

if missing:
    raise ValueError(f"Missing columns: {missing}")

companies = df[required_columns].copy()

companies["CompanyName"] = companies["CompanyName"].astype("string").str.strip()
companies["Symbol"] = companies["Symbol"].astype("string").str.strip()

companies = companies.dropna(subset=required_columns)
companies = companies[
    (companies["CompanyName"] != "") &
    (companies["Symbol"] != "")
]

companies = companies.drop_duplicates()
companies = companies.sort_values("Symbol").reset_index(drop=True)

companies.insert(0, "ID", range(1, len(companies) + 1))

with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
    companies.to_excel(writer, sheet_name="Companies", index=False)

    summary = pd.DataFrame({
        "Metric": ["Unique companies", "Unique symbols"],
        "Count": [
            companies["CompanyName"].nunique(),
            companies["Symbol"].nunique()
        ]
    })

    summary.to_excel(writer, sheet_name="Summary", index=False)

print(f"Excel file created: {output_file}")
print(f"Number of companies: {len(companies)}")

if len(companies) != 60:
    print("WARNING: The extracted count is not 60. Check company names and symbols.")
