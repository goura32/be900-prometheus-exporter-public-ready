# スマートホーム・自宅監視基盤の設計経緯とBE900 Exporter

> 2026年10月の技術検討の**公開用要約**。会話の逐語録ではなく、決定に至る判断と検証結果を記述したもの。LANアドレス、ネットワーク構成、個々のポート転送設定、実測の累積カウンター、所有機器一覧など、家庭環境を特定し得る情報は記載しない。具体的な運用値は各利用者の環境で設定する。

## 1. 目的

家庭内のスマートデバイス、Linuxマシン、NAS、ルーター、スイッチ等について、稼働状況とCPU/GPU/メモリ/ネットワークの時系列履歴を集約し、見やすいダッシュボードを作る。後から監視製品を移行する手間を避けるため、長期運用を想定した基盤を最初から選ぶ。

## 2. Matter・Thread・Zigbeeの整理

- Ethernet、Wi-Fi、Bluetooth LE、赤外線は通信手段として使われる。
- ThreadはIPv6ベースのメッシュで、Thread Border Routerを使って通常のIPネットワークと接続する。Zigbeeと共通のIEEE 802.15.4を用いることがあっても両者は同一プロトコルではない。
- MatterはWi-Fi、Ethernet、Thread等の上で機器相互運用を図るアプリケーション規格。Controller、対象デバイス、Device Type、Cluster、Attribute/Command/Event、Read/Write/Invoke/Subscribeを検討した。
- Apple Home、Alexa、Google Home、Home Assistant、国内のECHONET Liteや各社のブリッジ/ハブなどの役割を比較した。
- Matterは汎用PCの任意のCPU/GPU指標を標準で公開する仕組みではない。スマートホーム連携とPC監視を分ける方がよい。

## 3. Home Assistantと監視基盤の役割

- Home Assistantは家庭機器を統合する中核としてNAS等に1インスタンス配置。必要に応じてHomeKit BridgeやAlexa連携を行う。
- PCの高頻度時系列データはHome Assistantだけに抱え込まない。
- Glances、Zabbix、Netdata、BeszelとGrafana+Prometheusを比較。導入の容易さより可視化の柔軟性と拡張性を重視して **Grafana + Prometheusを採用**。
- LinuxホストにはNode Exporter、NVIDIA GPUがあるホストには対応GPU Exporterを配置する構成を選んだ。
- Prometheusが時系列を収集・保存、Grafanaが表示・アラートを担当。スクレイプ間隔や保存期間はハードウェアの負荷・容量を測って決める。
- Home Assistant連携は後工程。PrometheusのHTTP Query APIをRESTセンサー等から参照する案、逆方向にHAがPrometheus形式でセンサーデータを公開する案を検討した。

## 4. ネットワーク機器監視

- SNMP対応機器にはPrometheus SNMP Exporter（可能ならSNMPv3の読み取り専用）。
- 非対応機器の死活・遅延監視にはBlackbox Exporter。
- 非標準インターフェースを持つ機器には機種専用の小規模Exporterを使い、共通のPrometheusフォーマットに統一する。

## 5. TP-Link Archer BE900を調査した流れ

1. 設置LAN内のルーターへの到達性と公開ポートを安全な範囲で調べた。機器のSNMP対応は確認できなかったため、別方式を調査した。
2. 既存の非公式TP-Link管理ライブラリやTetherアプリの発見プロトコルを調べた。別機種の対応をBE900でも動くと推定せず、実機応答で検証した。
3. BE900のUPnP IGD機器説明から3サービスと18操作を確認し、読み取り操作を実験した。設定を変える操作は実行していない。
4. UPnPでWAN接続・物理リンク・NAT・稼働時間・累積バイト・累積パケット等を取得できた。ポート転送の一覧も読み取り可能だったが、公開するExporterでは各設定の詳細を収集しない方針にした。
5. TP-Link独自のTDP DiscoveryへBE900が応答することを確認。メーカー・モデル・機器種別等が取得できた。MACや個体識別値は使用しない。
6. NAT-PMPは有効な管理情報の取得につながらず、未認証Web管理APIも実用的な情報を返さなかった。CPU、メモリ、Wi-Fiクライアント一覧などは未取得。類似Archerモデルの非公式コードをそのままBE900対応済みとは扱わない。
7. Tetherアプリの認証後の通信方式は特定できなかった。iPhoneの通信キャプチャ等は必須ではなく、今回の目的（認証不要で取得可能なデータの監視）には進めないと判断した。

## 6. 収集・表示に関する技術的注意

- UPnPの受信・送信バイトカウンターは、時間差で増加することを検証した。ただしラップや再起動を考慮し、ExporterではCounterと偽らず生値Gaugeとして扱う。
- UPnPが申告する物理リンク速度を契約回線速度や実効帯域と同一視しない。
- ポート転送の全件列挙は負荷と機密性を考慮し**低頻度で件数のみ**を公開する。
- ルーターを識別するMACアドレス、WAN IP、家庭内LANアドレス、個別転送設定、認証情報をログやメトリクスに含めない。
- Prometheus用ExporterをWANに公開しない。ルーターは認証不要の読み取り専用操作だけを使う。

## 7. 最終決定

- **認証を要する管理APIの調査はいったん終了。**
- BE900から認証不要で取れる範囲を専用ExporterでPrometheusに集約する。
- 調査コードを再利用してPythonの小さなExporterを実装し、Dockerでも動かせるようにする。
- テストと実機動作を確認した後、NAS等のPrometheus+Grafana環境へ導入する。スマートホーム画面との統合は後回し。
- ソースと設計経緯をGitHubで参照できるようにする。**公開版は個人環境の実測値を含めない。**

## 8. 未完了・将来の課題

NASでの本番配備、Prometheus保存期間設計、Grafanaダッシュボードとアラート、複数の機器の横断監視は別工程。BE900における認証済みWeb API、CPU・メモリ・Wi-Fiの詳細取得は対象外。

## 参考資料

- [Prometheus](https://prometheus.io/docs/introduction/overview/)
- [Prometheus Exporters](https://prometheus.io/docs/instrumenting/exporters/)
- [Prometheus SNMP Exporter](https://github.com/prometheus/snmp_exporter)
- [Prometheus Blackbox Exporter](https://github.com/prometheus/blackbox_exporter)
- [TP-Link 非公式Home Assistant連携](https://github.com/AlexandrErohin/home-assistant-tplink-router)
