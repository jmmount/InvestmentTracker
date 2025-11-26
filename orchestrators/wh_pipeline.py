from sqlalchemy import text
import pandas as pd

def wh_dimensions(df, stg_history_df) :
    transaction_dates = df.copy()
    historical_dates = stg_history_df.copy()
    all_dates = pd.concat([transaction_dates, historical_dates], ignore_index=True)

    dim_date = all_dates[['Date']]
    dim_date.loc[:, 'Date'] = pd.to_datetime(dim_date['Date'])
    dim_date = dim_date.drop_duplicates(subset=['Date'])
    dim_date = dim_date.sort_values('Date').reset_index(drop=True)

    dim_ticker = df[['Ticker']].drop_duplicates()
    dim_sector = df[['Sector']].drop_duplicates()
    dim_purchase_type = df[['Purchase Type']].drop_duplicates()

    return dim_date, dim_ticker, dim_sector, dim_purchase_type
   

def dimension_tables(engine, dim_date, dim_ticker, dim_sector, dim_purchase_type) :
    drop_dim = [
    "DROP TABLE IF EXISTS dim_date CASCADE;",
    "DROP TABLE IF EXISTS dim_ticker CASCADE;",
    "DROP TABLE IF EXISTS dim_sector CASCADE;",
    "DROP TABLE IF EXISTS dim_purchase_type CASCADE;"
        ]

    with engine.begin() as conn:
            for keys in drop_dim :
                conn.execute(text(keys))

    dim_date.to_sql('dim_date', engine, if_exists='replace', index=False)
    dim_ticker.to_sql('dim_ticker', engine, if_exists='replace', index=False)
    dim_sector.to_sql('dim_sector', engine, if_exists='replace', index=False)
    dim_purchase_type.to_sql('dim_purchase_type', engine, if_exists='replace', index=False)

if __name__ == "__main__": 
    wh_dimensions()
    dimension_tables()