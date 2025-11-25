import pandas as pd
import yfinance as yf

csv_url = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vRf1Xxc1wycc2YRWoIEnM7sWXbmKeZ74ZGbTbaE1bhNROHwMe3_5WaqozTQ2WnGed84RPB51bMQfBwb/pub?gid=1509911894&single=true&output=csv'


def stg_transaction(engine):
    df = pd.read_csv(csv_url)
    df['Date'] = pd.to_datetime(df['Date'])
    df.to_sql('stg_transaction', engine, if_exists='replace', index=False)
    print("stg_transaction loaded successfully!")
    return df

def stg_history(df, engine):
    tickers = df['Ticker'].dropna().unique().tolist()
    history = yf.download(tickers, start="2024-01-02", interval="1wk", group_by='Ticker')
    
    records = []
    for ticker in tickers:
        ticker_df = history[ticker].copy()
        ticker_df = ticker_df.reset_index()
        ticker_df['Ticker'] = ticker
        records.append(ticker_df)

    stg_history_df = pd.concat(records, ignore_index=True)
    stg_history_df.rename(columns=lambda x: x.replace(" ", "_"), inplace=True)
    stg_history_df.to_sql('stg_history', engine, if_exists='replace', index=False)
    print("stg_history loaded successfully!")
    return stg_history_df

if __name__ == "__main__":
    stg_transaction()
    stg_history()
