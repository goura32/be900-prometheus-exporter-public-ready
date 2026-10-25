# Archer BE900 公開インターフェース調査（匿名化版）

> 個人宅のLAN構成・端末情報・ポート転送番号や件数・生のWANカウンター値・MACアドレスは公開しない。以下は技術的な**取得可能性**と**制限**の記録。

## 調査原則

実機に対して、認証が不要で状態を変更しない問い合わせだけを送る。対象は本人管理下のルーターのみ。管理者ログイン、設定変更、脆弱性の利用、WAN側からの侵入テストは実施していない。

## 探索・ポート確認

- DNS (53/TCP, UDP)、HTTP/HTTPS (80, 443/TCP)、UPnP (1900/TCP, UDP) の応答を確認。
- TDP Discovery（20002/UDP）が実際に応答。ポートスキャンの `open|filtered` 表示だけを根拠にしていない。
- SSH/Telnet、SNMPの一般的なポートでは実用的な接続を確認できなかった。SNMP非対応を厳密に証明したわけではない。
- ファームウェアや設定が違えば結果も変わる。限定した範囲の調査で、全ポートの網羅的な検証ではない。

## UPnP IGD

機器が広告する `InternetGatewayDevice:1` のUPnP説明を取得した。Layer3Forwarding、WANCommonInterfaceConfig、WANIPConnectionの3サービスがあり、計18操作のうち**読み取り操作のみ**を検証した。

| 読み取り操作 | 動作と意味 |
|---|---|
| GetDefaultConnectionService | WAN接続サービス識別子を返す |
| GetCommonLinkProperties | WANアクセス種別・物理接続状態・リンク速度の申告値 |
| GetTotalBytesSent / GetTotalBytesReceived | 累積送受信バイト数 |
| GetTotalPacketsSent / GetTotalPacketsReceived | 累積送受信パケット数 |
| GetConnectionTypeInfo | IP接続方式 |
| GetStatusInfo | 接続状態・稼働時間・エラー |
| GetNATRSIPStatus | NAT・RSIP状態 |
| GetGenericPortMappingEntry | 設定済みポート転送を列挙可能（詳細非公開） |
| GetSpecificPortMappingEntry | 指定条件に一致する転送の取得が可能 |
| GetExternalIPAddress | SOAP応答はあったが、利用可能なIP文字列は返らなかった |

ポート転送の番号、宛先、件数、説明文字列は個人環境固有なのでこの公開版には記載しない。実測ではUPnPのリンク速度申告値と回線実速度の整合性が保証できず、監視用途では参考値として扱う。カウンターは短時間で増加することを確認したが、ラップやリセットの挙動は未検証。

## TP-Link TDP Discovery

UDP 20002に公開プロトコルで知られる機器発見要求を送信したところ、Archer BE900が応答。応答には `TP-Link`、`Archer BE900`、`WirelessRouter` などの機器カテゴリ情報が含まれた。個体識別子・MACアドレス・生パケットは公開しない。

この結果はDiscoveryへの応答であって、Tetherアプリの認証済み管理APIの互換性まで証明するものではない。

## その他の方式

- **NAT-PMP**: 探索要求にエラー応答。実用的な外部アドレス取得には至らず。
- **NTP**: 試験条件では応答を確認できず。
- **Web管理画面**: 静的アセットを閲覧できたが、類似機種のLuCI系パスに未認証でアクセスしても管理用データは取得できなかった。認証突破の試行はなし。
- **類似機種の非公式API**: CPU、メモリ、Wi-Fi情報などを取得する実装例があるが、BE900での稼働実績は確認していない。

## 実装の対象

UPnPによる状態・カウンターと、TDPによる個体情報を除いた機種メタデータをPrometheus形式に変換する。個別のポート転送設定はExportせず件数のみ。ユーザー管理下のネットワークでのみ運用すること。
