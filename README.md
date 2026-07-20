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

### 2. 最適化

Coming soon

### 3. LM Studioの設定

[Setup FastAlert MCP](./docs/setup_fastalert_mcp.md)の`Setup`を参照してください

### 4. 地震保険 補償額査定アプリの起動

事前に「3. LM Studioの設定」([Setup FastAlert MCP](./docs/setup_fastalert_mcp.md)の`Setup`)を完了させ、
LM Studio APIキー(`LM_STUDIO_API_KEY`)の取得とFASTALERT MCPの認証まで済ませておいてください。

#### 4.1 環境変数の設定

リポジトリのルートに`.env`を作成し、取得済みのLM Studio APIキーを設定する

```bash
echo "LM_STUDIO_API_KEY=<取得したトークン>" > .env
```

#### 4.2 FASTALERT特徴量CSVの作成(初回のみ)

FASTALERT MCPを実際に呼び出して、輪島市・長岡市・内灘町の被害特徴量CSVを作成する
(すでに`data/features/raw_topics_*.json`が生成済みならMCPは再呼び出しされず、それを再利用する)

```bash
uv run scripts/build_fastalert_features.py
```

#### 4.3 LM Studioサーバーの起動

ssh接続したRTX 5090上で実行する([Setup FastAlert MCP](./docs/setup_fastalert_mcp.md)の`Inference`と同じ)

```bash
lms load qwen3.6-35b-a3b --gpu max -c 32768
lms server start
```

#### 4.4 Webアプリの起動

```bash
uv run uvicorn webapp.main:app --app-dir src --host 127.0.0.1 --port 8000
```

#### 4.5 ブラウザで開く

- VS Codeでssh接続している場合は8000番ポートが自動フォワードされるので、ターミナルに表示される
  リンクをクリックすると手元PCのブラウザで開く
- それ以外の場合は、手元PCから以下のようにポートフォワードしてから`http://localhost:8000`を開く

    ```bash
    ssh -L 8000:127.0.0.1:8000 <ユーザー名>@<GPUサーバーのIPアドレス>
    ```

#### 4.6 使い方

- 画面上部で震度・特徴量それぞれの取得モード(CSVモック / ライブ(FASTALERT))を切り替えられる
  (既定はどちらもモック)
- チャット欄のボタンから「能登半島地震における住所の補償額を教えてください」の例文を入力するか、
  自分で住所を入力して送信する(対象自治体は輪島市・長岡市・内灘町)
- 補償額が回答されると「この補償額になった根拠を教えてください」ボタンが表示され、押すと数式を
  使わない平易な言葉で根拠が説明される
- 根拠の説明後は「数式を使って理由を説明してください」ボタンが表示され、押すと震度・特徴量・
  重み・計算式を含めた詳細な根拠が返る
- 地図には問い合わせた建物の位置に補償額の大きさ(円の大きさ)と震度(円の色)を示す円が表示され、
  別の住所を問い合わせても過去の円は残る

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
