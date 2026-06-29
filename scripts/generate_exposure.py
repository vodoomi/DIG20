import argparse
import csv
import random
import os
import yaml


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
class TaxonomyEstimator:
    def __init__(self, config_path: str, region_key: str):
        """
        YAMLファイルを読み込み、指定された地区のルールを保持します。
        """
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        if 'regions' not in config or region_key not in config['regions']:
            raise ValueError(f"指定された地区 '{region_key}' が設定ファイルに見つかりません。")
            
        self.region_config = config['regions'][region_key]
        self.code_ratios = self.region_config['code_ratios']
        self.building_rules = self.region_config['building_rules']

    def estimate_taxonomy(self, bld_type: str) -> str:
        """
        建物種別(type)から確率的にTaxonomyを割り当てます。
        """
        # 1. 耐震基準コードの決定 (YAMLで定義された確率から重み付きランダム選択)
        codes = list(self.code_ratios.keys())
        code_weights = list(self.code_ratios.values())
        selected_code = random.choices(codes, weights=code_weights, k=1)[0]

        # 2. 該当する建物種別のルールを取得 (存在しない場合は fallback)
        rule = self.building_rules.get(bld_type)
        if not rule:
            rule = self.building_rules.get('fallback')
            if not rule:
                raise ValueError(f"建物種別 '{bld_type}' に対するルールおよびfallbackが定義されていません。")

        # 3. 階数(height)の決定 (設定がある場合のみ確率選択)
        height_str = ""
        if 'heights' in rule and rule['heights']:
            heights = list(rule['heights'].keys())
            height_weights = list(rule['heights'].values())
            height_str = random.choices(heights, weights=height_weights, k=1)[0]

        # 4. Taxonomyテンプレートの抽出
        tax_templates = rule.get('taxonomies', {})
        # 選択された耐震コードに対する設定がない場合は、利用可能なコードで代用
        tax_template = tax_templates.get(selected_code)
        if not tax_template:
            available_codes = list(tax_templates.keys())
            tax_template = tax_templates[available_codes[0]]

        # 5. 階数プレースホルダー {height} を置換してTaxonomyを生成
        if "{height}" in tax_template:
            return tax_template.format(height=height_str)
        else:
            return tax_template

# ==========================================
# メイン処理
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="建物種別からTaxonomyを推定するスクリプト")
    parser.add_argument('--place', type=str, default='wajima', help='地区名 (デフォルト: wajima)')
    args = parser.parse_args()

    input_buildings_csv = f"./data/{args.place}_buildings/gsi/noto_buildings_sampled.csv"
    input_site_csv = f"./data/{args.place}_buildings/j-shis/site_model.csv"

    output_xml = f"./data/openquake/{args.place}_scenario_risk/exposure_model.xml"             # 保存先：サンプリング建物XML
    output_site_csv = f"./data/openquake/{args.place}_scenario_risk/site_model.csv"   # 保存先：サンプリング地盤CSV

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

    # 3. 露出モデル (XML) の書き出し
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

    estimator = TaxonomyEstimator(config_path="./config/taxonomy_rules.yaml", region_key=args.place)
    for idx, item in enumerate(merged_dataset, start=1):
        taxonomy = estimator.estimate_taxonomy(item['type'])
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

    # 4. サンプリングされた地盤モデル (site_model_sampled.csv) の書き出し
    seen_coordinates = set()
    written_site_count = 0

    with open(output_site_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['lon', 'lat', 'vs30', 'z1pt0', 'z2pt5', 'vs30measured', 'xvf', 'backarc', 'z1pt4'])
        writer.writeheader()
        
        for item in merged_dataset:
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