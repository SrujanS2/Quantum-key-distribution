from data_loader import load_dataset
df = load_dataset()
print("Loaded shape:", df.shape)
print("Columns:", df.columns.tolist())
print(df.head(5).to_string(index=False))
