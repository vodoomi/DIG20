window.DEMO_DATA = {
  "collected_at": "2026-08-29T08:29:38.788661+00:00",
  "progress_delay_ms": 600,
  "unsupported_message": "このサイトは発表用デモのため、回答できる住所と質問を限定しています。画面に表示された選択肢から選んでください。",
  "scenarios": [
    {
      "key": "wajima",
      "label": "輪島市 河井町1部115番地",
      "address": "石川県輪島市河井町1部115番地",
      "turns": {
        "payout": {
          "label": "補償額",
          "prompt": "能登半島地震における石川県輪島市河井町1部115番地の補償額を教えてください",
          "answer_html": "<p>補償額は<strong>3,091,005円</strong>です。</p>"
        },
        "reason": {
          "label": "平易な根拠",
          "prompt": "この補償額になった根拠を教えてください",
          "answer_html": "<p>この地域は<strong>震度7相当</strong>の極めて激しい揺れに見舞われました。\nFASTALERTで収集した被害投稿の情報を見ると、<strong>倒壊</strong>や<strong>道路被害</strong>、<strong>救助要請</strong>に関する情報が目立ちました。\n補償額の算定では、揺れの強さだけでなく、<strong>地盤変状</strong>といった被害の状況も反映しています。\nこれらの情報を総合的に評価した結果、法人契約の保険金額(1,000万円)に対して約31%を支払う水準と判断し、<strong>約309万円</strong>という補償額を算出しました。</p>"
        },
        "math": {
          "label": "数式による根拠",
          "prompt": "数式を使って理由を説明してください",
          "answer_html": "<p><strong>計算の内訳</strong></p>\n<p>支払率を求める基本式です。</p>\n<p>$$p = \\frac{1}{1 + \\exp(-z)}$$</p>\n<p>$$z = w_0 + w_1 S_i + \\sum_k w_k x_k$$</p>\n<ul>\n<li>震度スコア: $S_i=6.75$</li>\n<li>切片: $w_0=-14.85$</li>\n<li>震度の重み: $w_1=2.00$</li>\n<li>被害特徴量の重み: 液状化 0.24、地盤変状 0.72</li>\n<li>被害特徴量の寄与: 液状化 0.00、地盤変状 0.52</li>\n</ul>\n<p>震度と被害特徴量の寄与を合計します。</p>\n<p>$$w_1 S_i \\approx 13.53$$</p>\n<p>$$\\sum_k w_k x_k \\approx 0.52$$</p>\n<p>$$z \\approx -14.85 + 13.53 + 0.52$$</p>\n<p>$$z \\approx -0.80$$</p>\n<p>丸め前の値で算出した支払率です。</p>\n<p>$$p \\approx 30.91\\%$$</p>\n<p>法人契約の保険金額に支払率を掛けます。</p>\n<p>$$P \\approx 10,000,000 \\times 30.91\\%$$</p>\n<p>$$P = 3,091,005\\text{円}$$</p>\n<p>したがって、補償額は<strong>約309万円</strong>です。表示値は小数第3位で四捨五入していますが、補償額は丸め前の値で計算しています。</p>"
        },
        "photo": {
          "label": "被害写真",
          "prompt": "写真で被害の状況を教えてください",
          "answer_html": "<p><img alt=\"輪島市の道路損壊の被害画像\" src=\"images/wajima.jpg\" /></p>\n<p><em>輪島市・カテゴリ「道路損壊」の被害投稿画像(<a href=\"https://twitter.com/misakura_rin/status/1742111283472973918\">出典</a>)</em></p>\n<p>これが補償額算定で影響が大きかった地盤変状に対応する実際の投稿画像です。</p>"
        }
      },
      "query": {
        "address": "石川県輪島市河井町1部115番地",
        "lat": 37.396023,
        "lon": 136.899872,
        "matched_address": "石川県輪島市河井町１番",
        "muni_name": "輪島市"
      },
      "intensity": {
        "shindo_class": "7",
        "s_i": 6.75
      },
      "payout": {
        "payout_ratio": 0.30910046056781604,
        "payout_yen": 3091005,
        "payout_yen_formatted": "約309万円"
      },
      "damage_summary": "倒壊、道路被害、救助要請",
      "image": {
        "category": "道路損壊",
        "damage_type": "地盤変状",
        "local_path": "images/wajima.jpg",
        "source_url": "https://twitter.com/misakura_rin/status/1742111283472973918"
      }
    },
    {
      "key": "uchinada",
      "label": "内灘町 大学1丁目2番地1",
      "address": "石川県河北郡内灘町字大学1丁目2番地1",
      "turns": {
        "payout": {
          "label": "補償額",
          "prompt": "能登半島地震における石川県河北郡内灘町字大学1丁目2番地1の補償額を教えてください",
          "answer_html": "<p>補償額は<strong>597,363円</strong>です。</p>"
        },
        "reason": {
          "label": "平易な根拠",
          "prompt": "この補償額になった根拠を教えてください",
          "answer_html": "<p>この地域は<strong>震度5弱相当</strong>の揺れに見舞われました。</p>\n<p>SNS等から集めた被害投稿を見ると、<strong>液状化</strong>や<strong>倒壊</strong>に関する被害情報が目立ちました。</p>\n<p>補償額の算定では、揺れの強さとこうした被害状況を総合的に評価しました。その結果、法人契約の保険金額（1,000万円）に対して約6%を支払う水準と判断し、<strong>約60万円</strong>という補償額を算出しました。</p>"
        },
        "math": {
          "label": "数式による根拠",
          "prompt": "数式を使って理由を説明してください",
          "answer_html": "<p><strong>計算の内訳</strong></p>\n<p>支払率を求める基本式です。</p>\n<p>$$p = \\frac{1}{1 + \\exp(-z)}$$</p>\n<p>$$z = w_0 + w_1 S_i + \\sum_k w_k x_k$$</p>\n<ul>\n<li>震度スコア: $S_i=4.75$</li>\n<li>切片: $w_0=-14.85$</li>\n<li>震度の重み: $w_1=2.00$</li>\n<li>被害特徴量の重み: 液状化 0.24、地盤変状 0.72</li>\n<li>被害特徴量の寄与: 液状化 2.57、地盤変状 0.00</li>\n</ul>\n<p>震度と被害特徴量の寄与を合計します。</p>\n<p>$$w_1 S_i \\approx 9.52$$</p>\n<p>$$\\sum_k w_k x_k \\approx 2.57$$</p>\n<p>$$z \\approx -14.85 + 9.52 + 2.57$$</p>\n<p>$$z \\approx -2.76$$</p>\n<p>丸め前の値で算出した支払率です。</p>\n<p>$$p \\approx 5.97\\%$$</p>\n<p>法人契約の保険金額に支払率を掛けます。</p>\n<p>$$P \\approx 10,000,000 \\times 5.97\\%$$</p>\n<p>$$P = 597,363\\text{円}$$</p>\n<p>したがって、補償額は<strong>約60万円</strong>です。表示値は小数第3位で四捨五入していますが、補償額は丸め前の値で計算しています。</p>"
        },
        "photo": {
          "label": "被害写真",
          "prompt": "写真で被害の状況を教えてください",
          "answer_html": "<p><img alt=\"内灘町の液状化の被害画像\" src=\"images/uchinada.jpg\" /></p>\n<p><em>内灘町・カテゴリ「液状化」の被害投稿画像(<a href=\"https://twitter.com/Wizard_of_Oz__/status/1742088391234408549\">出典</a>)</em></p>\n<p>これが補償額算定で影響が大きかった被害カテゴリの実際の投稿画像です。</p>"
        }
      },
      "query": {
        "address": "石川県河北郡内灘町字大学1丁目2番地1",
        "lat": 36.653542,
        "lon": 136.644989,
        "matched_address": "石川県内灘町大学一丁目２番地",
        "muni_name": "内灘町"
      },
      "intensity": {
        "shindo_class": "5弱",
        "s_i": 4.75
      },
      "payout": {
        "payout_ratio": 0.05973627907368244,
        "payout_yen": 597363,
        "payout_yen_formatted": "約60万円"
      },
      "damage_summary": "液状化、倒壊、道路被害",
      "image": {
        "category": "液状化",
        "damage_type": "液状化",
        "local_path": "images/uchinada.jpg",
        "source_url": "https://twitter.com/Wizard_of_Oz__/status/1742088391234408549"
      }
    },
    {
      "key": "nagaoka",
      "label": "長岡市 中之島1993番地17",
      "address": "新潟県長岡市中之島1993番地17",
      "turns": {
        "payout": {
          "label": "補償額",
          "prompt": "能登半島地震における新潟県長岡市中之島1993番地17の補償額を教えてください",
          "answer_html": "<p>補償額は<strong>364,946円</strong>です。</p>"
        },
        "reason": {
          "label": "平易な根拠",
          "prompt": "この補償額になった根拠を教えてください",
          "answer_html": "<p>この地域は<strong>震度6弱相当</strong>の激しい揺れに見舞われました。</p>\n<p>補償額を算出する際は、揺れの強さに加えてFASTALERTで収集されたSNS投稿等の被害状況が反映されます。FASTALERTでは、<strong>倒壊</strong>や<strong>断水</strong>、特に<strong>液状化</strong>に関する被害情報が目立ちました。</p>\n<p>揺れの強さとこうした被害状況を総合的に評価した結果、法人契約の保険金額（1,000万円）に対して約4%の割合で計算され、<strong>約36万円</strong>という補償額となりました。</p>"
        },
        "math": {
          "label": "数式による根拠",
          "prompt": "数式を使って理由を説明してください",
          "answer_html": "<p><strong>計算の内訳</strong></p>\n<p>支払率を求める基本式です。</p>\n<p>$$p = \\frac{1}{1 + \\exp(-z)}$$</p>\n<p>$$z = w_0 + w_1 S_i + \\sum_k w_k x_k$$</p>\n<ul>\n<li>震度スコア: $S_i=5.75$</li>\n<li>切片: $w_0=-14.85$</li>\n<li>震度の重み: $w_1=2.00$</li>\n<li>被害特徴量の重み: 液状化 0.24、地盤変状 0.72</li>\n<li>被害特徴量の寄与: 液状化 0.05、地盤変状 0.00</li>\n</ul>\n<p>震度と被害特徴量の寄与を合計します。</p>\n<p>$$w_1 S_i \\approx 11.52$$</p>\n<p>$$\\sum_k w_k x_k \\approx 0.05$$</p>\n<p>$$z \\approx -14.85 + 11.52 + 0.05$$</p>\n<p>$$z \\approx -3.27$$</p>\n<p>丸め前の値で算出した支払率です。</p>\n<p>$$p \\approx 3.65\\%$$</p>\n<p>法人契約の保険金額に支払率を掛けます。</p>\n<p>$$P \\approx 10,000,000 \\times 3.65\\%$$</p>\n<p>$$P = 364,946\\text{円}$$</p>\n<p>したがって、補償額は<strong>約36万円</strong>です。表示値は小数第3位で四捨五入していますが、補償額は丸め前の値で計算しています。</p>"
        },
        "photo": {
          "label": "被害写真",
          "prompt": "写真で被害の状況を教えてください",
          "answer_html": "<p><img alt=\"長岡市の液状化の被害画像\" src=\"images/nagaoka.jpg\" /></p>\n<p><em>長岡市・カテゴリ「液状化」の被害投稿画像(<a href=\"https://twitter.com/Arianrod_kazuki/status/1741724102434730447\">出典</a>)</em></p>\n<p>これが補償額算定で影響が大きかった「液状化」被害カテゴリの実際の投稿画像です。</p>"
        }
      },
      "query": {
        "address": "新潟県長岡市中之島1993番地17",
        "lat": 37.532978,
        "lon": 138.875381,
        "matched_address": "新潟県長岡市中之島１９９３番地",
        "muni_name": "長岡市"
      },
      "intensity": {
        "shindo_class": "6弱",
        "s_i": 5.75
      },
      "payout": {
        "payout_ratio": 0.036494588710920615,
        "payout_yen": 364946,
        "payout_yen_formatted": "約36万円"
      },
      "damage_summary": "倒壊、断水、液状化",
      "image": {
        "category": "液状化",
        "damage_type": "液状化",
        "local_path": "images/nagaoka.jpg",
        "source_url": "https://twitter.com/Arianrod_kazuki/status/1741724102434730447"
      }
    }
  ]
};
