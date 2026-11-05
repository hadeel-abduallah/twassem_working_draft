
import re
import time
import pandas as pd
from datetime import datetime
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

BASE_URL = "https://ruknasi.com"
FILINGS_URL = "https://ruknasi.com/filings"

TARGET_COMPANIES = {
    "1010": "Riyad Bank",
    "1030": "Saudi Investment Bank",
    "1050": "Banque Saudi Fransi",
    "1060": "Saudi Awwal Bank",
    "1080": "Arab National Bank",
    "1140": "Bank Albilad",
    "1150": "Alinma Bank",
    "1180": "Saudi National Bank",
    "4030": "Bahri",
    "7010": "stc",
    "7020": "Mobily",
    "7030": "Zain KSA"
}

def get_card_data(page):
    return page.locator('a[href*="/companies/"][href*="/filings/"]').evaluate_all("""
        (anchors) => {
            const targets = [
                "1010", "1030", "1050", "1060",
                "1080", "1140", "1150", "1180",
                "4030", "7010", "7020", "7030"
            ];

            return anchors.map(anchor => {
                let card = anchor;
                let cardText = "";

                for (let i = 0; i < 8 && card; i++) {
                    const text = (card.innerText || "").trim();

                    const hasTarget = targets.some(symbol => {
                        const regex = new RegExp("(^|\\\\D)" + symbol + "(\\\\D|$)");
                        return regex.test(text);
                    });

                    if (hasTarget) {
                        cardText = text;
                        break;
                    }

                    card = card.parentElement;
                }

                if (!cardText) {
                    card = anchor.parentElement;
                    cardText = (card?.innerText || anchor.innerText || "").trim();
                }

                const links = card
                    ? Array.from(card.querySelectorAll("a[href]"))
                    : [anchor];

                const pdfLinks = links
                    .map(link => link.href)
                    .filter(href => /\\.pdf($|\\?)/i.test(href) || /pdf/i.test(href));

                const statementLinks = links
                    .map(link => link.href)
                    .filter(href => href.includes("/financials/"));

                return {
                    filing_url: anchor.href,
                    title: (anchor.innerText || "").trim(),
                    card_text: cardText,
                    pdf_url: pdfLinks[0] || "",
                    statement_url: statementLinks[0] || ""
                };
            });
        }
    """)


def extract_symbol(text):
    for symbol in TARGET_COMPANIES:
        pattern = rf"(?<!\d){symbol}(?!\d)"
        if re.search(pattern, text):
            return symbol
    return ""


def extract_publication_date(text):
    patterns = [
        r"(?:Publication Date|Published|Publication|نشر)\s*:?\s*"
        r"([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
        r"(?:Publication Date|Published|Publication|نشر)\s*:?\s*"
        r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        r"(?:Publication Date|Published|Publication|نشر)\s*:?\s*"
        r"(\d{4}-\d{2}-\d{2})"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    return ""


def extract_period(url, text):
    match = re.search(
        r"/filings/(\d{4}(?:-q[1-4]|-h1|-h2|-9m)?)",
        url,
        re.IGNORECASE
    )

    if match:
        return match.group(1).upper()

    match = re.search(
        r"\b(20\d{2})\s*(Q[1-4]|H1|H2|9M)\b",
        text,
        re.IGNORECASE
    )

    if match:
        return f"{match.group(1)}-{match.group(2).upper()}"

    return ""


def main():
    all_rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.set_default_timeout(15000)

        print("Opening RUKNasi...")
        page.goto(FILINGS_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        print("Loading all available filings...")

        previous_count = 0
        unchanged_count = 0

        for i in range(100):
            current_count = page.locator(
                'a[href*="/companies/"][href*="/filings/"]'
            ).count()

            print(f"Loaded filings: {current_count}")

            if current_count == previous_count:
                unchanged_count += 1
            else:
                unchanged_count = 0

            if unchanged_count >= 3:
                print("No more new filings are loading.")
                break

            previous_count = current_count

            show_more = page.locator("button").filter(
                has_text=re.compile("Show more filings", re.IGNORECASE)
            )

            if show_more.count() == 0:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)
                continue

            if not show_more.first.is_visible():
                break

            try:
                show_more.first.scroll_into_view_if_needed()
                show_more.first.click()
                page.wait_for_timeout(1500)
            except Exception:
                print("Could not click Show more filings.")
                break

        print("\nExtracting filing information...")

        cards = get_card_data(page)
        print("Total filing cards found:", len(cards))

        seen_urls = set()

        for card in cards:
            filing_url = card["filing_url"]

            if filing_url in seen_urls:
                continue

            seen_urls.add(filing_url)

            card_text = card["card_text"]
            symbol = extract_symbol(card_text)

            if symbol not in TARGET_COMPANIES:
                continue

            company_name = TARGET_COMPANIES[symbol]

            row = {
                "Company Name": company_name,
                "TASI Symbol": symbol,
                "Filing Title": card["title"],
                "Reporting Period": extract_period(
                    filing_url, card_text
                ),
                "Publication Date": extract_publication_date(
                    card_text
                ),
                "Filing URL": filing_url,
                "Statements URL": card["statement_url"],
                "PDF URL": card["pdf_url"],
                "Raw Filing Text": card_text,
                "Scraped At": datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            }

            all_rows.append(row)

            print(f"Collected: {company_name} - {row['Reporting Period']}")

        browser.close()

    columns = [
        "Company Name",
        "TASI Symbol",
        "Filing Title",
        "Reporting Period",
        "Publication Date",
        "Filing URL",
        "Statements URL",
        "PDF URL",
        "Raw Filing Text",
        "Scraped At"
    ]

    df = pd.DataFrame(all_rows, columns=columns)

    if not df.empty:
        df = df.drop_duplicates(subset=["Filing URL"])
        df = df.sort_values(
            by=["TASI Symbol", "Reporting Period"],
            na_position="last"
        )

    summary = (
        df.groupby(["TASI Symbol", "Company Name"])
        .size()
        .reset_index(name="Number of Filings")
        if not df.empty
        else pd.DataFrame(
            columns=["TASI Symbol", "Company Name", "Number of Filings"]
        )
    )

    output_file = "RUKNasi_12_Companies_All_Filings.xlsx"

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="All Filings", index=False)
        summary.to_excel(writer, sheet_name="Summary", index=False)

    print("\n" + "=" * 45)
    print("SCRAPING COMPLETED")
    print("=" * 45)
    print("Total collected filings:", len(df))
    print("Companies with filings:", df["TASI Symbol"].nunique() if not df.empty else 0)
    print("Excel file:", output_file)

    print("\nFilings per company:")
    if not summary.empty:
        print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
