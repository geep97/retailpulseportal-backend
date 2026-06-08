import os
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def calculate_demographic(age):
    """
    Dynamically maps an age to the database check constraint:
    'Gen Z', 'Millennial', 'Gen X', or 'Senior'
    """
    if pd.isna(age):
        return "Millennial"  # Safe default fallback
    
    # Standard demographic age bounds for 2026 dataset
    if age <= 29:
        return "Gen Z"
    elif age <= 45:
        return "Millennial"
    elif age <= 61:
        return "Gen X"
    else:
        return "Senior"

def seed_operational_master_records():
    try:
        print("⚡ Initiating secondary migration engine for core operational registers...")
        
        # -------------------------------------------------------------------
        # 1. POPULATE CUSTOMERS TABLE
        # -------------------------------------------------------------------
        print("\nReading customer data frames from data/cleaned_customers.csv...")
        cust_df = pd.read_csv("data/cleaned_customers.csv")
        
        cust_payloads = []
        for _, row in cust_df.iterrows():
            # Calculate the required demographic group from age to satisfy the CHECK constraint
            demo_group = calculate_demographic(row["age"])
            
            cust_payloads.append({
                "loyalty_card_number": row["customer_id"],  # Using customer_id string as the unique card number
                "demographic_group": demo_group,
                "joined_at": row["date_joined"]
            })
            
        print(f"Uploading {len(cust_payloads)} rows to 'customers' table in batches...")
        chunk_size = 400
        for i in range(0, len(cust_payloads), chunk_size):
            chunk = cust_payloads[i:i+chunk_size]
            # Use upsert to safely bypass duplicate constraint failures if run multiple times
            supabase.table("customers").upsert(chunk, on_conflict="loyalty_card_number").execute()
            
        print("✔ 'customers' database rows uploaded cleanly.")

        # -------------------------------------------------------------------
        # 2. POPULATE INVENTORY TABLE
        # -------------------------------------------------------------------
        print("\nReading warehouse balance lists from data/cleaned_inventory.csv...")
        inv_df = pd.read_csv("data/cleaned_inventory.csv")
        
        print("Caching real-time relational ID indexes to prevent mapping lookups...")
        stores_res = supabase.table("stores").select("store_id, store_name").execute()
        store_map = {s["store_name"]: s["store_id"] for s in stores_res.data}
        
        products_res = supabase.table("product").select("product_id, product_name").execute()
        product_map = {p["product_name"]: p["product_id"] for p in products_res.data}
        
        inv_payloads = []
        unmatched_products = 0
        
        for _, row in inv_df.iterrows():
            p_name = row["product_name"]
            s_name = row["store_name"]
            
            # Skip safely if inventory row item isn't tracked in our global master products catalog yet
            if p_name not in product_map:
                unmatched_products += 1
                continue
                
            inv_payloads.append({
                "store_id": store_map[s_name],
                "product_id": product_map[p_name],
                "stock_quantity": int(row["stock_qty"]),  # Corrected key mapping from 'stock_qty'
                "reorder_level": int(row["reorder_level"]),
                "supplier": row.get("supplier", "Main Retail Vendor Distribution Hub")
            })
            
        print(f"Uploading {len(inv_payloads)} mapping links to 'inventory' ledger...")
        if inv_payloads:
            supabase.table("inventory").upsert(inv_payloads).execute()
        
        print(f"✔️ 'inventory' data seed metrics live! (Skipped {unmatched_products} records with unmatched product keys)")
        print("\n SEQUENTIAL INGESTION PIPELINE FULLY EXECUTED!")

    except Exception as e:
        print(f"\n Pipeline Aborted prematurely: {e}")

if __name__ == "__main__":
    seed_operational_master_records()