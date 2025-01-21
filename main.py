import csv
import re
import os
import logging
from logging.handlers import RotatingFileHandler

SETTING_LOG_LEVEL = os.environ.get('SETTING_LOG_LEVEL', "INFO")

logging.root.handlers = []  # Required to be before logging.basicConfig()
file_handler = RotatingFileHandler("application.log", maxBytes=1 * 1024 * 1024, backupCount=5)
file_handler.setFormatter(logging.Formatter('%(asctime)s [Process:%(process)d - %(threadName)s] [%(levelname)s] %(message)s'))
file_handler.setLevel(getattr(logging, SETTING_LOG_LEVEL, logging.INFO))
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s [Process:%(process)d - %(threadName)s] [%(levelname)s] %(message)s'))
console_handler.setLevel(getattr(logging, SETTING_LOG_LEVEL, logging.INFO))
logging.basicConfig(
    level=getattr(logging, SETTING_LOG_LEVEL, logging.INFO),
    handlers=[
        file_handler,
        console_handler
    ]
)

MONTH = "Nov"
YEAR = "2024"

raw_data = """
1 nov
     29 dad
      123 dad
      60 dad
     8.8 child lunch for 2 
     4.4  lunch for 2  child 
   9 dinner

2 nov
    7.4 child apples and bananas
   18.70 child. Taxi from hougang to pasir ris

4 nov
    6.1 lunch
    1 drink treat

5 nov
   5.3 lunch

6 nov
    45.59 pokka drinks. 24 bottles. 1.5l
    10.30 child fishing toy
   15.60 lunch
   123.45 tax

7 nov
    13.54 taxi. Hougang to Eunos. TODO - Handle this
    12.34 taxi. Hougan to Eunos. TODO - Handle this
    4.1 lunch

8 nov
     5 lunch

9 nov
    7.4 child bananas and apples
   4.2 lunch for 2
   10.04 dinner for 5
   21.02 taxi. Hougan to pasir ris
""".strip()


def categorize_description(raw_desc):
    """
    Returns (category, payee) given the transaction description.
    Priority:
    0. treat + personal if "for X" in desc
    1. child:            if "child" in desc
    2. Dad:             if "dad" in desc
    3. Household:       if "hougang", "utilities", "internet" in desc
    4. Gift/Treats:     if "gift", "treat" in desc
    5. Food:            if "lunch", "dinner", "breakfast"
    6. Transport:       if "taxi", "grab", "bus", "mrt"
    7. Tax               if "tax" in desc
    8. Bills:           if "mobile", "bill"
    9. Leisure:         if "snacks", "drinks", etc
    10. Others:          all others
    """
    description_lowered = raw_desc.lower()
    # 1. child
    if "child" in description_lowered:
        return ("child", "")
    # 2. Dad
    if "dad" in description_lowered:
        return ("Dad", "Dad")
    # 3. Household
    if any(x in description_lowered for x in ["hougang", "utilities", "internet"]):
        if "internet" in description_lowered:
            return ("Household", "Starhub")
        else:
            return ("Household", "")
    # 4. Gift/Treats
    if any(x in description_lowered for x in ["gift", "treat"]):
        return ("Gift/Treats", "")
    # 5. Food
    if any(x in description_lowered for x in ["lunch", "dinner", "breakfast"]):
        return ("Food", "")
    # 6. Transport
    if any(x in description_lowered for x in ["taxi", "grab", "bus", "mrt"]):
        return ("Transport", "")
    # 7. Tax
    if "tax" in description_lowered:
        return ("Tax", "IRAS")
    # 8. Bills
    if any(x in description_lowered for x in ["mobile", "bill", "chatgpt"]):
        return ("Bills", "")
    # 9. Leisure
    if any(x in description_lowered for x in ["snacks", "drinks"]):
        return ("Leisure", "")
    # 10. Others
    return ("Others", "")

def parse_raw_data(raw_text):
    """
    Parses the raw transaction data and returns a list of dicts:
    [
      {
        "date": str,
        "category": str,
        "description": str,
        "outflow": float,
        "payee": str
      },
      ...
    ]
    """
    processed_transactions = []
    transactions_split_count = 0
    dates_found_count = 0
    
    # Use a simple approach:
    #  - If a line matches something like "digit(s) + month name", treat as new date
    #  - Otherwise, parse as "amount + description"
    #  - Apply bill-splitting rule if "for X" is found
    #  - Otherwise, do normal categorization
    
    current_date = None
    # A pattern to match lines like "1 nov" or "12 nov" etc.
    date_pattern = re.compile(
        r"^\s*(0?[1-9]|[12][0-9]|3[01])\s+(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*$",
        re.IGNORECASE,
    )
        
    # A pattern to capture: amount at the start, then the rest is description
    # e.g. "  123 dad" -> "123", "dad"
    amount_pattern = re.compile(r"^\s*([\d.]+)\s+(.*)$")
    
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue  # skip empty lines
        
        # Check if this line is a date line
        m_date = date_pattern.match(line)
        if m_date:
            day_str, month_str = m_date.groups()
            # We'll store the date as "DAY MONTH YEAR", e.g. "1 Nov 2025"
            current_date = f"{day_str} {month_str.capitalize()} {YEAR}"
            logging.debug(f'Configured date: {current_date}')
            dates_found_count += 1
            continue
        
        # Otherwise, check if it is a transaction line
        m_amt = amount_pattern.match(line)
        if m_amt:
            amt_str, description = m_amt.groups()
            try:
                amount = float(amt_str)
            except ValueError:
                logging.error('Failed to parse amount value to float type')
                continue  # skip lines that don't parse correctly
            
            if not current_date:
                logging.error('Failed to register transaction to a date')
                # If no current date is set, skip or handle error
                continue
            
            # Check for the "for X" pattern
            # We'll look for: "for <number>"
            # e.g. "lunch for 2"
            # We'll capture that number if present
            multiple_pax_match = re.search(r"\bfor\s+(\d+)\b", description.lower())
            if multiple_pax_match:
                logging.debug('Found transaction to split')
                transactions_split_count += 1
                # We have a split scenario
                total_pax_number = int(multiple_pax_match.group(1))
                personal_portion = round(amount * (1/total_pax_number), 2)
                treat_portion = round(amount * ((total_pax_number-1)/total_pax_number), 2)

                treat_category = "Gift/Treats"
                if "child" in description.lower() and total_pax_number == 2:
                    treat_category = "child"

                # Entry 1: personal portion
                processed_transactions.append({
                    "date": current_date,
                    "category": "Food",  # forced by the rule
                    "description": description + " (personal)",
                    "outflow": personal_portion,
                    "payee": ""
                })
                # Entry 2: treat portion
                processed_transactions.append({
                    "date": current_date,
                    "category": treat_category,  # forced by the rule
                    "description": description + " (treat)",
                    "outflow": treat_portion,
                    "payee": ""
                })
            else:
                # Normal single transaction
                category, payee = categorize_description(description)
                processed_transactions.append({
                    "date": current_date,
                    "category": category,
                    "description": description,
                    "outflow": amount,
                    "payee": payee
                })
    return processed_transactions, dates_found_count, transactions_split_count

def generate_csv(transactions, output_filename):
    """
    Generates a CSV file with the specified format:
    Date,Category,Description,Outflow ($),Payee
    """
    with open(output_filename, mode='w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        # Write header
        writer.writerow(["Date", "Category", "Description", "Outflow ($)", "Payee"])
        
        for tx in transactions:
            writer.writerow([
                tx["date"],
                tx["category"],
                tx["description"],
                f"{tx['outflow']:.2f}",
                tx["payee"]
            ])

def main():
    logging.info('Started')
    transactions, dates_found_count, transactions_split_count = parse_raw_data(raw_data)
    output_filename = f"transactions_{YEAR}_{MONTH}.csv"
    generate_csv(transactions, output_filename)
    logging.info(f"CSV generated: {output_filename}")
    logging.info(f'Dates found: {dates_found_count}')
    logging.info(f'Transactions split count: {transactions_split_count}')

if __name__ == "__main__":
    main()
