import argparse
import polars as pl
from sklearn.model_selection import train_test_split


# ==========================================
# 設定
# ==========================================
input_csv = "./data/uchinada_buildings/gsi/noto_buildings.csv"
output_csv = "./data/uchinada_buildings/gsi/noto_buildings_sampled.csv"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="建物データのサンプリング")
    parser.add_argument("--input-csv", type=str, default=input_csv, help="入力CSVファイルのパス")
    parser.add_argument("--output-csv", type=str, default=output_csv, help="出力CSVファイルのパス")
    parser.add_argument("--sample-size", type=int, default=100, help="サンプルサイズ")
    args = parser.parse_args()
    df = pl.read_csv(args.input_csv)
    type_ = df["type"].to_numpy()
    sampled_df, _ = train_test_split(
        df, 
        train_size=args.sample_size,
        stratify=type_,
        random_state=42
    )
    sampled_df.write_csv(args.output_csv)
