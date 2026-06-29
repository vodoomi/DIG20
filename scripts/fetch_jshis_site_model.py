import argparse
import csv
import json
import urllib.request
import urllib.error
import time
import os

# ==========================================
# 設定
# ==========================================
input_csv = "./data/wajima_buildings/gsi/noto_buildings.csv"   # 前処理で作ったサンプリング済みの100件のCSVファイル名
output_csv = "./data/wajima_buildings/j-shis/site_model.csv"        # 出力する地盤モデルCSVファイル名

# APIエラー時や範囲外時のフォールバック（デフォルト値）
DEFAULT_VS30 = 250.0          # m/s
DEFAULT_Z1PT0 = 100.0         # m
DEFAULT_Z2PT5 = 1.5           # km
DEFAULT_VS30MEASURED = 0

# ==========================================
# API呼び出し関数
# ==========================================
def get_jshis_data(lon, lat):
    """
    指定した経緯度に対してJ-SHISの表層地盤・深部地下構造APIからデータを取得する
    """
    vs30 = DEFAULT_VS30
    z1pt0 = DEFAULT_Z1PT0
    z2pt5 = DEFAULT_Z2PT5
    
    # 1. 表層地盤情報提供API (sstrct) V4 から AVS (Vs30) を取得
    sstrct_url = f"https://www.j-shis.bosai.go.jp/map/api/sstrct/V4/meshinfo.geojson?position={lon},{lat}&epsg=4326"
    try:
        req = urllib.request.Request(sstrct_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            if 'features' in res_data and len(res_data['features']) > 0:
                properties = res_data['features'][0]['properties']
                # 'AVS'（表層30m平均S波速度）を取得
                if 'AVS' in properties and properties['AVS'] is not None:
                    vs30 = float(properties['AVS'])
    except Exception as e:
        print(f"  [警告] sstrct API取得失敗 ({lon}, {lat}): {e}")

    # APIサーバー保護のため僅かに待機
    time.sleep(0.1)

    # 2. 深部地下構造情報提供API (dstrct) V3.2 から層下面深さ (LYRD) を取得
    # Vs = 1,100 m/s の上面は D5 層、Vs = 2,700 m/s の上面は D9 層に対応
    dstrct_url = f"https://www.j-shis.bosai.go.jp/map/api/dstrct/V3.2/LYRD/meshinfo.geojson?position={lon},{lat}&epsg=4326"
    try:
        req = urllib.request.Request(dstrct_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            if 'features' in res_data and len(res_data['features']) > 0:
                properties = res_data['features'][0]['properties']
                
                # Z1.0 = S波速度1.1km/s層の上面深さ (D5)
                if 'D5' in properties and properties['D5'] is not None:
                    z1pt0 = float(properties['D5'])
                
                # Z2.5 = S波速度2.7km/s層の上面深さ (D9)
                # m単位からkm単位へ変換
                if 'D9' in properties and properties['D9'] is not None:
                    z2pt5 = float(properties['D9']) / 1000.0
    except Exception as e:
        print(f"  [警告] dstrct API取得失敗 ({lon}, {lat}): {e}")

    time.sleep(0.1)
    return vs30, z1pt0, z2pt5

# ==========================================
# メイン処理
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="J-SHIS APIから地盤情報を取得し、site_model.csvを生成するスクリプト")
    parser.add_argument('--input-csv', type=str, default=input_csv, help='入力CSVファイルのパス (デフォルト: ./data/wajima_buildings/gsi/noto_buildings.csv)')
    parser.add_argument('--output-csv', type=str, default=output_csv, help='出力CSVファイルのパス (デフォルト: ./data/wajima_buildings/j-shis/site_model.csv)')
    args = parser.parse_args()
    if not os.path.exists(args.input_csv):
        print(f"エラー: 入力ファイル '{args.input_csv}' が見つかりません。")
        return

    # 1. CSVデータの読み込み
    buildings = []
    with open(args.input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            buildings.append({
                'lon': float(row['lon']),
                'lat': float(row['lat'])
            })

    total_count = len(buildings)
    print(f"入力CSVから {total_count} 件の建物を読み込みました。J-SHIS APIから地盤情報を取得します。")

    # 2. 地盤データの取得とマッピング
    site_model_data = []
    for idx, bld in enumerate(buildings, start=1):
        lon, lat = bld['lon'], bld['lat']
        print(f"[{idx}/{total_count}] 座標 ({lon}, {lat}) のデータを取得中...")
        
        # API問い合わせ
        vs30, z1pt0, z2pt5 = get_jshis_data(lon, lat)
        
        site_model_data.append({
            'lon': f"{lon:.4f}",
            'lat': f"{lat:.4f}",
            'vs30': round(vs30, 1),
            'z1pt0': round(z1pt0, 1),
            'z2pt5': round(z2pt5, 4),
            'vs30measured': DEFAULT_VS30MEASURED
        })

    # 3. site_model.csv への出力
    with open(args.output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['lon', 'lat', 'vs30', 'z1pt0', 'z2pt5', 'vs30measured'])
        writer.writeheader()
        writer.writerows(site_model_data)

    print(f"\n完了しました。保存先: {args.output_csv} (データ数: {len(site_model_data)}件)")

if __name__ == "__main__":
    main()