from sqlalchemy import text, create_engine
import pandas as pd 

def stg_pipeline() :
    engine = create_engine('postgresql://admin:admin@localhost:5434/investments')
    csv_url = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vRf1Xxc1wycc2YRWoIEnM7sWXbmKeZ74ZGbTbaE1bhNROHwMe3_5WaqozTQ2WnGed84RPB51bMQfBwb/pub?gid=1509911894&single=true&output=csv'
    stg_transaction_df = pd.read_csv(csv_url)

    stg_transaction_df = stg_transaction_df.to_sql('stg_transaction', engine, if_exists='replace', index=False)

if __name__ == "__main__":
    stg_pipeline()