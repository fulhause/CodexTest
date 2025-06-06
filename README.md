# コンベアエミュレータ

このプロジェクトは三菱製PLCとSLMP(MCプロトコル)で通信するコンベアの簡易エミュレータです。
`pymcprotocol` を利用してPLCとI/O情報をやり取りし、Tkinter製のGUIでセンサ状態の表示や
ワーク投入が行えます。

## 使い方

1. 依存パッケージのインストール

```bash
pip install pymcprotocol
```

2. エミュレータの起動

```bash
python conveyor_emulator.py <PLCのIPアドレス>
```

`--port` オプションでポート番号を指定できます。

GUIからワークの追加やセンサ状態の確認が可能です。PLCからの指令によりコンベアの
開始・停止を行います。
