import csv
import random
import os

# ==========================================
# 設定
# ==========================================
input_buildings_csv = "./data/wajima_buildings/gsi/noto_buildings.csv" # 元の建物情報CSV (約2500件)
input_site_csv = "./data/wajima_buildings/j-shis/site_model.csv"            # API取得した地盤情報CSV (約2500件)

output_xml = "./data/openquake/noto_scenario_risk/exposure_model.xml"             # 保存先：サンプリング建物XML
output_site_csv = "./data/openquake/noto_scenario_risk/site_model.csv"   # 保存先：サンプリング地盤CSV
sample_size = 100

# 再現性のためのシード固定
random.seed(42)

# ==========================================
# サイトパラメータのデフォルト設定
# ==========================================
DEFAULT_XVF = 100.0  # 火山フロントからの距離 (km) の初期値 (ダミー値)
DEFAULT_BACKARC = 0  # 前弧 (0: False) か 背弧 (1: True) かの初期値
DEFAULT_Z1PT4 = 300.0 # S波速度 1.4 km/s 層上面までの深さ (m) の初期値 (KeyError回避用)

# ==========================================
# 脆弱性モデルの定義に完全合致させたTaxonomy推定ロジック
# ==========================================
def estimate_taxonomy(bld_type):
    # 耐震基準の決定（60%が旧耐震 CDL、40%が新耐震 CDH）
    is_low_code = random.random() < 0.60

    if bld_type == "普通建物":
        # 階数の決定（30%が1階建て H:1、70%が2階建て H:2）
        height = "H:1" if random.random() < 0.30 else "H:2"
        if is_low_code:
            # 旧耐震木造在来工法: W+WHE/LPB/CDL+ERL/...
            return f"W+WHE/LPB/CDL+ERL/{height}/RES"
        else:
            # 新耐震木造枠組壁工法: W+WLI/LWAL/CDH+ERM/...
            return f"W+WLI/LWAL/CDH+ERM/{height}/RES"

    elif bld_type == "堅ろう建物":
        # 階数の決定（70%が3階建て H:3、30%が4階建て H:4）
        height = "H:3" if random.random() < 0.70 else "H:4"
        if is_low_code:
            # 旧耐震壁式RC造: CR/LWAL/CDL+ERM/...
            return f"CR/LWAL/CDL+ERM/{height}/RES"
        else:
            # 新耐震壁式RC造: CR/LWAL/CDH+ERM/...
            return f"CR/LWAL/CDH+ERM/{height}/RES"

    elif bld_type == "普通無壁舎":
        # 鉄骨ブレース造（1階建て、非居住/商業用）
        if is_low_code:
            return "S/LFBR/CDL+ERM/H:1/COM"
        else:
            return "S/LFBR/CDH+ERH/H:1/COM"

    elif bld_type == "堅ろう無壁舎":
        # RCデュアルシステム造（3階建て、非居住/商業用）
        if is_low_code:
            return "CR/LDUAL/CDL+ERM/H:3/COM"
        else:
            return "CR/LDUAL/CDH+ERH/H:3/COM"

    else:
        # 想定外の種別があった場合のフォールバック（一般的な木造2階建て住宅）
        if is_low_code:
            return "W+WHE/LPB/CDL+ERL/H:2/RES"
        else:
            return "W+WLI/LWAL/CDH+ERM/H:2/RES"

# ==========================================
# メイン処理
# ==========================================
def main():
    # ファイル存在チェック
    for filepath in [input_buildings_csv, input_site_csv]:
        if not os.path.exists(filepath):
            print(f"エラー: 必須ファイル '{filepath}' が見つかりません。")
            return

    # 1. 地盤情報 (site_model.csv) の読み込みとハッシュマップ化
    site_lookup = {}
    with open(input_site_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lon_key = f"{float(row['lon']):.4f}"
                lat_key = f"{float(row['lat']):.4f}"
                site_lookup[(lon_key, lat_key)] = row
            except ValueError:
                continue

    # 2. 建物情報 (wajima_buildings.csv) を読み込み、地盤情報とマージ
    merged_dataset = []
    with open(input_buildings_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lon_key = f"{float(row['lon']):.4f}"
                lat_key = f"{float(row['lat']):.4f}"
                
                # 同一座標の地盤データをルックアップ
                site_info = site_lookup.get((lon_key, lat_key))
                
                if site_info:
                    merged_dataset.append({
                        'fid': row['fid'],
                        'type': row['type'],
                        'lon_str': lon_key,
                        'lat_str': lat_key,
                        'area': float(row['area']) if row['area'] else 0.0,
                        'vs30': site_info['vs30'],
                        'z1pt0': site_info['z1pt0'],
                        'z2pt5': site_info['z2pt5'],
                        'vs30measured': site_info['vs30measured']
                    })
            except ValueError:
                continue

    total_count = len(merged_dataset)
    print(f"マージ完了: 建物と地盤が一致したデータ数は {total_count} 件です。")

    if total_count == 0:
        print("エラー: 建物データと地盤データの座標が一致しませんでした。")
        return

    # 3. 100件のランダムサンプリング
    actual_sample_size = min(sample_size, total_count)
    sampled_data = random.sample(merged_dataset, actual_sample_size)
    print(f"{actual_sample_size} 件をサンプリングしました。")

    # 4. 露出モデル (XML) の書き出し
    xml_lines = []
    xml_lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    xml_lines.append('<nrml xmlns:gml="http://www.opengis.net/gml" xmlns="http://openquake.org/xmlns/nrml/0.5">')
    xml_lines.append('  <exposureModel id="noto_exposure" category="buildings" taxonomySource="GEM_Building_Taxonomy_2.0">')
    xml_lines.append('    <description>Noto Peninsula Exposure Model (Normalized to Ratio)</description>')
    xml_lines.append('    <conversions>')
    xml_lines.append('      <!-- 単位を ratio（比率）に変更 -->')
    xml_lines.append('      <costTypes>')
    xml_lines.append('        <costType name="structural" type="per_asset" unit="ratio" />')
    xml_lines.append('      </costTypes>')
    xml_lines.append('    </conversions>')
    xml_lines.append('    ')
    xml_lines.append('    <assets>')

    for idx, item in enumerate(sampled_data, start=1):
        taxonomy = estimate_taxonomy(item['type'])
        xml_lines.append('      <!-- 価値を 1.0 (再調達価額を1とした比率) に設定 -->')
        xml_lines.append(f'      <asset id="asset_{idx}" taxonomy="{taxonomy}" number="1">')
        xml_lines.append(f'        <location lon="{item["lon_str"]}" lat="{item["lat_str"]}" />')
        xml_lines.append('        <costs>')
        xml_lines.append('          <cost type="structural" value="1.0" />')
        xml_lines.append('        </costs>')
        xml_lines.append('      </asset>')

    xml_lines.append('    </assets>')
    xml_lines.append('  </exposureModel>')
    xml_lines.append('</nrml>')

    with open(output_xml, 'w', encoding='utf-8') as f:
        f.write('\n'.join(xml_lines) + '\n')
    print(f"露出モデルXMLを保存しました: {output_xml}")

    # 5. サンプリングされた地盤モデル (site_model_sampled.csv) の書き出し
    seen_coordinates = set()
    written_site_count = 0

    with open(output_site_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['lon', 'lat', 'vs30', 'z1pt0', 'z2pt5', 'vs30measured', 'xvf', 'backarc', 'z1pt4'])
        writer.writeheader()
        
        for item in sampled_data:
            coord_key = (item['lon_str'], item['lat_str'])
            
            # すでに書き出し済みの座標ペアであればスキップ
            if coord_key in seen_coordinates:
                continue
                
            writer.writerow({
                'lon': item['lon_str'],
                'lat': item['lat_str'],
                'vs30': item['vs30'],
                'z1pt0': item['z1pt0'],
                'z2pt5': item['z2pt5'],
                'vs30measured': item['vs30measured'],
                'xvf': DEFAULT_XVF,
                'backarc': DEFAULT_BACKARC,
                'z1pt4': DEFAULT_Z1PT4
            })
            
            seen_coordinates.add(coord_key)
            written_site_count += 1
            
    print(f"サンプリングされた地盤モデルCSVを保存しました: {output_site_csv} (重複除外後のユニーク地点数: {written_site_count}箇所)")

if __name__ == "__main__":
    main()