# DIG20（Digital Innovators Grand Prix 20）

[第20回データビジネス創造コンテスト](https://dmc-lab.sfc.keio.ac.jp/dig20/)のためのリポジトリ

## 動作確認

### 1. OpenQuakeによるデータセット作成

#### 1.1 依存関係のインストール

```bash
uv sync
```

#### 1.2 建物データの取得

[国土地理院の基盤地図情報ダウンロードサービス](https://service.gsi.go.jp/kiban/)から`基本項目`を選択し、左のサイドバーから以下の条件で検索（例えば、輪島市の場合）

- 作成年月：過去データを含む（2023年10月から2023年12月までを指定）
- 地物等：全項目
- ダウンロードするファイルの単位：メッシュ単位->都道府県・市区町村上でメッシュ->石川県輪島市

`FG-GML-553677-ALL-20231001.zip`と`FG-GML-563710-ALL-20231001.zip`が得られるので、`FG-GML-553677-BldA-20231001-0001.xml`と`FG-GML-563710-BldA-20231001-0001.xml`を`data/wajima_buildings/gsi/`に配置する。

> ⚠️ この先の分析では、新潟県長岡市と石川県内灘町のデータも使用するが、輪島市だけでも動作確認は可能

#### 1.3 建物データの前処理

[QGIS](https://qgis.org/ja/)を使って、1.2で取得したXMLファイルから緯度経度と面積をGUIで抽出する

1. QGISにドラッグ＆ドロップする

- BldA のXMLファイル群をすべてQGISの「レイヤ」パネルにドラッグ＆ドロップ
- 座標参照系（CRS）の選択画面が出た場合は、JGD2011（EPSG:6668 または EPSG:4612）を選択

2. レイヤを1つに結合する

- 上部メニューから ベクタ ＞ データ管理ツール ＞ ベクタレイヤのマージ を選択
- 入力レイヤに読み込んだすべての BldA レイヤを指定し、実行します。これで複数のXMLが1つの統合レイヤになる

3. 属性テーブルに経緯度（代表点）と面積を追加する

- 結合したレイヤを選択し、属性テーブル（フィールド計算機）を開く
- 以下の設定で新規フィールドを3つ作成：
    - 経度（lon）: 小数点付き数値（リアル型）を選択し、式に x(centroid($geometry)) と入力
    - 緯度（lat）: 小数点付き数値（リアル型）を選択し、式に y(centroid($geometry)) と入力
    - 面積（area）（今後の分類に便利です）: 小数点付き数値を選択し、式に $area と入力

4. CSVとしてエクスポートする

- 結合レイヤを右クリックし、エクスポート ＞ 新規ファイルに地物を保存 を選択
- 形式：CSV (Comma Separated Values) を選択
    - 保存先は`data/wajima_buildings/gsi/noto_buildings.csv`とする
    - 出力する属性（カラム）として、fid（地理院ID）、type（建物種別：普通建物や堅ろう建物）、先ほど計算した lon、lat、area のみにチェックを入れて保存

#### 1.4 建物のサンプリング

計算の都合上、建物は100件にサンプリングしている

```bash
uv run scripts/sampling.py \
    --input-csv ./data/wajima_buildings/gsi/noto_buildings.csv \
    --output-csv ./data/wajima_buildings/gsi/noto_buildings_sampled.csv \
    --sample-size 100
```

> ⚠️ 長岡市や内灘町の建物データも同様にサンプリングする場合は、`--input-csv`と`--output-csv`のパスを変更して実行する

#### 1.5 建物の場所ごとのサイト特性・地盤の取得

```bash
uv run scripts/fetch_jshis_site_model.py \
    --input-csv ./data/wajima_buildings/gsi/noto_buildings_sampled.csv \
    --output-csv ./data/wajima_buildings/j-shis/site_model.csv
```

#### 1.6 曝露モデルの作成

> ⚠️ 長岡市や内灘町の曝露モデルを作成する場合は、以下を実行してからスクリプトを回す

```bash
cp -r data/openquake/wajima_scenario_risk/ data/openquake/nagaoka_scenario_risk/
cp -r data/openquake/wajima_scenario_risk/ data/openquake/uchinada_scenario_risk/
```

曝露モデルを作成するスクリプトを実行するコマンド

```bash
uv run scripts/generate_exposure.py --place wajima
```

#### 1.7 OpenQuakeによる地震動解析

```bash
uv run oq engine --run ./data/openquake/wajima_scenario_risk/job.ini
```

#### 1.8 結果の保存

job_idは、`uv run oq engine --lrc`で確認できる

```bash
uv run oq export avg_losses-rlzs <job_id> --export-dir ./data/openquake/wajima_scenario_risk/
```

## 参考資料

- 震源断層
    - 国土地理院 [令和6年能登半島地震の震源断層モデル](https://www.gsi.go.jp/common/000255958.pdf)
- 脆弱性関数
    - GEM(Global Earthquake Model) [Global Vulnerability Model](https://github.com/gem/global_vulnerability_model/blob/main/East_Asia/Japan/vulnerability_structural.xml)
- 建物データ
    - 国土地理院 [基盤地図情報ダウンロードサービス](https://service.gsi.go.jp/kiban/)
    - 国土交通省 [R6能登半島地震の被災市町村における住宅関連データ
](https://www.nilim.go.jp/lab/ibg/contents/SAIGAI/saigai.html)
    - Built Environment Data Experiments [Taxonomy](https://experiments.builtenvdata.eu/taxonomy)
    - 国土地理院 [公共測量標準図式](https://www.gsi.go.jp/common/000258741.pdf)
    - J-SHIS [地震ハザードステーション](https://www.j-shis.bosai.go.jp/)
