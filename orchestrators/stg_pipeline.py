import sqlalchemy
import pandas as pd 

csv = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vRf1Xxc1wycc2YRWoIEnM7sWXbmKeZ74ZGbTbaE1bhNROHwMe3_5WaqozTQ2WnGed84RPB51bMQfBwb/pub?gid=1509911894&single=true&output=csv'

try: 
    stg_transaction  = pd.read_csv(csv)
    print(stg_transaction.head(3))
except Exception as e:
    print("Error reading CSV:", e)