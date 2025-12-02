
filename = "reptask_P1JRNC_DATABRICKS_1_B (6).log"
with open(filename, "rb") as f:
    header = f.read(16)
    print(f"Header bytes: {header}")
    try:
        print(f"Decoded utf-8: {header.decode('utf-8')}")
    except Exception as e:
        print(f"UTF-8 decode error: {e}")
    
    try:
        print(f"Decoded utf-16: {header.decode('utf-16')}")
    except Exception as e:
        print(f"UTF-16 decode error: {e}")

