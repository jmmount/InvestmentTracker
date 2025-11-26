from sqlalchemy import text, create_engine
from orchestrators.stg_pipeline import stg_transaction, stg_history
from orchestrators.wh_pipeline import wh_dimensions, dimension_tables


engine = create_engine('postgresql://admin:admin@localhost:5434/investments')

def main() :
    # Staging
    stg_df = stg_transaction(engine)
    stg_history_df = stg_history(stg_df, engine)

    # Warehousing
    dim_date, dim_ticker, dim_sector, dim_purchase_type = wh_dimensions(stg_df, stg_history_df)
    dimension_tables(engine, dim_date, dim_ticker, dim_sector, dim_purchase_type)



if __name__ == "__main__":
    main()