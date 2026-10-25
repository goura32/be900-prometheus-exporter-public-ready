# TP-Link Archer BE900 Prometheus Exporter

A small **read-only, no-login** Prometheus exporter for TP-Link Archer BE900, implemented in Python without third-party dependencies. Japanese documentation is included below.

**Public-release note:** This repository describes protocols and anonymized observations. It does **not** publish private LAN addresses, device inventory, port-forwarding configurations, captured credentials or raw response payloads.

## 機能

- **UPnP IGD (SOAP over TCP 1900)**: WAN接続状態、物理リンク状態、WAN稼働時間、NATの状態、累積送受信バイト数・パケット数、UPnPポート転送件数
- **TP-Link TDP (UDP 20002)**: メーカー、機種名、機器種別、役割（MAC、個体識別子は除外）
- 認証不要。ルーターへの設定変更、ポート開放・削除、ログイン試行は行わない。
- CPU、メモリ、Wi-Fiクライアント数など、認証が必要な情報は対象外。

**互換性:** 特定のArcher BE900で動作を確認。ファームウェアによる動作差がありうるため、ほかの機器・版での互換性は未保証。

## ドキュメント

- [設計検討の日本語要約](docs/conversation-summary-ja.md): スマートホーム技術の比較、Home Assistantと監視システムの役割、Grafana/Prometheus採用理由、BE900の調査、決定事項。公開用に個人の環境を抽象化した要約。
- [匿名化したBE900調査記録](docs/be900-investigation-2026-10-25.md): UPnP/TDP/その他のプロトコルについて検証したことと未確認の点
- [運用手順](docs/operations.md): 実行、確認、Prometheus、セキュリティ上の注意

## 使い方

Python 3.10以降が必要。事前に `export BE900_ROUTER_IP=...` で自分のルーターのLAN IPv4を指定する。

```sh
python3 -m unittest discover -s tests -v
python3 be900_exporter.py --router "$BE900_ROUTER_IP" --listen 127.0.0.1 --port 9119
curl -fsS http://127.0.0.1:9119/metrics
```

環境変数は自分のLANに合わせて設定し、実値をコミットしない。

## Docker Compose

```sh
cp .env.example .env
# .env の BE900_ROUTER_IP を自分の環境に変更
docker compose up -d --build
curl -fsS http://127.0.0.1:9119/metrics
```

`compose.yaml` はホストの **127.0.0.1:9119** にのみバインドする。Prometheusを同じDockerネットワークに参加させると `be900-exporter:9119` にアクセスできる。別のホストから公開したい場合はLAN内だけに制限し、外部公開はしない。

Prometheusの設定例: [examples/prometheus-scrape.yml](examples/prometheus-scrape.yml)。初期の収集間隔は30秒、ポート転送件数の取得は15分間隔を想定。

## 注意点

- WAN送受信カウンターは機器のリセットや桁あふれの可能性があるため、Prometheus **Gauge（`*_raw`）** として公開する。単純に`rate()`を適用して帯域速度と見なすのは避ける。
- 申告されたリンク速度は実際の回線速度を表すとは限らない。
- ポート転送の各宛先・番号・説明は収集対象にしない。件数だけ取得する。
- `/metrics` 自体に認証はない。WANへ公開しない。
- `/healthz` はExporterのHTTPサーバーを確認するもので、ルーターの状態は `be900_upnp_up` / `be900_tdp_up` を見る。

## 開発状況

単体テストと限定した実機スモークテストを実施済み。NASにPrometheus/Grafanaを本番配備する工程は、このリポジトリには含まない。GitHub Actions等の自動実行ワークフローは使用しない。

## ライセンス

MIT。
