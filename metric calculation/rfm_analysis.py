# %%
print("hello")

# %% Load data
import pandas as pd

df = pd.read_excel("data/online+retail/Online Retail.xlsx")

print(df.shape)
print(df.dtypes)
df.head()

# %% Clean data
print("Before cleaning:", df.shape)

# 1. Drop rows with no CustomerID. Cannot attribute these to a customer for RFM
df_clean = df.dropna(subset=["CustomerID"]).copy()
print("After dropping null CustomerID:", df_clean.shape)

# 2. Remove cancellations (InvoiceNo starting with 'C') and any other non positive quantity
df_clean = df_clean[~df_clean["InvoiceNo"].astype(str).str.startswith("C")]
df_clean = df_clean[df_clean["Quantity"] > 0]
print("After removing cancellations/negative quantity:", df_clean.shape)

# 3. Remove non-positive unit prices (bad data, not real sales)
df_clean = df_clean[df_clean["UnitPrice"] > 0]
print("After removing UnitPrice <= 0:", df_clean.shape)

# 4. Drop exact duplicate rows
df_clean = df_clean.drop_duplicates()
print("After dropping duplicates:", df_clean.shape)

# 5. CustomerID should be a whole number, not a float
df_clean["CustomerID"] = df_clean["CustomerID"].astype(int)

# 6. Add the line-level revenue figure need for Monetary
df_clean["TotalPrice"] = df_clean["Quantity"] * df_clean["UnitPrice"]

df_clean.head()

# %% Calculate RFM metrics
import datetime as dt

# recency needs a fixed reference point - one day after the last transaction
# in the whole dataset, so the most recent customer still gets a Recency > 0
snapshot_date = df_clean["InvoiceDate"].max() + dt.timedelta(days=1)
print("Snapshot date:", snapshot_date)

rfm = df_clean.groupby("CustomerID").agg(
    Recency=("InvoiceDate", lambda x: (snapshot_date - x.max()).days),
    Frequency=("InvoiceNo", "nunique"),
    Monetary=("TotalPrice", "sum")
).reset_index()

print(rfm.shape)
rfm.describe()

# %% Score customer 1-4 on each dimension
def score_column(series, ascending):
    # rank first so tied values don't break qcut's quartile edges
    ranks = series.rank(method="first", ascending=ascending)
    return pd.qcut(ranks, 4, labels=[1, 2, 3, 4]).astype(int)

rfm["R_score"] = score_column(rfm["Recency"], ascending=False) # fewer days since purchase = better = higher score
rfm["F_score"] = score_column(rfm["Frequency"], ascending=True) # more orders = better = higher score
rfm["M_score"] = score_column(rfm["Monetary"], ascending=True) # more spend = better = higher score

rfm["RFM_score"] = rfm["R_score"].astype(str) + rfm["F_score"].astype(str) + rfm["M_score"].astype(str)

rfm.sort_values("RFM_score", ascending=False).head(10)

# %% Assign segment labels based on R and F scores
segment_map = {
    (4,4): "Champions", (4,3): "Loyal Customers", (4,2): "Potential Loyalists", (4,1): "New Customers",
    (3,4): "Loyal Customers", (3,3): "Potential Loyalists", (3,2): "Promising", (3,1): "New Customers",
    (2,4): "At Risk", (2,3): "Need Attention", (2,2): "About to Sleep", (2,1): "About to Sleep",
    (1,4): "Can't Lose Them", (1,3): "At Risk", (1,2): "Hibernating", (1,1): "Lost",
}

rfm["Segment"] = rfm.apply(lambda row: segment_map[(row["R_score"], row["F_score"])], axis=1)

rfm["Segment"].value_counts()

# %% Analyse behavior patterns per segment
segment_summary = rfm.groupby("Segment").agg(
    Customers=("CustomerID", "count"),
    Avg_Recency=("Recency", "mean"),
    Avg_Frequency=("Frequency", "mean"),
    Avg_Monetary=("Monetary", "mean"),
    Total_Revenue=("Monetary", "sum")
).round(1).sort_values("Total_Revenue", ascending=False)

segment_summary

# %% Targeted marketing recommendations per segment
recommendations = {
    "Champions":           ("Retain",      "Reward with loyalty perks, early access, and referral incentives. Avoid discounting -- retention risk is already low."),
    "Loyal Customers":     ("Grow",        "Upsell/cross-sell via personalized recommendations; invite into a loyalty tier to push them toward Champions."),
    "Potential Loyalists": ("Grow",        "Encourage a second/third purchase with a targeted follow-up offer and loyalty program enrollment."),
    "At Risk":             ("Win back",    "High historical value but going quiet -- prioritize a personalized win-back offer over generic email blasts."),
    "Can't Lose Them":     ("Win back",    "Small group of former top spenders -- worth direct, high-touch outreach rather than automated campaigns."),
    "Need Attention":      ("Win back",    "Time-limited reactivation offer before they slide further into 'About to Sleep'."),
    "About to Sleep":      ("Nurture",     "Reminder/reactivation email with a modest incentive; low cost, moderate upside."),
    "New Customers":       ("Nurture",     "Welcome series and a first-repeat-purchase incentive to build early habit."),
    "Promising":           ("Nurture",     "Onboarding content and small incentives to convert into repeat buyers."),
    "Hibernating":         ("Deprioritize","Low historical value and long dormant -- low-cost/automated reactivation only."),
    "Lost":                ("Deprioritize","Lowest value and most dormant -- not worth active win-back spend."),
}

rec_df = pd.DataFrame.from_dict(recommendations, orient="index", columns=["Priority", "Recommendation"])
segment_summary = segment_summary.join(rec_df)

segment_summary

# %% Export for Power BI
rfm.to_csv("data/rfm_customer_level.csv", index=False)
segment_summary.reset_index().to_csv("data/rfm_segment_summary.csv", index=False)

print("Exported:")
print("- rfm_customer_level.csv:", rfm.shape)
print("- rfm_segment_summary.csv", segment_summary.shape)
