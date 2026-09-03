# Tap and Target command steps:
**Step 01**

create and go to the folder
```bash
meltano init olist_elt_pipeline
cd olist_elt_pipeline
```

**Step 02**

create python file called `download_kaggle.py`, and save the file inside `cd olist_elt_pipeline`

copy following code:
```python
import os
import kagglehub

def fetch_dataset():
    print("🚀 Fetching latest Brazilian E-Commerce dataset via kagglehub...")
    cache_dir = kagglehub.dataset_download("olistbr/brazilian-ecommerce")
    
    target_dir = "./data/brazilian_ecommerce"
    os.makedirs(target_dir, exist_ok=True)
    
    for file_name in os.listdir(cache_dir):
        if file_name.endswith('.csv'):
            src_path = os.path.join(cache_dir, file_name)
            dst_path = os.path.join(target_dir, file_name)
            
            # Read with utf-8-sig to drop BOM
            with open(src_path, "r", encoding="utf-8-sig") as f_in:
                content = f_in.read()
            
            # Write back as clean utf-8 (overwrite if exists)
            with open(dst_path, "w", encoding="utf-8") as f_out:
                f_out.write(content)
            
            print(f"📥 Processed: {file_name}")
    
    print(f"✅ All CSV files re-encoded to UTF-8 at {target_dir}")
    
    # Simple integrity check: counts + sizes
    cache_csvs = [f for f in os.listdir(cache_dir) if f.endswith('.csv')]
    target_csvs = [f for f in os.listdir(target_dir) if f.endswith('.csv')]
    
    print("\n🔍 Running simple integrity validation...")
    if set(cache_csvs) == set(target_csvs):
        print("✔️ File presence check passed.")
    else:
        print("❌ Mismatch in file names between cache and target.")
    
    for f in cache_csvs:
        src_path = os.path.join(cache_dir, f)
        dst_path = os.path.join(target_dir, f)
        if os.path.exists(dst_path):
            src_size = os.path.getsize(src_path)
            dst_size = os.path.getsize(dst_path)
            if dst_size == 0 or dst_size < src_size * 0.9:  # heuristic
                print(f"⚠️ Possible issue: {f} (size mismatch)")
        else:
            print(f"❌ Missing in target: {f}")

if __name__ == "__main__":
    fetch_dataset()
```
> this source code is utilities plugin in meltano.yml. Refer to `sample_meltano.yml`

**Step 03**

install plugin
```bash
meltano add tap-csv
```
> refer `sample_meltano.yml` template to add/edit *files* configuration

**Step 04**

run tap test
```bash
# 1. Download the utilities file first
meltano invoke kaggle-extractor:download
## it will download all the csv file into data/brazilian ecommerce

# Ensure olist_geolocation_dataset.csv file is downloaded to this folder. 
# If not, please download it manually

# 2. Test the tap configuration
meltano test tap-csv
```

**Step 05**

add a dummy loader to dump data into JSON
```bash
meltano add target-jsonl
```

then dry run csv to JSON
```bash
meltano run tap-csv target-jsonl
```

**Step 06**

install a loader to load data into BigQuery
```bash
meltano add target-bigquery
```
> refer `sample_meltano.yml` template for BigQuery configuration*

**Step 07**

run CSV to BigQuery
```bash
meltano run tap-csv target-bigquery
```