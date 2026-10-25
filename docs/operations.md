# 運用・セキュリティ

## 導入

Python 3.10以降が必要。ルーターのIPアドレスは**コード中に書き込まず**オプションか環境変数で指定する。下記のコマンドより前に `export BE900_ROUTER_IP=...` で設定する。

```sh
python3 -m unittest discover -s tests -v
python3 be900_exporter.py --router "$BE900_ROUTER_IP" --listen 127.0.0.1 --port 9119
curl -fsS http://127.0.0.1:9119/healthz
curl -fsS http://127.0.0.1:9119/metrics
```

Dockerの場合は `cp .env.example .env` として `BE900_ROUTER_IP` を設定してから `docker compose up -d --build`。

Docker Composeの公開先は既定で `127.0.0.1:9119`。Prometheusを同一Dockerネットワーク内に置くか、適切なアクセス制御を設けてLAN内だけに限定する。**WAN公開は禁止**。

Prometheusのscrape intervalの目安は30秒。Exporterは20秒キャッシュ、UPnPポート転送件数の再列挙は15分以上の間隔を空ける。

## 注意事項

- `be900_upnp_up`、`be900_tdp_up` がそれぞれの成功状態。`/healthz` はHTTPサーバーが動いていることだけを示す。
- ポート転送取得に失敗した場合、最後の成功値を保持することがある。 `be900_upnp_port_mappings_last_success_timestamp_seconds` の鮮度に注意。
- UPnPのカウンターはリセット・ラップがあり得るので `*_raw` Gauge。レートを計算するときは不連続点を適切に処理する。
- リンク速度申告値は契約速度や実効帯域ではない。
- `/metrics` は認証なし。LAN専用で運用し、MAC、WAN IP、ポート転送の詳細、認証情報を露出しない。
- 管理APIへの認証操作やルーターの設定変更はこのExporterのスコープ外。

## 実機スモークテスト（匿名化）

管理対象のBE900に接続した試験環境で、読み取り専用のUPnP/TDPからデータを取得し、`/metrics` の出力を確認。WAN接続状態、WANカウンター、TDP機種メタデータ、ポート転送件数を取得できた。具体的なネットワーク値やポート転送構成は記録しない。

単体テストを継続し、CIは使用しない。NASへの本番配備、実運用Prometheusによる定期収集・Grafanaダッシュボードの公開はこのコードの範囲外。

## 公開前チェック

1. `.env` や実機のログ、PCAP、資格情報をコミットしない。
2. 個人の内部IP、ホスト名、MAC、実際のポート転送設定、端末インベントリ、生のトラフィック値を公開ドキュメントに載せない。
3. **過去のGitコミットに機微情報が含まれている場合、新しい公開用リポジトリを初期コミットから作る。** ファイルを削除・修正しても古いコミットは残る。force-pushだけではGitHub側のキャッシュ等が消えるとは保証できない。
