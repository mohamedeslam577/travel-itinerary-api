import pandas as pd
from sqlalchemy import create_engine

DATABASE_URL = "postgresql://postgres:YqavFXcTXlyBuMNKTWObIkZeiGodEuiA@kodama.proxy.rlwy.net:26773/railway"

# # Railway fix
# DATABASE_URL = DATABASE_URL.replace(
#     "postgres://",
#     "postgresql://"
# )

engine = create_engine(DATABASE_URL)

# =========================
# Upload recommendation_df
# =========================
recommendation_df = pd.read_csv("recommendation_df.csv")

recommendation_df.to_sql(
    "recommendation_places",
    engine,
    if_exists="replace",
    index=False
)

print("recommendation_df uploaded successfully!")

# =========================
# Upload child_df
# =========================
child_df = pd.read_csv("child_df.csv")

child_df.to_sql(
    "child_places",
    engine,
    if_exists="replace",
    index=False
)

print("child_df uploaded successfully!")

print("ALL DATA UPLOADED SUCCESSFULLY!")