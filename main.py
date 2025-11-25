from sqlalchemy import create_engine
from orchestrators.stg_pipeline import stg_transaction
from orchestrators.stg_pipeline import stg_history


engine = create_engine('postgresql://admin:admin@localhost:5434/investments')

def main() :
    stg_df = stg_transaction(engine)
    stg_history(stg_df, engine)

if __name__ == "__main__":
    main()